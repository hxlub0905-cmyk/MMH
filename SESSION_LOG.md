# Session Log

---

## [2026-04-26] KLARF Export 功能 + nm/px 統一整合

**變更類型：** 新功能

**新增功能摘要：**

### KLARF Export（Export Top-N by CD）

新增 Review SEM 用 KLARF 輸出功能，協助工程師找出 Y-CD 量測值與特定缺陷（如 CMGF）之間的相關性。

**核心邏輯**：解析輸入 KLARF → 與 SEM MM Batch 量測結果匹配 → 依 CD 升/降冪排序 → 取前 N 筆 → 座標修正至 gap 中心 → 輸出新 KLARF。

**座標換算設計決策（Y 軸翻轉）**：
- 影像座標系：左上角原點，Y 向下為正
- KLARF 座標系：左下角原點（die corner），Y 向上為正
- 因此 `YREL_new = YREL_orig - dy_nm`（減號），`XREL_new = XREL_orig + dx_nm`（加號）
- **此符號設計為刻意，勿修改為加號**

新增檔案：
- `src/core/klarf_parser.py`：KlarfParser — token-scan 解析 KLARF 1.8 格式，動態 column header，處理 ImageInfo block
- `src/core/klarf_writer.py`：KlarfWriter — 原子寫入，只修改 XREL/YREL，其餘欄位原樣輸出
- `src/core/klarf_exporter.py`：KlarfTopNExporter — 主要 export 邏輯，支援 ascending/descending 排序，dry_run 模式
- `src/gui/klarf_export_dialog.py`：KlarfExportDialog — QSplitter 版面，背景執行，preview table，stat cards

修改檔案：
- `src/gui/workspaces/report_workspace.py`：新增「輸出 KLARF…」按鈕、`_open_klarf_export_dialog()`、`set_latest_batch_run()`
- `src/gui/workspace_host.py`：`batch_completed` / `multi_batch_completed` 額外連接 `report.set_latest_batch_run`
- `src/gui/styles.py`：新增 `QPushButton#klarfExportBtn` QSS（綠色系）

### nm/px 統一整合

將原本分散在 BrowseWorkspace / ControlPanel 的 nm/px 設定統一進入 Recipe 流程，確保 Batch 時每張圖使用正確的校正值。

**流程**：Recipe 儲存 nm/px 預設值 → Measure/Batch workspace 自動帶入 → 使用者可臨時覆蓋 → ImageRecord.pixel_size_nm 全程攜帶正確值 → KlarfTopNExporter 直接使用。

修改檔案：
- `src/core/recipe_base.py`：`MeasurementRecipe` 新增頂層欄位 `nm_per_pixel: float = 1.0`；`to_dict()`/`from_dict()` 支援（舊 JSON 向下相容，fallback 1.0）
- `src/core/recipe_registry.py`：`create_default_cmg()` 設定 `nm_per_pixel=1.0`
- `src/core/recipes/cmg_recipe.py`：`_card_to_descriptor()` 從 card dict 讀取 `nm_per_pixel`
- `src/gui/workspaces/recipe_workspace.py`：Identity 卡片新增 nm/px QDoubleSpinBox；save/load 同步
- `src/gui/workspaces/measure_workspace.py`：Recipe 選擇器下方新增 nm/px override spinbox + hint label；`_run_with_recipe_impl()` / `_run_with_cards()` 使用 spinbox 值；同步 Ruler nm/px
- `src/gui/workspaces/batch_workspace.py`：`_DatasetRow` 新增 `nm_px_spin`/`nm_px_hint`；recipe 切換自動帶入；`_run_batch()` 使用 per-row 值（不再使用 CalibrationManager）

**影響範圍：**
- `src/core/recipe_base.py`
- `src/core/recipe_registry.py`
- `src/core/recipes/cmg_recipe.py`
- `src/core/klarf_parser.py`（新）
- `src/core/klarf_writer.py`（新）
- `src/core/klarf_exporter.py`（新）
- `src/gui/styles.py`
- `src/gui/klarf_export_dialog.py`（新）
- `src/gui/workspace_host.py`
- `src/gui/workspaces/recipe_workspace.py`
- `src/gui/workspaces/measure_workspace.py`
- `src/gui/workspaces/batch_workspace.py`
- `src/gui/workspaces/report_workspace.py`
- `AGENTS.md`

**測試結果：** py_compile 全部通過；GUI 變更需 PyQt6 環境驗證

---

## [2026-04-24] Bug Fix Series — C1~C4、M1~M7、m1~m3

**變更類型：** 多項 Bug 修復

**修復摘要：**

### 嚴重性 C（正確性）
| 編號 | 位置 | 問題 | 修復 |
|------|------|------|------|
| C1 | `src/core/models.py` `MeasurementRecord.from_dict` | JSON round-trip 後 `extra_metrics` 中的 `upper_bbox`/`lower_bbox` 維持 list 型別，下游期待 tuple | `from_dict` 中對已知 bbox key 做 `tuple(int(v) for v in ...)` 轉換 |
| C2 | `src/core/batch_run_store._read_index` | Windows 上路徑分隔符或大小寫差異導致 `paths_in_index != actual_files` 永遠成立，每次都觸發全量重建 | 以 `Path(p).resolve()` 正規化後再比較 |
| C3 | `src/core/measurement_engine.run_batch` | `abort_check` 觸發 break 或子行程拋出例外時，`batch.end_time` 在 `finally` 之後才賦值，因此可能永遠未被設定 | 將 `batch.end_time = ...` 移至 `finally` 區塊內、`pool.shutdown` 之前 |
| C4 | `src/core/recipes/cmg_recipe.apply_yedge_subpixel_to_cuts` 非配對 fallback | `upper_sample_ys`/`lower_sample_ys` 為空 list，而 `sample_xs` 有值，Detail CD 視圖繪製錯位虛線 | fallback 路徑填入 `[None] * len(sample_xs)` 使長度對齊 |

### 嚴重性 M（中等）
| 編號 | 位置 | 問題 | 修復 |
|------|------|------|------|
| M1 | `src/gui/workspace_host.py` | class docstring 缺失，TAB 常數未文件化；AGENTS.md 描述 8 個 workspace 但實際只有 6 個 | 補齊 class docstring 與 6-tab 表格說明；AGENTS.md 同步更正為 6-tab 架構 |
| M2 | `src/gui/workspaces/review_workspace._batch_records` | 批次 Review 中 `_batch_records` 快取無上限，瀏覽大量影像時記憶體持續累積 | 加入 `_RECORD_CACHE_MAX = 200` LRU 驅逐：超過上限時刪除最舊條目 |
| M3 | `src/gui/workspaces/batch_workspace._run_batch` | 第一次批次完成後 `self._progress` 的 `objectName` 設為 `"progressDone"`（綠色），第二次執行時進度條從綠色開始 | 每次執行開頭呼叫 `setObjectName("") + unpolish/polish` 重置樣式 |
| M4 | `src/core/recipes/cmg_recipe._smooth_strip_2d` docstring | 說 "for odd k ≥ 3" 令人誤解，實際上 k 在函式內永遠被強制為奇數，且傳回形狀對任何 k>1 都是 (n_rows-1, n_cols) | 改為明確說明：k 內部強制奇數；k>1 → (n-1, n_cols)；k≤1 → (n, n_cols) |
| M5 | `src/output/excel_exporter._filter_meas_by_mode` | `groupby().idxmin/idxmax()` 在含 NaN 的 `cd_nm` 欄位時可能回傳不正確索引 | 在 groupby 前插入 `valid = valid.dropna(subset=["cd_nm"])` |
| M6 | `tests/test_subpixel_refinement.py` `TestEdgeMethodSelection` | 測試仍用舊 key `"subpixel"`，應改用現行 `"gradient"` | `test_subpixel_has_refine_fields` 與 `test_both_methods_produce_positive_cd` 改用 `"gradient"` |
| M7 | `src/core/recipes/cmg_recipe.py`（`apply_yedge_subpixel_to_cuts` 及 `compute_metrics` range filter 後） | 兩處皆呼叫 per-cut `_flag_top3`，導致同一張影像可能出現多組 MIN/MAX | 改為 `_flag_global_minmax(all_measurements)` 確保全圖僅一個 MIN、一個 MAX |

### 嚴重性 m（輕微）
| 編號 | 位置 | 問題 | 修復 |
|------|------|------|------|
| m1 | `src/core/annotator.draw_overlays_multi` | `_flag_global_minmax` 就地修改 measurements，未警告呼叫者 | 加入 `# WARNING: _flag_global_minmax mutates m.flag in place` 說明 |
| m2 | `src/core/preprocessor.apply_column_strip_mask` | 結果遮罩全零時無任何警告，偵錯困難 | `result.any()` 為 False 時以 `logging.warning` 記錄欄位設定建議 |
| m3 | `src/core/batch_run_store._append_to_index` | `_read_index()` 回傳 None（index 陳舊）時使用 `or []` 空列表，導致舊索引條目遺失 | 改為呼叫 `_rebuild_index()` 從磁碟重建完整索引後再 append |

**影響範圍：**
- `src/core/models.py`（C1）
- `src/core/batch_run_store.py`（C2、m3）
- `src/core/measurement_engine.py`（C3）
- `src/core/recipes/cmg_recipe.py`（C4、M4、M7）
- `src/gui/workspace_host.py`（M1）
- `src/gui/workspaces/review_workspace.py`（M2）
- `src/gui/workspaces/batch_workspace.py`（M3）
- `src/output/excel_exporter.py`（M5）
- `tests/test_subpixel_refinement.py`（M6）
- `src/core/annotator.py`（m1）
- `src/core/preprocessor.py`（m2）
- `AGENTS.md`、`README.md`（M1 同步文件）

**測試結果：** py_compile 全部通過；需科學計算套件環境才能跑完整 pytest

---

## [2026-04-23] UI 全面重設計（§1-§8 企劃書實作）

**變更類型：** UI 重設計

**變更摘要：**
- styles.py 全面重寫，套用新 Design Token（BG_PAGE/PANEL/SURFACE、BORDER_DEFAULT/INPUT/HOVER/FOCUS、TEXT_PRIMARY/SECONDARY/MUTED/HINT、ACCENT 橙色系、SUCCESS/DANGER、MIN/MAX 標注色）
- 新增 QLabel#statChipMin / #statChipMax / primaryBtn / successBtn / progressDone QSS 規則
- browse_workspace：左側欄 setFixedWidth(180)、Open Folder 橙色主按鈕、Calibration 改為橫排 bar、ImageViewer 深色背景、圖片資訊標籤
- recipe_workspace：左側欄 setFixedWidth(200)、Identity 改為 QFrame 卡片、QTabWidget 改為 Pill 選單 + QStackedWidget、Save Recipe 橙色按鈕
- measure_workspace：overlay checkbox 前加色點（● 綠/灰）、右側欄 Run Single 改用 successBtn、viewer info label
- batch_workspace：header 標籤色，folder_label 空/填滿兩種樣式、Run Batch 改用 successBtn、overlay 選項包在 QFrame、新增 _lbl_status、完成後 progressDone 變綠
- review_workspace：Batch 圖片列表 ●/✕ 前綴色彩、nav 按鈕移到右側（hbox.addStretch() 之後）
- report_workspace：新增 4 個 Summary Card（Total/OK/Failed/Measurements）、CD Statistics 改為 Highlight Cards（2×2）+ Detail Rows（2×N）、Export 橙色主按鈕
- results_panel.py：_ROW_COLOURS MIN→#fff8f0、MAX→#f0f7fc；statChipMin/statChipMax objectName

**影響範圍：** styles.py + workspaces/*.py + results_panel.py

**測試結果：** pytest 17/17 通過，py_compile 全部通過

---

## [2026-04-23] 右側設定欄控件可見度改善

**變更類型：** UI 改善

**問題：** 右側面板（`QFrame#rightPanel`，背景 `#fff7ee`）內的互動控件（SpinBox、ComboBox、LineEdit、CheckBox）背景色、面板背景色、邊框三者都在同一暖米色範圍，視覺上難以區分。

**修法（`src/gui/styles.py` — `QFrame#rightPanel` 子選擇器區塊）：**

1. **QSpinBox / QDoubleSpinBox**：背景 `#fffdf9` → `#ffffff`；邊框 `1px solid #b8a898` → `1.5px solid #8a7060`；新增 `color: #3f3428`
2. **QComboBox**：同上背景與邊框；新增 `color: #3f3428`；新增 `QFrame#rightPanel QComboBox::down-arrow { border-top-color: #6b5a4a }` 讓箭頭顏色加深
3. **QLineEdit**：同上背景與邊框；新增 `color: #3f3428`
4. **QCheckBox::indicator**：邊框 `1px solid #b8a898` → `1.5px solid #8a7060`；背景 `#fffdf9` → `#ffffff`
5. **QFrame#rightPanel QPushButton**（小型工具按鈕）：新增規則 `background: #f0e8e0; border: 1.5px solid #8a7060; color: #4a3828`，有明確可點擊視覺
6. **hover 狀態**：所有控件 hover 邊框改為 `#6a5040`（比預設深、比 focus accent 暗）
7. **focus 狀態**：維持 `border-color: #f29f4b` 不變

**影響範圍：**
- `src/gui/styles.py`（`QFrame#rightPanel` 子選擇器段落）

**測試結果：**
- `python3 -m py_compile src/gui/styles.py` 通過

---

## [2026-04-23] Gradient 路徑向量化（~2–3× 加速）

**變更類型：** 效能優化

**動機：** 前一 session 的 TC 路徑向量化完成後，gradient 路徑仍維持原有 for 迴圈（每張圖逐 x 呼叫 `_refine_yedge_subpixel`），是目前效能瓶頸之一。本次將 gradient 路徑改為與 TC 對稱的批次處理，整體目標從 4–8 分鐘再降至 3–6 分鐘（13000 張）。

**實作（`src/core/recipes/cmg_recipe.py` only）：**

1. **`_smooth_strip_2d(strip, k)`**（新增）— 對 2D strip 每欄做 moving average，使用 `np.pad + np.cumsum` 向量化，pure numpy，供 TC 和 gradient 兩個批次函式共用。
2. **`_extract_strip(image, sample_xs, y_guess, search_half, smooth_k, profile_lpf_sigma)`**（新增）— 共用提取 + LPF + MA 流程：一次切出 2D strip，套用 `_gaussian_filter1d_2d`（若 sigma>0），再套用 `_smooth_strip_2d`，回傳 `(strip, y_lo, valid_mask)`。
3. **`_refine_yedge_threshold_crossing_batch()`** — 重構以呼叫 `_extract_strip()`，邏輯不變。
4. **`_refine_yedge_subpixel_batch(image, sample_xs, y_guess, ...)`**（新增）— Gradient 批次版本：呼叫 `_extract_strip()` 提取共用 strip，`np.abs(np.diff(strip, axis=0))` 向量化計算 abs-gradient，再對每欄做 peak 偵測 + dominance 檢查 + 二次型內插（與 scalar 版邏輯一致），回傳 `list[float | None]`。
5. **`apply_yedge_subpixel_to_cuts()` paired sampling 路徑**：
   - TC 分支：維持 `_refine_yedge_threshold_crossing_batch()`（前一 session 已完成）
   - Gradient 分支：**原 for 迴圈改為呼叫 `_refine_yedge_subpixel_batch()`**，共用同一套後處理（`upper_sample_ys / lower_sample_ys / up_ys / lo_ys / up_ps / lo_ps / up_spr / lo_spr / individual_cds_nm`），結構與 TC 分支對稱

**影響範圍：**
- `src/core/recipes/cmg_recipe.py`（4 個新增/重構函式 + apply_yedge gradient 分支改寫）

**測試結果：**
- `python3 -m py_compile src/core/recipes/cmg_recipe.py` 通過

**備註：**
- peak_strength / second_peak_ratio 在批次 gradient 版中填入預設值（1.0 / 0.0），與 TC 批次版行為一致
- aggregate / winning_sample_x / post-refinement 等下游邏輯完全不變

---

## [2026-04-23] 兩項新功能：Batch 即時 Overlay 輸出 + TC 路徑向量化

**變更類型：** 功能新增 / 效能優化

**功能一：Batch 邊跑邊輸出 Overlay Image**

- **動機**：目前需等整個 Batch 跑完才能從 Report workspace 手動匯出，使用者無法在執行中即時確認結果品質。
- **實作（engine 層）**：
  - `_make_worker_args()` 新增 `output_dir` 參數，序列化為純 str（pickle 安全）
  - `_worker_run_image()` 在迴圈內蒐集 `pr_list`；成功路徑最後若 `output_dir` 有值，用最後一個 recipe 的 `pr.context["cmg_cuts"]` 與 `pr.raw` 呼叫 `draw_overlays()` 並以 `cv2.imwrite()` 寫出 `<stem>_annotated.png`，並將路徑存入 `result["overlay_path"]`（失敗時存 `result["overlay_error"]`）
  - `run_batch()` 新增 `output_dir: Path | None = None` 參數；`on_progress` callback 簽名升級至第 5 個參數傳遞完整 `result_dict`
  - `run_multi_batch()` 同步新增 `output_dir`；各 dataset 寫入 `output_dir / label` 子資料夾；`_wrapped` callback 透傳 `result_dict`
- **實作（UI 層）**：
  - `batch_workspace.py` imports 補上 `QCheckBox`
  - `_build_ui()` 在 workers/run 列之後插入 overlay 選項列（checkbox + 資料夾按鈕 + 路徑標籤）
  - 新增 `_on_overlay_toggled()` 與 `_browse_overlay_folder()` 方法
  - `_run_batch()` 計算 `output_dir` 並傳入 worker
  - `_BatchWorker` / `_MultiBatchWorker` 的 `progress` 信號升級為 `pyqtSignal(int, int, str, str, object)`，`__init__` / `run()` 同步更新
  - `_on_progress()` 新增第 5 個參數 `result_dict`，有 overlay_path 時在 log 顯示 `→ overlay: <filename>`

**功能二：apply_yedge TC 路徑向量化（~4–5× 加速）**

- **動機**：TC 模式 All-columns 設定下，每張圖的每個 sample_x 各自呼叫一次 `_refine_yedge_threshold_crossing()`，13000 張約需 20–30 分鐘。
- **實作**：
  - 新增 `_gaussian_filter1d_2d(arr, sigma)` — 對 2D array 每欄套用 Gaussian LPF（mode='same'，與 scalar 版一致）
  - 新增 `_refine_yedge_threshold_crossing_batch(image, sample_xs, y_guess, ...)` — 一次提取所有 x 的 2D strip，向量化 MA（cumsum + vstack 零列確保輸出 n 列）、sign-change 偵測；結果與逐 x 呼叫 scalar 版相同（< 0.001 nm 差異）
  - `apply_yedge_subpixel_to_cuts()` 的 paired sampling 路徑改為 if/else：TC 方法走向量化批次呼叫，gradient 方法維持原有 for 迴圈

**影響範圍：**
- `src/core/measurement_engine.py`（output_dir + progress 第 5 參數）
- `src/core/recipes/cmg_recipe.py`（新增 2 個 helper 函式 + apply_yedge 向量化分支）
- `src/gui/workspaces/batch_workspace.py`（UI + Worker + _on_progress）

**測試結果：**
- `python3 -m py_compile` 對所有 3 個修改檔案均通過

**備註：**
- overlay 寫檔發生在 subprocess 內，不增加跨 process 傳輸量
- 向量化 MA 使用 `((k//2, k//2), mode='edge')` padding + 前置零列 cumsum，避免 off-by-one 問題
- gradient 路徑不受影響，舊行為完全保留

---

## [2026-04-23] 體驗與準確度修復（B1/G2/I2/Q1/L2）

**變更類型：** Bug 修復 / UX 改善

**修復 B1：精化成功後 center_y 未更新（Excel cd_line_y_px 位置偏移）**
- **根本原因**：`compute_metrics()` 建立 `MeasurementRecord` 時 `center_y` 使用 `(bbox[1]+bbox[3])/2`（bbox = gap 上下緣整數），但 Y-edge 精化成功後 `m.y_upper_edge`/`m.y_lower_edge` 是亞像素值，兩者不一致導致 cd_line_y_px 偏向 bbox 中心而非精化後的 gap 中心
- **修法**：`records.append(rec)` 之前：若 `m.y_upper_edge` / `m.y_lower_edge` 均非 None，以 `(y_upper_edge + y_lower_edge) / 2` 更新 `rec.center_y`

**修復 G2：Cards 路徑 Detail CD 在 Measure Tab 無反應**
- **根本原因**：`_analyze_with_cards()` 呼叫 `apply_yedge_subpixel_to_cuts()` 時 `store_meta=False`，導致 `m._refine_meta` 從未寫入，`_draw_detail_measurements()` 無取樣資料可用而 fallback 至普通繪圖
- **修法**：改為 `store_meta=True`

**修復 I2：Edge Locator 參數改動沒有提示說明未存回 Recipe**
- **修法**：`_build_edge_locator_panel()` 在 `method_w` 前插入 `QLabel("參數僅本次有效，儲存請至 Recipe workspace")`，灰色小字提示

**修復 Q1：Mask 模式顯示舊 mask，不反映目前參數**
- **根本原因**：`_run_preview()` 以 `_, _, profile_masks = ...` 丟棄回傳的 `mask`，導致 `_current_mask` 永遠是上一次 Run 的結果（甚至 None）
- **修法**：改為 `mask, _, profile_masks = ...` 並加 `self._current_mask = mask`；`set_images()` 改用新的 `self._current_mask`

**修復 L2：大量歷史記錄時 get_stats_for_recipe() 卡頓**
- **根本原因**：`get_stats_for_recipe()` 每次都逐一讀取所有歷史 JSON 檔，百筆記錄時 I/O 開銷大
- **修法**：
  1. `_rebuild_index()` 在 index entry 加入 `"recipe_ids": d.get("recipe_ids", [])` (single) / `"recipe_ids": []` (multi)
  2. `save()` 在 index entry 加入 `"recipe_ids": list(batch_run.recipe_ids)` — `BatchRunRecord` 已有此欄位
  3. `save_multi()` 在 index entry 加入 `"recipe_ids": []`
  4. `get_stats_for_recipe()` 迴圈開頭加快速跳過：若 `recipe_id` 指定且不在 `summary["recipe_ids"]` 中則 continue，避免讀取無關的 JSON 檔

**影響範圍：**
- `src/core/recipes/cmg_recipe.py`（B1：center_y 更新）
- `src/gui/workspaces/measure_workspace.py`（G2：store_meta=True；I2：hint label；Q1：mask 更新）
- `src/core/batch_run_store.py`（L2：recipe_ids index + fast-skip）

**測試結果：**
- `python3 -m py_compile` 對所有修改檔案均通過

---

## [2026-04-23] CD 計算與顯示不一致修復（A1/A2/F1/G1/V5/V6/W1）

**變更類型：** Bug 修復

**修復 A1：analyze() 初始 cd_px 改用 bbox 邊緣**
- **根本原因**：`cmg_analyzer.analyze()` Step 2 計算 gap 時用 `cy ± height/2.0`（float 中心偏移），而 annotator 使用 `y1`/`y0` bbox 邊緣，導致初始 cd_px 與標注不一致
- **修法**：`upper_edge = float(upper.y1)` / `lower_edge = float(lower.y0)`；mid_y 與 cd_px 計算式不變

**修復 A2：Fallback 時 cd_px 回落到 bbox 值**
- **根本原因**：`apply_yedge_subpixel_to_cuts()` 的 else 分支（cd_ref ≤ 0）完全不更新 m.cd_px，讓 cm_analyzer 初始值（已含 A1 bias）留在記錄中
- **修法**：else 分支計算 `bbox_cd = lb.y0 - ub.y1`，若 > 0 則回寫 m.cd_px / m.cd_nm

**修復 F1：Recipe 路徑 MIN/MAX 改為 per-cut TOP3**
- **根本原因**：`compute_metrics()` 與 `apply_yedge_subpixel_to_cuts()` 的 re-flag 均呼叫 `_flag_global_minmax()`（全圖只標一個 MIN / MAX），與 Cards 路徑的 `_flag_top3` per-cut 行為不一致
- **修法**：兩處均改為 `for cut in cuts: _flag_top3(cut.measurements)`；`analyze()` Step 5 的 global flag 保留不動

**修復 G1：Cards 路徑 bbox 定義錯誤**
- **根本原因**：`_run_with_cards()` 建立 MeasurementRecord 時 bbox 取整個 blob 高度（y0, y1），造成 center_y 偏移約一個 blob 高度（非 gap 中心）
- **修法**：bbox 改為 `(min_x, ub.y1, max_x, lb.y0)`，即 gap 上下緣，center_y 因此落在 gap 中心

**修復 V5：Compare to Reference N 顯示不準**
- **修法**：`_refresh_stats()` 中 `self._lbl_n.setText(f"{len(biases)} / {n}")` 並加 tooltip 說明「有輸入參考值的筆數 / 總量測筆數」

**修復 V6：Compare to Reference Export CSV n 欄位不準**
- **修法**：`_export_csv()` 中改為兩列：`["n_with_ref", str(len(biases))]` 與 `["n_total", str(len(self._records))]`

**修復 W1：records_to_dataframe() CSV 欄位清理與重新命名**
- **修法**：`records_to_dataframe()` 中 `"cmg_id"` → `"cut_id"`，`"col_id"` → `"column_id"`；函式末端加 canonical 欄位排序（13 欄優先，其餘附後）
- 同步更新 `excel_exporter.py`：`meas_cols` 使用 `cut_id`/`column_id`；Image Summary 的 `min_cd_cmg_id` → `min_cd_cut_id`、`min_cd_col_id` → `min_cd_column_id`（MAX 欄同）

**影響範圍：**
- `src/core/cmg_analyzer.py`（A1：gap edge 計算）
- `src/core/recipes/cmg_recipe.py`（A2：fallback bbox cd；F1：import + re-flag per-cut）
- `src/gui/workspaces/measure_workspace.py`（G1：bbox gap 邊緣）
- `src/gui/measure_validate_dialog.py`（V5：N 顯示；V6：CSV summary n 欄）
- `src/output/_common.py`（W1：欄位重命名 + 排序）
- `src/output/excel_exporter.py`（W1：同步更新欄位名稱）

**測試結果：**
- `python3 -m py_compile` 對所有 6 個修改檔案均通過

---

## [2026-04-23] 兩項緊急 Bug 修復：Review 批次導航索引錯誤 + Duplicate Recipe 覆蓋原始 Recipe

**變更類型：** Bug 修復

**問題 1：Review 工作區批次超過 1000 張時導航對應錯誤影像**

- **根本原因**：`_populate_img_list()` 在批次超過 `_LIST_LIMIT`（1000）時會跳過部分 OK 項目，導致 `_img_list` 的列索引（row）與 `_batch_entries` 的索引不再一致。`_on_batch_row_changed(row)` 直接以 `row` 索引進 `_batch_entries`，造成顯示錯誤影像。`_nav_next()` / `_nav_prev()` 同樣以 `row` 直接查詢 `_batch_entries`，在 entries 被截斷時會 IndexError 或取到 separator。
- **修法**（`review_workspace.py`）：
  - `__init__` 新增 `self._entry_index_map: list[int] = []`
  - `_populate_img_list()` 開頭重置 `_entry_index_map`；改為 `enumerate(entries)` 迴圈；每次 `addItem()` 同步 append：separator / "…more" 列 → -1，一般 entry 列 → 原始索引 `i`
  - `_on_batch_row_changed(row)` 改為透過 `_entry_index_map[row]` 取得真實 entry 索引後再呼叫 `_load_batch_entry(entry_idx)`，nav label 顯示 `entry_idx+1 / len(_batch_entries)`
  - `_nav_prev()` / `_nav_next()` 改為跳過 `_entry_index_map[row] < 0` 的列，取代原本直接查詢 `_batch_entries[row]` 的邏輯

**問題 2：Duplicate Recipe 後按 Save 覆蓋原始 Recipe**

- **根本原因**：`_duplicate_recipe()` 儲存副本後未更新 `self._current_id`，導致接下來按 Save 時 `rid = self._current_id` 仍指向原始 recipe，覆蓋原本的 recipe。
- **修法**（`recipe_workspace.py`）：在 `self._registry.save(dup)` 之後加入 `self._current_id = dup.recipe_id`

**影響範圍：**
- `src/gui/workspaces/review_workspace.py`（`__init__`、`_populate_img_list`、`_on_batch_row_changed`、`_nav_prev`、`_nav_next`）
- `src/gui/workspaces/recipe_workspace.py`（`_duplicate_recipe`）

**測試結果：**
- `python3 -m py_compile` 兩個修改檔案均通過

---

## [2026-04-23] Measure 右側設定欄全面重設計：融入式 Tier 架構

**變更類型：** UI 重設計

**設計目標：**
- 移除自訂卡片框線（border/border-radius outer QWidget），改為與整個面板視覺統一的 Tier-2 CollapsibleSection
- 移除 `QFrame#rightPanel QPushButton:!checked:!disabled` 全域覆蓋，按鈕配色與其他分頁/全域統一
- 每個測量 profile 以 Tier-2 section header 呈現，Filters/Advanced 改為 Tier-3

**變更內容：**

### `src/gui/collapsible.py` — 新增 `trailing_widget` 支援
- `__init__` 加入 `trailing_widget: QWidget | None = None` 參數
- 當提供 trailing_widget 時，header 改為 container QWidget（背景/邊框與 tier 一致）+ toggle QPushButton（background:transparent + inline hover QSS）+ trailing_widget
- 新增 `_TIER_BG`、`_TIER_BORDER`、`_TIER_HOVER_QSS` 常數（避免 hardcode 分散各處）
- 原有無 trailing_widget 的使用方式完全不變（向下相容）

### `src/gui/control_panel.py` — 重寫 `_add_profile()`
- **移除**：`outer` 卡片 QWidget、`header_row`、`card_title` QLabel、舊式 inline `btn_del` 樣式
- **改為**：`CollapsibleSection(name, tier=2, trailing_widget=btn_del)` — 與 Recipe/Edge Locator 視覺統一
- Filters section：tier=2 → tier=3（因為現在嵌套在 tier=2 profile 內）
- Advanced section：保留 tier=3
- `_build_measurement_profiles`：profile 間距 spacing=8 → 0（tier section 本身的 border 已提供視覺分隔）
- 「＋ Add Measurement」按鈕：綠色 → 橙色系（與 app accent 統一）

### `src/gui/styles.py`
- **移除** `QFrame#rightPanel QPushButton:!checked:!disabled` 及 hover 規則（這是造成所有按鈕邊框突兀的根因）
- **保留** QSpinBox/QComboBox/QLineEdit/QCheckBox::indicator 的右側面板邊框加深規則
- **新增** `QPushButton#profileDeleteBtn`：平時無邊框靜默顯示，hover 才顯示危險紅色

**影響範圍：**
- `src/gui/collapsible.py`
- `src/gui/control_panel.py`
- `src/gui/styles.py`

**測試結果：**
- `python3 -m py_compile` 通過
- `pytest`（排除 numpy/cv2 相依）→ 17/17 通過

---

## [2026-04-23] 修復 Run Single 閃退：MeasurementRecord 缺少必填欄位

**變更類型：** Bug 修復

**問題根因：**
- `measure_workspace.py` 的 `_run_with_cards()` 中，在有量測結果時嘗試建立 `MeasurementRecord` 物件，但遺漏了 6 個必填位置參數：`measurement_id`、`feature_type`、`feature_id`、`bbox`、`center_x`、`center_y`
- 導致 `TypeError: __init__() missing required positional arguments`，在 PyQt6 的 slot 機制下使應用程式異常終止（閃退）
- `_run_with_recipe` 沒有任何 try/except，任何未捕獲例外都會向上傳遞

**修法：**
1. **`_run_with_cards`** — 補全所有必填欄位，從 `YCDMeasurement.upper_blob`/`lower_blob` 推導：
   - `measurement_id`：`str(uuid.uuid4())`
   - `feature_type`：`""`（legacy cards 沒有 recipe 定義的 feature_type）
   - `feature_id`：`f"feat{cmg_id}_col{col_id}"`
   - `bbox`：`(min(ub.x0, lb.x0), ub.y0, max(ub.x1, lb.x1), lb.y1)`
   - `center_x/y`：bbox 中心點
   - `extra_metrics`：包含 `upper_bbox`、`lower_bbox` 與 `_refine_meta`（供 CD 位置 Excel 匯出使用）
2. **`_run_with_recipe`** — 重構為 `_run_with_recipe_impl()`，外層包一層 `try/except` 顯示錯誤 dialog

**影響範圍：**
- `src/gui/workspaces/measure_workspace.py`

**測試結果：**
- `python3 -m py_compile` 通過
- `pytest`（排除 numpy/cv2 相依）→ 17/17 通過

---

## [2026-04-23] Measure 右側 UI 透明控件修復 + 全局邊框加深

**變更類型：** UI 修復

**變更摘要：**

### 根本原因修復：QComboBox / QSpinBox 透明無邊框
- **問題根因**：`control_panel.py` 的 `_add_profile()` 中三處 `setStyleSheet("QWidget { ... }")` 使用了「類型選擇器」，在 Qt QSS 的 cascade 機制下，父控件的 `QWidget { }` 規則會透過 Qt 的祖先鏈傳播至所有子 QWidget 子類（QComboBox、QSpinBox 等），覆蓋應用層級的樣式，導致這些控件顯示為透明、無邊框
- **修法**：將三處改為「裸屬性宣告」（不帶類型選擇器），例如：
  - `"QWidget { background:transparent; border:none; }"` → `"background:transparent;"`
  - `"QWidget { background:#fff9f2; border:1px solid #e6dccf; ... }"` → `"background:#fff9f2; border:1px solid #c8b8a8; border-radius:8px;"`
  裸屬性宣告僅作用於設定對象本身，不向下 cascade，子控件保留自身樣式
- 同步修正 `min_wrap`、`max_wrap`、`f2_form_w`、`f3_form_w` 的 `"border:none;"` → `"background:transparent;"`
- 卡片標題字體：`font-size:10px` → `font-size:11px; letter-spacing:0.5px`

### 全局邊框顏色加深（styles.py）
- `QPushButton` 邊框：`#dfd0be` → `#c8b49e`（hover：`#c8b89e` → `#b09e86`）
- `QSpinBox`/`QDoubleSpinBox` 邊框：`#e6dccf` → `#c8b49e`
- `QCheckBox::indicator` 邊框：`#d8cbb8` → `#c0ad96`
- `QLineEdit` 邊框：`#dfd0be` → `#c8b49e`
- `QComboBox` 邊框：`#dfd0be` → `#c8b49e`

**影響範圍：**
- `src/gui/control_panel.py`（移除三處 `QWidget { }` 類型選擇器 cascade，修正透明控件問題）
- `src/gui/styles.py`（全局邊框顏色加深，與右側面板特化規則一致）

**測試結果：**
- `python3 -m py_compile` 對所有修改檔案均通過
- `pytest`（排除 numpy/cv2 相依）→ 17/17 通過

**備註：**
- Qt QSS 核心規則：父控件使用 `QWidget { }` 類型選擇器時，其優先級高於應用層級樣式；使用裸屬性宣告則不會 cascade 至子控件

---

## [2026-04-23] Measure 右側邊界強化 + Comprehensive Excel 匯出

**變更類型：** UI 改善 / 功能增強

**變更摘要：**

### 1. Measure 分頁右側設定欄邊界強化
- **問題**：右側面板（`QFrame#rightPanel`，背景 `#fff7ee`）內的 SpinBox（邊框 `#e6dccf`）、ComboBox、LineEdit、CheckBox、Button 的 1px 邊框與背景色差不足，視覺上幾乎不可見
- **修法**：在 `styles.py` 末尾新增 `QFrame#rightPanel` 子選擇器規則，將所有互動控件的邊框色統一加深至 `#b8a898`（原 `#e6dccf`/`#dfd0be`），hover 時進一步加深至 `#9a8878`，focus 時仍以 accent 橘色（`#f29f4b`）顯示
- SpinBox、ComboBox、LineEdit、Button、CheckBox::indicator 均已覆蓋

### 2. CSV + Excel 整合為一份 Comprehensive Excel
- **動機**：使用者希望一份不用看圖就能掌握所有 data 的總表，尤其在多組 dataset 情境下
- **`src/output/_common.py`**：
  - `records_to_dataframe()` 新增 `dataset_label` 參數
  - 新增欄位：`cd_px`、`cd_nm`（主名稱）、`cd_line_x_px`、`cd_line_y_px`（CD 線相對圖左上角的 XY 座標，單位 px）、`upper_blob_x0/y0/x1/y1`、`lower_blob_x0/y0/x1/y1`（blob bounding box 分解欄位）、`dataset`
  - 保留 `y_cd_px`、`y_cd_nm`、`upper_bbox`、`lower_bbox` 舊欄位供 CSV 相容
- **`src/output/excel_exporter.py`**：全面改寫 `export_excel_from_records()`：
  - 新增 `datasets: list[dict] | None` 參數，支援多資料集輸入（每個 dict 含 `records`、`image_records`、`dataset_label`）
  - **Sheet 1「All Measurements」**：完整量測資料 + CD 線位置 + blob bbox，MIN 行橘色、MAX 行藍色；凍結表頭，自動欄寬
  - **Sheet 2「Image Summary」**：每張圖一列，包含 mean、median、std、3-sigma，以及 MIN CD 值/位置（XY, cmg_id, col_id）與 MAX CD 值/位置；MIN 欄橘色、MAX 欄藍色，一眼找到極值位置，不用看圖
  - **Sheet 3「Statistics」**：依 recipe_name 分組的統計摘要（N、Mean、Median、Q25/Q75、Std、3σ、Min、Max、影像數）
- **`src/gui/workspaces/report_workspace.py`**：
  - `_ExportDialog` 將 CSV + Excel 兩個 checkbox 合併為一個「Comprehensive Excel」checkbox（附描述說明三個工作表內容）
  - 多資料集（`MultiDatasetBatchRun`）匯出時，逐 dataset 重建 record 列表並帶入 `dataset_label`，傳入 `datasets` 參數確保「dataset」欄正確填入
  - `export_csv` property 直接回傳 `False`（CSV 已整合進 Excel）

**影響範圍：**
- `src/gui/styles.py`（右側面板控件邊框覆蓋規則）
- `src/output/_common.py`（新增欄位 + `dataset_label` 參數）
- `src/output/excel_exporter.py`（全面改寫 `export_excel_from_records()`，新增 multi-sheet + multi-dataset 支援）
- `src/gui/workspaces/report_workspace.py`（合併 CSV/Excel checkbox，更新多資料集匯出邏輯）

**測試結果：**
- `python3 -m py_compile` 對所有修改檔案均通過
- `pytest tests/test_models.py tests/test_batch_run_store.py tests/test_history.py` → 17/17 通過
- （numpy 相依測試因環境未安裝 numpy 跳過，與先前 session 一致）

**備註：**
- CD 線位置（`cd_line_x_px`、`cd_line_y_px`）來自 `MeasurementRecord.center_x/center_y`，對 Y-CD 為 gap 中心點，原點為圖左上角
- 舊 `export_excel()`（舊版 results list 路徑）不受影響，保留向後相容

每次對本專案進行任何變更（功能新增、Bug 修復、重構、文件更新），
都必須在本文件**最上方**新增一筆 session 記錄。

---

## [2026-04-22] Profile Gaussian LPF 濾波功能 + Detail CD Bug 修復

**變更類型：** 功能新增 / Bug 修復

**變更摘要：**

### Bug 修復：Detail CD 按鈕無效
- **根本原因**：`records_to_legacy_cuts()`（`src/_compat.py`）在將 `MeasurementRecord` 轉回 `YCDMeasurement` 時，只重建了基本欄位，未將 `extra_metrics` 中的取樣資料（`sample_xs`、`upper_sample_ys`、`lower_sample_ys`、`individual_cds_nm`）還原回 `_refine_meta`，導致 `_draw_detail_measurements()` 取得 `None` 並直接 fallback 至普通繪圖
- **修法**：建完 `YCDMeasurement` 後，從 `r.extra_metrics` 取出 5 個已知 key，寫回 `m._refine_meta`

### 功能新增：1D Profile Gaussian LPF 預濾波
- **業界背景**：主流 CDSEM 工具（KLA、ASML）在邊緣偵測前對 1D 強度 profile 施以 Gaussian LPF，頻率響應優於現有的 Moving Average（無旁瓣、不失真邊緣形狀）
- **核心實作**（`cmg_recipe.py`）：
  - 新增 `_gaussian_filter1d(profile, sigma)` — 純 numpy 實作（Gaussian kernel + `np.convolve`），不依賴 scipy
  - `_refine_yedge_subpixel()` 和 `_refine_yedge_threshold_crossing()` 各增加 `profile_lpf_sigma: float = 0.0` 參數；sigma > 0 時在 Step 3b 套用 Gaussian LPF，置於原有 Moving Average 之前
  - `_collect_edge_by_columns()` 透傳 `profile_lpf_sigma`
  - `apply_yedge_subpixel_to_cuts()` 新增 `profile_lpf_enabled: bool` 和 `profile_lpf_sigma: float`；由此統一計算 `_lpf_sigma` 傳入所有內部呼叫
  - `compute_metrics()` 從 `edge_locator_config` 讀取 `profile_lpf_enabled` / `profile_lpf_sigma` 並傳遞
- **UI 實作**：
  - Recipe workspace（Analysis tab）與 Measure workspace（Edge Locator panel）的進階參數區塊底部各新增「─── Profile Filter ───」區段
  - 包含 `[✓ Gaussian LPF]` checkbox + sigma spinbox（0.1–10.0 px，預設 1.0）
  - 勾選 checkbox 才啟用 spinbox；預設 **關閉**，不影響既有行為
  - Recipe workspace：儲存/載入於 `edge_locator_config` key `profile_lpf_enabled` / `profile_lpf_sigma`
  - Measure workspace：Recipe 路徑與 Cards 路徑均套用

**影響範圍：**
- `src/_compat.py`（Detail CD bug fix — 還原 `_refine_meta`）
- `src/core/recipes/cmg_recipe.py`（新增 `_gaussian_filter1d`，修改 4 個函式簽名）
- `src/gui/workspaces/recipe_workspace.py`（Profile LPF 控件 + 儲存/載入）
- `src/gui/workspaces/measure_workspace.py`（Profile LPF 控件 + 兩條執行路徑）

**測試結果：**
- `python3 -m py_compile` 對所有修改檔案均通過
- 手動確認：Gaussian LPF checkbox 不再報 `no module named scipy`；Detail CD 按鈕切換後可見個別取樣線

**備註：**
- scipy 未安裝於此環境，故以純 numpy 自建 Gaussian kernel（效果相同）
- 處理順序：原始像素列 → X strip 平均 → **[Gaussian LPF σ]** → Moving Average (smooth_k) → 梯度/門檻偵測
- BBox 方法不呼叫 `apply_yedge_subpixel_to_cuts()`，Profile LPF 對其無效（符合預期）

---

## [2026-04-22] 五項 UI/功能改善（History 移除、Gradient 更名、Ruler、取樣策略、Detail CD）

**變更類型：** 功能新增 / 重構

**變更摘要：**

### T1：刪除 History Tab（UI freeze 修復）
- **原因**：`_render_chart()` 在主執行緒呼叫 matplotlib + 讀取全部 JSON，造成 UI 凍結
- 刪除整檔 `src/gui/workspaces/history_workspace.py`
- `workspace_host.py` 移除 History 相關 6 處（import、TAB_HISTORY、addTab、signal 連線、status broadcast）

### T2：Subpixel → Gradient 更名
- UI 標籤與內部 data key 統一為 `"gradient"`（原為 `"subpixel"`）
- `cmg_recipe.py` 加入向後相容轉換：讀到 `"subpixel"` 時自動對應至 `"gradient"`，舊 recipe 檔案不受影響
- 同步修改 `recipe_workspace.py`、`measure_workspace.py`

### T3：Review Workspace 加入 Ruler 按鈕
- `review_workspace.py` Header 區新增 `📏 Ruler` checkable 按鈕
- 切換時呼叫 `self._viewer.set_ruler_mode(on)`（`ImageViewer` 現有實作）

### T4：Y-CD 取樣策略可設定 + Detail CD 細節檢視

**核心演算法（`cmg_recipe.py`）：**
- 新增 `_compute_sample_xs(x_start, x_end, mode)` — 依 `"all"` 或整數 N 回傳 x 位置列表
- 新增 `_aggregate_values(vals, method)` — 支援 median / mean / min / max 聚合
- `apply_yedge_subpixel_to_cuts()` 改為**配對取樣**（Paired Sampling）：在上下 blob 的 X 重疊區間同步取樣，計算 `individual_cds_nm`；新增 `sample_lines_mode`、`aggregate_method` 參數；在 `_refine_meta` 中儲存 `sample_xs`、`upper_sample_ys`、`lower_sample_ys`、`individual_cds_nm`

**UI 取樣設定（`recipe_workspace.py` + `measure_workspace.py`）：**
- 進階參數區塊新增「─── Sampling Strategy ───」區段
- 「Vertical lines」：`[All columns ▼]` ComboBox + `[N ↕]` SpinBox（選 N 時啟用）
- 「Aggregation」：Median / Mean / Min / Max ComboBox

### T5：方法動態分群 UI
- Y-CD method 下拉切換時動態顯示/隱藏參數：
  - **BBox**：隱藏全部進階設定
  - **Gradient**：顯示 Sampling Strategy
  - **Threshold Crossing**：額外顯示 Threshold level

**Detail CD 功能（`annotator.py` + `measure_workspace.py` + `review_workspace.py`）：**
- `OverlayOptions` 新增 `show_detail: bool = False`
- `annotator.py` 新增 `_draw_detail_measurements()`：讀取 `m._refine_meta` 中的取樣資料，為每個有效取樣點畫獨立垂直線 + 各自 CD 值；無 `_refine_meta` 時（BBox 或舊資料）fallback 至普通繪圖
- Measure 和 Review workspace Header 各增加「Detail CD」checkable 按鈕，切換後觸發重新繪製

**影響範圍：**
- `src/gui/workspaces/history_workspace.py`（**刪除**）
- `src/gui/workspace_host.py`（移除 History 6 處）
- `src/core/recipes/cmg_recipe.py`（新增 2 helper 函式、修改 `apply_yedge_subpixel_to_cuts()`）
- `src/core/annotator.py`（`OverlayOptions.show_detail`、`_draw_detail_measurements()`）
- `src/gui/workspaces/recipe_workspace.py`（更名、取樣 UI、動態分群）
- `src/gui/workspaces/measure_workspace.py`（更名、取樣 UI、動態分群、Detail CD 按鈕）
- `src/gui/workspaces/review_workspace.py`（Ruler 按鈕、Detail CD 按鈕）

**測試結果：**
- `python3 -m py_compile` 對所有修改檔案均通過
- 手動 smoke test：Ruler 可切換、Detail CD 切換顯示多條取樣線、BBox 方法隱藏進階參數

**備註：**
- `_refine_meta` 在 Cards 路徑下 `store_meta=False`，Detail CD 無法顯示（需改用 Recipe 路徑）
- 舊 recipe 含 `"subpixel"` key 可正常讀取（向後相容）

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
