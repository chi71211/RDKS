import sys
# 防止終端機顯示中文時發生亂碼崩潰，遇到無法顯示的字元自動替換
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import os
import requests
import pandas as pd
import re
import json
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 🌟 全域設定與檔案路徑
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '胎壓自動修改.db')
SQL_PATH = os.path.join(SCRIPT_DIR, '胎壓自動修改.sql')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'scrape_progress修改.json')

session = requests.Session()
retry_strategy = Retry(
    total=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
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
# 1. 進度與 7 天週期管理 (修復 PDF 問題 1 & 5)
# ==========================================
def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[警告] 讀取進度檔失敗: {e}")
    return {"cycle_start": time.time(), "last_brand": "", "last_class": "", "last_tg": ""}

def save_progress(brand, car_class="", tg_id="", completed=False):
    prog = load_progress()
    prog["last_brand"] = "" if completed else brand
    prog["last_class"] = "" if completed else car_class
    prog["last_tg"] = "" if completed else tg_id
    if completed:
        prog["cycle_start"] = time.time()
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(prog, f)
    except Exception as e:
        print(f"[警告] 儲存進度失敗: {e}")

def check_7_day_cycle():
    """檢查是否超過 7 天，超過則只重置進度，【不刪除】資料庫以保證歷史資料安全"""
    prog = load_progress()
    now = time.time()
    if now - prog.get("cycle_start", now) > 604800:
        print("\n⏳ [週期檢查] 距離上次全面掃描已超過 7 天！啟動【全面巡邏模式】...")
        fresh_prog = {"cycle_start": now, "last_brand": "", "last_class": "", "last_tg": ""}
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(fresh_prog, f)
        return fresh_prog, True
    else:
        if prog.get("last_brand"):
            print(f"\n⏳ [週期檢查] 7 天內中斷恢復，啟動【繼續進度模式】...")
        return prog, False

# ==========================================
# 2. API 請求與輔助函式
# ==========================================
def get_manufacturers():
    res = session.get("https://www.interpneu-raederkonfigurator.de/api/cars/manufacturers", timeout=15)
    return res.json() if res.status_code == 200 else []

def get_classes(brand):
    res = session.get(f"https://www.interpneu-raederkonfigurator.de/api/cars/classes?manufacturer={brand}", timeout=15)
    return res.json() if res.status_code == 200 else []

def get_type_groups(brand, car_class):
    res = session.get("https://www.interpneu-raederkonfigurator.de/api/cars/type-groups", params={"manufacturer": brand, "class": car_class}, timeout=15)
    return res.json() if res.status_code == 200 else []

def get_versions(type_group):
    res = session.get("https://www.interpneu-raederkonfigurator.de/api/cars/version-groups", params={"group": type_group}, timeout=15)
    return res.json() if res.status_code == 200 else []

def get_car_hsn_tsn(car_tag):
    res = session.get("https://www.interpneu-raederkonfigurator.de/api/cars/car", params={"carTag": car_tag}, timeout=15)
    return res.json() if res.status_code == 200 else {}

def get_tpms(car_tag):
    res = session.get("https://www.interpneu-raederkonfigurator.de/api/tpms/carTpms", params={"carTag": car_tag}, timeout=15)
    return res.json() if res.status_code == 200 else {}

def format_year(date_str):
    return "至今" if not date_str or date_str == "0000-00-00" else date_str[:7]

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

def find_key_value(d, keywords):
    if isinstance(d, dict):
        label = str(d.get("name", d.get("key", d.get("label", "")))).lower()
        if any(kw in label for kw in keywords) and ("value" in d or "val" in d):
            val = d.get("value", d.get("val", ""))
            if val and str(val).strip(): return str(val).strip()
        for k, v in d.items():
            k_lower = str(k).lower()
            if any(kw in k_lower for kw in keywords) and not isinstance(v, (dict, list)):
                if v is not None and str(v).strip(): return str(v).strip()
            res = find_key_value(v, keywords)
            if res: return res
    elif isinstance(d, list):
        for item in d:
            res = find_key_value(item, keywords)
            if res: return res
    return ""

# ==========================================
# 3. 核心比對邏輯與資料庫操作 (修復 PDF 問題 2 & 3)
# ==========================================
def get_scraped_models():
    """取得資料庫中已存在的所有世代，快速辨識新舊車款"""
    if not os.path.exists(DB_PATH): return set()
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT 品牌, 車系, 型號, 年份起點 FROM tpms_sensors", conn)
        conn.close()
        return set(tuple(str(x).strip() for x in row) for row in df.values)
    except Exception as e:
        print(f"[警告] 讀取歷史模型失敗: {e}")
        return set()

def get_db_signature(brand, car_class, model, year_from):
    """(新增) 從資料庫抓取該車型的感測器簽章，用來與新資料比對差異"""
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query('''
            SELECT HSN, TSN, "建設日期(Baujahr)", OE感測器, "廠商(Hersteller)", "頻率(Frequenz)"
            FROM tpms_sensors
            WHERE 品牌=? AND 車系=? AND 型號=? AND 年份起點=?
            ORDER BY HSN, TSN
        ''', conn, params=(brand, car_class, model, year_from))
        conn.close()
        return str(df.values.tolist())
    except Exception:
        return ""

def get_local_signature(raw_rows):
    """(新增) 將剛抓下來的 API 原始資料合併排序，產生簽章供比對"""
    if not raw_rows: return str([])
    df = pd.DataFrame(raw_rows)
    group_cols = ['HSN', 'TSN']
    df = df.fillna("")
    df_merged = df.groupby(group_cols, as_index=False).agg(
        lambda x: ', '.join(sorted(list(set(str(v) for v in x if str(v).strip()))))
    )
    df_merged = df_merged.sort_values(by=['HSN', 'TSN'])
    sig_cols = ['HSN', 'TSN', '建設日期(Baujahr)', 'OE感測器', '廠商(Hersteller)', '頻率(Frequenz)']
    for col in sig_cols:
        if col not in df_merged.columns: df_merged[col] = ""
    return str(df_merged[sig_cols].values.tolist())

def auto_export_sql():
    if not os.path.exists(DB_PATH): return
    try:
        conn = sqlite3.connect(DB_PATH)
        with open(SQL_PATH, 'w', encoding='utf-8') as f:
            for line in conn.iterdump():
                f.write('%s\n' % line)
        conn.close()
        print(f"  [備份] 🎉 已自動產出 {os.path.basename(SQL_PATH)} 備份檔！")
    except Exception as e:
        print(f"[警告] SQL備份失敗: {e}")

def save_batch_to_sql(batch_data):
    if not batch_data: return
    df = pd.DataFrame(batch_data)
    columns_order = [
        '品牌', '車系', '型號', '年份起點', '年份終點', 'HSN', 'TSN', 
        '建設日期(Baujahr)', 'OE感測器', '廠商(Hersteller)', '頻率(Frequenz)'
    ]
    df = df.reindex(columns=columns_order).fillna("")
    
    group_cols = ['品牌', '車系', '型號', '年份起點', '年份終點', 'HSN', 'TSN']
    df_merged = df.groupby(group_cols, as_index=False).agg(
        lambda x: ', '.join(sorted(list(set(str(v) for v in x if str(v).strip()))))
    )
    df_merged = df_merged[columns_order] 
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.executemany('''
            REPLACE INTO tpms_sensors 
            (品牌, 車系, 型號, 年份起點, 年份終點, HSN, TSN, "建設日期(Baujahr)", OE感測器, "廠商(Hersteller)", "頻率(Frequenz)") 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', df_merged.values.tolist())
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[警告] 寫入資料庫失敗: {e}")

# ==========================================
# 4. 終極版：全面抓取主程式
# ==========================================
def main_scraper_all():
    folder_name = sanitize_filename("胎壓自動修改")
    folder_path = os.path.join(SCRIPT_DIR, folder_name) 
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)

    brands = get_manufacturers()
    if not brands: 
        print("❌ [錯誤] 無法取得品牌清單。")
        return

    # 讀取進度，設定斷點接關
    prog, is_new_cycle = check_7_day_cycle()
    skip_mode = bool(prog.get("last_brand"))
    target_brand = prog.get("last_brand")
    target_class = prog.get("last_class")
    target_tg = prog.get("last_tg")

    # 確保資料表存在
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tpms_sensors (
            品牌 TEXT, 車系 TEXT, 型號 TEXT, 年份起點 TEXT, 年份終點 TEXT,
            HSN TEXT, TSN TEXT, "建設日期(Baujahr)" TEXT, OE感測器 TEXT,
            "廠商(Hersteller)" TEXT, "頻率(Frequenz)" TEXT,
            UNIQUE(品牌, 車系, 型號, 年份起點, HSN, TSN) 
        )
    ''')
    conn.commit()
    conn.close()

    scraped_models = get_scraped_models()
    print(f"\n[開始] 資料庫現有 {len(scraped_models)} 種世代紀錄。")
    print("-" * 50)

    for brand in brands:
        if skip_mode and target_brand and brand != target_brand: continue

        print(f"\n[執行中] 品牌：【{brand}】")
        batch_data = [] 

        classes = get_classes(brand)
        if not classes: continue

        for car_class in classes:
            if skip_mode and target_class and car_class != target_class: continue
            
            type_groups = get_type_groups(brand, car_class)

            for tg_data in type_groups:
                tg_id = tg_data.get("group")
                if not tg_id: continue

                if skip_mode and target_tg and tg_id != target_tg: continue

                # 🌟 如果執行到這裡，代表完全定位到斷點了，解除跳過模式！
                if skip_mode:
                    skip_mode = False
                    print(f"▶️ [接關成功] 從 {brand} > {car_class} 恢復抓取！")

                # --- 儲存極細緻進度 (品牌+車系+型號) ---
                save_progress(brand, car_class, tg_id)

                versions = get_versions(tg_id)
                versions.sort(key=lambda x: x.get('productionFrom', ''), reverse=True)

                for idx, version in enumerate(versions):
                    car_tag = str(version.get("tag") or version.get("carTag"))
                    if not car_tag: continue

                    year_from = format_year(version.get("productionFrom"))
                    year_to = format_year(version.get("productionTo"))
                    model_version = version.get("version", "")
                    model_identity = (str(brand).strip(), str(car_class).strip(), str(model_version).strip(), str(year_from).strip())

                    # 🌟 核心修正：正確的舊年份跳過邏輯
                    if idx > 0 and model_identity in scraped_models:
                        # 舊年份且資料庫已有記錄 -> 直接跳過剩下的舊年份，極速提升效能！
                        break 
                    
                    time.sleep(0.3) 
                    try:
                        car_details = get_car_hsn_tsn(car_tag)
                        hsn = car_details.get("hsn", "")
                        tsn = car_details.get("tsn", "")

                        tpms_data = get_tpms(car_tag)
                        oe_sensors_info = []
                        
                        if isinstance(tpms_data, dict) and "tpms" in tpms_data:
                            for sensor in tpms_data["tpms"]:
                                if sensor.get("oeAm") == "O":
                                    hersteller = str(sensor.get("hersteller", "")) or find_key_value(sensor, ['hersteller', 'manufacturer', 'brand', 'marke'])
                                    frequenz = str(sensor.get("frequenz", "")) or find_key_value(sensor, ['frequenz', 'frequency', 'mhz'])
                                    if not frequenz: 
                                        s_dump = str(sensor).lower()
                                        if '433' in s_dump: frequenz = '433'
                                        elif '434' in s_dump: frequenz = '434'
                                        elif '315' in s_dump: frequenz = '315'
                                    baujahr = str(sensor.get("baujahr", "")) or find_key_value(sensor, ['baujahr', 'production', 'year'])
                                    if not baujahr or baujahr == "0000-00-00": baujahr = f"{year_from} ~ {year_to}"

                                    oe_sensors_info.append({
                                        "oe": str(sensor.get("tpmsDescFrontend", "")),
                                        "baujahr": baujahr,
                                        "hersteller": hersteller,
                                        "frequenz": frequenz
                                    })

                        if not oe_sensors_info:
                            oe_sensors_info = [{"oe": "", "baujahr": "", "hersteller": "", "frequenz": ""}]

                        # 準備將解析後的資料打包
                        raw_rows = []
                        for s_info in oe_sensors_info:
                            raw_rows.append({
                                "品牌": brand, "車系": car_class, "型號": model_version,
                                "年份起點": year_from, "年份終點": year_to, "HSN": hsn, "TSN": tsn,
                                "建設日期(Baujahr)": s_info["baujahr"], "OE感測器": s_info["oe"],
                                "廠商(Hersteller)": s_info["hersteller"], "頻率(Frequenz)": s_info["frequenz"]
                            })

                        # 🌟 核心修正：最新年份的簽章比對 (Signature Verification)
                        if idx == 0 and model_identity in scraped_models:
                            new_sig = get_local_signature(raw_rows)
                            old_sig = get_db_signature(brand, car_class, model_version, year_from)
                            
                            if new_sig == old_sig:
                                # 最新年份的資料一模一樣，代表沒更新，直接跳過後面的所有舊車！
                                break
                            else:
                                print(f"    🔄 [智慧比對] 發現 {model_version} 資料更新！準備覆寫...")
                                
                        batch_data.extend(raw_rows)
                        scraped_models.add(model_identity) 

                        if len(batch_data) >= 100:
                            save_batch_to_sql(batch_data)
                            print(f"  💾 [批次合併存檔] 累積新車款已排版寫入！ (車系: {car_class})")
                            batch_data = [] 

                    except Exception as e:
                        print(f"⚠️ [錯誤] 抓取 {model_version} 時發生異常，跳過此筆: {e}")
                        continue

            print(f"  ✅ 車系掃描完成: {car_class}")

        # 批次殘留存檔
        if batch_data:
            save_batch_to_sql(batch_data)
            batch_data = []

        # 🌟 匯出單一品牌 Excel
        try:
            conn = sqlite3.connect(DB_PATH)
            df_brand = pd.read_sql_query("SELECT * FROM tpms_sensors WHERE 品牌=?", conn, params=(brand,))
            conn.close()

            if not df_brand.empty:
                df_brand['年份'] = df_brand['年份起點'].astype(str) + " ~ " + df_brand['年份終點'].astype(str)
                columns_order = [
                    '品牌', '車系', '型號', '年份', 'HSN', 'TSN', 
                    '建設日期(Baujahr)', 'OE感測器', '廠商(Hersteller)', '頻率(Frequenz)'
                ]
                df_brand = df_brand.reindex(columns=columns_order)
                
                safe_brand_name = sanitize_filename(brand)
                excel_name = os.path.join(folder_path, f"{safe_brand_name}_Data.xlsx")
                df_brand.to_excel(excel_name, index=False)
                print(f"  📊 【{brand}】Excel 匯出成功！")
        except Exception as e:
            print(f"  ⚠️ [警告] 匯出 Excel 發生錯誤: {e}")

        print("-" * 50)

    # 任務全數完成
    print("\n🎉 [全部完成] 所有品牌的資料爬取與更新檢查完畢！")
    save_progress("", "", "", completed=True)
    auto_export_sql()

# ==========================================
# 執行區塊
# ==========================================
if __name__ == "__main__":
    main_scraper_all()