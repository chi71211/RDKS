🚗 RDKS 自動爬蟲系統 - 使用說明與架構手冊

本系統專為自動化抓取、彙整汽車胎壓感測器（TPMS）資料所設計，具備「智慧斷點接關」、「七天週期自動重置」以及「新舊世代資料自動覆寫」等企業級防護機制。

壹、 日常操作與使用指南

1. 如何啟動爬蟲？

本系統已設定為「一鍵執行」。您不需要開啟任何程式碼編輯器。

Mac 用戶： 在桌面上找到 開始抓取資料.command 檔案，連續點擊兩下即可自動開啟終端機並開始抓取。

執行過程中，請勿關閉黑色的終端機視窗。程式完成後會顯示「🎉 爬蟲任務結束！您可以關閉此視窗了」。

2. 產出檔案在哪裡？

系統執行完畢後，您會在腳本旁邊看到以下檔案與資料夾：

📁 RDKS/ (資料夾)：存放所有抓取完畢的 Excel 報表（依照品牌命名，例如 BMW_Data.xlsx）。裡面的排版已經自動合併相同型號與 HSN/TSN 的車款。

🗄️ RDKS.db：系統的 SQLite 記憶資料庫，請勿隨意刪除（除非想強制重新抓取）。

📝 RDKS_Backup.sql：資料庫的純文字備份檔。

⚙️ scrape_progress.json：系統的「進度記憶卡」，記錄上次抓到哪個品牌。

3. 常見問題與疑難排解

Q: 程式跑到一半不小心關掉了怎麼辦？

A: 不用擔心！直接再次點擊桌面的捷徑重新啟動即可。系統會讀取 scrape_progress.json，瞬間跳過已經抓完的品牌，從斷掉的地方繼續抓取（無縫接關）。

Q: 我懷疑資料有缺，想要程式「從頭到尾徹底重抓」該怎麼做？

A: 請手動將資料夾內的 RDKS.db 與 scrape_progress.json 這兩個檔案刪除。下次啟動時，系統就會因為「失去記憶」而啟動全面檢查模式，從第一台車開始重新收集。

貳、 系統四大核心機制

🕖 7 天週期巡邏機制 (7-Day Cycle)

程式啟動時會檢查上次「全面重抓」是什麼時候。

超過 7 天：自動清空所有記憶與舊資料庫，啟動大掃除，從第一筆開始全面更新。

7 天以內：啟動「繼續進度模式」，只針對上次沒抓完的部分繼續努力。

⏭️ 智能防重複與極速跳過 (Smart Skip)

系統以「品牌 + 車系 + 型號 + 年份起點」作為世代辨識標準。

掃描時，若發現連續 5 個較舊年份的車款都沒有更新，程式會啟動「極速跳過」，直接略過該型號剩餘的舊車，大幅節省時間。

🔄 最新年份強制檢查 (Force Update Latest)

針對每個型號的「最新年份（第一筆資料）」，無論資料庫有沒有記錄，系統都會強制檢查一次。

搭配 REPLACE INTO 語法，如果發現網站補上了胎壓資料，或延長了出廠年份，系統會「無痕覆寫」舊資料，永遠保持最準確狀態。

🧠 多感測器智慧合併排版 (Smart Merge)

當同一款車支援多種 OE 感測器、不同頻率或多家廠商時，系統不會產生多餘的重複列。

程式會在匯出 Excel 前，自動將差異資料使用「逗號 ,」串接於同一儲存格內，保證版面乾淨整潔。

參、 系統運作流程圖 (System Flowchart)

以下為爬蟲系統的底層運作邏輯架構：

flowchart TD
    Start([啟動爬蟲程式]) --> LoadProg[讀取上次執行進度\n(scrape_progress)]
    LoadProg --> Check7Days{距離上次全面掃描\n是否超過 7 天?}
    
    Check7Days -- 是 (超過 7 天) --> FullMode[啟動【全面檢查模式】\n清除資料庫與進度紀錄]
    Check7Days -- 否 (7 天內) --> ResumeMode[啟動【繼續進度模式】\n讀取上次中斷的品牌]
    
    FullMode --> BrandLoop
    ResumeMode --> BrandLoop
    
    BrandLoop[遍歷所有汽車品牌] --> CheckSkip{是否在跳過模式?}
    
    CheckSkip -- 是 (還沒找到中斷點) --> SkipBrand[略過此品牌] --> BrandLoop
    CheckSkip -- 否 (進入處理) --> SaveProg[儲存目前進度\nsave_progress]
    
    SaveProg --> ClassLoop[遍歷該品牌所有車系與型號]
    ClassLoop --> VersionLoop[依年份從新到舊排序版本]
    
    VersionLoop --> CheckIdx{是否為該型號的\n最新年份 (idx=0)?}
    
    CheckIdx -- 是 (最新年份) --> ForceCheck[強制檢查更新\n(streak = 0)] --> ApiCall
    CheckIdx -- 否 (較舊年份) --> CheckDB{此世代是否已存在\n資料庫中?}
    
    CheckDB -- 不存在 --> ApiCall
    CheckDB -- 已存在 --> AddStreak[連續存在計數器 + 1]
    
    AddStreak --> CheckStreak{計數器 >= 5 ?}
    CheckStreak -- 是 --> BreakLoop[觸發極速跳過\n忽略該型號剩餘舊車] --> ClassLoop
    CheckStreak -- 否 --> VersionLoop
    
    ApiCall[執行 API 抓取\n取得 HSN/TSN 與 TPMS] --> ParseData[解析感測器隱藏資訊\n(廠商, 頻率, 日期兜底)]
    ParseData --> AddBatch[加入 batch_data 佇列]
    
    AddBatch --> CheckBatch{累積 >= 100 筆?}
    CheckBatch -- 是 --> SaveDB[(寫入資料庫)\n使用 REPLACE INTO 覆寫更新]
    SaveDB --> VersionLoop
    CheckBatch -- 否 --> VersionLoop
    
    ClassLoop -- 品牌處理完畢 --> ExportExcel[匯出該品牌專屬 Excel 報表]
    ExportExcel --> BrandLoop
    
    BrandLoop -- 所有品牌處理完畢 --> Finalize[清除進度紀錄\n標記任務 100% 完成]
    Finalize --> ExportSQL[匯出最終 SQL 備份檔]
    ExportSQL --> End([程式圓滿結束])


(本文件與爬蟲程式皆已調校至最佳化狀態，適合長期自動化營運使用。)
