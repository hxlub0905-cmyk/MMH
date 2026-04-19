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
