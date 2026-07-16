import sys
# 防止終端機顯示中文時發生亂碼崩潰，遇到無法顯示的字元自動替換
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import sqlite3
import os
import time
import requests
import pandas as pd
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 🌟 全域設定與防護機制
# ==========================================
# 設定最大執行時間為 5.5 小時 (預留 30 分鐘給 GitHub 打包上傳)
MAX_RUNTIME_SECONDS = 5.5 * 3600 
PROGRAM_START_TIME = time.time()

# 建立穩定的連線 Session
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

# 設定全域 Headers
session.headers.update({
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Connection": "keep-alive"
})

# ==========================================
# 1. API 請求基礎函式
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
    if not date_str or date_str == "0000-00-00":
        return "至今"
    return date_str[:7] 

def sanitize_filename(filename):
    """將 Windows 檔案名稱中不允許的特殊字元替換為底線，防止存檔崩潰"""
    return re.sub(r'[\\/*?:"<>|]', '_', filename)

# ==========================================
# 2. 資料庫輔助與轉檔函式
# ==========================================
def get_scraped_tags(db_name='RDKS.db'):
    """讀取資料庫，獲取所有已經抓取過的 carTag 集合"""
    if not os.path.exists(db_name):
        return set()
    try:
        conn = sqlite3.connect(db_name)
        df = pd.read_sql_query("SELECT carTag FROM tpms_sensors", conn)
        conn.close()
        return set(df['carTag'].astype(str).tolist())
    except:
        return set()

def auto_export_sql(db_name='RDKS.db', sql_name='RDKS_Backup.sql'):
    """將 SQLite 資料庫匯出成純文字的 .sql 檔案"""
    print(f"\n[轉檔] 準備將 {db_name} 轉換為純文字 {sql_name} 檔案...")
    if not os.path.exists(db_name):
        print(f"[錯誤] 找不到 {db_name}，無法轉檔！")
        return
    conn = sqlite3.connect(db_name)
    with open(sql_name, 'w', encoding='utf-8') as f:
        for line in conn.iterdump():
            f.write('%s\n' % line)
    conn.close()
    print(f"[完成] 🎉 已經成功自動產出 {sql_name} 備份檔！")

def save_batch_to_sql(batch_data, db_name='RDKS.db'):
    """獨立的批次存檔函式 (已更新為 11 個欄位)"""
    if not batch_data: return
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    values_list = [
        (
            r["carTag"], r["品牌"], r["車系"], r["型號"], r["年份"], 
            r["HSN"], r["TSN"], r["建設日期(Baujahr)"], r["OE感測器"], 
            r["廠商(Hersteller)"], r["頻率(Frequenz)"]
        )
        for r in batch_data
    ]
    cursor.executemany('''
        INSERT OR IGNORE INTO tpms_sensors 
        (carTag, 品牌, 車系, 型號, 年份, HSN, TSN, "建設日期(Baujahr)", OE感測器, "廠商(Hersteller)", "頻率(Frequenz)") 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', values_list)
    conn.commit()
    conn.close()

# ==========================================
# 3. 終極版：全面抓取主程式
# ==========================================
def main_scraper_all():
    folder_name = sanitize_filename("RDKS")
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    BATCH_SIZE = 100 
    
    brands = get_manufacturers()
    if not brands:
        print("[錯誤] 無法取得品牌清單。")
        return

    # --- 建立擴充新欄位的資料表 ---
    conn = sqlite3.connect('RDKS.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tpms_sensors (
            carTag TEXT,
            品牌 TEXT,
            車系 TEXT,
            型號 TEXT,
            年份 TEXT,
            HSN TEXT,
            TSN TEXT,
            "建設日期(Baujahr)" TEXT,
            OE感測器 TEXT,
            "廠商(Hersteller)" TEXT,
            "頻率(Frequenz)" TEXT,
            UNIQUE(carTag, OE感測器) 
        )
    ''')
    conn.commit()
    conn.close()

    scraped_tags = get_scraped_tags()
    print(f"[開始] 準備啟動！資料庫已有 {len(scraped_tags)} 筆車款紀錄。")
    print("-" * 50)

    time_is_up = False 

    for target_brand in brands:
        if time_is_up: break

        print(f"\n[執行中] 進入品牌：【{target_brand}】")
        batch_data = [] 

        classes = get_classes(target_brand)
        if not classes: continue

        for car_class in classes:
            if time_is_up: break 

            type_groups = get_type_groups(target_brand, car_class)

            for tg_data in type_groups:
                if time_is_up: break 

                tg_id = tg_data.get("group")
                if not tg_id: continue

                versions = get_versions(tg_id)
                versions.sort(key=lambda x: x.get('productionFrom', ''), reverse=True)
                
                already_exists_streak = 0 

                for version in versions:
                    if time.time() - PROGRAM_START_TIME > MAX_RUNTIME_SECONDS:
                        print("\n⚠️ [超時警告] 執行時間已達極限！準備進入安全暫停程序...")
                        time_is_up = True
                        break 

                    car_tag = str(version.get("tag") or version.get("carTag"))
                    if not car_tag: continue

                    if car_tag in scraped_tags:
                        already_exists_streak += 1
                        if already_exists_streak >= 5:
                            print(f"    ⏭️ [跳過舊車] 型號 {tg_id} 連續 5 筆無更新，跳過剩餘版本。")
                            break 
                        continue 
                    else:
                        already_exists_streak = 0

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
                                    # 抓取新欄位資訊 (使用多種可能 key 來保證抓到)
                                    oe_name = str(sensor.get("tpmsDescFrontend", ""))
                                    baujahr = str(sensor.get("baujahr", sensor.get("productionFrom", "")))
                                    hersteller = str(sensor.get("hersteller", sensor.get("manufacturer", sensor.get("brand", ""))))
                                    frequenz = str(sensor.get("frequenz", sensor.get("frequency", "")))
                                    
                                    oe_sensors_info.append({
                                        "oe": oe_name,
                                        "baujahr": baujahr,
                                        "hersteller": hersteller,
                                        "frequenz": frequenz
                                    })

                        # 如果同一台車有多個相同的 Sensor，先做基礎去重
                        unique_sensors = [dict(t) for t in {tuple(d.items()) for d in oe_sensors_info}]
                        if not unique_sensors:
                            unique_sensors = [{"oe": "", "baujahr": "", "hersteller": "", "frequenz": ""}]

                        year_from = format_year(version.get("productionFrom"))
                        year_to = format_year(version.get("productionTo"))

                        for s_info in unique_sensors:
                            row_data = {
                                "carTag": car_tag,
                                "品牌": target_brand,
                                "車系": car_class,
                                "型號": version.get("version", ""),
                                "年份": f"{year_from} ~ {year_to}",
                                "HSN": hsn,
                                "TSN": tsn,
                                "建設日期(Baujahr)": s_info["baujahr"],
                                "OE感測器": s_info["oe"],
                                "廠商(Hersteller)": s_info["hersteller"],
                                "頻率(Frequenz)": s_info["frequenz"]
                            }
                            batch_data.append(row_data)
                            
                        scraped_tags.add(car_tag) 

                        if len(batch_data) >= BATCH_SIZE:
                            save_batch_to_sql(batch_data)
                            print(f"  💾 [批次存檔] 累積 {BATCH_SIZE} 筆，已安全寫入資料庫！ (車系: {car_class})")
                            batch_data = [] 

                    except Exception as e:
                        print(f"⚠️ 抓取 {car_tag} 時發生異常，跳過此筆。錯誤訊息: {e}")
                        continue

            print(f"  ✅ 車系掃描完成: {car_class}")

        if batch_data:
            save_batch_to_sql(batch_data)
            batch_data = []

        # 🌟 超級防漏機制與智慧合併輸出
        try:
            conn = sqlite3.connect('RDKS.db')
            df_brand = pd.read_sql_query("SELECT * FROM tpms_sensors WHERE 品牌=?", conn, params=(target_brand,))
            conn.close()

            if not df_brand.empty:
                # 1. 刪除 carTag (不顯示在 Excel)
                df_brand = df_brand.drop(columns=['carTag'], errors='ignore')
                
                # 2. 指定最終排版順序
                columns_order = [
                    '品牌', '車系', '型號', '年份', 'HSN', 'TSN', 
                    '建設日期(Baujahr)', 'OE感測器', '廠商(Hersteller)', '頻率(Frequenz)'
                ]
                df_brand = df_brand.reindex(columns=columns_order)
                
                # 3. 智慧合併邏輯 (只要 型號、HSN、TSN 一樣就自動合併，其餘差異資訊用 ", " 隔開)
                group_cols = ['品牌', '車系', '型號', '年份', 'HSN', 'TSN']
                df_brand = df_brand.fillna("")
                
                # 執行合併，使用逗號分隔
                df_brand = df_brand.groupby(group_cols, as_index=False).agg(
                    lambda x: ', '.join(sorted(list(set(str(v) for v in x if str(v).strip()))))
                )
                
                # 4. 再次確保合併後的順序正確
                df_brand = df_brand[columns_order]

                safe_brand_name = sanitize_filename(target_brand)
                excel_name = f"{folder_name}/{safe_brand_name}_Data.xlsx"
                df_brand.to_excel(excel_name, index=False)
                print(f"  📊 【{target_brand}】Excel 匯出且合併成功！共處理 {len(df_brand)} 種不重複車型配置。")
        except Exception as e:
            print(f"  ⚠️ 匯出 Excel 時發生錯誤: {e}")

        print("-" * 50)

    if time_is_up:
        print("\n🛑 [程式暫停] 已安全結束本次任務，下次啟動將自動從斷點與新車款繼續抓取！")
    else:
        print("\n🎉 [完成] 所有品牌的資料爬取與更新檢查完畢！")

# ==========================================
# 4. 執行區塊 (終極一鍵啟動)
# ==========================================
if __name__ == "__main__":
    main_scraper_all()
    auto_export_sql()
