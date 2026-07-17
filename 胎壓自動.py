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
from tqdm import tqdm

# ==========================================
# 全域設定
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測.db')
SQL_PATH = os.path.join(SCRIPT_DIR, '胎壓偵測.sql')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'scrape_progress.json')

# 🌟 新增：設定最大執行時間（5.8 小時 = 20880 秒），預留時間給 GitHub 存檔
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
    print(f"🎉 SQL 備份完成: {os.path.basename(SQL_PATH)}")

# ==========================================
# 主程式
# ==========================================
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
    conn.execute('''CREATE TABLE IF NOT EXISTS tpms_sensors (
        品牌 TEXT, 車系 TEXT, 型號 TEXT, 年份起點 TEXT, 年份終點 TEXT,
        HSN TEXT, TSN TEXT, "建設日期(Baujahr)" TEXT, 
        OE感測器 TEXT, "廠商(Hersteller)" TEXT, "頻率(Frequenz)" TEXT,
        UNIQUE(品牌, 車系, 型號, 年份起點, HSN, TSN)
    )''')
    conn.commit()
    conn.close()

    batch_data = []
    completed_brands = []
    time_limit_reached = False # 🌟 新增：超時標記

    print(f"🔍 共 {len(brands)} 個品牌\n")

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

        for car_class in tqdm(classes, desc=f"{brand} 車系", leave=False, ncols=80):
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
                    # 🌟 核心：每次處理前檢查是否即將超時
                    if time.time() - PROGRAM_START_TIME > MAX_RUNTIME_SECONDS:
                        tqdm.write(f"\n⏱️ 警告：執行時間即將超過 6 小時限制！觸發安全暫停...")
                        time_limit_reached = True
                        break # 中斷最內層迴圈

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
                                        frequenz = '433' if '433' in sd else '434' if '434' in sd else '315' if '315' in sd else ''
                                    baujahr = s.get("baujahr") or find_key_value(s, ['baujahr','year'])
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
                        tqdm.write(f"⚠️ 異常 {model_version}: {e}")

            # 車系結束後強制存檔
            if batch_data:
                save_batch_to_sql(batch_data)
                batch_data.clear()

            if not time_limit_reached:
                tqdm.write(f"   ✅ 車系完成: {car_class}")

        # 品牌完成後匯出 Excel
        try:
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM tpms_sensors WHERE 品牌=?", conn, params=(brand,))
            conn.close()
            if not df.empty:
                df['年份'] = df['年份起點'].astype(str) + " ~ " + df['年份終點'].astype(str)
                order = ['品牌','車系','型號','年份','HSN','TSN','建設日期(Baujahr)','OE感測器','廠商(Hersteller)','頻率(Frequenz)']
                df = df.reindex(columns=order)
                path = os.path.join(folder_path, f"{sanitize_filename(brand)}_Data.xlsx")
                df.to_excel(path, index=False)
                if not time_limit_reached:
                    tqdm.write(f"✅ {brand} Excel 匯出完成 → {len(df)} 筆")
        except Exception as e:
            tqdm.write(f"⚠️ Excel 匯出失敗: {e}")

        if not time_limit_reached:
            completed_brands.append(brand)
            tqdm.write(f"🎉 品牌完成: 【{brand}】 ✅")

    # 最終總結
    print("\n" + "="*60)
    if time_limit_reached:
        print("⏸️ 爬蟲任務因接近 6 小時限制而暫停！")
        print(f"進度已安全儲存，下次將從斷點繼續。")
    else:
        print("🎊 爬蟲任務全部完成！")
        save_progress(completed=True) # 只有全部跑完才清除進度

    print(f"✅ 此次共完整處理 {len(completed_brands)} 個品牌")
    print("="*60)

    auto_export_sql()

if __name__ == "__main__":
    main_scraper_all()
```eof

### 改造二：修改 GitHub Actions YAML 設定檔

要讓檔案能「接續寫在一起」，最核心的關鍵是：**GitHub Actions 每次啟動時，必須把「上一次」產生的資料庫（`RDKS.db`）和進度檔（`scrape_progress.json`）給「下載」回來。**

在原本的設定中，機器人每次醒來都是一台全新的乾淨虛擬機。現在，我們加入一個「拉取上一次進度」的步驟，然後把您的排程設定為每 6 小時自動喚醒一次。

請修改 `.github/workflows/scrape.yml`：

```yaml:.github/workflows/scrape.yml
name: 自動化 RDKS 爬蟲

# 設定排程時間
on:
  schedule:
    - cron: '0 */6 * * *' # 每天每 6 小時喚醒一次
  workflow_dispatch:

permissions:
  contents: write

jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 360 # 給足 6 小時

    steps:
      - name: 取得程式碼
        uses: actions/checkout@v4
        with:
          # 🌟 關鍵：取得包含所有 commit 歷史的程式碼，確保能拉到上一次存下來的 db 和 json
          fetch-depth: 0 

      - name: 設定 Python 環境
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: 安裝套件
        run: |
          pip install requests pandas openpyxl urllib3 tqdm

      - name: 執行爬蟲腳本
        run: python 胎壓自動.py

      - name: 上傳爬取結果 (Artifacts 備份)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: RDKS_Data_Backup
          path: |
            胎壓偵測/
            胎壓偵測.db
            胎壓偵測.sql
            scrape_progress.json

      - name: 提交並推送更新進度到 GitHub
        if: always()
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          
          # 🌟 關鍵：強制加入進度檔與資料庫
          git add -f 胎壓偵測.db || true
          git add -f 胎壓偵測.sql || true
          git add -f scrape_progress.json || true
          git add -f 胎壓偵測/ || true
          
          if git diff --quiet && git diff --staged --quiet; then
            echo "沒有偵測到任何資料更新，跳過提交。"
          else
            git commit -m "🤖 [自動存檔] 爬蟲進度與資料庫更新 [skip ci]"
            git push
          fi
```eof

### 運作原理解析

有了這雙重改造，系統的運作會變成這樣：

1. **第 1 小時 ~ 5.8 小時**：機器人開心抓取資料。
2. **5.8 小時**：Python 腳本的「碼錶」響了！它會優雅地停下迴圈，把目前抓到的所有資料存進 `胎壓偵測.db`，並把斷點記在 `scrape_progress.json`。
3. **5.8 ~ 6 小時**：YAML 設定檔接手，把這些檔案 `git commit` 並 `git push` 到您的 GitHub 首頁。
4. **第 6 小時**：下一個排程時間到了！GitHub 喚醒一台新的虛擬機器。
5. **關鍵動作**：這台新的機器因為我們設定了 `actions/checkout@v4`，它會從 GitHub 首頁把**剛剛熱騰騰上傳的資料庫和進度檔下載下來**。
6. **接續運作**：Python 腳本啟動，讀到 `scrape_progress.json`，發現上次斷在某個型號；它同時也連上了剛剛下載的 `胎壓偵測.db`。它接著上次的地方抓，並把新資料無縫 `REPLACE INTO` 同一個資料庫裡！

這就是完美的「自動接力跑」機制！
