# 🚗 RDKS 胎壓感測器自動爬蟲系統 (每週自動更新本機版)

這是一個專為抓取、彙整汽車胎壓感測器（TPMS）資料所設計的全自動化爬蟲系統。此版本專為 **本機環境 (如 VS Code) 手動執行** 所打造，具備強大的環境適應力與中斷保護。

## ✨ 核心特色

1. **極致 SQL View 壓縮**：
   * 透過 SQL 原生的 `GROUP_CONCAT` 視圖，確保 **品牌、車系、型號** 相同的車款只會佔據一行 Excel。
   * 不同的感測器 (OE sensor)、頻率、HSN/TSN 會自動使用 `,` 逗號整齊串接，版面極度乾淨！
2. **深度 API 解析**：
   * 內建雙重 API 抓取。遇到隱藏的日期或頻率時，會自動解析 `gpsr/data` 接口補齊。
3. **無縫斷點接關與優雅中斷 (Graceful Shutdown)**：
   * 隨時可以在 VS Code 按下暫停 (Ctrl+C 或停止鍵)。程式會攔截中斷訊號，將暫存區的殘留資料安全寫入資料庫並匯出備份，達成「零資料遺失」。
   * 下次啟動時，精準從中斷的「車系型號」接續努力，完美銜接零浪費。
4. **七天自動大掃除**：
   * 內建七天週期檢查。只要距離上次完整抓取超過 7 天，按下啟動鍵時系統會自動失去記憶，進入「全面掃描模式」更新所有最新年份資料。（註：需使用者定期手動執行程式觸發此機制）。
5. **智能環境適應 (突破 PEP 668/uv 限制)**：
   * 執行時會自動檢查並安裝缺少的套件 (如 `requests`, `pandas`)。
   * 具備「三重突破機制」，即使在受保護的 Python 環境 (如 `uv` 管理的環境) 也能強制且安全地完成安裝，實現真正的一鍵啟動。

## 📁 檔案產出說明

執行完畢後，所有最新資料會自動儲存於 `胎壓資料庫_每週更新版/` 資料夾內，並依據汽車品牌分類為獨立的 Excel 報表。


# 🚗 RDKS 爬蟲系統運作流程圖 (VS Code 手動執行版)

本流程圖展示了在 VS Code 手動啟動下，系統如何運作，包含環境檢查、週期判斷與中斷保護。

## 詳細完整流程圖

```mermaid
flowchart TD
    Start([在 VS Code 手動點擊 Run 啟動]) --> InstallReq["自動檢查並安裝缺失套件\n包含突破 uv/PEP 668 限制"]
    InstallReq --> LoadProg["讀取 scrape_progress_weekly.json 紀錄"]
    
    LoadProg --> Check7Days{"距離上次「全新掃描」\n是否超過 7 天?"}
    
    Check7Days -- 是 (超過 7 天) --> FullMode["啟動【全面更新模式】\n清除斷點紀錄，準備從頭掃描"]
    Check7Days -- 否 (7 天內) --> ResumeMode["啟動【繼續進度模式】\n讀取上次中斷的品牌/車系斷點"]
    
    FullMode --> SetupDB[("建立/連接 SQLite 資料庫")]
    ResumeMode --> SetupDB
    
    SetupDB --> InitView[("建立 SQL View 視圖\n設定自動壓縮與合併邏輯")]
    
    InitView --> BrandLoop["遍歷所有汽車品牌 Brand"]
    
    BrandLoop --> CheckSkip{"品牌是否需要略過?\n(因還沒到達斷點)"}
    CheckSkip -- 是 --> SkipBrand["跳過此品牌"] --> BrandLoop
    CheckSkip -- 否 --> SaveProg["儲存目前進度 (更新 JSON)"]
    
    SaveProg --> ClassLoop["遍歷該品牌所有車系 Model"]
    ClassLoop --> TGLoop["遍歷型號 Typ"]
    
    TGLoop --> VersionLoop["依年份從新到舊排序版本"]
    
    VersionLoop --> CheckManualStop{"使用者是否按下\nCtrl+C 或 停止鍵?"}
    
    CheckManualStop -- 是 --> GracefulStop(["觸發安全中斷訊號"])
    CheckManualStop -- 否 --> ApiCall1["呼叫 API 1: 取得基礎 TPMS 與 HSN/TSN"]
    
    ApiCall1 --> CheckOE{"是否有 OE 原廠感測器?"}
    CheckOE -- 無 --> EmptyData["寫入空值保留車型"] --> AddBatch
    CheckOE -- 有 --> ApiCall2["呼叫 API 2: 批次取得感測器深度資訊"]
    
    ApiCall2 --> ParseData["解析感測器資訊 - 廠商, 頻率, 建造日期"]
    ParseData --> AddBatch["加入暫存佇列 batch_data"]
    
    AddBatch --> CheckBatch{"暫存累積超過 80 筆?"}
    CheckBatch -- 是 --> SaveDB[("寫入資料庫: 使用 REPLACE INTO 去重覆寫")]
    SaveDB --> ClearBatch["清空暫存區"] --> VersionLoop
    CheckBatch -- 否 --> VersionLoop
    
    VersionLoop -- 版本處理完畢 --> TGLoop
    TGLoop -- 型號處理完畢 --> FlushRemain[("強制寫入殘留暫存資料")]
    FlushRemain --> ClassLoop
    
    ClassLoop -- 車系處理完畢 --> ExportExcel["查詢 SQL View 匯出 Excel 壓縮報表"]
    ExportExcel --> BrandLoop
    
    BrandLoop -- 所有品牌處理完畢 --> Finalize["清除斷點紀錄，標記本輪任務完成"]
    GracefulStop --> ExportSQL[("匯出 .sql 備份檔")]
    Finalize --> ExportSQL
    ExportSQL --> End(["程式安全結束"])
