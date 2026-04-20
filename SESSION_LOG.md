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
