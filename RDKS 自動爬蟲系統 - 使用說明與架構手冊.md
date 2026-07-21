```markdown:RDKS_User_Manual_V10.md
# 🚗 RDKS 自動爬蟲系統 - 使用說明與架構手冊 (V10 版本)

本系統專為自動化抓取、彙整汽車胎壓感測器（TPMS）資料所設計，具備「智慧斷點接關」、「七天週期自動重置」、「新舊世代資料自動覆寫」以及 **「極致空間壓縮 (SQL View)」** 等企業級防護與整理機制。

## 壹、 系統四大核心機制

1. **🕖 7 天週期巡邏機制 (7-Day Cycle)**

   * 程式啟動時會檢查上次「全面重抓」是什麼時候。

   * **超過 7 天**：自動清空所有記憶與舊資料庫，啟動大掃除，從第一筆開始全面更新。

   * **7 天以內**：啟動「繼續進度模式」，只針對上次沒抓完的部分繼續努力。

2. **⏭️ 智能防重複與極致壓縮 (Smart Aggregation & SQL View)**

   * **底層儲存 (Raw Data)：** SQLite 資料庫中的 `tpms_sensors` 表格會以 `Brand, Model, Typ, Start Year, End Year, HSN, TSN, OE sensor, created date` 為唯一鍵值 (Unique Key)。只要有任何一點不同，就會被分開儲存，確保資料**不遺失任何細節**。

   * **展示層壓縮 (SQL View)：** 這是 V10 版本的最大亮點！我們建立了一個名為 `view_tpms_sensors_unique1` 的視圖。當匯出 Excel 時，程式只會看 `Brand` (品牌), `Model` (車系), `Typ` (型號) 這三個欄位。

     * **只要這三個欄位一樣，系統就會強制把它們擠成同一行！**

     * 年份會自動抓出 `MIN` (最早) 到 `MAX` (最晚)。

     * 而 `OE Sensor`, `HSN`, `TSN`, `Frequency` 等細節，如果有多種，系統會自動使用**逗號 (,) 串接起來**。這大幅減少了 Excel 的行數，讓閱讀更加直觀。

3. **🕵️ 深度抓取隱藏日期 (Deep Detail Fetching)**

   * 為了克服原本 API 缺少精確 `Baujahr` (建設日期) 的問題，V10 系統會自動解析感測器 ID，並偷偷去呼叫另一個 `/api/gpsr/data` (詳細資訊 API)。

   * 如果 API 回傳不佳，系統還會啟動 **「正則表達式 (Regex) 掃描器」**，直接在整包資料中硬撈出類似 `07/2022 -` 這種德國日期格式，確保 `created date` 的極致準確性。

4. **⏱️ GitHub Actions 防斷線保鑣 (Timeout Protection)**

   * GitHub Actions 的虛擬機最多只能活 6 小時。

   * 程式內建了計時器，當執行時間來到 **5.8 小時** 時，會主動停止迴圈，觸發安全暫停並存檔。確保不會因為突然被 GitHub 殺掉而導致資料庫損壞或進度遺失。

## 貳、 日常操作與使用指南

### 1. 產出檔案在哪裡？

系統執行完畢後，您會在腳本旁邊看到以下檔案與資料夾：

* 📁 **`胎壓檢測器資料庫_V10/` (資料夾)**：存放所有抓取完畢並經過 SQL View 極致壓縮的 Excel 報表。

* 🗄️ **`胎壓檢測器資料庫_V10.db`**：系統的 SQLite 記憶資料庫。

* 📝 **`胎壓檢測器資料庫_V10.sql`**：資料庫的純文字備份檔。

* ⚙️ **`scrape_progress_V10.json`**：系統的「進度記憶卡」。

### 2. 常見問題與疑難排解

* **Q: 我懷疑資料有缺，想要程式「從頭到尾徹底重抓」該怎麼做？**

  * **A:** 請手動將資料夾內的 `胎壓檢測器資料庫_V10.db` 與 `scrape_progress_V10.json` 這兩個檔案**刪除**。下次啟動時，系統就會因為「失去記憶」而啟動全面檢查模式，從第一台車開始重新收集。

本流程圖展示了 V10 版本的核心架構，包含：「雙重 API 深度抓取」、「6 小時超時防護」、「斷點無縫接關」以及「SQL View 自動聚合合併」機制。

# 🚗 RDKS 自動爬蟲系統 - 運作流程圖 (V10 終極版)

本流程圖展示了 V10 版本的核心架構，包含：「雙重 API 深度抓取」、「6 小時超時防護」、「斷點無縫接關」以及「SQL View 自動聚合合併」機制。

```mermaid
flowchart TD
    Start([啟動爬蟲程式]) --> LoadProg[讀取上次執行進度]
    
    LoadProg --> Check7Days{距離上次全面掃描是否超過 7 天?}
    
    Check7Days -- 是 --> FullMode[啟動全面檢查模式 - 清除資料庫與進度紀錄]
    Check7Days -- 否 --> ResumeMode[啟動繼續進度模式 - 讀取上次中斷的品牌]
    
    FullMode --> SetupDB[(建立/連接 SQLite tpms_sensors 資料表)]
    ResumeMode --> SetupDB
    
    SetupDB --> InitView[(建立 SQL View 視圖 - 設定自動合併邏輯)]
    
    InitView --> BrandLoop[遍歷所有汽車品牌 Brand]
    
    BrandLoop --> CheckSkip{品牌是否需跳過?}
    CheckSkip -- 是 --> SkipBrand[略過此品牌] --> BrandLoop
    CheckSkip -- 否 --> SaveProg[儲存目前進度]
    
    SaveProg --> ClassLoop[遍歷該品牌所有車系 Model]
    ClassLoop --> TGLoop[遍歷型號 Typ]
    
    TGLoop --> VersionLoop[依年份從新到舊排序版本]
    
    VersionLoop --> CheckTimeout{執行時間是否超時 5.8 小時?}
    
    CheckTimeout -- 是 --> Timeout([觸發安全暫停])
    CheckTimeout -- 否 --> ApiCall1[呼叫 API 1: 取得基礎 TPMS 與車輛 HSN/TSN]
    
    ApiCall1 --> CheckOE{是否有 OE 原廠感測器?}
    CheckOE -- 無 --> EmptyData[寫入空值保留車型] --> AddBatch
    CheckOE -- 有 --> ApiCall2[呼叫 API 2: 批次取得感測器深度資訊]
    
    ApiCall2 --> ParseData[解析感測器資訊 - 廠商, 頻率, 建造日期 Baujahr]
    ParseData --> AddBatch[加入暫存佇列 batch_data]
    
    AddBatch --> CheckBatch{累積超過 80 筆?}
    CheckBatch -- 是 --> SaveDB[(寫入資料庫使用 REPLACE INTO 覆寫)]
    SaveDB --> ClearBatch[清空暫存區] --> VersionLoop
    CheckBatch -- 否 --> VersionLoop
    
    VersionLoop -- 版本處理完畢 --> TGLoop
    TGLoop -- 型號處理完畢 --> FlushRemain[(強制寫入殘留暫存資料)]
    FlushRemain --> ClassLoop
    
    ClassLoop -- 車系處理完畢 --> ExportExcel[查詢 SQL View 匯出 Excel 報表]
    ExportExcel --> BrandLoop
    
    BrandLoop -- 所有品牌處理完畢 --> Finalize[清除進度紀錄標記任務完成]
    Timeout --> ExportSQL[(匯出 .sql 備份檔)]
    Finalize --> ExportSQL
    ExportSQL --> End([程式安全結束])
