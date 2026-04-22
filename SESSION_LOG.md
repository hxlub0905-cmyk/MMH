# Session Log

每次對本專案進行任何變更（功能新增、Bug 修復、重構、文件更新），
都必須在本文件**最上方**新增一筆 session 記錄。

---

<!-- ===== 記錄範本（複製後填寫） =====

## [YYYY-MM-DD] 標題

**變更類型：** 功能新增 / Bug 修復 / 重構 / 文件更新

**變更摘要：**
- 說明 1
- 說明 2

**影響範圍：**
- 受影響的檔案或模組

**測試結果：**
- pytest 結果或手動 smoke test 說明

**備註：**
- 任何注意事項或後續 TODO

===== 範本結束 ===== -->

---

## [2026-04-21] Phase B — Task 4：歷史資料庫與趨勢 Run Chart

**變更類型：** 功能新增

**變更摘要：**
- 新增 `HistoryWorkspace`（`src/gui/workspaces/history_workspace.py`）：顯示 `~/.mmh/runs/` 歷史批次清單，以 matplotlib 繪製 Run Chart（CD Mean ± 1σ + ±3σ 控制線），支援 Recipe 過濾與時間範圍篩選
- 在 `BatchRunStore` 新增 `get_stats_for_recipe(recipe_id)` 方法：從歷史 JSON 讀取所有量測值、計算 mean/std，可依 recipe_id 過濾
- 整合至 `WorkspaceHost`：新增 History tab，`history.load_requested` 連接至 `report.load_from_file()`
- 新增測試 `tests/test_history.py`（4 項）

**影響範圍：**
- `src/core/batch_run_store.py`（新增 `get_stats_for_recipe()`）
- `src/gui/workspaces/history_workspace.py`（新增）
- `src/gui/workspace_host.py`（整合 HistoryWorkspace）

**測試結果：**
- `pytest tests/ -q` → 77/77 通過（含新增 4 項）

**備註：**
- matplotlib 為 optional；無安裝時 chart label 顯示提示文字，不崩潰

---

## [2026-04-21] Phase B — Task 3：Recipe 驗證模式（Golden Sample 比對）

**變更類型：** 功能新增

**變更摘要：**
- 在 `src/core/models.py` 新增 `GoldenSampleEntry`、`ValidationResult` dataclass
- 新增 `RecipeValidator`（`src/core/recipe_validator.py`）：依序量測 golden sample，計算 Bias / Precision 統計
- 新增 `ValidationWorkspace`（`src/gui/workspaces/validation_workspace.py`）：Recipe 選擇 + golden sample 表格（Add Files / Remove / Load CSV）+ Run Validation + 結果展示（Bias 顏色標示）+ Export CSV
- 整合至 `WorkspaceHost`：插入 Validate tab（TAB_VALIDATE=2），tab index 整體後移
- 新增測試 `tests/test_recipe_validator.py`（4 項）

**影響範圍：**
- `src/core/models.py`（新增 2 個 dataclass）
- `src/core/recipe_validator.py`（新增）
- `src/gui/workspaces/validation_workspace.py`（新增）
- `src/gui/workspace_host.py`（整合 ValidationWorkspace）

**測試結果：**
- `pytest tests/ -q` → 77/77 通過（含新增 4 項）

---

## [2026-04-21] Phase B — Task 2：批次結果持久化（BatchRunStore）

**變更類型：** 功能新增

**變更摘要：**
- 新增 `BatchRunStore`（`src/core/batch_run_store.py`）：儲存 `BatchRunRecord` / `MultiDatasetBatchRun` 至 `~/.mmh/runs/*.json`；支援 `save / save_multi / list_runs / load / delete / get_stats_for_recipe`
- `BatchWorkspace.__init__` 接受 `run_store` 參數；`_on_single_finished` 自動呼叫 `run_store.save()`；`_on_multi_finished` 呼叫 `run_store.save_multi()`；Progress 區塊下新增「Load History…」按鈕開啟 `_HistoryDialog`
- 新增 `_HistoryDialog`（同 `batch_workspace.py`）：顯示歷史批次清單，可載入或刪除
- `ReportWorkspace.__init__` 接受 `run_store` 參數；Export 區塊新增「Load from History…」按鈕；新增 `load_from_file()` public 方法
- `WorkspaceHost` 建立 `BatchRunStore` 並注入各 Workspace
- 新增測試 `tests/test_batch_run_store.py`（7 項）

**影響範圍：**
- `src/core/batch_run_store.py`（新增）
- `src/gui/workspaces/batch_workspace.py`（整合 BatchRunStore + _HistoryDialog）
- `src/gui/workspaces/report_workspace.py`（整合 BatchRunStore）
- `src/gui/workspace_host.py`（注入 BatchRunStore）

**測試結果：**
- `pytest tests/ -q` → 77/77 通過（含新增 7 項）

**備註：**
- 儲存路徑：`~/.mmh/runs/<batch_id>.json`（single）、`~/.mmh/runs/multi_<run_id>.json`（multi）

---

## [2026-04-21] Phase B — Task 1：Bug 修復（5 項）

**變更類型：** Bug 修復

**變更摘要：**
- **Bug 1**：新增 `_flag_top3()` 至 `cmg_analyzer.py`；更新 `analyze()` Step 5、`apply_yedge_subpixel_to_cuts()` 尾端、`compute_metrics()` range filter、`batch_dialog._filter_by_range()`、`measure_workspace._filter_by_range()`；MIN/MAX 改為每 CMGCut 內前 3 小 / 前 3 大（MIN 優先，不重疊）
- **Bug 2**：`measurement_engine._worker_run_image()` 空 cuts 時補 `else: cmg_id_offset += 1000`，避免不同 recipe 的 cmg_id 衝突
- **Bug 3**：`review_workspace._nav_next()` / `_nav_prev()` 改為迴圈跳過 separator 列
- **Bug 4**：`results_panel._on_selection()` 改為防禦性解析，解析失敗時 `print` 警告而非靜默忽略
- **Bug 5**：`csv_exporter.py` / `excel_exporter.py` 頂層 `import pandas` 改為函式內延遲 import（`_require_pandas()` / `_require_openpyxl()`），避免啟動時崩潰
- 更新既有測試 `test_min_max_flagging`（新增 6-column 場景）、`test_min_max_flagging_two_meas`（記錄 2-measurement 行為）、`test_bbox_method_default_is_threshold_crossing`

**影響範圍：**
- `src/core/cmg_analyzer.py`（新增 `_flag_top3`，更新 Step 5）
- `src/core/recipes/cmg_recipe.py`（import `_flag_top3`，更新兩處 re-flag）
- `src/core/measurement_engine.py`（`_worker_run_image` 空 cuts 處理）
- `src/gui/batch_dialog.py`（`_filter_by_range`）
- `src/gui/workspaces/measure_workspace.py`（`_filter_by_range`）
- `src/gui/workspaces/review_workspace.py`（nav skip separator）
- `src/gui/results_panel.py`（防禦性 feature_id 解析）
- `src/output/csv_exporter.py`（延遲 import）
- `src/output/excel_exporter.py`（延遲 import）
- `tests/test_cmg_analyzer.py`（更新 + 新增 test case）
- `tests/test_subpixel_refinement.py`（更新 test name + assertion）

**測試結果：**
- `pytest tests/ -q` → 62/62 通過（原 59 + 新增 3）

---

## [2026-04-20] Phase G2 — 六項新功能 + 標注字體調整

**變更類型：** 功能新增

**變更摘要：**
- **G2-1**：Measure 頁新增「Save Cards as Recipe…」按鈕，一鍵將 ControlPanel 所有 profile 轉存為 Recipe；同步補全 `CMGRecipe._card_to_descriptor()` 缺少的 17 個 col_mask / range 參數（確保 roundtrip 無損）
- **G2-2**：Results / Review 結果表格支援點擊表頭排序；CD 數值欄（px / nm）使用 `_NumericItem`（浮點比較）而非字串比較；`insertRow()` 期間暫停排序避免行重排亂序
- **G2-3**：Batch Run 點擊後立即於進度列顯示「Preparing N job(s)…」（ProcessPool 建立前）→「Submitted N job(s), waiting…」（所有 job 提交後），解決 worker 行程生成期間 UI 看似凍結的問題
- **G2-4a**：Report HTML 匯出修正 — matplotlib import 改為 `try/except ImportError`，無 matplotlib 時直方圖顯示佔位提示文字（不影響其餘匯出內容）
- **G2-4b**：Report 圖片匯出加入 `QProgressDialog`（可取消），解決大批次匯出 UI 凍結問題
- **G2-5**：Recipe 編輯器 UI/UX 重構 — `_build_editor()` 改為「Identity 群組（常駐）+ QTabWidget 四 Tab」佈局：Preprocessing / Detection / Strip Mask / Analysis；所有 `self._xxx` 屬性名稱保持不變，`_load_descriptor_to_form()` / `_save_recipe()` 無需修改
- **G2-6**：Annotated 標注數值字體縮小（`max(0.18, h/3200)`）、標籤最小間距 8→6 px、碰撞 lane 縮窄（`//30`）、X offset 緊貼量測線（`+2`）

**影響範圍：**
- `src/core/recipes/cmg_recipe.py`（`_card_to_descriptor()` 補全 17 個欄位）
- `src/core/annotator.py`（字體、間距、lane、offset 常數）
- `src/gui/batch_dialog.py`（早期 progress.emit）
- `src/gui/results_panel.py`（`_NumericItem`、`setSortingEnabled`）
- `src/gui/workspaces/measure_workspace.py`（Save Cards as Recipe 按鈕 + handler）
- `src/gui/workspaces/recipe_workspace.py`（`_build_editor()` 改為 Tab 佈局）
- `src/gui/workspaces/report_workspace.py`（`QProgressDialog` 圖片匯出）
- `src/output/report_generator.py`（matplotlib try/except fallback）

**測試結果：**
- `pytest tests/ -q` → 36/36 通過（無新增測試，改動均為 UI 層與 recipe 輔助邏輯）

**備註：**
- matplotlib 非必要相依，無安裝時 HTML 報告仍可正常輸出（直方圖區塊改為說明文字）
- G2-5 Tab 佈局中 Identity 群組（Name / Target layer / Structure + Axis）永遠顯示於最上方，Tab 區塊下方可視需要滾動

---

## [2026-04-20] Phase F2 — X-Proj 改為 Pitch-Anchored 相位偵測

**變更類型：** Bug 修復 / 演算法替換

**變更摘要：**
- 移除 `detect_mg_column_centers_twopass()`（兩階段獨立峰值偵測），改以 `detect_mg_column_centers_pitch_phase()` 取代
- 新演算法原理：利用已知 MG pitch，對 X-proj 信號做相位搜尋（向量化 reshape → argmax），找出全局最優相位偏移 φ，再以等間距正規網格生成欄位中心。PEPI 貢獻在全局平均中被消除，不再偏移單根峰值
- 三處 call site 同步更新（`cmg_recipe.py`、`measure_workspace.py`、`batch_dialog.py`）
- Batch 模式下每張圖各自獨立偵測，解決不同圖 Start X 偏移的問題

**影響範圍：**
- `src/core/mg_detector.py`（新增 `detect_mg_column_centers_pitch_phase()`，移除 `detect_mg_column_centers_twopass()`）
- `src/core/recipes/cmg_recipe.py`（import + 呼叫更新）
- `src/gui/workspaces/measure_workspace.py`（import + 呼叫更新）
- `src/gui/batch_dialog.py`（import + 呼叫更新）

**測試結果：**
- `pytest tests/ -q` → 36/36 通過

**備註：**
- `xproj_min_pitch_px` 參數在 UI 仍保留（無害），但新演算法不再使用（pitch 由 `col_mask_pitch_px` 決定）
- Edge-padded smoothing（`np.pad(..., mode='edge')`）避免邊界零填充導致的偽峰

---

## [2026-04-20] Phase A vNext 架構升級

**變更類型：** 重構（重大架構升級）

**變更摘要：**
- 引入 Recipe 驅動架構（`BaseRecipe` 抽象介面 + `CMGRecipe` 包裝現有 CMG 演算法）
- 建立統一資料模型：`ImageRecord`、`MeasurementRecord`、`BatchRunRecord`（`src/core/models.py`）
- 建立 `CalibrationManager`（`src/core/calibration.py`，持久化至 `~/.mmh/calibrations/`）
- 建立 `RecipeRegistry`（`src/core/recipe_registry.py`，持久化至 `~/.mmh/recipes/`）
- 建立 `MeasurementEngine`（`src/core/measurement_engine.py`，單張 + batch pipeline）
- 建立相容層 `src/_compat.py`（`MeasurementRecord` → 舊版 `CMGCut` 格式橋接）
- GUI 全面改版為六工作區模式（Browse / Recipe / Measure / Review / Batch / Report）
  - `src/gui/workspace_host.py`（WorkspaceHost + 信號匯流）
  - `src/gui/workspaces/` 六個工作區 Panel
  - `src/gui/main_window.py` 精簡至 ~70 行
- Output 層新增 `_from_records` 系列函式（csv / excel / json / html，保留舊版相容）
- 新增測試：`tests/test_models.py`（6）、`tests/test_recipe_base.py`（12）、`tests/test_measurement_engine.py`（8）
- 更新 `AGENTS.md`（繁體中文重寫，加入 Session Log 規定）
- 更新 `README.md`（繁體中文重寫，反映 Phase A vNext 架構）

**影響範圍：**
- **新增：** `src/core/models.py`、`src/core/calibration.py`、`src/core/recipe_base.py`、
  `src/core/recipes/cmg_recipe.py`、`src/core/recipe_registry.py`、
  `src/core/measurement_engine.py`、`src/_compat.py`、`src/gui/workspace_host.py`、
  `src/gui/workspaces/`（6 個檔案）、`tests/test_models.py`、`tests/test_recipe_base.py`、
  `tests/test_measurement_engine.py`、`SESSION_LOG.md`
- **修改：** `src/gui/main_window.py`、`src/output/_common.py`、`src/output/csv_exporter.py`、
  `src/output/excel_exporter.py`、`src/output/json_exporter.py`、
  `src/output/report_generator.py`、`AGENTS.md`、`README.md`
- **完全未動：** `src/core/cmg_analyzer.py`、`src/core/preprocessor.py`、
  `src/core/mg_detector.py`、`src/core/annotator.py`、`src/core/image_loader.py`、
  `src/gui/batch_dialog.py`、`src/gui/batch_review_dialog.py`、
  `src/gui/control_panel.py`、`src/gui/styles.py`、`main.py`、`requirements.txt`、
  `tests/test_cmg_analyzer.py`

**測試結果：**
- `pytest tests/ -v` → 36 項全數通過
  - `test_cmg_analyzer.py`：10/10
  - `test_models.py`：6/6
  - `test_recipe_base.py`：12/12
  - `test_measurement_engine.py`：8/8

**備註：**
- Phase B 優先項目：Batch 結果快取持久化、Review Accept/Reject 工作流程、ReportWorkspace 嵌入式直方圖
- `src/_compat.py` 為過渡期產物，Phase B 後應逐步減少依賴
- Windows 上 `ProcessPoolExecutor` 已由 `main.py` 的 `if __name__ == "__main__"` 保護
