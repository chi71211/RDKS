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
