"""
AutoBild 爬蟲系統 v11.0 - DOM 結構精準擷取版
================================================
核心修正：
1. 不再開新分頁爬 detail page → 直接在模型頁面提取所有資料
2. 不再用 leafNode 全頁面掃描 → 精準定位 vv__ / vvp__ / editorialTable 區塊
3. 新增 API 攔截器 → 嘗試從動態載入的 API 回應中提取 HSN/TSN
4. 新增 model_progress 進度表 → 增量更新，跳過已完成車系
5. 新增「顯示更多」自動展開 → 點擊所有 vv__fuelType-dataFooterToggle

用法：
  python autobild_v11.py              # 完整掃描
  python autobild_v11.py --test       # 測試模式 (2 廠牌 x 2 車系)
  python autobild_v11.py --reset      # 重置資料庫
  python autobild_v11.py --status     # 查看統計
  python autobild_v11.py --brand VW   # 只抓特定品牌
"""

import nest_asyncio
nest_asyncio.apply()
import asyncio
import os
import sys
import time
import random
import sqlite3
import argparse
import pandas as pd
import re
from datetime import datetime
from urllib.parse import urljoin
from playwright.async_api import async_playwright
from IPython.display import display

os.chdir(os.path.dirname(os.path.abspath(__file__)))


class Config:
    BASE_URL = "https://www.autobild.de"
    CATALOG_URL = f"{BASE_URL}/marken-modelle/#aktuell"
    CSV_DIR = "AutoBild_Exports"
    DB_FILE = "autobild_master.db"
    BATCH_SIZE = 50
    DELAY_MIN = 0.8
    DELAY_MAX = 1.6
    MAX_RETRIES = 3
    MAX_RUNTIME_HOURS = 5.5
    API_WAIT_TIMEOUT = 8


class DatabaseManager:
    def __init__(self):
        os.makedirs(Config.CSV_DIR, exist_ok=True)
        self.conn = sqlite3.connect(Config.DB_FILE)
        self.cursor = self.conn.cursor()
        self.batch = []
        self._init_db()

    def _init_db(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS car_catalog (
                Brand TEXT,
                Model TEXT,
                Category TEXT,
                Fuel_Type TEXT,
                Typ TEXT,
                Start_Year TEXT,
                End_Year TEXT,
                HSN_TSN TEXT,
                Power TEXT,
                UNIQUE(Brand, Model, Category, Fuel_Type, Typ, Start_Year, End_Year, HSN_TSN)
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_progress (
                Brand TEXT,
                Model TEXT,
                variant_count INTEGER,
                last_scraped TEXT,
                PRIMARY KEY(Brand, Model)
            )
        ''')

        self.cursor.execute('DROP VIEW IF EXISTS view_car_catalog')
        self.cursor.execute('''
            CREATE VIEW view_car_catalog AS
            SELECT
                Brand, Model, Category, Fuel_Type, Typ, Start_Year, End_Year,
                HSN_TSN, Power
            FROM car_catalog
            GROUP BY Brand, Model, Category, Fuel_Type, Typ, Start_Year, End_Year, HSN_TSN
        ''')
        self.conn.commit()

    def add_to_batch(self, record: dict):
        self.batch.append(record)
        if len(self.batch) >= Config.BATCH_SIZE:
            self.flush()

    def flush(self):
        if not self.batch:
            return
        for r in self.batch:
            self.cursor.execute('''
                INSERT OR IGNORE INTO car_catalog
                (Brand, Model, Category, Fuel_Type, Typ, Start_Year, End_Year, HSN_TSN, Power)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                r.get('Brand', 'N/A'), r.get('Model', 'N/A'),
                r.get('Category', 'N/A'), r.get('Fuel_Type', 'N/A'),
                r.get('Typ', 'N/A'), r.get('Start_Year', 'N/A'),
                r.get('End_Year', 'N/A'), r.get('HSN_TSN', 'N/A'),
                r.get('Power', 'N/A')
            ))
        self.conn.commit()
        self.batch.clear()

    def get_progress(self, brand: str, model: str):
        self.cursor.execute(
            'SELECT variant_count FROM model_progress WHERE Brand=? AND Model=?',
            (brand, model)
        )
        row = self.cursor.fetchone()
        return row[0] if row else None

    def update_progress(self, brand: str, model: str, count: int):
        self.cursor.execute('''
            INSERT OR REPLACE INTO model_progress (Brand, Model, variant_count, last_scraped)
            VALUES (?, ?, ?, ?)
        ''', (brand, model, count, datetime.now().isoformat()))
        self.conn.commit()

    def export_brand_csv(self, brand: str):
        self.flush()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM view_car_catalog WHERE Brand = ?",
                self.conn, params=(brand,)
            )
            if not df.empty:
                path = os.path.join(Config.CSV_DIR, f"{brand}.csv")
                df.to_csv(path, index=False, encoding='utf-8-sig')
                return len(df)
        except Exception:
            pass
        return 0

    def get_stats(self):
        try:
            df = pd.read_sql_query('''
                SELECT Brand, Fuel_Type, Category,
                       COUNT(DISTINCT Model) as Models,
                       COUNT(*) as Rows
                FROM view_car_catalog
                GROUP BY Brand, Fuel_Type, Category
                ORDER BY Brand, Fuel_Type
            ''', self.conn)
            return df
        except Exception:
            return pd.DataFrame()

    def close(self):
        self.flush()
        self.conn.close()


async def smart_delay(success=True):
    delay = random.uniform(Config.DELAY_MIN, Config.DELAY_MAX) if success else random.uniform(2.5, 4.5)
    if random.random() < 0.12:
        delay += random.uniform(1.0, 2.5)
    await asyncio.sleep(max(0.5, min(delay, 6.0)))


async def dismiss_cookie(page):
    try:
        iframe = page.frame_locator('iframe[id^="sp_message_iframe"]')
        btn = iframe.get_by_role("button", name="Alle akzeptieren")
        await btn.click(timeout=5000)
    except Exception:
        pass


def clean_text(text):
    if not text:
        return "N/A"
    t = re.sub(r'\s+', ' ', text).strip()
    t = t.rstrip(':').strip()
    if not t or t == '-' or t.lower() == 'n/a':
        return "N/A"
    return t


def extract_date_range(text):
    match = re.search(r'(\d{2}/\d{4})\s*[–-]\s*(\d{2}/\d{4})', text)
    if match:
        return f"{match.group(1)} - {match.group(2)}"
    match = re.search(r'seit\s+(\d{2}/\d{4})', text)
    if match:
        return f"seit {match.group(1)}"
    return "N/A"


class AutoBildScraper:
    def __init__(self, test_mode=False, target_brand=None):
        self.test_mode = test_mode
        self.target_brand = target_brand.upper() if target_brand else None
        self.db = DatabaseManager()
        self.start_time = time.time()
        self.api_hsn_tsn = None
        self.api_captured = False

    def is_timeout(self):
        elapsed = (time.time() - self.start_time) / 3600
        return elapsed >= Config.MAX_RUNTIME_HOURS

    async def handle_api_response(self, response):
        try:
            url = response.url.lower()
            if response.status == 200 and ('api' in url or 'graphql' in url or 'json' in url):
                if 'hsn' in url or 'tsn' in url or 'schluessel' in url or 'vehicle' in url:
                    try:
                        data = await response.json()
                        self.api_hsn_tsn = data
                        self.api_captured = True
                    except Exception:
                        pass
        except Exception:
            pass

    async def collect_brand_urls(self, page):
        print("\n🌐 步驟 1：前往總目錄頁收集廠牌...")
        await page.goto(Config.CATALOG_URL, timeout=90000, wait_until="domcontentloaded")
        await dismiss_cookie(page)

        for scroll_y in range(0, 3000, 600):
            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
            await asyncio.sleep(0.5)
        await smart_delay()

        raw_links = await page.evaluate(r'''() => {
            return Array.from(document.querySelectorAll('a[href*="/marken-modelle/"]'))
                .map(a => ({
                    href: a.getAttribute('href'),
                    text: (a.textContent || '').trim()
                }))
                .filter(l => l.href && l.text.length > 0);
        }''')

        brand_urls = []
        seen = set()
        for item in raw_links:
            href = item['href']
            if not href or '/marken-modelle/' not in href:
                continue

            full = urljoin(Config.BASE_URL, href).split('#')[0].split('?')[0]
            full = full.rstrip('/') + '/'

            parts = full.replace(Config.BASE_URL, '').strip('/').split('/')
            if len(parts) == 2 and parts[0] == 'marken-modelle' and parts[1]:
                if full not in seen:
                    seen.add(full)
                    brand_urls.append(full)

        brand_urls.sort(reverse=True)
        if self.target_brand:
            brand_urls = [u for u in brand_urls if f'/{self.target_brand.lower()}/' in u]
        elif self.test_mode:
            brand_urls = brand_urls[:2]

        print(f"   找到 {len(brand_urls)} 個廠牌")
        return brand_urls

    async def collect_model_urls(self, page, brand_url):
        brand_name = brand_url.strip('/').split('/')[-1].upper()
        print(f"\n➔ 進入廠牌: {brand_name}")
        await page.goto(brand_url, timeout=60000, wait_until="domcontentloaded")
        await dismiss_cookie(page)
        await smart_delay()

        await page.evaluate(r'''() => {
            const allEls = Array.from(document.querySelectorAll('a, button, div, span, li, h2, h3'));
            const btn = allEls.find(el => {
                const txt = (el.textContent || '').replace(/\s+/g, '').trim().toUpperCase();
                return txt === 'ALLEMODELLE';
            });
            if (btn) btn.click();
        }''')
        await asyncio.sleep(2.5)

        raw_links = await page.evaluate(r'''() => {
            return Array.from(document.querySelectorAll('a[href*="/marken-modelle/"]'))
                .map(a => a.getAttribute('href'))
                .filter(h => h);
        }''')

        models = []
        seen = set()
        brand_path = brand_url.rstrip('/')
        for href in raw_links:
            full = urljoin(Config.BASE_URL, href).split('#')[0].split('?')[0]
            if full.startswith(brand_path + '/') and full != brand_path + '/':
                segments = full.replace(Config.BASE_URL, '').strip('/').split('/')
                if len(segments) == 3:
                    clean = full.rstrip('/') + '/'
                    if clean not in seen:
                        seen.add(clean)
                        models.append(clean)

        models = list(dict.fromkeys(models))
        if self.test_mode:
            models = models[:2]

        print(f"   找到 {len(models)} 個車系")
        return brand_name, models

    async def expand_all_variants(self, page):
        for _ in range(20):
            clicked = await page.evaluate(r'''() => {
                const btns = document.querySelectorAll('.vv__fuelType-dataFooterToggle');
                for (const btn of btns) {
                    if (btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                }
                return false;
            }''')
            if not clicked:
                break
            await asyncio.sleep(1.5)

    async def extract_page_data(self, page):
        data = await page.evaluate(r'''() => {
            const result = {
                headerTitle: 'N/A',
                headerSubtitle: 'N/A',
                fuelTypes: [],
                variants: [],
                editorialTable: null,
                jsonBuildingPeriod: null,
                jsonBodyType: null
            };

            const titleEl = document.querySelector('.vv__header-text-title');
            if (titleEl) result.headerTitle = titleEl.textContent.trim();

            const subtitleEl = document.querySelector('.vv__header-text-subtitle');
            if (subtitleEl) result.headerSubtitle = subtitleEl.textContent.trim();

            const fuelBadges = document.querySelectorAll('.vv__fuelType > .fuelTypeBadge');
            fuelBadges.forEach(badge => {
                const txt = badge.textContent.trim();
                if (txt) result.fuelTypes.push(txt);
            });

            const fuelSections = document.querySelectorAll('.vv__fuelType');
            fuelSections.forEach(section => {
                const badge = section.querySelector('.fuelTypeBadge');
                const fuelType = badge ? badge.textContent.trim() : 'N/A';

                const rows = section.querySelectorAll('.vv__fuelType-dataBodyLine');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('div');
                    if (cells.length >= 5) {
                        const rawVariant = cells[0].textContent.trim();
                        const match = rawVariant.match(/^(.+?)\s+(\d{2}\/\d{4})\s*[–-]\s*(\d{2}\/\d{4})/);
                        const variantName = match ? match[1].trim() : rawVariant;
                        const dateRange = match
                            ? match[2] + ' - ' + match[3]
                            : (rawVariant.match(/seit\s+\d{2}\/\d{4}/) || [''])[0];

                        result.variants.push({
                            fuelType: fuelType,
                            name: variantName,
                            dateRange: dateRange,
                            power: cells[1] ? cells[1].textContent.trim() : 'N/A',
                            acceleration: cells[2] ? cells[2].textContent.trim() : 'N/A',
                            consumption: cells[3] ? cells[3].textContent.trim() : 'N/A',
                            price: cells[4] ? cells[4].textContent.trim() : 'N/A'
                        });
                    }
                });
            });

            const tables = document.querySelectorAll('.editorialTable__table');
            if (tables.length > 0) {
                const table = tables[0];
                const headers = [];
                table.querySelectorAll('.editorialTable__headerCell').forEach(th => {
                    headers.push(th.textContent.trim());
                });
                const rows = [];
                table.querySelectorAll('.editorialTable__bodyRow').forEach(tr => {
                    const label = tr.querySelector('th.firstColumn, th.editorialTable__bodyCell');
                    const vals = [];
                    tr.querySelectorAll('td.editorialTable__bodyCell').forEach(td => {
                        vals.push(td.textContent.trim());
                    });
                    if (label) {
                        rows.push({
                            label: label.textContent.trim(),
                            values: vals
                        });
                    }
                });
                result.editorialTable = { headers: headers, rows: rows };
            }

            try {
                const ctxEl = document.querySelector('#vike_pageContext');
                if (ctxEl) {
                    const ctx = JSON.parse(ctxEl.textContent);
                    const mg = ctx.irContent && ctx.irContent.modelGeneration;
                    if (mg) {
                        if (mg.buildingPeriod) {
                            const from = mg.buildingPeriod.fromYear || '';
                            const till = mg.buildingPeriod.tillYear || '';
                            result.jsonBuildingPeriod = till
                                ? from + ' - ' + till
                                : 'seit ' + from;
                        }
                        if (mg.constructionTypeImages && mg.constructionTypeImages[0]) {
                            result.jsonBodyType = mg.constructionTypeImages[0].type || null;
                        }
                    }
                }
            } catch(e) {}

            return result;
        }''')
        return data

    async def try_extract_hsn_tsn_from_overlay(self, page, variant_index):
        self.api_hsn_tsn = None
        self.api_captured = False

        try:
            clicked = await page.evaluate(r'''(idx) => {
                const rows = document.querySelectorAll('.vv__fuelType-dataBodyLine');
                if (idx < rows.length) {
                    const link = rows[idx].querySelector('.vv__fuelType-dataBodyLineLink');
                    if (link) {
                        link.click();
                        return true;
                    }
                }
                return false;
            }''', variant_index)

            if not clicked:
                return "N/A"

            await asyncio.sleep(Config.API_WAIT_TIMEOUT)

            if self.api_hsn_tsn:
                hsn = self._find_in_json(self.api_hsn_tsn, ['hsn'])
                tsn = self._find_in_json(self.api_hsn_tsn, ['tsn'])
                if hsn and tsn:
                    return f"{hsn}/{tsn}"
                elif hsn:
                    return hsn

            hsn_from_dom = await page.evaluate(r'''() => {
                const overlay = document.querySelector('.vvp');
                if (!overlay) return null;
                const allText = overlay.innerText || '';
                const match = allText.match(/(\d{4})\s*[\/\-]\s*([A-Z0-9]{2,6})/);
                if (match) return match[1] + '/' + match[2];
                return null;
            }''')

            if hsn_from_dom:
                return hsn_from_dom

            await page.evaluate(r'''() => {
                const btn = document.querySelector('.sectionOverlay__buttonClose');
                if (btn) btn.click();
            }''')
            await asyncio.sleep(1.0)

        except Exception:
            try:
                await page.evaluate(r'''() => {
                    const btn = document.querySelector('.sectionOverlay__buttonClose');
                    if (btn) btn.click();
                }''')
                await asyncio.sleep(0.5)
            except Exception:
                pass

        return "N/A"

    def _find_in_json(self, data, keys, depth=0):
        if depth > 10:
            return None
        if isinstance(data, dict):
            for k, v in data.items():
                if any(key in str(k).lower() for key in keys):
                    if v and str(v).strip() and str(v).strip() != '-':
                        return str(v).strip()
            for v in data.values():
                res = self._find_in_json(v, keys, depth + 1)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = self._find_in_json(item, keys, depth + 1)
                if res:
                    return res
        return None

    def build_records(self, brand, model, page_data, fuel_type_filter=None):
        records = []
        body_type = page_data.get('jsonBodyType') or 'N/A'
        body_map = {
            'fliessheck': '掀背車',
            'limousine': '轎車',
            'suv': '休旅車',
            'cabrio': '敞篷車',
            'coupe': '雙門跑車',
            'kombi': '旅行車',
            'van': '廂型車',
            'geländewagen': '越野車',
            'kleinwagen': '小型車'
        }
        if body_type.lower() in body_map:
            body_type = body_map[body_type.lower()]

        fuel_map = {
            'benzin': '汽油',
            'diesel': '柴油',
            'elektro': '電動',
            'benzin/hybrid': '油電混合',
            'erdgas': '天然氣',
            'autogas': '液化石油氣',
            'plug-in-hybrid': '插電式油電混合',
            'wasserstoff': '氫燃料'
        }

        tech_rows = {}
        if page_data.get('editorialTable'):
            for row in page_data['editorialTable']['rows']:
                label = row['label'].lower()
                tech_rows[label] = row

        for v in page_data.get('variants', []):
            fuel = v.get('fuelType', 'N/A')
            if fuel_type_filter and fuel != fuel_type_filter:
                continue
            fuel_zh = fuel_map.get(fuel.lower(), fuel)

            power = v.get('power', 'N/A')
            if power == 'N/A' and 'leistung' in tech_rows:
                vals = tech_rows['leistung'].get('values', [])
                if vals:
                    power = vals[0] if vals[0] else 'N/A'

            year = page_data.get('jsonBuildingPeriod') or 'N/A'
            if year == 'N/A':
                subtitle = page_data.get('headerSubtitle', '')
                year = extract_date_range(subtitle)

            start_year = 'N/A'
            end_year = 'N/A'
            if year and year != 'N/A':
                parts = re.split(r'\s*[–-]\s*', year.replace('seit ', ''))
                if len(parts) == 2:
                    start_year = parts[0].strip()
                    end_year = parts[1].strip()
                elif len(parts) == 1:
                    start_year = parts[0].strip()
                    end_year = '至今'

            records.append({
                'Brand': brand,
                'Model': model,
                'Category': body_type,
                'Fuel_Type': fuel_zh,
                'Typ': v.get('name', 'N/A'),
                'Start_Year': start_year,
                'End_Year': end_year,
                'HSN_TSN': 'N/A',
                'Power': power
            })

        return records

    async def process_model(self, page, brand, model_url):
        model_name = model_url.strip('/').split('/')[-1].replace('-', ' ').title()
        base_brand = brand

        if self.is_timeout():
            print(f"\n⏰ 超時保護觸發（已超過 {Config.MAX_RUNTIME_HOURS} 小時），安全暫停...")
            return False

        await page.goto(model_url, timeout=60000, wait_until="domcontentloaded")
        await dismiss_cookie(page)

        for scroll_y in range(0, 2000, 400):
            await page.evaluate(f"window.scrollTo(0, {scroll_y})")
            await asyncio.sleep(0.3)
        await asyncio.sleep(1.0)

        has_variants = await page.evaluate(r'''() => {
            return document.querySelectorAll('.vv__fuelType-dataBodyLine').length > 0;
        }''')

        if not has_variants:
            page_data = await self.extract_page_data(page)
            records = self.build_records(base_brand, model_name, page_data)
            if records:
                saved = self.db.get_progress(base_brand, model_name)
                if saved is not None and saved == len(records) and not self.test_mode:
                    print(f"  ⏭️ [{model_name}] 跳過 (已知 {saved} 筆)")
                    return True

                for r in records:
                    self.db.add_to_batch(r)
                self.db.update_progress(base_brand, model_name, len(records))
                print(f"  ✓ [{model_name}] 單一規格: {len(records)} 筆")
            return True

        await self.expand_all_variants(page)

        page_data = await self.extract_page_data(page)

        variant_count = len(page_data.get('variants', []))
        saved_count = self.db.get_progress(base_brand, model_name)

        if saved_count is not None and saved_count == variant_count and not self.test_mode:
            print(f"  ⏭️ [{model_name}] 跳過 (已知 {saved_count} 款，目前 {variant_count} 款)")
            return True

        print(f"  ↳ [{base_brand} - {model_name}] {variant_count} 個變體，開始擷取...")

        records = self.build_records(base_brand, model_name, page_data)

        if self.test_mode:
            records = records[:6]

        for i, record in enumerate(records):
            if self.is_timeout():
                print(f"\n⏰ 超時，暫停擷取...")
                break

            sys.stdout.write(
                f"\r      [{i+1}/{len(records)}] {record['Fuel_Type'][:8]} - "
                f"{record['Typ'][:25]}..."
            )
            sys.stdout.flush()

            if record['HSN_TSN'] == 'N/A' and i < 10:
                hsn = await self.try_extract_hsn_tsn_from_overlay(page, i)
                if hsn != 'N/A':
                    record['HSN_TSN'] = hsn

            self.db.add_to_batch(record)

        print()
        self.db.flush()
        self.db.update_progress(base_brand, model_name, variant_count)
        return True

    async def run(self):
        print("\n🚀 ==============================================")
        print("  AutoBild 爬蟲 v11.0 - DOM 結構精準擷取版")
        print(f"  模式: {'測試' if self.test_mode else '完整'}")
        if self.target_brand:
            print(f"  目標品牌: {self.target_brand}")
        print(f"  超時保護: {Config.MAX_RUNTIME_HOURS} 小時")
        print("==============================================\n")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1440, 'height': 900}
            )
            context.on("response", self.handle_api_response)
            page = await context.new_page()

            try:
                brand_urls = await self.collect_brand_urls(page)

                total_brands = len(brand_urls)
                for b_idx, b_url in enumerate(brand_urls):
                    if self.is_timeout():
                        break

                    brand_name, model_urls = await self.collect_model_urls(page, b_url)

                    for m_idx, m_url in enumerate(model_urls):
                        if self.is_timeout():
                            break

                        try:
                            await self.process_model(page, brand_name, m_url)
                        except Exception as e:
                            print(f"    ❌ 車系處理失敗: {e}")

                    csv_count = self.db.export_brand_csv(brand_name)
                    elapsed = (time.time() - self.start_time) / 60
                    print(f"\n   📁 {brand_name} 匯出完成 ({csv_count} 筆) "
                          f"[{b_idx+1}/{total_brands} 廠牌] [{elapsed:.1f} 分鐘]")

            except Exception as e:
                print(f"\n❌ 執行中斷: {e}")
            finally:
                self.db.flush()
                await browser.close()

        self.db.close()

        elapsed = (time.time() - self.start_time) / 60
        print(f"\n🎉 爬蟲任務完成！耗時 {elapsed:.1f} 分鐘")
        print(f"📂 資料庫: {Config.DB_FILE}")
        print(f"📂 CSV 目錄: {Config.CSV_DIR}/")


def show_status():
    if not os.path.exists(Config.DB_FILE):
        print("❌ 資料庫不存在，請先執行爬蟲")
        return
    conn = sqlite3.connect(Config.DB_FILE)
    try:
        df = pd.read_sql_query('''
            SELECT Brand, Fuel_Type, Category,
                   COUNT(DISTINCT Model) as Models,
                   COUNT(*) as Rows
            FROM view_car_catalog
            GROUP BY Brand, Fuel_Type, Category
            ORDER BY Brand, Fuel_Type
        ''', conn)
        if df.empty:
            print("📭 資料庫是空的")
        else:
            print("\n📊 資料庫統計：")
            display(df)
            total = pd.read_sql_query("SELECT COUNT(*) as Total FROM view_car_catalog", conn)
            print(f"\n  總筆數: {total.iloc[0]['Total']}")
    except Exception as e:
        print(f"❌ 讀取失敗: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AutoBild 爬蟲 v11.0")
    parser.add_argument("--test", action="store_true", help="測試模式")
    parser.add_argument("--reset", action="store_true", help="重置資料庫")
    parser.add_argument("--status", action="store_true", help="查看統計")
    parser.add_argument("--brand", type=str, default=None, help="只抓特定品牌")
    args = parser.parse_args()

    if args.reset:
        if os.path.exists(Config.DB_FILE):
            os.remove(Config.DB_FILE)
        print("✅ 資料庫已重置！")
        sys.exit(0)

    if args.status:
        show_status()
        sys.exit(0)

    scraper = AutoBildScraper(test_mode=args.test, target_brand=args.brand)
    asyncio.run(scraper.run())
