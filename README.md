# 🚗 RDKS 胎壓感測器自動爬蟲系統 (V10 終極版)

這是一個專為抓取、彙整汽車胎壓感測器（TPMS）資料所設計的全自動化爬蟲系統，已完美部署於 GitHub Actions。

## ✨ V10 核心特色

1. **極致 SQL View 壓縮**：
   * 透過 SQL 原生的 `GROUP_CONCAT` 視圖，確保 **品牌、車系、型號** 相同的車款只會佔據一行 Excel。
   * 不同的感測器 (OE sensor)、頻率、HSN/TSN 會自動使用 `,` 逗號整齊串接，版面極度乾淨！
2. **深度 API 解析**：
   * 內建雙重 API 抓取。遇到隱藏的日期或頻率時，會自動解析 `gpsr/data` 接口補齊。
3. **無縫斷點接關**：
   * GitHub Actions 會在快滿 6 小時限制前（約 5.8 小時）主動觸發「安全暫停」。
   * 下次啟動時，精準從中斷的「車系型號」接續努力，完美銜接零浪費。
4. **七天自動大掃除**：
   * 超過 7 天未重啟，系統會自動失去記憶，進入「全面掃描模式」更新所有最新年份資料。


# 🚗 RDKS 爬蟲系統運作流程圖 (V10 終極版)

本流程圖展示了 V10 版本的核心架構（為確保在 GitHub 上完美渲染，已採用標準純淨語法）。

```mermaid
flowchart TD
    Start([啟動爬蟲程式]) --> LoadProg[讀取上次執行進度]
    
    LoadProg --> Check7Days{距離上次全面掃描是否超過 7 天?}
    
    Check7Days -- 是 --> FullMode[啟動全面檢查模式 - 清除資料庫與進度紀錄]
    Check7Days -- 否 --> ResumeMode[啟動繼續進度模式 - 讀取上次中斷的品牌]
    
    FullMode --> SetupDB[(建立 SQLite tpms_sensors 資料表)]
    ResumeMode --> SetupDB
    
    SetupDB --> InitView[(建立 SQL View 視圖 - 設定自動壓縮與合併邏輯)]
    
    InitView --> BrandLoop[遍歷所有汽車品牌 Brand]
    
    BrandLoop --> CheckSkip{品牌是否需跳過?}
    CheckSkip -- 是 --> SkipBrand[略過此品牌] --> BrandLoop
    CheckSkip -- 否 --> SaveProg[儲存目前品牌進度]
    
    SaveProg --> ClassLoop[遍歷該品牌所有車系 Model]
    ClassLoop --> TGLoop[遍歷型號 Typ]
    
    TGLoop --> VersionLoop[依年份從新到舊排序版本]
    
    VersionLoop --> CheckTimeout{執行時間是否超時 5.8 小時?}
    
    CheckTimeout -- 是 --> Timeout([觸發安全暫停])
    CheckTimeout -- 否 --> ApiCall1[呼叫 API 1: 取得基礎 TPMS 與車輛 HSN/TSN]
    
    ApiCall1 --> CheckOE{是否有 OE 原廠感測器?}
    CheckOE -- 無 --> EmptyData[寫入空值保留車型] --> AddBatch
    CheckOE -- 有 --> ApiCall2[呼叫 API 2: 批次取得感測器深度資訊]
    
    ApiCall2 --> ParseData[解析感測器資訊 - 廠商, 頻率, 建造日期]
    ParseData --> AddBatch[加入暫存佇列 batch_data]
    
    AddBatch --> CheckBatch{累積超過 80 筆?}
    CheckBatch -- 是 --> SaveDB[(寫入資料庫使用 REPLACE INTO 去重覆寫)]
    SaveDB --> ClearBatch[清空暫存區] --> VersionLoop
    CheckBatch -- 否 --> VersionLoop
    
    VersionLoop -- 版本處理完畢 --> TGLoop
    TGLoop -- 型號處理完畢 --> FlushRemain[(強制寫入殘留暫存資料)]
    FlushRemain --> ClassLoop
    
    ClassLoop -- 車系處理完畢 --> ExportExcel[查詢 SQL View 匯出 Excel 壓縮報表]
    ExportExcel --> BrandLoop
    
    BrandLoop -- 所有品牌處理完畢 --> Finalize[清除進度紀錄標記任務完成]
    Timeout --> ExportSQL[(匯出 .sql 備份檔)]
    Finalize --> ExportSQL
    ExportSQL --> End([程式安全結束])
