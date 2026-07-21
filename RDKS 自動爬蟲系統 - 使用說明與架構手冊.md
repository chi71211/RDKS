"""

AutoBild 爬蟲系統 - 終極企業版 (v10.0 極簡雙表直球對決版)

特色：

1. 資料庫極簡化：嚴格遵守指示，只保留 1 個資料表 (car_catalog) 與 1 個視圖 (view)。

2. 拔除狀態表：刪除所有自作聰明的續傳邏輯，強制每台車都爬取，由資料庫 UNIQUE 自動去重，解決「沒寫進去」的問題。

3. 自動路徑修正：解決 VS Code 右上角箭頭執行時造成的 Read-only 唯讀報錯。

4. 終極展開與新分頁擷取：完美展開多層次分類與「顯示更多」，背景分頁精準挖字。

"""

import nest_asyncio

nest_asyncio.apply()

import asyncio

import os

import sys

import random

import sqlite3

import argparse

import pandas as pd

from playwright.async_api import async_playwright

from IPython.display import display

# ==========================================

# 🌟 自動切換到程式所在目錄，解決右上角箭頭的唯讀問題

# ==========================================

os.chdir(os.path.dirname(os.path.abspath(_file_)))

class Config:

BASE_URL = "https://www.autobild.de"

CATALOG_URL = f"{BASE_URL}/marken-modelle/#aktuell"

CSV_DIR = "AutoBild_Exports"

DB_FILE = "autobild_master.db"

BATCH_SIZE = 50

DELAY_MIN = 0.8

DELAY_MAX = 1.6


async def smart_delay(success=True):

delay = random.uniform(Config.DELAY_MIN, Config.DELAY_MAX) if success else random.uniform(2.5, 4.5)

if random.random() < 0.15: delay += random.uniform(1.0, 3.0)

await asyncio.sleep(max(0.5, min(delay, 6.0)))


class DatabaseManager:

def \__init_\_(self):

    os.makedirs(Config.CSV_DIR, exist_ok=True)

    self.conn = sqlite3.connect(Config.DB_FILE)

    self.cursor = self.conn.cursor()

    self.batch = \[\]

    self.\_init_db()



def \_init_db(self):

    \# 🌟 聽您的！把之前多餘的狀態表全部刪掉，保持資料庫乾淨

    self.cursor.execute('DROP TABLE IF EXISTS model_status')

    self.cursor.execute('DROP TABLE IF EXISTS system_metadata')

    

    \# 1. 唯一的核心資料表

    self.cursor.execute('''

        CREATE TABLE IF NOT EXISTS car_catalog (

            Brand TEXT, Model TEXT, Category TEXT, Fuel_Type TEXT, Typ TEXT, Year TEXT, HSN_TSN TEXT,

            UNIQUE(Brand, Model, Category, Fuel_Type, Typ, Year, HSN_TSN)

        )

    ''')

    

    \# 2. 唯一的報表檢視圖 (自動把相同的車款 HSN_TSN 串接)

    self.cursor.execute('DROP VIEW IF EXISTS view_car_catalog_unique')

    self.cursor.execute('''

        CREATE VIEW view_car_catalog_unique AS

        SELECT 

            Brand, 

            Model, 

            Category,

            Fuel_Type,

            Typ, 

            Year, 

            GROUP_CONCAT(HSN_TSN, ', ') AS HSN_TSN

        FROM car_catalog

        GROUP BY Brand, Model, Category, Fuel_Type, Typ, Year

    ''')

    self.conn.commit()

def add_to_batch(self, record: dict):

    self.batch.append(record)

    if len(self.batch) >= Config.BATCH_SIZE:

        self.flush()



def flush(self):

    if not self.batch: return

    for r in self.batch:

        \# 使用 INSERT OR IGNORE，遇到重複資料自動忽略，絕不報錯

        self.cursor.execute('''

            INSERT OR IGNORE INTO car_catalog (Brand, Model, Category, Fuel_Type, Typ, Year, HSN_TSN)

            VALUES (?, ?, ?, ?, ?, ?, ?)

        ''', (r\['Brand'\], r\['Model'\], r\['Category'\], r\['Fuel_Type'\], r\['Typ'\], r\['Year'\], r\['HSN_TSN'\]))

    self.conn.commit()

    self.batch.clear()

    

def export_brand_csv(self, brand: str):

    self.flush()

    try:

        df = pd.read_sql_query("SELECT \* FROM view_car_catalog_unique WHERE Brand = ?", self.conn, params=(brand,))

        if not df.empty:

            path = os.path.join(Config.CSV_DIR, f"{brand}.csv")

            df.to_csv(path, index=False, encoding='utf-8-sig')

    except Exception: pass



def close(self):

    self.flush()

    self.conn.close()


async def full_catalog_scraper(test_mode=False):

print("\\n🚀 ==============================================")

print("AutoBild 爬蟲系統 - v10.0 極簡直球對決版啟動")

db = DatabaseManager()

print("==============================================\\n")



async with async_playwright() as p:

    browser = await p.chromium.launch(headless=True)

    context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    page = await context.new_page()

    

    try:

        await page.goto(Config.CATALOG_URL, timeout=90000, wait_until="domcontentloaded")

        await smart_delay()

        

        \# 同意 Cookie

        try:

            iframe = page.frame_locator('iframe\[id^="sp_message_iframe"\]')

            await iframe.get_by_role("button", name="Alle akzeptieren").click(timeout=8000)

        except: pass

        

        await page.evaluate("window.scrollTo(0, 1200)")

        await smart_delay()

        

        \# 取得廠牌連結

        links = await page.query_selector_all("a\[href\*='/marken-modelle/'\]")

        brand_urls = \[\]

        seen = set()

        for link in links:

            href = await link.get_attribute("href")

            if href and "/marken-modelle/" in href and href.count("/") >= 4:

                full = Config.BASE_URL + href if not href.startswith("http") else href

                full = full.split("#")\[0\].split("?")\[0\]

                if full.endswith("/") and full not in seen:

                    seen.add(full)

                    brand_urls.append(full)

        

        brand_urls.sort(reverse=True)

        if test_mode: brand_urls = brand_urls\[:2\]

        

        for b_url in brand_urls:

            base_brand = b_url.strip("/").split("/")\[-1\].upper()

            print(f"\\n➔ 進入廠牌: {base_brand}")

            await page.goto(b_url, timeout=60000, wait_until="domcontentloaded")

            await smart_delay()

            

            \# 🌟 步驟 1：強制點擊 ALLE MODELLE

            await page.evaluate(r'''() => {

                const btns = Array.from(document.querySelectorAll('a, button, li, span')).filter(el => el.innerText && el.innerText.trim().toUpperCase() === 'ALLE MODELLE');

                if(btns.length > 0) btns\[0\].click();

            }''')

            await asyncio.sleep(2.0)

            

            model_links = await page.query_selector_all("a\[href\*='/marken-modelle/'\]")

            models = \[\]

            for ml in model_links:

                h = await ml.get_attribute("href")

                if h and h.count("/") > b_url.count("/") and h.startswith(b_url):

                    full_m = Config.BASE_URL + h if not h.startswith("http") else h

                    models.append(full_m.split("#")\[0\])

            models = list(dict.fromkeys(models))

            if test_mode: models = models\[:2\]

            for m_url in models:

                base_model = m_url.strip("/").split("/")\[-1\].replace("-", " ").title()

                await page.goto(m_url, timeout=60000, wait_until="domcontentloaded")

                

                await page.evaluate(r'''async () => {

                    window.scrollBy(0, 800);

                    await new Promise(r => setTimeout(r, 800));

                    window.scrollBy(0, -300);

                }''')

                await asyncio.sleep(1.5)

                \# 🌟 步驟 2：點擊 ALLE DATEN & VARIANTEN

                await page.evaluate(r'''() => {

                    const btns = Array.from(document.querySelectorAll('a, button, li, span, div, h2')).filter(el => el.innerText && el.innerText.toUpperCase().includes('ALLE DATEN & VARIANTEN'));

                    if(btns.length > 0) { try { btns\[0\].click(); } catch(e){} }

                }''')

                await asyncio.sleep(2.0)

                \# 🌟 步驟 3：展開所有變體 (Kraftstoffarten, Karosserie 等)

                await page.evaluate(r'''() => {

                    const headers = Array.from(document.querySelectorAll('div, span, button, h2, h3, a')).filter(el => {

                        let txt = el.innerText || '';

                        return txt.includes('Kraftstoffarten') || txt.includes('Karosserie') || txt.includes('Antrieb');

                    });

                    headers.forEach(h => { try { h.click(); } catch(e){} });

                }''')

                await asyncio.sleep(2.0)

                

                \# 🌟 步驟 4：瘋狂點擊 WEITERE VARIANTEN ANZEIGEN 直到消失

                while True:

                    clicked = await page.evaluate(r'''() => {

                        const moreBtns = Array.from(document.querySelectorAll('div, span, button')).filter(b => b.innerText && b.innerText.includes('WEITERE VARIANTEN ANZEIGEN') && b.offsetParent !== null);

                        if (moreBtns.length > 0) {

                            try { moreBtns\[0\].click(); return true; } catch(e) {}

                        }

                        return false;

                    }''')

                    if not clicked:

                        break

                    await asyncio.sleep(1.2)

                \# 🌟 步驟 5：收集畫面上所有展開後的專屬 URL

                vehicle_hrefs = await page.evaluate(r'''() => {

                    return Array.from(document.querySelectorAll('.vvp__fuelType-dataBodyRow')).map(row => {

                        const a = row.querySelector('a');

                        return a ? a.getAttribute('href') : null;

                    }).filter(h => h);

                }''')

                

                vehicle_hrefs = list(dict.fromkeys(vehicle_hrefs))

                

                \# 🌟 單頁防呆：如果網頁沒有清單(如 Xiaomi)，就把當下這頁當作唯一車款

                if not vehicle_hrefs:

                    vehicle_hrefs = \[m_url\]

                total_variants_in_model = len(vehicle_hrefs)

                print(f"  ↳ \[{base_brand} - {base_model}\] 成功展開 {total_variants_in_model} 個獨立車款，開始背景擷取...")

                \# 🌟 步驟 6：背景開新分頁擷取詳細資料

                for i, href in enumerate(vehicle_hrefs):

                    if test_mode and i >= 3: break

                    

                    detail_url = Config.BASE_URL + href if not href.startswith('http') else href

                    detail_page = await context.new_page()

                    

                    try:

                        await detail_page.goto(detail_url, timeout=45000, wait_until="domcontentloaded")

                        

                        \# 展開詳細頁面的折疊表格

                        await detail_page.evaluate(r'''() => {

                            Array.from(document.querySelectorAll('span, div, h3, h4, button'))

                                .filter(el => el.textContent && (el.textContent.trim() === 'Basisdaten' || el.textContent.trim().includes('Motor')))

                                .forEach(b => { try{b.click();}catch(e){} try{if(b.parentElement) b.parentElement.click();}catch(e){} });

                        }''')

                        await asyncio.sleep(1.0)

                        

                        \# 終極精準挖字 (直接從 Basisdaten 挖出所有分類)

                        dom_data = await detail_page.evaluate(r'''() => {

                            let data = { Typ: 'N/A', Year: 'N/A', HSN_TSN: 'N/A', Category: 'N/A', Fuel_Type: 'N/A' };

                            

                            let titleEl = document.querySelector('h1, .vvp__vehicleTitle');

                            if(titleEl) data.Typ = titleEl.innerText.trim().replace(/\\n/g, ' ');

                            let allCells = Array.from(document.querySelectorAll('div, span, td, th'));

                            for (let j = 0; j < allCells.length; j++) {

                                let txt = allCells\[j\].innerText ? allCells\[j\].innerText.trim().toLowerCase().replace(/:\$/, '') : '';

                                if (!txt) continue;

                                let val = allCells\[j+1\] ? allCells\[j+1\].innerText.trim() : '';

                                

                                if (txt === 'modell' && data.Typ === 'N/A') data.Typ = val;

                                if ((txt === 'bauzeitraum' || txt === 'baujahr' || txt === 'produktionszeitraum') && data.Year === 'N/A') data.Year = val;

                                if ((txt === 'hsn/tsn schlüsselnummern' || txt === 'hsn/tsn' || txt === 'schlüsselnummer') && data.HSN_TSN === 'N/A') data.HSN_TSN = val;

                                if (txt === 'karosserieform' && data.Category === 'N/A') data.Category = val;

                                if (txt === 'kraftstoffart' && data.Fuel_Type === 'N/A') data.Fuel_Type = val;

                            }

                            return data;

                        }''')

                        

                        final_brand = base_brand

                        final_variant = dom_data.get('Typ', 'N/A')

                        final_year = dom_data.get('Year', 'N/A')

                        final_hsn_tsn = dom_data.get('HSN_TSN', 'N/A')

                        final_category = dom_data.get('Category', 'N/A')

                        final_fuel = dom_data.get('Fuel_Type', 'N/A')

                        \# 髒字防呆過濾

                        if final_variant == 'N/A' or "auswählen" in final_variant.lower():

                            final_variant = f"Typ\_{i+1}"

                        if final_year == 'N/A' or "kraftstoffart" in final_year.lower():

                            final_year = "N/A"

                        \# 寫入資料庫 (交給 SQLite UNIQUE 處理去重)

                        if final_hsn_tsn != 'N/A' and ',' in final_hsn_tsn:

                            for code in \[c.strip() for c in final_hsn_tsn.split(',')\]:

                                db.add_to_batch({"Brand": final_brand, "Model": base_model, "Category": final_category, "Fuel_Type": final_fuel, "Typ": final_variant, "Year": final_year, "HSN_TSN": code})

                        else:

                            db.add_to_batch({"Brand": final_brand, "Model": base_model, "Category": final_category, "Fuel_Type": final_fuel, "Typ": final_variant, "Year": final_year, "HSN_TSN": final_hsn_tsn})

                            

                        sys.stdout.write(f"\\r      \[寫入中\] {final_fuel\[:10\]} - 第 {i+1}/{total_variants_in_model} 款: {final_variant\[:20\]}...")

                        sys.stdout.flush()

                    except Exception as e:

                        pass

                    finally:

                        await detail_page.close()

                print() 

                db.flush()

            

            db.export_brand_csv(base_brand)

            

        print("\\n🎉 爬蟲任務完美結束！")

    except Exception as e:

        print(f"\\n❌ 執行中斷: {e}")

    finally:

        db.close()

        await browser.close()


if _name_ == "_main_":

parser = argparse.ArgumentParser()

parser.add_argument("--test", action="store_true")

\# 保留 reset 功能以防您未來想手動清空整個 DB，但現在預設執行就不會卡跳過了

parser.add_argument("--reset", action="store_true")

parser.add_argument("--status", action="store_true")

args = parser.parse_args()



if args.reset:

    if os.path.exists(Config.DB_FILE): os.remove(Config.DB_FILE)

    print("✅ 舊資料庫已完全重置！")

    sys.exit(0)

    

if args.status:

    if os.path.exists(Config.DB_FILE):

        conn = sqlite3.connect(Config.DB_FILE)

        try:

            df = pd.read_sql("SELECT Brand, Fuel_Type, COUNT(DISTINCT Model) as Models, COUNT(\*) as Total_Rows FROM view_car_catalog_unique GROUP BY Brand, Fuel_Type", conn)

            display(df)

        except: pass

        conn.close()

    sys.exit(0)



asyncio.run(full_catalog_scraper(test_mode=args.test))

