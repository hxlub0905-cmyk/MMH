# SEM MM — Massive Measurement

SEM MM 是一套用於掃描式電子顯微鏡（SEM）影像自動化量測的桌面應用程式，
以 **Recipe 驅動的 SEM Metrology Platform** 為核心架構（Phase A vNext）。

核心功能為偵測 CMG（Conductor Mask Grid）結構並量測 Y-CD / X-CD（Critical Dimension），
支援單張分析、大批次平行處理，以及可持久化的 Recipe 與 Calibration 管理。

---

## 功能特點

- **Recipe 量測**：以 Recipe 封裝量測邏輯，可建立、編輯、儲存多組 Recipe，隨時套用於不同影像
- **Calibration 管理**：建立並管理多組 nm/pixel 校正設定，支援手動輸入或自動讀取 TIFF tag
- **單張分析**：選取影像 + Recipe 後即時執行，結果顯示於 ResultsPanel，標注影像即時更新
- **批次處理**：多核心平行處理整個資料夾的影像，附進度條與 ETA 顯示
- **結果標注**：影像上以顏色標示 MIN（橘色）/ MAX（天藍色）/ 正常（薄荷綠）的 CD 值
- **多格式匯出**：CSV、Excel（含統計工作表）、JSON、HTML 報告
- **六工作區 UI**：Browse → Recipe → Measure → Review → Batch → Report 完整作業流程
- **向下相容**：Legacy Cards 路徑保留，舊版設定檔仍可直接使用

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

啟動後應用程式會自動在 `~/.mmh/` 建立 `recipes/` 與 `calibrations/` 資料夾。

---

## 使用說明

### 完整作業流程（推薦）

```
Browse → Recipe → Measure → Review → Batch → Report
```

#### 1. Browse — 開啟影像資料夾

1. 選單 **File → Open Folder…** 或按 `Ctrl+O`
2. 左側檔案樹列出所有支援格式的影像（`.tif`, `.tiff`, `.png`, `.bmp`, `.jpg`）
3. 點選影像預覽；右側可選擇或建立 Calibration Profile（nm/pixel）
4. 按 **Send to Measure →** 將影像送至 Measure 工作區

#### 2. Recipe — 管理量測 Recipe

1. 切換至 **Recipe** 頁籤
2. 點選 **New** 建立新 Recipe，或選擇現有 Recipe 進行編輯
3. 設定：
   - **名稱 / 量測方向**（Y-CD 或 X-CD）
   - **前處理參數**（GL Min/Max、高斯核、形態學參數）
   - **偵測參數**（Min Blob Area）
   - **分群參數**（X Overlap Ratio、Y Cluster Tolerance）
4. 按 **Save** 儲存至 `~/.mmh/recipes/`

#### 3. Measure — 單張量測

1. 切換至 **Measure** 頁籤（或從 Browse 自動跳轉）
2. 從下拉選單選擇 Recipe
3. 按 **Run with Recipe** 執行；結果顯示於下方結果表格，標注影像即時更新
4. （可選）按 **Send to Review →** 查看詳細標注結果

#### 4. Review — 結果審閱

- 檢視 Raw / Mask / Annotated 三種模式
- 結果表格顯示每個 CMG gap 的量測值與 MIN/MAX 標示

#### 5. Batch — 批次處理

1. 切換至 **Batch** 頁籤
2. 選擇輸入資料夾
3. 選擇要套用的 Recipe（可多選）
4. 調整 Worker 數量（預設 = CPU 核數 - 1）
5. 按 **Run Batch** 開始；進度條即時更新
6. 完成後自動切換至 Report 頁籤

#### 6. Report — 統計與匯出

- 查看批次統計（筆數、Mean、Median、Std Dev、3-Sigma）
- 匯出：**CSV**、**Excel**、**JSON**、**HTML 報告**

---

## 使用者資料目錄

```
~/.mmh/
  recipes/          — 儲存的 MeasurementRecipe（JSON 格式）
  calibrations/     — 儲存的 CalibrationProfile（JSON 格式）
```

---

## 專案架構

```
MMH/
├── main.py                          # 程式進入點（含 Windows multiprocessing 支援）
├── requirements.txt
├── AGENTS.md                        # AI Agent / 開發者快速參考指南
├── SESSION_LOG.md                   # 每次變更的 session 記錄
├── src/
│   ├── _compat.py                   # 相容層：MeasurementRecord → 舊版 CMGCut 格式
│   ├── core/
│   │   ├── models.py                # 統一資料模型：ImageRecord / MeasurementRecord / BatchRunRecord
│   │   ├── calibration.py           # CalibrationProfile + CalibrationManager
│   │   ├── recipe_base.py           # BaseRecipe 抽象介面 + MeasurementRecipe + PipelineResult
│   │   ├── recipe_registry.py       # RecipeRegistry（~/.mmh/recipes/*.json）
│   │   ├── measurement_engine.py    # MeasurementEngine（單張 + batch）
│   │   ├── recipes/
│   │   │   └── cmg_recipe.py        # CMGRecipe（包裝 CMG 演算法，不修改原始碼）
│   │   ├── image_loader.py          # 影像讀取與資料夾掃描
│   │   ├── preprocessor.py          # 前處理流程（CLAHE → GL 遮罩 → 形態學）
│   │   ├── mg_detector.py           # Blob 偵測（連通元件）
│   │   ├── cmg_analyzer.py          # CMG gap 分群與 Y-CD 計算（核心演算法 ⚠️）
│   │   └── annotator.py             # 影像標注（線條、數值、框、圖例）
│   ├── gui/
│   │   ├── main_window.py           # 主視窗（精簡殼層，~70 行）
│   │   ├── workspace_host.py        # WorkspaceHost（QTabWidget + 信號匯流）
│   │   ├── workspaces/
│   │   │   ├── browse_workspace.py  # 資料集瀏覽 + Calibration 選擇
│   │   │   ├── recipe_workspace.py  # Recipe 建立 / 編輯 / 管理
│   │   │   ├── measure_workspace.py # 單張影像量測
│   │   │   ├── review_workspace.py  # 量測結果審閱
│   │   │   ├── batch_workspace.py   # 批次執行
│   │   │   └── report_workspace.py  # 統計 + 匯出
│   │   ├── batch_dialog.py          # 保留（Legacy 相容）
│   │   ├── batch_review_dialog.py   # 保留（Legacy 相容）
│   │   ├── control_panel.py         # 保留（Legacy Cards 路徑）
│   │   ├── file_tree_panel.py       # 檔案樹（共用）
│   │   ├── image_viewer.py          # 影像檢視器（共用）
│   │   ├── results_panel.py         # 結果表格（共用）
│   │   └── styles.py                # QSS 主題
│   └── output/
│       ├── _common.py               # 共用：results_to_dataframe + records_to_dataframe
│       ├── csv_exporter.py          # export_csv / export_csv_from_records
│       ├── excel_exporter.py        # export_excel / export_excel_from_records
│       ├── json_exporter.py         # export_json / export_json_from_records
│       └── report_generator.py      # generate_report / generate_report_from_records
└── tests/
    ├── test_cmg_analyzer.py         # CMG 演算法測試（10 項）
    ├── test_models.py               # 資料模型 round-trip 測試（6 項）
    ├── test_recipe_base.py          # CMGRecipe pipeline + Registry 測試（12 項）
    └── test_measurement_engine.py   # 引擎整合 + 相容層測試（8 項）
```

---

## 核心演算法流程

```
影像讀取
  → Stage 2 前處理（高斯模糊 → CLAHE → GL 遮罩 → 形態學 open/close）
  → Stage 3 特徵偵測（連通元件 blob 偵測）
  → Stage 4 邊緣定位（X-CD 時進行座標轉換）
  → Stage 5 量測計算（blob 分群 → CMG gap → Y-CD/X-CD nm 值）
  → Stage 6 標注繪製（MIN/MAX/正常 顏色編碼）
```

---

## 執行測試

```bash
# 執行全部 36 項測試
pytest tests/ -v

# 各測試模組
pytest tests/test_cmg_analyzer.py        # 核心演算法（10 項）
pytest tests/test_models.py              # 資料模型（6 項）
pytest tests/test_recipe_base.py         # Recipe pipeline（12 項）
pytest tests/test_measurement_engine.py  # 引擎整合（8 項）
```

---

## 版本與開發階段

| 階段 | 狀態 | 內容摘要 |
|------|------|---------|
| Phase A | ✅ 完成（2026-04-20） | Recipe 抽象化、統一資料模型、六工作區 GUI、36 項測試 |
| Phase B | 規劃中 | Batch 結果快取、Review 工作流程完善、嵌入式直方圖 |
| Phase C | 規劃中 | Worker 上限保護、X-CD 標注修正、效能優化 |
| Phase D | 規劃中 | Recipe 遷移至 SQLite、Plugin 介面、多資料夾批次 |

---

## 授權

本專案內部使用，詳情請洽維護人員。
