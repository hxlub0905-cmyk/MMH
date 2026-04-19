# AGENTS.md — SEM MM 開發指南

本文件供 AI Agent 或開發者快速掌握 SEM MM 專案的架構、慣例與開發方式。

> **Phase A (vNext) 完成**：架構已從單一 CMG 量測工具升級為 Recipe-driven SEM Metrology Platform。
> 現有 CMG 邏輯完整保留，作為第一個 Recipe 實作。

---

## 快速導覽

| 目的 | 對應檔案 |
|------|---------|
| 啟動應用程式 | `main.py` |
| 修改主視窗佈局 | `src/gui/main_window.py` (精簡殼層，~70 行) |
| 新增 / 修改 Workspace | `src/gui/workspaces/` 目錄 |
| 修改影像前處理 | `src/core/preprocessor.py` |
| 修改 CMG 偵測演算法 | `src/core/cmg_analyzer.py` |
| CMG Recipe 包裝層 | `src/core/recipes/cmg_recipe.py` |
| 新增 Recipe 類型 | 繼承 `src/core/recipe_base.BaseRecipe`，在 `src/core/recipes/` 下建立 |
| 管理已儲存 Recipe | `src/core/recipe_registry.py` (JSON 在 ~/.mmh/recipes/) |
| 統一資料模型 | `src/core/models.py` (ImageRecord, MeasurementRecord, BatchRunRecord) |
| Calibration 管理 | `src/core/calibration.py` |
| Batch 執行引擎 | `src/core/measurement_engine.py` |
| 相容層 (legacy format) | `src/_compat.py` |
| 影像標注樣式 | `src/core/annotator.py` |
| 匯出格式 | `src/output/` 目錄 (_from_records 版本為新路徑) |
| 新增 / 修改測試 | `tests/` 目錄 |
| 修改 UI 主題 | `src/gui/styles.py` |

---

## 架構概覽 (Phase A)

```
main.py
  └─ MainWindow (main_window.py)  ~70 行
       └─ WorkspaceHost (QTabWidget)
            ├─ BrowseWorkspace   ← FileTreePanel + ImageViewer + Calibration
            ├─ RecipeWorkspace   ← Recipe CRUD 編輯器
            ├─ MeasureWorkspace  ← ImageViewer + ResultsPanel + ControlPanel + Recipe 選擇器
            ├─ ReviewWorkspace   ← 單張影像 Review (Phase A 基礎版)
            ├─ BatchWorkspace    ← Batch 執行 + 進度 (QThread + ProcessPoolExecutor)
            └─ ReportWorkspace   ← 統計 + 匯出按鈕

核心服務 (由 WorkspaceHost 持有):
  RecipeRegistry     ← ~/.mmh/recipes/*.json
  CalibrationManager ← ~/.mmh/calibrations/*.json
  MeasurementEngine  ← 執行 BaseRecipe.run_pipeline()
```

### Recipe Pipeline（6 個 Stage）

```
BaseRecipe.run_pipeline(ImageRecord)
  Stage 1: load_image()        → raw ndarray
  Stage 2: preprocess()        → mask ndarray
  Stage 3: detect_features()   → blobs list
  Stage 4: locate_edges()      → blobs (座標轉換，X 軸)
  Stage 5: compute_metrics()   → list[MeasurementRecord]
  Stage 6: render_annotations()→ annotated BGR ndarray
  → PipelineResult(records, raw, mask, annotated, context)
```

CMGRecipe 在每個 Stage 委派給對應的現有模組，不重寫演算法。

### 信號流（Batch Processing）

```
BatchWorkspace._run_batch()
  → _BatchWorker.run()           # QThread
      → MeasurementEngine.run_batch()
          → ProcessPoolExecutor → _worker_run_image(args_dict)  # 子行程
              → CMGRecipe.run_pipeline()
          → on_progress()        # 更新進度條
      → BatchRunRecord           # 包含 measurements (新) + cuts (舊相容)
  → batch_completed signal
  → ReportWorkspace.load_batch_run()
```

**重要**：`_on_batch_done` 使用 `QTimer.singleShot(0, self._open_batch_review)` 延遲開啟 ReviewDialog，確保不產生巢狀 event loop。

---

## 核心模組說明

### `src/core/preprocessor.py`

**職責**：將灰階影像轉換為 MG 二值遮罩。

```python
@dataclass
class PreprocessParams:
    gl_min: int = 100        # GL 範圍下限
    gl_max: int = 220        # GL 範圍上限
    gauss_kernel: int = 3
    morph_open_k: int = 3
    morph_close_k: int = 5
    use_clahe: bool = True
    clahe_clip: float = 2.0
    clahe_grid: int = 8

def preprocess(img: np.ndarray, params: PreprocessParams) -> np.ndarray:
    # 返回 uint8 二值遮罩（255 = MG）
```

### `src/core/mg_detector.py`

**職責**：從二值遮罩偵測 MG blob。

```python
@dataclass
class Blob:
    label: int
    x0: int; y0: int; x1: int; y1: int  # bounding box (exclusive x1/y1)
    area: int
    cx: float; cy: float                 # centroid

def detect_blobs(mask: np.ndarray, min_area: int = 50) -> list[Blob]:
```

### `src/core/cmg_analyzer.py`

**職責**：CMG gap 分群與 Y-CD 計算（核心演算法）。

```python
@dataclass
class Measurement:
    cmg_id: int; col_id: int
    y_cd_px: float; y_cd_nm: float
    flag: str          # "" | "MIN" | "MAX"
    axis: str          # "Y" | "X"
    state_name: str
    upper_blob: Blob; lower_blob: Blob

@dataclass
class CmgCut:
    cmg_id: int
    measurements: list[Measurement]

def analyze(blobs: list[Blob], nm_per_pixel: float) -> list[CmgCut]:
```

**演算法步驟**：
1. 依 X 範圍重疊（50% overlap ratio）將 blobs 分群為「欄位」
2. 在每個欄位內找相鄰 blob 對（CMG gap）
3. 跨欄位用 union-find 群集（10px y 座標容差）→ CMG cut 事件
4. 每個 cut 下計算每欄的 Y-CD（upper blob 底部到 lower blob 頂部的距離）

### `src/core/annotator.py`

**職責**：在影像上繪製量測標注。

```python
@dataclass
class OverlayOptions:
    show_lines: bool = True
    show_labels: bool = True
    show_boxes: bool = False
    show_legend: bool = True
    focus: tuple[int, int] | None = None   # (cmg_id, col_id) 聚焦高亮

def draw_overlays(
    raw: np.ndarray,
    mask: np.ndarray,
    cuts: list[CmgCut],
    opts: OverlayOptions = OverlayOptions(),
) -> np.ndarray:
    # 返回 BGR uint8 標注影像
```

**顏色規則**：MIN → 橘色 `(50, 150, 255)`，MAX → 天藍色 `(220, 180, 60)`，正常 → 薄荷綠 `(100, 200, 130)`

---

## GUI 模組說明

### `src/gui/control_panel.py`

發出的信號：
- `params_changed(nm_per_pixel: float, params: PreprocessParams)`：任意參數變更時
- `run_single()`：按下 Run Single 按鈕
- `run_batch()`：按下 Run Batch 按鈕

重要方法：
- `get_preprocess_params() -> PreprocessParams`
- `get_nm_per_pixel() -> float`
- `get_min_area() -> int`
- `get_measurement_cards() -> list[dict]`
  - 每個 card dict 包含：`name`, `axis`, `gl_min`, `gl_max`, `min_area`

### `src/gui/results_panel.py`

發出的信號：
- `row_selected(cmg_id: int, col_id: int)`：點選某量測列時，通知 main_window 聚焦標注
- `state_filter_changed(state_name: str)`：切換量測設定檔 tab 時

重要方法：
- `show_results(filename: str, cuts: list[CmgCut])`
- `show_fail(filename: str, reason: str)`
- `update_summary(total: int, n_meas: int, n_fail: int)`
- `clear()`

### `src/gui/batch_dialog.py`

- `_BatchWorker`（QThread）：使用 `ProcessPoolExecutor` 平行處理影像
- `_process_one(args: tuple) -> dict`：頂層函式（必須 picklable），在子行程中執行完整分析
- `_serialise_cuts(cuts) -> list[dict]`：將 dataclass 轉為純 dict，供跨行程傳輸
- `BatchDialog.batch_done: pyqtSignal(list)`：批次完成後發送結果給 MainWindow

---

## 開發慣例

### Python 版本相容性
- 所有檔案頂端加入 `from __future__ import annotations`（支援 Python 3.9 的 PEP 604 型別提示）

### 型別提示
- 函式簽名盡量完整加入型別提示
- 使用 `dataclass` 定義資料結構（`Blob`, `CmgCut`, `Measurement`, `PreprocessParams`, `OverlayOptions`）

### 信號/槽慣例
- 跨執行緒連線（QThread → 主執行緒）：PyQt6 自動使用 QueuedConnection
- 同執行緒連線：自動使用 DirectConnection（同步呼叫）
- 避免在 slot 內直接呼叫 `exec()`（會產生巢狀 event loop）；改用 `QTimer.singleShot(0, callback)`

### 批次序列化規則
- `_process_one` 的傳回值必須為純 Python dict/list/primitive，不可包含 dataclass 物件（因為需要跨行程 pickle）
- 使用 `_serialise_cuts()` 做轉換

### 匯入規則
- 明確列出所需的 PyQt6 類別，不使用萬用匯入（`from PyQt6.QtWidgets import *`）

---

## 測試

```bash
# 執行所有測試
pytest tests/ -v

# 單獨執行 CMG 分析測試
pytest tests/test_cmg_analyzer.py -v
```

測試涵蓋範圍：`src/core/cmg_analyzer.py` 的 union-find 分群、overlap 判斷、gap 分析（10 項測試）。

---

## 已知問題與待修項目

| 嚴重度 | 位置 | 說明 | 狀態 |
|--------|------|------|------|
| 高 | `batch_review_dialog.py:7` | ~~`QWidget` 未匯入，導致批次完成後閃退~~ | **已修復** |
| 中 | `main_window.py:_on_batch_done` | ~~巢狀 `exec()` 造成潛在不穩定~~ | **已修復** |
| 低 | `main_window.py:476` | ~~`f"Saved to:\\n{out_dir}"` escape 錯誤~~ | **已修復** |
| 低 | `batch_dialog.py:_BatchWorker` | ~~`cancelled` 為 class variable 而非 instance variable~~ | **已修復** |
| 低 | `main_window.py:_do_export` | 匯出時重新執行分析，應沿用 batch 結果 | 待修 |
| 低 | `annotator.py` | X-CD 標注座標轉換後 overlay 可能未正確對齊 | 待修 |

---

## 新增功能開發流程

1. **新增核心演算法**：在 `src/core/` 建立新模組，加入對應單元測試至 `tests/`
2. **新增 GUI 元件**：在 `src/gui/` 建立新模組，透過 signal/slot 與 `MainWindow` 整合
3. **新增匯出格式**：在 `src/output/` 建立新模組，並在 `main_window.py._do_export` 中呼叫
4. **修改主題**：編輯 `src/gui/styles.py` 中的 `STYLE` 字串（QSS 格式）

### 新增量測設定檔欄位

若需在量測設定檔（measurement card）中加入新參數：

1. `src/gui/control_panel.py`：在 card widget 中加入對應 UI 元件，更新 `get_measurement_cards()` 返回值
2. `src/gui/batch_dialog.py`：`_process_one()` 從 `card` dict 讀取新參數
3. `src/gui/main_window.py`：`_analyze_with_cards()` 傳遞新參數給 `PreprocessParams` 或 `detect_blobs()`
