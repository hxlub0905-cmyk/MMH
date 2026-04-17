# SEM MM — Massive Measurement

SEM MM 是一套用於掃描式電子顯微鏡（SEM）影像自動化量測的桌面應用程式。
核心功能為偵測 CMG（Conductor Mask Grid）結構並量測 Y-CD（Critical Dimension，臨界尺寸），支援單張分析與大批次處理。

---

## 功能特點

- **單張分析**：載入 SEM 影像後即時預覽遮罩與標注結果
- **批次處理**：多核心平行處理整個資料夾的影像，附進度條與 ETA 顯示
- **多量測設定檔**：可同時設定多組 GL 範圍（Y-CD / X-CD 方向），每組可獨立命名
- **結果標注**：在影像上以顏色編碼標示 MIN（橘色）/ MAX（天藍色）/ 正常（薄荷綠）的 CD 值
- **多格式匯出**：CSV、Excel（含統計工作表）、JSON、HTML 報告
- **批次審閱介面**：批次完成後逐張瀏覽影像與量測表格
- **即時調整**：拖動 GL Min / GL Max 滑桿即時預覽遮罩變化

---

## 環境需求

- Python 3.9+
- 相依套件（見 `requirements.txt`）：

| 套件 | 最低版本 |
|------|---------|
| PyQt6 | 6.5 |
| opencv-python | 4.8 |
| scikit-image | 0.21 |
| numpy | 1.24 |
| pandas | 2.0 |
| openpyxl | 3.1 |
| matplotlib | 3.7 |

---

## 安裝步驟

```bash
# 1. 複製專案
git clone <repo-url>
cd MMH

# 2. 建立虛擬環境（建議）
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.\.venv\Scripts\activate         # Windows

# 3. 安裝相依套件
pip install -r requirements.txt

# 4. 啟動應用程式
python main.py
```

---

## 使用說明

### 開啟影像資料夾
1. 選單 **File → Open Folder…** 或按 `Ctrl+O`
2. 左側檔案樹會列出資料夾內所有支援的影像（`.tif`, `.tiff`, `.png`, `.bmp`, `.jpg`）
3. 點選影像即可在中央檢視器預覽

### 設定量測設定檔
右側控制面板可新增量測設定檔（Measurement Profiles）：
- **Name**：設定檔名稱（會出現在結果表格與報告中）
- **Axis**：量測方向（Y-CD 或 X-CD）
- **GL Min / Max**：灰階範圍，指定 MG 材質的亮度區間
- **Min Area**：最小 blob 面積（過濾雜訊）

### 單張分析
- 選好影像並設定量測設定檔後，按 `F5` 或 **Run → Run Single**
- 結果顯示於右下方結果表格，並自動切換至 Annotated 模式

### 批次處理
1. 按 `F6` 或 **Run → Run Batch…**
2. 選擇包含影像的輸入資料夾
3. 進度對話框顯示處理進度與 ETA
4. 完成後自動開啟 **Batch Review Viewer**，可逐張瀏覽結果
5. 在 Batch Review Viewer 中可點選：
   - **Export Package**：匯出 CSV / Excel / JSON / HTML 報告 + 標注影像
   - **One-click Report**：快速產生報告至原始資料夾旁
   - **Export Batch Output**：僅匯出標注影像

### 匯出
- **Export Results…**（`Ctrl+E`）：手動選擇輸出目錄匯出所有格式

---

## 專案架構

```
MMH/
├── main.py                      # 程式進入點（含 Windows multiprocessing 支援）
├── requirements.txt
├── src/
│   ├── core/                    # 核心演算法
│   │   ├── image_loader.py      # 影像讀取與資料夾掃描
│   │   ├── preprocessor.py      # 高斯模糊 → CLAHE → GL 遮罩 → 形態學處理
│   │   ├── mg_detector.py       # 連通元件 blob 偵測
│   │   ├── cmg_analyzer.py      # CMG gap 分群與 Y-CD 計算（核心演算法）
│   │   └── annotator.py         # 影像標注（線條、數值、框、圖例）
│   ├── gui/                     # PyQt6 GUI 元件
│   │   ├── main_window.py       # 主視窗（三欄式佈局）
│   │   ├── batch_dialog.py      # 批次處理對話框（含 QThread + ProcessPoolExecutor）
│   │   ├── batch_review_dialog.py  # 批次結果審閱視窗
│   │   ├── control_panel.py     # 右側控制面板（滑桿、量測設定檔）
│   │   ├── file_tree_panel.py   # 左側檔案樹
│   │   ├── image_viewer.py      # 中央影像檢視器（QGraphicsView，支援縮放/平移）
│   │   ├── results_panel.py     # 結果表格（MIN/MAX 顏色標示）
│   │   └── styles.py            # QSS 主題（柔和橘色系）
│   └── output/                  # 匯出模組
│       ├── csv_exporter.py
│       ├── excel_exporter.py
│       ├── json_exporter.py
│       └── report_generator.py  # HTML 報告（統計 + 直方圖）
└── tests/
    └── test_cmg_analyzer.py     # CMG 分析演算法單元測試（10 項）
```

### 核心演算法流程

```
影像 → 高斯模糊 → CLAHE 對比增強 → GL 遮罩（像素亮度在 [gl_min, gl_max] 範圍）
     → 形態學 open/close → Blob 偵測（連通元件）
     → 依 X 範圍分群（欄位）→ 找相鄰 Blob 對（CMG gap）
     → 跨欄位群集（10px tolerance）→ CMG cut 事件
     → 計算每個 cut 的 Y-CD（px 與 nm）
```

---

## 優化建議

1. **批次匯出效率**：目前 `_do_export` 會重新執行完整分析流程（load / preprocess / detect / analyze），應改為直接沿用批次已計算的 `cuts` 資料，大幅減少不必要的重複運算。

2. **記憶體管控**：大批次（數百張）下所有結果字典同時存於記憶體，可考慮改用串流寫入（streaming）或分頁機制，避免 OOM。

3. **進度顯示強化**：批次進行中可增加顯示「已失敗數」計數器，讓使用者即時掌握失敗狀況而不必等到結束。

4. **Worker 數量可調**：目前 worker 數寫死為 `max(1, CPU 數 - 1)`，建議在 UI 加入可調整的滑桿或輸入欄位，方便在低負載或高負載環境下調整。

5. **X-CD 標注修正**：X-CD blobs 的座標轉換後，annotated overlay 的線條與框位置可能未正確對齊，建議統一在 `annotator.py` 中增加 X-CD 專用繪製路徑。

---

## 應用擴充建議

1. **多資料夾遞迴批次**：目前只支援單一資料夾；可擴充為遞迴掃描子資料夾，並在結果中保留相對路徑結構。

2. **即時預覽 (Live View)**：透過資料夾監控（如 `watchdog` 套件）偵測新影像並自動觸發單張分析，適合生產線即時監控場景。

3. **自訂報告模板**：HTML 報告目前格式固定，可引入 Jinja2 模板引擎，讓使用者自訂版面與內容。

4. **資料庫整合**：批次結果可寫入本地 SQLite 資料庫，支援跨 session 的歷史查詢、趨勢分析與資料比對。

5. **Plugin 量測設定檔**：將量測設定檔的參數邏輯抽象為可插拔的 Plugin 介面，方便針對不同材料或製程客製化偵測邏輯。

---

## 執行測試

```bash
pytest tests/ -v
```

預期結果：10 項測試全數通過。

---

## 授權

本專案內部使用，詳情請洽維護人員。
