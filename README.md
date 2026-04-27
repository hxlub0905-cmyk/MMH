# SEM MM — Massive Measurement

SEM MM 是一套用於掃描式電子顯微鏡（SEM）影像自動化量測的桌面應用程式，
以 **Recipe 驅動的 SEM Metrology Platform** 為核心架構（Phase B）。

核心功能為偵測 CMG（Conductor Mask Grid）結構並量測 Y-CD / X-CD（Critical Dimension），
支援單張分析、大批次平行處理，以及可持久化的 Recipe 與 Calibration 管理。

---

## 功能特點

- **Recipe 量測**：以 Recipe 封裝量測邏輯，可建立、編輯、儲存多組 Recipe，隨時套用於不同影像
- **一鍵轉存 Recipe**：在 Measure 頁調好 ControlPanel 參數後，按「Save Cards as Recipe」直接建立 Recipe，不需手動重輸
- **Recipe 連動 Cards**（2026-04-27）：在 Measure 頁選擇已存在的 Recipe，ControlPanel 量測卡片（gl_min/gl_max/篩選器/進階參數等）自動帶出對應值，不需逐欄手調
- **Calibration 管理**：建立並管理多組 nm/pixel 校正設定，支援手動輸入或自動讀取 TIFF tag
- **單張分析**：選取影像 + Recipe 後即時執行，結果就地顯示於 Measure 頁的 ResultsPanel（2026-04-27 起不再強制跳轉至 Review）
- **結果表格排序**：點擊表頭可排序，CD 欄位依數字大小排列（非字串比較）
- **批次處理**：多核心平行處理整個資料夾的影像，附進度條與 ETA 顯示；啟動後立即顯示準備狀態，不再看似凍結
- **批次容錯**（2026-04-27）：Worker 子進程崩潰時不再中止整批，自動記為單筆 FAIL 並繼續處理後續影像
- **Strip Mask 自動欄位偵測**：以 Pitch-anchored 相位偵測（`detect_mg_column_centers_pitch_phase`）自動找出 MG 欄位中心，批次時每張圖各自偵測，不受 PEPI 干擾
- **結果標注**：影像上以顏色標示 MIN（橘色）/ MAX（天藍色）/ 正常（薄荷綠）的 CD 值；數值標籤字體精緻化，間距緊湊
- **多格式匯出**：CSV、Excel（含統計工作表）、JSON、HTML 報告（無 matplotlib 時自動降級顯示提示）；圖片批次匯出附進度條可取消
- **KLARF Export Top-N**：以 CD 值篩選前 N 顆 defect，自動修正 XREL/YREL 座標並輸出新 KLARF
- **KLARF Export 影像預覽**（2026-04-27）：在 KLARF Export 對話框預覽表格中選列，下方即時顯示對應 SEM 影像，並以紅色（原始）/藍色（新）十字標示座標位置，方便視覺確認補正結果；十字尺寸依影像大小自適應，16-bit TIFF 自動正規化以確保可見
- **KLARF Export 進度條**（2026-04-27）：「執行並輸出 KLARF」按下後顯示脈動進度條，避免大批次匯出時 UI 看起來凍結
- **Image Quality Checker 即時影像預覽**（2026-04-27）：`tools/image_quality_checker.py` 結果表格右側新增即時影像預覽，選列即顯示對應 SEM 影像 + PASS/FAIL 標記與三項 metrics，方便視覺判斷自動篩選結果是否合理
- **Recipe 編輯器 Tab 佈局**：Preprocessing / Detection / Strip Mask / Analysis 四 Tab，欄位不再擠在一起
- **批次結果持久化（SQLite）**：每次 Batch 執行後自動儲存至 `~/.mmh/runs.db`（Phase D，WAL+thread-local）；支援歷史記錄瀏覽、載入舊結果至 Report，以及刪除紀錄
- **Recipe 驗證模式**：以黃金樣品（Golden Sample）驗證 Recipe 精確度，計算 Bias、3σ、Precision 等統計指標，結果可匯出 CSV
- **歷史趨勢 Run Chart**：以 matplotlib 繪製歷批次 Mean CD 趨勢圖，依 Recipe 與時間範圍篩選，一鍵載入至 Report 詳覽
- **六工作區 UI**：Browse → Recipe → Measure → Batch → Review → Report 完整作業流程（Validate / History 規劃於 Phase D）
- **Batch 即時 Overlay 輸出**：在 Batch 頁勾選「邊跑邊輸出 Overlay Image」並選擇資料夾，每張圖跑完即寫出 `<stem>_annotated.png`，不需等批次結束再手動匯出
- **TC 路徑向量化**：Threshold Crossing 模式改用向量化批次運算，All-columns 設定下 13000 張影像從 20–30 分鐘縮短至約 4–8 分鐘（~4–5× 加速）
- **Gradient 路徑向量化**：Gradient 模式同樣改為批次處理（共用 `_extract_strip()` + `np.diff()` 向量化），再獲 ~2–3× 加速；TC + Gradient 合計目標 3–6 分鐘
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
Browse → Recipe → Validate → Measure → Batch → Review → Report → History
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

#### 3. Validate — Recipe 驗證

1. 切換至 **Validate** 頁籤
2. 從上方下拉選單選擇要驗證的 Recipe
3. 在樣品表格中新增黃金樣品：
   - 按 **Add Files…** 選取影像（支援多選）
   - 填入每張影像對應的 **Reference nm**（標準值）、**CMG ID**、**Col ID**
   - 或按 **Load CSV…** 從 CSV 批次匯入樣品清單
4. 按 **Run Validation** 執行；進度條即時更新
5. 完成後下方顯示統計摘要（N、Mean Bias、3σ、Precision、Max |Bias|）
6. 結果表格以顏色標示偏差等級（綠色 < 1 nm、黃色 1–2 nm、紅色 > 2 nm）
7. 按 **Export CSV…** 匯出詳細驗證結果

#### 4. Measure — 單張量測

1. 切換至 **Measure** 頁籤（或從 Browse 自動跳轉）
2. 從下拉選單選擇 Recipe — 此時會**自動連動** ControlPanel 卡片參數（gl_min/gl_max/篩選/進階參數），同時帶入 nm/pixel 與 Edge Locator 設定
3. 按 **Run Single (F5)** 執行；結果就地顯示於下方結果表格，標注影像即時更新；**頁面停留在 Measure**，方便調整參數重跑（2026-04-27 起）
4. 如需查看完整批次比對或在 Annotated/Mask 切換審閱，手動切換至 **Review** 頁籤

#### 5. Review — 結果審閱

- 檢視 Raw / Mask / Annotated 三種模式
- 結果表格顯示每個 CMG gap 的量測值與 MIN/MAX 標示
- **使用情境**：批次完成後自動切換至此頁，逐張瀏覽結果；單張 Run Single 不再強制跳轉，需手動切換

#### 6. Batch — 批次處理

1. 切換至 **Batch** 頁籤
2. 選擇輸入資料夾
3. 選擇要套用的 Recipe（可多選）
4. 調整 Worker 數量（預設 = CPU 核數 - 1）
5. 按 **Run Batch** 開始；進度條即時更新
6. 完成後自動切換至 Report 頁籤；本次執行自動儲存至歷史記錄
7. 按 **Load History…** 可從過去的批次紀錄中選取並重新載入結果

#### 7. Report — 統計與匯出

- 查看批次統計（筆數、Mean、Median、Std Dev、3-Sigma）
- 匯出：**CSV**、**Excel**、**JSON**、**HTML 報告**
- 按 **Load from History…** 從持久化紀錄中載入任一歷史批次

#### 8. History — 歷史趨勢

1. 切換至 **History** 頁籤
2. 從 **Recipe** 下拉選單篩選（留空顯示全部）
3. 從 **Time Range** 下拉選單選擇時間範圍（7 天 / 30 天 / 90 天 / All）
4. 按 **Refresh** 重新載入
5. 上方 Run Chart 顯示歷批次 Mean CD (nm) 趨勢；需安裝 matplotlib 方可顯示圖表
6. 下方表格列出所有符合條件的批次紀錄
7. 雙擊表格中的任一列可將該批次載入至 Report 工作區詳覽

---

## 使用者資料目錄

```
~/.mmh/
  recipes/          — 儲存的 MeasurementRecipe（JSON 格式，待 Phase D 遷移至 SQLite）
  calibrations/     — 儲存的 CalibrationProfile（JSON 格式）
  runs.db           — 批次執行歷史記錄（SQLite，Phase D 已完成；WAL + thread-local；舊版 runs/*.json 不再使用）
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
│   │   ├── models.py                # 統一資料模型：ImageRecord / MeasurementRecord / BatchRunRecord / GoldenSampleEntry / ValidationResult
│   │   ├── calibration.py           # CalibrationProfile + CalibrationManager
│   │   ├── recipe_base.py           # BaseRecipe 抽象介面 + MeasurementRecipe + PipelineResult
│   │   ├── recipe_registry.py       # RecipeRegistry（~/.mmh/recipes/*.json）
│   │   ├── measurement_engine.py    # MeasurementEngine（單張 + batch）
│   │   ├── batch_run_store.py       # BatchRunStore（SQLite ~/.mmh/runs.db、歷史統計、WAL 模式）★ Phase D
│   │   ├── recipe_validator.py      # RecipeValidator（黃金樣品驗證、Bias/3σ 統計）★ Phase B
│   │   ├── recipes/
│   │   │   └── cmg_recipe.py        # CMGRecipe（包裝 CMG 演算法，不修改原始碼）
│   │   ├── image_loader.py          # 影像讀取與資料夾掃描
│   │   ├── preprocessor.py          # 前處理流程（CLAHE → GL 遮罩 → 形態學）
│   │   ├── mg_detector.py           # Blob 偵測（連通元件）
│   │   ├── cmg_analyzer.py          # CMG gap 分群與 Y-CD 計算（核心演算法 ⚠️）
│   │   └── annotator.py             # 影像標注（線條、數值、框、圖例）
│   ├── gui/
│   │   ├── main_window.py           # 主視窗（精簡殼層，~70 行）
│   │   ├── workspace_host.py        # WorkspaceHost（QTabWidget + 信號匯流，八工作區）
│   │   ├── workspaces/
│   │   │   ├── browse_workspace.py  # 資料集瀏覽 + Calibration 選擇
│   │   │   ├── recipe_workspace.py  # Recipe 建立 / 編輯 / 管理
│   │   │   ├── validation_workspace.py  # Recipe 驗證模式（黃金樣品）★ Phase B
│   │   │   ├── measure_workspace.py # 單張影像量測
│   │   │   ├── review_workspace.py  # 量測結果審閱
│   │   │   ├── batch_workspace.py   # 批次執行（含歷史對話框）
│   │   │   ├── report_workspace.py  # 統計 + 匯出（含歷史載入）
│   │   │   └── history_workspace.py # 歷史趨勢 Run Chart★ Phase B
│   │   ├── batch_dialog.py          # 保留（Legacy 相容）
│   │   ├── batch_review_dialog.py   # 保留（Legacy 相容）
│   │   ├── control_panel.py         # 保留（Legacy Cards 路徑）
│   │   ├── file_tree_panel.py       # 檔案樹（共用）
│   │   ├── image_viewer.py          # 影像檢視器（共用）
│   │   ├── results_panel.py         # 結果表格（共用）
│   │   └── styles.py                # QSS 主題
│   └── output/
│       ├── _common.py               # 共用：results_to_dataframe + records_to_dataframe
│       ├── csv_exporter.py          # export_csv / export_csv_from_records（lazy import）
│       ├── excel_exporter.py        # export_excel / export_excel_from_records（lazy import）
│       ├── json_exporter.py         # export_json / export_json_from_records
│       └── report_generator.py      # generate_report / generate_report_from_records
└── tests/
    ├── test_cmg_analyzer.py         # CMG 演算法測試（11 項）
    ├── test_models.py               # 資料模型 round-trip 測試（6 項）
    ├── test_recipe_base.py          # CMGRecipe pipeline + Registry 測試（12 項）
    ├── test_measurement_engine.py   # 引擎整合 + 相容層測試（8 項）
    ├── test_subpixel_refinement.py  # 次像素精細化測試
    ├── test_batch_run_store.py      # BatchRunStore 持久化測試（7 項）★ Phase B
    ├── test_recipe_validator.py     # RecipeValidator 驗證測試（4 項）★ Phase B
    └── test_history.py              # get_stats_for_recipe 歷史統計測試（4 項）★ Phase B
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
# 完整測試（需 numpy + cv2 + scikit-image）
pytest tests/ -v

# 不依賴科學計算套件的測試（17 項）
pytest tests/test_models.py tests/test_batch_run_store.py tests/test_history.py -v

# 各測試模組
pytest tests/test_cmg_analyzer.py        # 核心演算法（11 項，需 cv2）
pytest tests/test_models.py              # 資料模型（6 項）
pytest tests/test_recipe_base.py         # Recipe pipeline（12 項，需 numpy）
pytest tests/test_measurement_engine.py  # 引擎整合（8 項，需 numpy）
pytest tests/test_subpixel_refinement.py # 次像素精細化（需 numpy）
pytest tests/test_batch_run_store.py     # 批次結果持久化（7 項）
pytest tests/test_recipe_validator.py    # Recipe 驗證（4 項，需 numpy）
pytest tests/test_history.py             # 歷史統計（4 項）
```

---

## 版本與開發階段

| 階段 | 狀態 | 內容摘要 |
|------|------|---------|
| Phase A | ✅ 完成（2026-04-20） | Recipe 抽象化、統一資料模型、六工作區 GUI、36 項測試 |
| Phase F2 | ✅ 完成（2026-04-20） | X-Proj 改為 Pitch-Anchored 相位偵測，Auto-detect 準確性大幅提升 |
| Phase G2 | ✅ 完成（2026-04-20） | Save as Recipe、表格排序、Batch 早期進度、HTML 容錯、圖片匯出進度條、Recipe Tab UI、標注字體優化 |
| Phase B | ✅ 完成（2026-04-21） | 批次結果持久化（BatchRunStore）、Recipe 驗證邏輯、歷史統計 API、77 項測試 |
| Bug Fix Series | ✅ 完成（2026-04-23） | CD 計算一致性（bbox edge / fallback / 精化 center_y）、Cards 路徑修正（bbox / Detail CD）、Review 批次導航（> 1000 張）、Duplicate Recipe、Edge Locator UX 提示、Mask 即時更新、歷史查詢效能（recipe_ids fast-skip）、CSV/Excel 欄位重命名（cut_id/column_id） |
| Phase C | 部分完成（2026-04-23） | Batch 即時 Overlay 輸出、TC 路徑向量化（4–5×）、Gradient 路徑向量化（2–3×，13000 張目標 3–6 min）；Worker 上限保護、X-CD 標注修正待完成 |
| Bug Fix C1–C4/M1–M7/m1–m3 | ✅ 完成（2026-04-24） | bbox tuple 還原、Windows 路徑正規化、end_time finally 保證、Detail CD fallback 對齊、全域 MIN/MAX、LRU 快取上限、進度條重置、dropna 防 NaN、測試 key 更新等 14 項修復 |
| Bug Fix Round2 | ✅ 完成（2026-04-27） | H1 cv2.imwrite 回傳值驗證、H3 NumPy 2.0 ptp() 移除、M1 無任務 QMessageBox 警告、M2 X-CD blob _rot_blob_to_ori 修正、M3 FileTreePanel root_path()、M4 html.escape XSS 防護、L1 _EC_CANONICAL_KEYS 過濾廢棄鍵、L2 KLARF XREL/YREL 大小寫不敏感查詢 |
| Phase D（部分） | ✅ 完成（2026-04-27） | BatchRunStore 遷移至 SQLite（WAL+Thread-local）、thread-safe QThread 存取、executemany 批量寫入、get_stats_for_recipe SQL JOIN；Plugin 介面、ValidationWorkspace、HistoryWorkspace 規劃中 |
| UI Improvements + Bug Fix B1–B6 | ✅ 完成（2026-04-27） | 功能一 KLARF Export 進度條；功能二 KLARF Export 影像預覽 + 原始/新座標十字 overlay；功能三 Recipe 連動 ControlPanel Cards；功能四 Run Single 不再跳轉 Review；B1 worker 訊號洩漏；B2 _size_cache 上限；B3 BatchRunStore.close()；B4 nm_per_pixel=0 警告；B5 Nth Y-CD 降冪邊界值；B6 future.result() 例外捕捉 |
| Round3 修復 + IQC 影像預覽 | ✅ 完成（2026-04-27） | 修正 KLARF Export 影像 overlay 不顯示問題（16-bit TIFF 正規化 + 十字尺寸自適應）；tools/image_quality_checker 加入即時影像預覽；H2 RecipeRegistry 原子寫入；H4 BatchRunRecord/MultiDatasetBatchRun 加 aborted 欄位 + SQLite 持久化；M6 順便修 |

---

## 授權

本專案內部使用，詳情請洽維護人員。
