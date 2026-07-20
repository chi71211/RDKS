import sys
import os

# ==========================================
# 解決 Windows 終端機中文亂碼問題
# ==========================================
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())
else:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import requests
import pandas as pd
import re
import json
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# ==========================================
# 全域設定
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測優化.db')
SQL_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測優化.sql')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'scrape_progress優化.json')

MAX_RUNTIME_SECONDS = 5.8 * 3600 
PROGRAM_START_TIME = time.time()

session = requests.Session()
retry_strategy = Retry(total=5, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.mount("http://", adapter)
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Connection": "keep-alive"
})

# ==========================================
# 1. 進度與週期管理
# ==========================================
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {"cycle_start": time.time(), "last_brand": "", "last_class": "", "last_tg": ""}

def save_progress(brand="", car_class="", tg_id="", completed=False):
    prog = load_progress()
    if completed:
        prog["cycle_start"] = time.time()
        prog.update({"last_brand": "", "last_class": "", "last_tg": ""})
    else:
        prog["last_brand"] = brand
        prog["last_class"] = car_class
        prog["last_tg"] = tg_id
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f)

def check_7_day_cycle():
    prog = load_progress()
    if time.time() - prog.get("cycle_start", 0) > 604800:
        print("\n⏳ [週期檢查] 超過 7 天，啟動全面掃描（保留歷史資料）...")
        fresh = {"cycle_start": time.time(), "last_brand": "", "last_class": "", "last_tg": ""}
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(fresh, f)
        return fresh, True
    return prog, False

# ==========================================
# 2. 安全請求 & 輔助函式
# ==========================================
def safe_json_get(url, params=None, timeout=15):
    try:
        r = session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json() if r.text and r.text.strip() else []
    except Exception as e:
        if "429" in str(e):
            print("⚠️ Rate Limit，等待 10 秒...")
            time.sleep(10)
        else:
            print(f"請求失敗 {url}: {e}")
        time.sleep(1.5)
        return []

def get_manufacturers(): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/manufacturers")
def get_classes(brand): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/classes", {"manufacturer": brand})
def get_type_groups(brand, car_class): 
    return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/type-groups", {"manufacturer": brand, "class": car_class})
def get_versions(tg): 
    return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/version-groups", {"group": tg})
def get_car_hsn_tsn(tag): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/car", {"carTag": tag})
def get_tpms(tag): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/tpms/carTpms", {"carTag": tag})

def get_sensor_details(manufacturer_ids):
    if not manufacturer_ids: return {}
    ids_str = ",".join(map(str, manufacturer_ids)) if isinstance(manufacturer_ids, list) else str(manufacturer_ids)
    return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/gpsr/data", {"manufacturerIds": ids_str})

def format_year(d): 
    return "至今" if not d or d == "0000-00-00" else d[:7]

def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    return name.replace('ü','ue').replace('ä','ae').replace('ö','oe').replace('ß','ss')

def find_key_value(d, keywords):
    if isinstance(d, dict):
        for k, v in d.items():
            if any(kw in str(k).lower() for kw in keywords) and not isinstance(v, (dict, list)):
                if v and str(v).strip(): return str(v).strip()
            res = find_key_value(v, keywords)
            if res: return res
    elif isinstance(d, list):
        for item in d:
            res = find_key_value(item, keywords)
            if res: return res
    return ""

# ==========================================
# 資料庫
# ==========================================
def save_batch_to_sql(batch_data):
    if not batch_data: return
    df = pd.DataFrame(batch_data).fillna("")

    # 使用無引號的欄位名作為群組依據
    group_cols = ['Brand', 'Model', 'Typ', 'Start Year', 'End Year', 'HSN', 'TSN']
    agg_dict = {
        'OE sensor': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        'Manufacturer': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        'Frequency': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        'created date': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
    }
    for col in group_cols:
        agg_dict[col] = 'first'

    df_merged = df.groupby(group_cols, as_index=False).agg(agg_dict)
    
    cols = ['Brand', 'Model', 'Typ', 'Start Year', 'End Year', 'HSN', 'TSN',
            'created date', 'OE sensor', 'Manufacturer', 'Frequency']
    df_merged = df_merged.reindex(columns=cols)

    conn = sqlite3.connect(DB_PATH)
    # 使用引號包裹所有欄位名稱，確保 SQLite 能接受帶有空格的欄位
    conn.executemany('''
        REPLACE INTO tpms_sensors 
        ("Brand", "Model", "Typ", "Start Year", "End Year", "HSN", "TSN", "created date", 
         "OE sensor", "Manufacturer", "Frequency")
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', df_merged.values.tolist())
    conn.commit()
    conn.close()

def auto_export_sql():
    if not os.path.exists(DB_PATH): return
    conn = sqlite3.connect(DB_PATH)
    with open(SQL_PATH, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write(f'{line}\n')
    conn.close()
    print(f"🎉 SQL 備份完成: {os.path.basename(SQL_PATH)}")

# ==========================================
# 主程式
# ==========================================
def main_scraper_all():
    folder_path = os.path.join(SCRIPT_DIR, sanitize_filename("胎壓偵測優化"))
    os.makedirs(folder_path, exist_ok=True)

    brands = get_manufacturers()
    if not isinstance(brands, list) or not brands:
        print("❌ 無法取得Brand清單")
        return

    prog, _ = check_7_day_cycle()
    skip_mode = bool(prog.get("last_brand"))

    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS tpms_sensors (
        "Brand" TEXT, "Model" TEXT, "Typ" TEXT, "Start Year" TEXT, "End Year" TEXT,
        "HSN" TEXT, "TSN" TEXT, "created date" TEXT, 
        "OE sensor" TEXT, "Manufacturer" TEXT, "Frequency" TEXT,
        UNIQUE("Brand", "Model", "Typ", "Start Year", "HSN", "TSN")
    )''')
    conn.commit()
    conn.close()

    batch_data = []
    completed_brands = []
    time_limit_reached = False

    print(f"🔍 共 {len(brands)} 個Brand\n")

    for brand in tqdm(brands, desc="總進度", ncols=100):
        if time_limit_reached:
            break

        if skip_mode and brand != prog.get("last_brand"):
            tqdm.write(f"⏭️ 已完成: {brand} ✅")
            completed_brands.append(brand)
            continue

        if skip_mode and brand == prog.get("last_brand"):
            skip_mode = False
            tqdm.write(f"▶️ 從 {brand} 繼續...")

        tqdm.write(f"\n🚗 正在處理: 【{brand}】")
        save_progress(brand=brand)

        classes = get_classes(brand)
        if not isinstance(classes, list): classes = []

        for car_class in tqdm(classes, desc=f"{brand} Model", leave=False, ncols=80):
            if time_limit_reached:
                break

            type_groups = get_type_groups(brand, car_class)
            if not isinstance(type_groups, list): type_groups = []

            for tg_data in type_groups:
                if time_limit_reached:
                    break

                tg_id = tg_data.get("group") if isinstance(tg_data, dict) else None
                if not tg_id: continue

                if skip_mode and tg_id != prog.get("last_tg"): continue
                if skip_mode:
                    skip_mode = False

                save_progress(brand, car_class, tg_id)

                versions = get_versions(tg_id)
                if not isinstance(versions, list): continue
                versions.sort(key=lambda x: x.get('productionFrom', ''), reverse=True)

                for version in versions:
                    if time.time() - PROGRAM_START_TIME > MAX_RUNTIME_SECONDS:
                        tqdm.write(f"\n⏱️ 警告：執行時間即將超過 6 小時限制！觸發安全暫停...")
                        time_limit_reached = True
                        break

                    car_tag = str(version.get("tag") or version.get("carTag") or "")
                    if not car_tag: continue

                    year_from = format_year(version.get("productionFrom"))
                    year_to = format_year(version.get("productionTo"))
                    model_version = version.get("version", "")

                    time.sleep(random.uniform(0.65, 1.35))

                    try:
                        car_details = get_car_hsn_tsn(car_tag)
                        hsn = car_details.get("hsn", "") if isinstance(car_details, dict) else ""
                        tsn = car_details.get("tsn", "") if isinstance(car_details, dict) else ""

                        tpms_data = get_tpms(car_tag)
                        oe_list = []

                        if isinstance(tpms_data, dict) and "tpms" in tpms_data:
                            sensor_ids = []
                            for s in tpms_data["tpms"]:
                                if s.get("oeAm") == "O":
                                    m_id = s.get("manufacturerId") or s.get("articleId") or s.get("id") or s.get("tpmsId")
                                    if m_id: sensor_ids.append(m_id)
                            
                            details_dict = {}
                            if sensor_ids:
                                time.sleep(random.uniform(0.3, 0.7)) 
                                detailed_info = get_sensor_details(sensor_ids)
                                if isinstance(detailed_info, list):
                                    for item in detailed_info:
                                        item_id = item.get("manufacturerId") or item.get("id") or item.get("articleId")
                                        if item_id: details_dict[str(item_id)] = item
                                elif isinstance(detailed_info, dict):
                                    data_list = detailed_info.get("data", []) or detailed_info.get("items", [])
                                    if isinstance(data_list, list):
                                        for item in data_list:
                                            item_id = item.get("manufacturerId") or item.get("id") or item.get("articleId")
                                            if item_id: details_dict[str(item_id)] = item
                                    else:
                                        details_dict = detailed_info

                            for s in tpms_data["tpms"]:
                                if s.get("oeAm") == "O":
                                    m_id = str(s.get("manufacturerId") or s.get("articleId") or s.get("id") or s.get("tpmsId") or "")
                                    s_detail = details_dict.get(m_id, {}) if m_id else {}

                                    hersteller = s_detail.get("hersteller") or s.get("hersteller") or find_key_value(s, ['hersteller','manufacturer','marke'])
                                    frequenz = s_detail.get("frequenz") or s.get("frequenz") or find_key_value(s, ['frequenz','frequency','mhz'])
                                    
                                    if not frequenz:
                                        sd = str(s).lower() + str(s_detail).lower()
                                        frequenz = '433' if '433' in sd else '434' if '434' in sd else '315' if '315' in sd else ''
                                    
                                    baujahr = s_detail.get("baujahr") or s.get("baujahr", "")
                                    if not baujahr:
                                        s_str = str(s) + str(s_detail)
                                        match = re.search(r'(\d{2}/\d{4}\s*-(\s*\d{2}/\d{4})?)', s_str)
                                        if match:
                                            baujahr = match.group(1).strip()
                                        else:
                                            baujahr = find_key_value(s, ['baujahr'])
                                            
                                    if not baujahr or baujahr == "0000-00-00":
                                        baujahr = f"{year_from} ~ {year_to}"
                                        
                                    oe_list.append({
                                        "oe": str(s.get("tpmsDescFrontend", "")),
                                        "baujahr": baujahr,
                                        "hersteller": str(hersteller),
                                        "frequenz": str(frequenz)
                                    })

                        if not oe_list:
                            oe_list = [{"oe":"","baujahr":"","hersteller":"","frequenz":""}]

                        for info in oe_list:
                            batch_data.append({
                                "Brand": brand, "Model": car_class, "Typ": model_version,
                                "Start Year": year_from, "End Year": year_to,
                                "HSN": hsn, "TSN": tsn,
                                "created date": info["baujahr"],
                                "OE sensor": info["oe"],
                                "Manufacturer": info["hersteller"],
                                "Frequency": info["frequenz"]
                            })

                        if len(batch_data) >= 80:
                            save_batch_to_sql(batch_data)
                            batch_data.clear()

                    except Exception as e:
                        tqdm.write(f"⚠️ 異常 {model_version}: {e}")

            if batch_data:
                save_batch_to_sql(batch_data)
                batch_data.clear()

            if not time_limit_reached:
                tqdm.write(f"   ✅ Model完成: {car_class}")

        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query('SELECT * FROM tpms_sensors WHERE "Brand"=?', conn, params=(brand,))
            conn.close()
            if not df.empty:
                df['年份'] = df['Start Year'].astype(str) + " ~ " + df['End Year'].astype(str)
                order = ['Brand','Model','Typ','年份','HSN','TSN','created date','OE sensor','Manufacturer','Frequency']
                df = df.reindex(columns=order)
                path = os.path.join(folder_path, f"{sanitize_filename(brand)}_Data.xlsx")
                df.to_excel(path, index=False)
                if not time_limit_reached:
                    tqdm.write(f"✅ {brand} Excel 匯出完成 → {len(df)} 筆")
        except Exception as e:
            tqdm.write(f"⚠️ Excel 匯出失敗: {e}")

        if not time_limit_reached:
            completed_brands.append(brand)
            tqdm.write(f"🎉 Brand完成: 【{brand}】 ✅")

    print("\n" + "="*60)
    if time_limit_reached:
        print("⏸️ 爬蟲任務因接近 6 小時限制而暫停！")
        print(f"進度已安全儲存，下次將從斷點繼續。")
    else:
        print("🎊 爬蟲任務全部完成！")
        save_progress(completed=True)

    print(f"✅ 此次共完整處理 {len(completed_brands)} 個Brand")
    print("="*60)

    auto_export_sql()

if __name__ == "__main__":
    main_scraper_all()
