🚗 RDKS 自動爬蟲系統 - 使用說明與架構手冊 (V7 版本)

本系統專為自動化抓取、彙整汽車胎壓感測器（TPMS）資料所設計，具備「智慧斷點接關」、「七天週期自動重置」、「新舊世代資料自動覆寫」以及 「極致空間壓縮 (SQL View)」 等企業級防護與整理機制。

壹、 系統四大核心機制

🕖 7 天週期巡邏機制 (7-Day Cycle)

程式啟動時會檢查上次「全面重抓」是什麼時候。

超過 7 天：自動清空所有記憶與舊資料庫，啟動大掃除，從第一筆開始全面更新。

7 天以內：啟動「繼續進度模式」，只針對上次沒抓完的部分繼續努力。

⏭️ 智能防重複與極致壓縮 (Smart Aggregation & SQL View)

底層儲存 (Raw Data)： SQLite 資料庫中的 tpms_sensors 表格會以 Brand, Model, Typ, Start Year, End Year, HSN, TSN, OE sensor, created date 為唯一鍵值 (Unique Key)。只要有任何一點不同（例如同年份但有兩種不同的 OE Sensor），就會被分開儲存，確保資料不遺失任何細節。

展示層壓縮 (SQL View)： 這是 V7 版本的最大亮點！我們建立了一個名為 view_tpms_sensors_unique1 的視圖。當匯出 Excel 時，程式只會看 Brand (品牌), Model (車系), Typ (型號) 這三個欄位。

只要這三個欄位一樣，系統就會強制把它們擠成同一行！

年份會自動抓出 MIN (最早) 到 MAX (最晚)。

而 OE Sensor, HSN, TSN, Frequency 等細節，如果有多種，系統會自動使用逗號 (,) 串接起來。這大幅減少了 Excel 的行數，讓閱讀更加直觀。

🕵️ 深度抓取隱藏日期 (Deep Detail Fetching)

為了克服原本 API 缺少精確 Baujahr (建設日期) 的問題，V7 系統會自動解析感測器 ID，並偷偷去呼叫另一個 /api/gpsr/data (詳細資訊 API)。

如果 API 回傳不佳，系統還會啟動 「正則表達式 (Regex) 掃描器」，直接在整包資料中硬撈出類似 07/2022 - 這種德國日期格式，確保 created date 的極致準確性。

⏱️ GitHub Actions 防斷線保鑣 (Timeout Protection)

GitHub Actions 的虛擬機最多只能活 6 小時。

程式內建了計時器，當執行時間來到 5.8 小時 時，會主動停止迴圈，觸發安全暫停並存檔。確保不會因為突然被 GitHub 殺掉而導致資料庫損壞或進度遺失。

貳、 日常操作與使用指南

1. 產出檔案在哪裡？

系統執行完畢後，您會在腳本旁邊看到以下檔案與資料夾：

📁 胎壓檢測器資料庫_V7/ (資料夾)：存放所有抓取完畢並經過 SQL View 極致壓縮的 Excel 報表。

🗄️ 胎壓檢測器資料庫_V7.db：系統的 SQLite 記憶資料庫。

📝 胎壓檢測器資料庫_V7.sql：資料庫的純文字備份檔。

⚙️ scrape_progress_V7.json：系統的「進度記憶卡」。

2. 常見問題與疑難排解

Q: 我懷疑資料有缺，想要程式「從頭到尾徹底重抓」該怎麼做？

A: 請手動將資料夾內的 胎壓檢測器資料庫_V7.db 與 scrape_progress_V7.json 這兩個檔案刪除。下次啟動時，系統就會因為「失去記憶」而啟動全面檢查模式，從第一台車開始重新收集。


# RDKS 自動爬蟲系統 - 完整運作流程圖

```mermaid
flowchart TD
    Start([啟動爬蟲]) 
    --> LoadProg[讀取 scrape_progress.json]
    
    LoadProg 
    --> Check7Days{距離上次全面掃描<br>是否超過 7 天?}
    
    Check7Days -- 是 --> FullMode[全面掃描模式<br>保留歷史資料]
    Check7Days -- 否 --> ResumeMode[繼續模式<br>讀取斷點]
    
    FullMode & ResumeMode 
    --> SetupDB[建立/檢查 SQLite 資料表]
    
    SetupDB 
    --> InitBatch[初始化 batch_data]
    
    InitBatch 
    --> BrandLoop[遍歷所有品牌]
    
    BrandLoop 
    --> CheckSkipBrand{是否在跳過模式?}
    
    CheckSkipBrand -- 是 --> SkipBrand[跳過此品牌] 
    SkipBrand --> BrandLoop
    
    CheckSkipBrand -- 否 --> SaveBrandProg[儲存品牌進度]
    SaveBrandProg --> ClassLoop[遍歷車系]
    
    ClassLoop 
    --> CheckSkipClass{是否在跳過模式?}
    
    CheckSkipClass -- 是 --> SkipClass[跳過此車系] 
    SkipClass --> ClassLoop
    
    CheckSkipClass -- 否 --> TGLoop[遍歷 Type Group]
    
    TGLoop 
    --> SaveTGProg[儲存 TG 進度]
    SaveTGProg 
    --> VersionLoop[版本迴圈<br>新→舊排序]
    
    VersionLoop 
    --> RandomSleep[隨機延遲 0.65~1.35 秒]
    
    RandomSleep 
    --> SafeAPI[safe_json_get<br>取得車輛與 TPMS 資料]
    
    SafeAPI 
    --> Parse[解析感測器資料<br>find_key_value]
    
    Parse 
    --> AddToBatch[加入 batch_data]
    
    AddToBatch 
    --> CheckBatchSize{batch_data >= 80 筆?}
    
    CheckBatchSize -- 是 --> SaveDB[save_batch_to_sql<br>Pandas聚合 + REPLACE]
    SaveDB --> ClearBatch[清除 batch_data]
    ClearBatch --> VersionLoop
    
    CheckBatchSize -- 否 --> VersionLoop
    
    VersionLoop -- 車系結束 --> FinalFlush{還有殘留資料?}
    FinalFlush -- 是 --> SaveResidual[強制存檔清理]
    SaveResidual --> ClassLoop
    FinalFlush -- 否 --> ClassLoop
    
    ClassLoop -- 品牌結束 --> ExportExcel[匯出該品牌 Excel]
    ExportExcel --> BrandLoop
    
    BrandLoop -- 全部完成 --> Finalize[標記完成<br>清除進度]
    Finalize --> ExportSQL[產出 SQL 備份]
    ExportSQL --> End([程式結束])
