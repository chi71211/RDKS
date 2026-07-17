import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import os
import requests
import pandas as pd
import re
import json
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測.db')
SQL_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測.sql')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'scrape_progress.json')

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

# ====================== 進度管理 ======================
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
        print("\n⏳ 超過 7 天，啟動全面掃描模式...")
        fresh = {"cycle_start": time.time(), "last_brand": "", "last_class": "", "last_tg": ""}
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(fresh, f)
        return fresh, True
    return prog, False

# ====================== API 請求 ======================
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
            print(f"請求失敗 {url}")
        time.sleep(1.5)
        return []

def get_manufacturers(): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/manufacturers")
def get_classes(brand): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/classes", {"manufacturer": brand})
def get_type_groups(brand, car_class): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/type-groups", {"manufacturer": brand, "class": car_class})
def get_versions(tg): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/version-groups", {"group": tg})
def get_car_hsn_tsn(tag): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/cars/car", {"carTag": tag})
def get_tpms(tag): return safe_json_get("https://www.interpneu-raederkonfigurator.de/api/tpms/carTpms", {"carTag": tag})

# ====================== 輔助函式 ======================
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

# ====================== 資料庫 ======================
def save_batch_to_sql(batch_data):
    if not batch_data: return
    df = pd.DataFrame(batch_data).fillna("")
    group_cols = ['品牌', '車系', '型號', '年份起點', '年份終點', 'HSN', 'TSN']
    agg_dict = {
        'OE感測器': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        '廠商(Hersteller)': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        '頻率(Frequenz)': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
        '建設日期(Baujahr)': lambda x: ', '.join(sorted({str(v).strip() for v in x if str(v).strip()})),
    }
    for col in group_cols:
        agg_dict[col] = 'first'
    df_merged = df.groupby(group_cols, as_index=False).agg(agg_dict)
    cols = ['品牌','車系','型號','年份起點','年份終點','HSN','TSN',
            '建設日期(Baujahr)','OE感測器','廠商(Hersteller)','頻率(Frequenz)']
    df_merged = df_merged.reindex(columns=cols)

    conn = sqlite3.connect(DB_PATH)
    conn.executemany('''
        REPLACE INTO tpms_sensors 
        (品牌, 車系, 型號, 年份起點, 年份終點, HSN, TSN, "建設日期(Baujahr)", 
         OE感測器, "廠商(Hersteller)", "頻率(Frequenz)")
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
    print(f"🎉 SQL 備份完成")

# ====================== 主程式 ======================
def main_scraper_all():
    folder_path = os.path.join(SCRIPT_DIR, sanitize_filename("胎壓偵測"))
    os.makedirs(folder_path, exist_ok=True)

    brands = get_manufacturers()
    if not isinstance(brands, list) or not brands:
        print("❌ 無法取得品牌清單")
        return

    prog, _ = check_7_day_cycle()
    skip_mode = bool(prog.get("last_brand"))

    # 建立資料表
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tpms_sensors (
            品牌 TEXT, 車系 TEXT, 型號 TEXT, 年份起點 TEXT, 年份終點 TEXT,
            HSN TEXT, TSN TEXT, "建設日期(Baujahr)" TEXT, 
            OE感測器 TEXT, "廠商(Hersteller)" TEXT, "頻率(Frequenz)" TEXT,
            UNIQUE(品牌, 車系, 型號, 年份起點, HSN, TSN)
        )
    ''')
    conn.commit()
    conn.close()

    batch_data = []
    print(f"🔍 開始處理 {len(brands)} 個品牌...\n")

    for brand in brands:
        if skip_mode and brand != prog.get("last_brand"):
            print(f"⏭️ 已完成: {brand} ✅")
            continue

        if skip_mode and brand == prog.get("last_brand"):
            skip_mode = False
            print(f"▶️ 從 {brand} 繼續...")

        print(f"\n🚗 正在處理: 【{brand}】")
        save_progress(brand=brand)

        classes = get_classes(brand)
        if not isinstance(classes, list): classes = []

        for car_class in classes:
            print(f"   📌 車系: {car_class}")
            type_groups = get_type_groups(brand, car_class)
            if not isinstance(type_groups, list): type_groups = []

            for tg_data in type_groups:
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
                            for s in tpms_data["tpms"]:
                                if s.get("oeAm") == "O":
                                    hersteller = s.get("hersteller") or find_key_value(s, ['hersteller','manufacturer','marke'])
                                    frequenz = s.get("frequenz") or find_key_value(s, ['frequenz','frequency','mhz'])
                                    if not frequenz:
                                        sd = str(s).lower()
                                        frequenz = next((f for f in ['433','434','315'] if f in sd), '')
                                    baujahr = s.get("baujahr") or find_key_value(s, ['baujahr'])
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
                                "品牌": brand, "車系": car_class, "型號": model_version,
                                "年份起點": year_from, "年份終點": year_to,
                                "HSN": hsn, "TSN": tsn,
                                "建設日期(Baujahr)": info["baujahr"],
                                "OE感測器": info["oe"],
                                "廠商(Hersteller)": info["hersteller"],
                                "頻率(Frequenz)": info["frequenz"]
                            })

                        if len(batch_data) >= 80:
                            save_batch_to_sql(batch_data)
                            batch_data.clear()

                    except Exception as e:
                        print(f"⚠️ 錯誤 {model_version}: {e}")

            if batch_data:
                save_batch_to_sql(batch_data)
                batch_data.clear()
            print(f"   ✅ 車系完成: {car_class}")

        print(f"🎉 品牌完成: 【{brand}】 ✅\n")

    print("\n" + "="*60)
    print("🎊 全部任務完成！")
    print("="*60)

    save_progress(completed=True)
    auto_export_sql()

if __name__ == "__main__":
    main_scraper_all()
