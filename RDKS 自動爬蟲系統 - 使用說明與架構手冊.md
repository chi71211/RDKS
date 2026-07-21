🚗 RDKS 自動爬蟲系統 - 運作流程圖 (V7 終極版)

本流程圖展示了 V7 版本的核心架構，包含：「雙重 API 深度抓取」、「6 小時超時防護」、「斷點無縫接關」以及「SQL View 自動聚合合併」機制。

```mermaid

    Start((啟動爬蟲)) ::: startEnd --> LoadProg[讀取上次進度 scrape_progress] ::: process
    
    LoadProg --> Check7Days{是否超過 7 天?} ::: check
    Check7Days -- 是 --> FullMode[全面掃描模式 - 清除進度與資料庫] ::: process
    Check7Days -- 否 --> ResumeMode[繼續進度模式 - 讀取斷點接關] ::: process
    
    FullMode & ResumeMode --> SetupDB[(建立/連接 SQLite tpms_sensors)] ::: db
    SetupDB --> InitView[(建立 SQL View 視圖 - 設定聚合邏輯)] ::: db
    
    InitView --> BrandLoop(遍歷所有品牌 Brand) ::: loop
    
    BrandLoop --> CheckSkipBrand{品牌需跳過?} ::: check
    CheckSkipBrand -- 是 --> BrandLoop
    CheckSkipBrand -- 否 --> SaveBrandProg[儲存品牌進度] ::: process
    
    SaveBrandProg --> ClassLoop(遍歷車系 Model) ::: loop
    ClassLoop --> TGLoop(遍歷型號 Typ) ::: loop
    
    TGLoop --> VersionLoop(遍歷年份版本) ::: loop
    VersionLoop --> CheckTimeout{執行超時 5.8 小時?} ::: check
    
    CheckTimeout -- 是 --> Timeout((觸發安全暫停)) ::: startEnd
    CheckTimeout -- 否 --> SafeAPI[API 1: 取得基礎 TPMS 與車輛 HSN/TSN] ::: api
    
    SafeAPI --> CheckOE{有 OE 原廠感測器?} ::: check
    CheckOE -- 無 --> EmptyData[寫入空值保留車型] ::: process --> AddBatch
    CheckOE -- 有 --> DeepAPI[API 2: gpsr/data 批次取得感測器深度資訊] ::: api
    
    DeepAPI --> ExtractData[解析 Baujahr, Frequenz - 正則表達式強制挖字] ::: process
    ExtractData --> AddBatch[加入 batch_data 暫存區] ::: process
    
    AddBatch --> BatchCheck{暫存超過 80 筆?} ::: check
    BatchCheck -- 是 --> SaveDB[(寫入 tpms_sensors - REPLACE INTO)] ::: db
    SaveDB --> ClearBatch[清空暫存區] ::: process --> VersionLoop
    BatchCheck -- 否 --> VersionLoop
    
    VersionLoop -- 車型結束 --> TGLoop
    TGLoop -- 車系結束 --> FlushRemain[(強制寫入殘留暫存資料)] ::: db
    FlushRemain --> ClassLoop
    
    ClassLoop -- 品牌結束 --> ExportExcel[查詢 SQL View 匯出 Excel] ::: process
    ExportExcel --> BrandLoop
    
    BrandLoop -- 全部品牌完成 --> Finish[清除進度標記任務完成] ::: process
    Timeout --> ExportSQL[(備份 .sql 檔案)] ::: db
    Finish --> ExportSQL
    ExportSQL --> End((程式安全結束)) ::: startEnd
