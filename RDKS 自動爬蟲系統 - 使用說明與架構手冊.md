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



## 詳細完整流程圖

# 🚗 RDKS 爬蟲系統核心架構圖 (Pro 專業版)

本版本致敬高階系統架構圖風格，採用暗色模組劃分、全彩狀態標示，並完整收錄 7 天週期、API 雙軌抓取與優雅中斷防護的所有底層邏輯。

```mermaid
flowchart LR

    %% ==========================================
    %% 視覺樣式定義 (致敬參考圖配色)
    %% ==========================================
    classDef startEnd fill:#fff,stroke:#333,stroke-width:2px,color:#000,font-weight:bold;
    classDef diamond fill:#fff,stroke:#555,stroke-width:2px,color:#000,font-weight:bold;
    classDef greenBox fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20,font-weight:bold;
    classDef redBox fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c,font-weight:bold;
    classDef actionBox fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1,font-weight:bold;
    classDef dbBox fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100,font-weight:bold;
    classDef warningBox fill:#fff8e1,stroke:#fbc02d,stroke-width:2px,color:#f57f17,font-weight:bold;

    %% ==========================================
    %% ① 啟動前進度檢查
    %% ==========================================
    subgraph SG1 ["① 啟動前進度檢查"]
        direction TB
        S1([系統啟動]) --> S2["自動檢查/安裝缺失套件\n(突破環境限制)"]
        S2 --> S3{"讀取\nscrape_progress.json"}
        S3 --> S4{"距離上次掃描\n< 7 天?"}
        
        S4 -- 否 (>7天) --> S5["全新週期\n清空舊斷點紀錄\n開始全新掃描"]
        S4 -- 是 (<7天) --> S6["接續執行\n載入中斷之品牌\n(last_brand)"]
    end
    style SG1 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% ② 資料庫與導航
    %% ==========================================
    subgraph SG2 ["② 資料庫與爬蟲導航"]
        direction TB
        D1[("建立 SQLite 與表單\n建立 SQL View 視圖")]
        D2{"遍歷 品牌 (Brand)\n是否需略過?"}
        D3["跳過此品牌"]
        D4["儲存進度 (JSON)"]
        D5["遍歷車系 (Model)\n遍歷型號 (Typ)\n遍歷年份 (Year)"]

        D1 --> D2
        D2 -- 是 (未達斷點) --> D3 --> D2
        D2 -- 否 (進入斷點) --> D4 --> D5
    end
    style SG2 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% ③ 靜態 API 攔截與解析
    %% ==========================================
    subgraph SG3 ["③ 靜態 API 攔截與解析"]
        direction TB
        A1["呼叫 API 1: 取得基礎資料\n(HSN / TSN)"]
        A2{"包含 OE 原廠\n感測器?"}
        A3["寫入空值保留車型"]
        A4["呼叫 API 2: 批次取得\n感測器深度詳細資訊"]
        A5["解析字串與防呆提取:\n廠商 / 頻率 / 日期"]
        A6["加入暫存佇列\nbatch_data"]

        A1 --> A2
        A2 -- 無 --> A3 --> A6
        A2 -- 有 --> A4 --> A5 --> A6
    end
    style SG3 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% ④ 資料寫入與聚合
    %% ==========================================
    subgraph SG4 ["④ 資料寫入與聚合"]
        direction TB
        W1{"暫存佇列\n> 80 筆?"}
        W2[("寫入 SQLite 資料庫\n(REPLACE INTO 去重)")]
        W3["清空暫存區"]

        W1 -- 是 --> W2 --> W3
    end
    style SG4 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% ⑤ 防護與錯誤恢復
    %% ==========================================
    subgraph SG5 ["⑤ 防護與錯誤恢復"]
        direction TB
        E1{"攔截 Ctrl+C 或中斷訊號\n(signal_handler)"}
        E2["觸發 graceful_stop = True"]
        E3[("強制寫入殘留暫存\n保護當前斷點")]

        E1 -- 觸發 --> E2 --> E3
    end
    style SG5 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% ⑥ 匯出與收尾管理
    %% ==========================================
    subgraph SG6 ["⑥ 匯出與收尾管理"]
        direction TB
        F1["該品牌遍歷完畢"]
        F2["透過 SQL View 查詢\n(GROUP_CONCAT 壓縮重複列)"]
        F3["匯出 Brand_Data.xlsx"]
        F4{"所有品牌完成?"}
        F5["標記任務完成\n清除斷點"]
        F6[("匯出 .sql 備份檔")]
        F7([程式安全退出])

        F1 --> F2 --> F3 --> F4
        F4 -- 是 --> F5 --> F6 --> F7
    end
    style SG6 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% 模組間核心連線 (跨區塊動線)
    %% ==========================================
    
    %% 啟動 -> 導航
    S5 --> D1
    S6 --> D1
    
    %% 導航 -> API
    D5 ==>|執行迴圈| E1
    E1 -- 否 (平穩運行) --> A1
    
    %% API -> 寫入
    A6 ==> W1
    
    %% 寫入 -> 導航 (迴圈返回)
    W1 -- 否 --> D5
    W3 --> D5
    
    %% 導航 -> 匯出
    D5 -. 該品牌結束 .-> F1
    F4 -- 否 (回到下一品牌) --> D2

    %% 中斷 -> 備份退出
    E3 ===> F6


    %% ==========================================
    %% 統一套用顏色類別 (GitHub 100% 相容寫法)
    %% ==========================================
    class S1,F7 startEnd;
    class S3,S4,D2,A2,W1,F4 diamond;
    class S6,A5,F3,F5 greenBox;
    class S5,E1 redBox;
    class S2,D4,D5,A1,A4,A6,F1,F2 actionBox;
    class D1,W2,E3,F6 dbBox;
    class A3,E2 warningBox;
```

---
【簡化版流程圖 / 技術架構展示】

🚗 RDKS 爬蟲系統核心架構圖 (簡報專用版)

此版本去除了繁瑣的迴圈返回線條，將系統抽象為四大平行階段，呈現完美的 1x4 橫向佈局，最適合用於簡報提案。同時套用了專業的深色背景與高對比色彩。

```mermaid
flowchart LR

    %% ==========================================
    %% 視覺樣式定義 (致敬參考圖配色)
    %% ==========================================
    classDef startEnd fill:#fff,stroke:#333,stroke-width:2px,color:#000,font-weight:bold;
    classDef diamond fill:#fff,stroke:#555,stroke-width:2px,color:#000,font-weight:bold;
    classDef greenBox fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20,font-weight:bold;
    classDef redBox fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c,font-weight:bold;
    classDef actionBox fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,color:#0d47a1,font-weight:bold;
    classDef dbBox fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#e65100,font-weight:bold;
    classDef warningBox fill:#fff8e1,stroke:#fbc02d,stroke-width:2px,color:#f57f17,font-weight:bold;

    %% ==========================================
    %% 階段 1：啟動與防護
    %% ==========================================
    subgraph P1 ["① 啟動與環境自適應"]
        direction TB
        A1([系統手動啟動]) --> A2["自動安裝缺失套件\n(突破底層保護)"]
        A2 --> A3{"超過 7 天未更新?"}
        
        A3 -- 是 --> A4["【全面更新】\n清除舊斷點紀錄"]
        A3 -- 否 --> A5["【繼續進度】\n載入 JSON 斷點"]
    end
    style P1 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% 階段 2：資料庫與導航
    %% ==========================================
    subgraph P2 ["② 智能導航與聚合設定"]
        direction TB
        B1[("連接 SQLite\n建立資料表")] --> B2[("建立 SQL View\n(設定合併與壓縮)")]
        B2 --> B3["展開全站品牌\n(過濾已完成)"]
        B3 --> B4["遍歷車系與型號\n(Model / Typ)"]
        B4 --> B5["依年份新到舊排序\n(Year)"]
    end
    style P2 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% 階段 3：靜態 API 攔截
    %% ==========================================
    subgraph P3 ["③ 靜態 API 攔截與解析"]
        direction TB
        C1["呼叫 API 1\n(獲取 HSN / TSN)"] --> C2{"有 OE 原廠\n感測器?"}
        
        C2 -- 無 --> C3["寫入空值保留"]
        C2 -- 有 --> C4["呼叫 API 2\n(獲取深度規格)"]
        
        C3 --> C5
        C4 --> C5["解析 JSON 結構\n(廠商/頻率/日期)"]
        C5 --> C6["加入暫存佇列\n(batch_data)"]
    end
    style P3 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% 階段 4：寫入與安全退出
    %% ==========================================
    subgraph P4 ["④ 無損寫入與安全防護"]
        direction TB
        D1{"遭遇中斷?\n(Ctrl+C / 暫停)"}
        
        D1 -- 否 (平穩運行) --> D2{"暫存滿 80 筆?"}
        D2 -- 是 --> D3[("寫入資料庫\n(REPLACE INTO)")]
        D2 -- 否 --> D4["累積數據，繼續抓取"]
        
        D1 -- 是 (觸發防護) --> D5[("強制寫入殘留\n保留當前斷點")]
        
        D3 --> D6["(該品牌全數完成時)\n透過 View 匯出 Excel"]
        
        D4 -.-> D6
        D5 --> D7[("匯出 .sql 備份檔")]
        D6 -- "(所有品牌完成)" --> D7
        D7 --> D8([程式安全退出])
    end
    style P4 fill:#2d2d2d,stroke:#555,color:#fff

    %% ==========================================
    %% 跨區塊連線 (強制建立 1 -> 2 -> 3 -> 4 佈局)
    %% ==========================================
    A4 --> B1
    A5 --> B1
    
    B5 --> C1
    
    C6 --> D1

    %% ==========================================
    %% 統一套用顏色類別 (GitHub 100% 相容寫法)
    %% ==========================================
    class A1,D8 startEnd;
    class A3,C2,D1,D2 diamond;
    class A5,C5,D6 greenBox;
    class A4,D5 redBox;
    class A2,B3,B4,B5,C1,C4,C6,D4 actionBox;
    class B1,B2,D3,D7 dbBox;
    class C3 warningBox;
```

