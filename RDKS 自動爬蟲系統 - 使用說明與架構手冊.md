🚗 RDKS 自動爬蟲系統 - 運作流程圖 (V7 終極版)

本流程圖展示了 V7 版本的核心架構，包含：「雙重 API 深度抓取」、「6 小時超時防護」、「斷點無縫接關」以及「SQL View 自動聚合合併」機制。

flowchart TD
    %% 自定義顏色與樣式
    classDef startEnd fill:#ff5252,stroke:#333,stroke-width:2px,color:#fff,font-weight:bold;
    classDef loop fill:#e1f5fe,stroke:#0288d1,stroke-width:2px,color:#000,font-weight:bold;
    classDef check fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,color:#000;
    classDef api fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#000,font-weight:bold;
    classDef db fill:#ede7f6,stroke:#7b1fa2,stroke-width:2px,color:#000;
    classDef process fill:#f5f5f5,stroke:#9e9e9e,stroke-width:2px,color:#000;

    Start(["🚀 啟動爬蟲"]) ::: startEnd --> LoadProg["讀取上次進度<br>(scrape_progress.json)"] ::: process
    
    LoadProg --> Check7Days{"是否超過 7 天?"} ::: check
    Check7Days -- "是" --> FullMode["🧹 全面掃描模式<br>清除進度與資料庫"] ::: process
    Check7Days -- "否" --> ResumeMode["⏭️ 繼續進度模式<br>讀取斷點接關"] ::: process
    
    FullMode & ResumeMode --> SetupDB[("建立/連接 SQLite<br>tpms_sensors")] ::: db
    SetupDB --> InitView[("建立 SQL View 視圖<br>設定聚合與串接邏輯")] ::: db
    
    InitView --> BrandLoop(("🚗 遍歷所有品牌 Brand")) ::: loop
    
    BrandLoop --> CheckSkipBrand{"品牌需跳過?"} ::: check
    CheckSkipBrand -- "是" --> BrandLoop
    CheckSkipBrand -- "否" --> SaveBrandProg["儲存品牌進度"] ::: process
    
    SaveBrandProg --> ClassLoop(("🚙 遍歷車系 Model")) ::: loop
    ClassLoop --> TGLoop(("🏎️ 遍歷型號 Typ")) ::: loop
    
    TGLoop --> VersionLoop(("📅 遍歷年份版本")) ::: loop
    VersionLoop --> CheckTimeout{"執行超時 5.8 小時?"} ::: check
    
    CheckTimeout -- "是" --> Timeout["⏱️ 觸發安全暫停"] ::: startEnd
    CheckTimeout -- "否" --> SafeAPI["🌐 API 1: 取得基礎 TPMS<br>與車輛 HSN/TSN"] ::: api
    
    SafeAPI --> CheckOE{"有 OE 原廠感測器?"} ::: check
    CheckOE -- "無" --> EmptyData["寫入空值保留車型"] ::: process --> AddBatch
    CheckOE -- "有" --> DeepAPI["🌐 API 2: gpsr/data<br>批次取得感測器深度資訊"] ::: api
    
    DeepAPI --> ExtractData["⚙️ 解析 Baujahr, Frequenz<br>(正則表達式強制挖字)"] ::: process
    ExtractData --> AddBatch["加入 batch_data 暫存區"] ::: process
    
    AddBatch --> BatchCheck{"暫存 >= 80 筆?"} ::: check
    BatchCheck -- "是" --> SaveDB[("💾 寫入 tpms_sensors<br>REPLACE INTO 去重覆寫")] ::: db
    SaveDB --> ClearBatch["清空暫存區"] ::: process --> VersionLoop
    BatchCheck -- "否" --> VersionLoop
    
    VersionLoop -- "車型結束" --> TGLoop
    TGLoop -- "車系結束" --> FlushRemain[("💾 強制寫入殘留暫存資料")] ::: db
    FlushRemain --> ClassLoop
    
    ClassLoop -- "品牌結束" --> ExportExcel["📊 查詢 SQL View 匯出 Excel<br>(自動壓縮、合併跨年份)"] ::: process
    ExportExcel --> BrandLoop
    
    BrandLoop -- "全部品牌完成" --> Finish["🎊 清除進度標記任務完成"] ::: process
    Timeout --> ExportSQL[("備份 .sql 檔案")] ::: db
    Finish --> ExportSQL
    ExportSQL --> End(["🏁 程式安全結束"]) ::: startEnd
