# AGENTS.md — SEM MM 開發指南

本文件供 AI Agent 或開發者快速掌握 SEM MM 專案的架構、慣例與開發方式。
最後更新：2026-04-24（Bug Fix Series C1–C4 / M1–M7 / m1–m3）

---

## ⚠️ 重要：Session Log 規定

**每次對本專案進行任何變更（功能新增、Bug 修復、重構、文件更新），
都必須在 `SESSION_LOG.md` 的最上方新增一筆 session 記錄。**

記錄格式請參考 `SESSION_LOG.md` 中的範本。
沒有 session log 的 commit 視為不完整的變更。

---

## 目前版本狀態

| 項目 | 說明 |
|------|------|
| 版本階段 | **Phase A + F2 + G2 + B + Bug Fix Series + Phase C（部分）+ Bug Fix C1–C4/M1–M7/m1–m3 已完成** |
| 核心演算法 | CMG Y-CD / X-CD 量測（完整保留，以 Recipe 包裝） |
| X-Proj 偵測 | Pitch-anchored 相位偵測（`detect_mg_column_centers_pitch_phase()`） |
| 架構模型 | Recipe-driven SEM Metrology Platform |
| 測試數量 | 17 項通過（環境無 numpy/cv2，其餘 60 項需科學計算套件） |
| Phase B 完成 | Bug 修復 5 項 + 批次持久化 + Recipe 驗證模式 + 歷史趨勢 Run Chart |
| Bug Fix Series | CD 計算一致性（A1/A2/F1/G1）、UX 修復（B1/G2/I2/Q1）、效能（L2）、導航（Review/Recipe） |
| Phase C（部分） | Batch 即時 Overlay 輸出 + TC 路徑向量化（4–5×）+ Gradient 路徑向量化（2–3×）；合計 13000 張目標 3–6 分鐘 |
| 未完成 Phase | C（Worker 上限保護、X-CD 標注修正）、D（平台化） |

---

## 快速導覽

| 目的 | 對應檔案 |
|------|---------|
| 啟動應用程式 | `main.py` |
| 主視窗（精簡殼層） | `src/gui/main_window.py`（~70 行） |
| 新增 / 修改 Workspace 面板 | `src/gui/workspaces/` 目錄 |
| 工作區信號匯流 | `src/gui/workspace_host.py` |
| 統一資料模型 | `src/core/models.py` |
| Calibration 管理 | `src/core/calibration.py` |
| Recipe 抽象介面 | `src/core/recipe_base.py` |
| CMG Recipe 實作 | `src/core/recipes/cmg_recipe.py` |
| 新增 Recipe 類型 | 繼承 `BaseRecipe`，放入 `src/core/recipes/` |
| Recipe 持久化管理 | `src/core/recipe_registry.py` |
| Batch / 單張執行引擎 | `src/core/measurement_engine.py` |
| **批次結果持久化** | **`src/core/batch_run_store.py`** |
| **Recipe 驗證邏輯** | **`src/core/recipe_validator.py`** |
| 相容層（舊格式橋接） | `src/_compat.py` |
| 修改 CMG 偵測演算法 | `src/core/cmg_analyzer.py`（⚠️ 核心演算法，謹慎修改） |
| 修改影像前處理 | `src/core/preprocessor.py` |
| 修改影像標注樣式 | `src/core/annotator.py` |
| 新匯出路徑 | `src/output/`（`_from_records` 系列函式） |
| 舊匯出路徑（相容保留） | `src/output/`（原始函式，不建議新功能使用） |
| UI 主題 | `src/gui/styles.py` |
| **Recipe 驗證 Workspace** | **`src/gui/workspaces/validation_workspace.py`** |
| **歷史趨勢 Workspace** | **`src/gui/workspaces/history_workspace.py`** |
| 所有測試 | `tests/` 目錄 |
| 開發歷程記錄 | `SESSION_LOG.md` |

---

## 架構概覽（Phase A + Bug Fix Series）

六個工作區（TAB 索引與 workspace_host.py 常數對應）：

```
main.py
  └─ MainWindow (src/gui/main_window.py)  ← ~70 行殼層
       └─ WorkspaceHost (src/gui/workspace_host.py)  ← QTabWidget（6 tab）+ 信號匯流
            ├─ TAB_BROWSE  (0) BrowseWorkspace  (workspaces/browse_workspace.py)
            │    ← FileTreePanel + ImageViewer（預覽）+ CalibrationManager
            ├─ TAB_RECIPE  (1) RecipeWorkspace  (workspaces/recipe_workspace.py)
            │    ← Recipe CRUD 編輯器，存至 ~/.mmh/recipes/*.json
            ├─ TAB_MEASURE (2) MeasureWorkspace (workspaces/measure_workspace.py)
            │    ← ImageViewer + ResultsPanel + ControlPanel（舊版 cards）
            │       + Recipe 選擇器（新路徑）
            ├─ TAB_BATCH   (3) BatchWorkspace   (workspaces/batch_workspace.py)
            │    ← Batch 執行 + _BatchWorker(QThread) + ProcessPoolExecutor
            │       + Load History 按鈕（_HistoryDialog）
            ├─ TAB_REVIEW  (4) ReviewWorkspace  (workspaces/review_workspace.py)
            │    ← 單張影像 Review + 批次瀏覽（LRU 快取 200 筆）
            └─ TAB_REPORT  (5) ReportWorkspace  (workspaces/report_workspace.py)
                 ← 統計 + 匯出按鈕（使用 _from_records 路徑）
                    + Load from History 按鈕

共用服務（由 WorkspaceHost 持有，各 Workspace 透過建構子注入）：
  RecipeRegistry      src/core/recipe_registry.py   → ~/.mmh/recipes/*.json
  CalibrationManager  src/core/calibration.py        → ~/.mmh/calibrations/*.json
  MeasurementEngine   src/core/measurement_engine.py → 執行 Recipe pipeline
  BatchRunStore       src/core/batch_run_store.py    → ~/.mmh/runs/*.json
```

> **注意**：ValidationWorkspace 與 HistoryWorkspace 已規劃為未來擴充（Phase D），
> 目前尚未實作；README 描述的「八工作區」為規格目標，非現行狀態。

### 工作區信號流

```
Browse.image_selected  →  Measure.set_image_record + 切換至 Measure tab
Measure.run_completed  →  Review.load_result + 切換至 Review tab
Batch.batch_completed  →  Report.load_batch_run + 切換至 Report tab
Recipe.recipe_saved    →  Measure.refresh_recipe_selector
Recipe.recipe_saved    →  Batch.refresh_recipe_selector
各 workspace.status_message  →  MainWindow status bar
```

---

## 核心資料模型（src/core/models.py）

所有模型皆為 `json.dumps` 安全（無 numpy 型別、無 Path 物件），並提供 `to_dict()` / `from_dict()` 雙向序列化。

```python
@dataclass
class ImageRecord:
    image_id: str          # uuid4
    file_path: str
    source_folder: str
    pixel_size_nm: float   # nm/pixel 校正值
    magnification: float
    acquisition_metadata: dict
    created_at: str        # ISO 8601
    analyzed_at: str

@dataclass
class MeasurementRecord:
    measurement_id: str    # uuid4
    image_id: str
    recipe_id: str
    feature_type: str      # 目前："CMG_GAP"
    feature_id: str        # e.g. "cmg3_col1"
    bbox: tuple[int,int,int,int]
    axis: Literal["X","Y"]
    raw_px: float
    calibrated_nm: float
    status: Literal["normal","min","max","outlier","rejected","corrected"]
    review_state: Literal["unreviewed","accepted","rejected"]
    extra_metrics: dict    # 儲存 upper_bbox / lower_bbox 等額外資訊
    # Legacy 欄位（供 ResultsPanel / annotator 相容）
    cmg_id: int; col_id: int; flag: str; state_name: str

@dataclass
class BatchRunRecord:
    batch_id: str
    input_folder: str
    recipe_ids: list[str]
    total_images: int; success_count: int; fail_count: int
    start_time: str; end_time: str
    worker_count: int
    error_log: list[dict]
    output_manifest: dict   # 含 "results" list（新格式 measurements + 舊格式 cuts）
```

---

## Recipe Pipeline（src/core/recipe_base.py）

```python
class BaseRecipe(ABC):
    """6-stage 量測 pipeline 抽象介面。"""

    # Stage 1：載入影像（預設委派 image_loader，可 override）
    def load_image(self, ir: ImageRecord, ctx: dict) -> np.ndarray

    # Stage 2：前處理（返回 binary mask）
    @abstractmethod
    def preprocess(self, raw: np.ndarray, ctx: dict) -> np.ndarray

    # Stage 3：特徵偵測（返回 blobs / contours 等）
    @abstractmethod
    def detect_features(self, mask: np.ndarray, ctx: dict) -> list

    # Stage 4：邊緣定位（座標轉換、精修）
    @abstractmethod
    def locate_edges(self, features: list, ctx: dict) -> list

    # Stage 5：計算量測值（返回 MeasurementRecord list）
    @abstractmethod
    def compute_metrics(self, edges, ir: ImageRecord, ctx: dict) -> list[MeasurementRecord]

    # Stage 6：繪製標注（返回 BGR ndarray）
    def render_annotations(self, raw, mask, records, ctx, opts) -> np.ndarray

    # 便利方法：依序執行 6 stages
    def run_pipeline(self, ir: ImageRecord, opts=None) -> PipelineResult
```

**CMGRecipe 委派關係：**

| Stage | 委派目標 |
|-------|---------|
| preprocess | `preprocessor.preprocess()` |
| detect_features | `mg_detector.detect_blobs()` |
| locate_edges | X 軸時執行 `_rot_blob_to_ori()` 座標轉換 |
| compute_metrics | `cmg_analyzer.analyze()` → CMGCut → MeasurementRecord |
| render_annotations | `annotator.draw_overlays()` |

---

## 核心演算法模組（不建議輕易修改）

### `src/core/cmg_analyzer.py` ⚠️

**職責**：CMG gap 分群與 Y-CD / X-CD 計算。

**演算法步驟**：
1. 依 X 範圍重疊（50% overlap ratio，可由 Recipe edge_locator_config 調整）將 blobs 分群為「欄位」（union-find）
2. 在每個欄位內找相鄰 blob 對 → CMG gap；gap 上緣 = `upper.y1`（bbox 底緣），gap 下緣 = `lower.y0`（bbox 頂緣）
3. 跨欄位 union-find 群集（10px Y 座標容差）→ CMG cut 事件
4. 計算每個 cut 每欄的 Y-CD（`lower.y0 - upper.y1`，與 annotator 一致）
5. 標記每個 cut 內的 MIN / MAX 量測值（`_flag_global_minmax`）

```python
def analyze(
    blobs: list[Blob],
    nm_per_pixel: float,
    x_overlap_ratio: float = 0.5,
    y_cluster_tol: int = 10,
) -> list[CMGCut]
```

### `src/core/preprocessor.py`

```python
@dataclass
class PreprocessParams:
    gl_min: int = 100; gl_max: int = 220
    gauss_kernel: int = 3
    morph_open_k: int = 3; morph_close_k: int = 5
    use_clahe: bool = True; clahe_clip: float = 2.0; clahe_grid: int = 8
```

### `src/core/mg_detector.py`

```python
@dataclass
class Blob:
    label: int
    x0: int; y0: int; x1: int; y1: int  # bounding box (x1/y1 exclusive)
    area: int; cx: float; cy: float

def detect_blobs(mask: np.ndarray, min_area: int | None = None) -> list[Blob]

def detect_mg_column_centers_pitch_phase(
    mask: np.ndarray,
    pitch_px: int,
    smooth_k: int = 5,
    min_height_frac: float = 0.3,
    edge_margin_px: int = 0,
) -> list[int]:
    """Pitch-anchored phase detection：對 X-proj 以已知 pitch 做相位搜尋，
    返回等間距 MG 欄位中心列表。PEPI 偏向在全局平均中被消除。"""

def regularize_blobs_to_columns(
    blobs, col_centers, half_w, tol, norm_x
) -> list[Blob]
```

⚠️ `detect_mg_column_centers_twopass()` 已於 Phase F2 移除，請勿引用。

### `src/core/annotator.py`

```python
@dataclass
class OverlayOptions:
    show_lines: bool = True; show_labels: bool = True
    show_boxes: bool = False; show_legend: bool = True
    focus: tuple[int, int] | None = None  # (cmg_id, col_id) 高亮

def draw_overlays(img_gray, mask, cuts: list[CMGCut], opts) -> np.ndarray
```

顏色：MIN → 橘色，MAX → 天藍色，正常 → 薄荷綠

**標注文字常數（Phase G2 調整）：**

| 常數 | 值 | 說明 |
|------|----|------|
| `_LABEL_MIN_DY` | `6` | 標籤碰撞最小 Y 間距（px） |
| `fs` | `max(0.18, h/3200)` | 字體縮放公式（縮小以減少重疊） |
| lane | `x_lbl // 30` | 碰撞偵測 lane 寬（縮窄避免遠欄互推） |
| x offset | `x_mid + _TICK_HALF + 2` | 數值標籤緊貼量測線

---

## Calibration 系統（src/core/calibration.py）

```python
@dataclass
class CalibrationProfile:
    profile_id: str; profile_name: str
    nm_per_pixel: float
    magnification: float; detector_type: str
    source: str  # "manual" | "tiff_tag" | "imported"

class CalibrationManager:
    # 持久化路徑：~/.mmh/calibrations/<profile_id>.json
    def list_profiles() -> list[CalibrationProfile]
    def get(profile_id) -> CalibrationProfile | None
    def get_default() -> CalibrationProfile   # 無 profile 時返回 1.0 nm/px fallback
    def save(profile) -> None
    def create_new(name, nm_per_pixel, ...) -> CalibrationProfile
```

---

## Recipe Registry（src/core/recipe_registry.py）

```python
class RecipeRegistry:
    # 持久化路徑：~/.mmh/recipes/<recipe_id>.json
    def list_recipes() -> list[MeasurementRecipe]
    def get(recipe_id) -> BaseRecipe | None          # 根據 recipe_type 實例化
    def get_descriptor(recipe_id) -> MeasurementRecipe | None
    def save(descriptor: MeasurementRecipe) -> None
    def delete(recipe_id) -> bool
    def import_from_card(card: dict) -> MeasurementRecipe  # 舊版 card 轉新格式
    def create_default_cmg() -> MeasurementRecipe    # 建立預設 CMG Y-CD Recipe
```

**Recipe 類型擴充方式**：
1. 在 `src/core/recipes/` 建立新 class（繼承 `BaseRecipe`）
2. 在 `RecipeRegistry.get()` 的 `if desc.recipe_type in (...)` 中加入新類型對應

---

## MeasurementEngine（src/core/measurement_engine.py）

```python
class MeasurementEngine:
    def run_single(ir: ImageRecord, recipe: BaseRecipe) -> PipelineResult

    def run_batch(
        image_records: list[ImageRecord],
        recipe_ids: list[str],
        on_progress: Callable[[int, int, str, str, dict], None] | None,
        max_workers: int | None,
        output_dir: Path | None = None,   # Phase C：每張圖跑完即寫 overlay PNG
    ) -> BatchRunRecord

    def run_multi_batch(
        datasets: list[dict],
        on_dataset_start: Callable | None,
        on_progress: Callable[[int, int, str, str, dict], None] | None,
        max_workers: int | None,
        output_dir: Path | None = None,   # 各 dataset 寫入 output_dir / label 子資料夾
    ) -> MultiDatasetBatchRun
```

**Batch 序列化規則**（ProcessPoolExecutor 限制）：
- 所有傳入子行程的資料必須為純 dict/list/primitive（不可含 dataclass）
- Worker args：`{image_path, image_id, pixel_size_nm, recipe_descriptors: [dict, ...], output_dir: str | None}`
- Worker 返回值：`{image_path, status, error, measurements: [dict], cuts: [dict], overlay_path: str | None, overlay_error: str | None}`
- `measurements`：新格式（`MeasurementRecord.to_dict()` 列表）
- `cuts`：舊格式（`_compat.serialise_cuts_from_records()` 轉換，供舊版 exporter 使用）
- `on_progress` 第 5 個參數為完整 `result_dict`（UI 層用來顯示 overlay_path）

---

## 相容層（src/_compat.py）

Phase A 過渡期間，舊格式元件（ResultsPanel、BatchReviewDialog、舊版 exporter）透過此模組橋接：

```python
def serialise_cuts_from_records(records: list[MeasurementRecord]) -> list[dict]:
    """MeasurementRecord → 舊版 cuts dict（BatchRunRecord.output_manifest["cuts"] 格式）"""

def records_to_legacy_cuts(records: list[MeasurementRecord]) -> list[CMGCut]:
    """MeasurementRecord → CMGCut dataclass（供 ResultsPanel.show_results() 使用）"""
```

**Phase B 後應逐步移除對此模組的依賴**，改由各元件直接使用 `MeasurementRecord`。

---

## GUI 模組說明

### WorkspaceHost（src/gui/workspace_host.py）

共用服務的生命週期擁有者，所有 Workspace 透過建構子接收共用服務：
```python
self._registry    = RecipeRegistry()
self._cal_manager = CalibrationManager()
self._engine      = MeasurementEngine(self._registry)
```

### MeasureWorkspace

同時支援兩種執行路徑：
- **Recipe 路徑**（新）：選擇 Registry 中的 Recipe → `engine.run_single()` → `PipelineResult` → `records_to_legacy_cuts()` → `ResultsPanel`
- **Legacy Cards 路徑**（舊，保留相容）：使用 `ControlPanel` 的量測設定檔卡片直接呼叫 `cmg_analyzer.analyze()`

### ControlPanel（src/gui/control_panel.py，保留不動）

Phase A 保留供 MeasureWorkspace 的 Legacy Cards 路徑使用。Phase B 考慮將其拆解整合至 RecipeWorkspace。

重要方法：
- `get_preprocess_params() -> PreprocessParams`
- `get_nm_per_pixel() -> float`
- `get_min_area() -> int | None`
- `get_measurement_cards() -> list[dict]`（每個 card 含：`name`, `axis`, `gl_min`, `gl_max`, `min_area`）

### ResultsPanel（src/gui/results_panel.py，保留不動）

接受 `list[CMGCut]`（透過 `records_to_legacy_cuts()` 轉換後傳入）。
Phase B 考慮直接接受 `list[MeasurementRecord]`。

---

## 匯出模組（src/output/）

| 函式 | 路徑 | 輸入 |
|------|------|------|
| `export_csv()` | csv_exporter.py | 舊版 results list（保留相容） |
| `export_csv_from_records()` | csv_exporter.py | `list[MeasurementRecord]`（新路徑） |
| `export_excel()` | excel_exporter.py | 舊版 |
| `export_excel_from_records()` | excel_exporter.py | 新路徑 |
| `export_json()` | json_exporter.py | 舊版 |
| `export_json_from_records()` | json_exporter.py | 新路徑 |
| `generate_report()` | report_generator.py | 舊版 |
| `generate_report_from_records()` | report_generator.py | 新路徑 |

新功能請一律使用 `_from_records` 版本。

---

## 開發慣例

### Python 版本相容性
- 所有檔案頂端加入 `from __future__ import annotations`（支援 Python 3.9 的 PEP 604 型別提示）

### 資料模型規則
- 所有新資料結構使用 `@dataclass`
- 跨行程傳遞的資料必須 `json.dumps` 安全：無 numpy 型別、無 Path 物件、無 datetime 物件（改用 ISO 8601 字串）
- `to_dict()` / `from_dict()` 必須互為逆操作（round-trip 測試是驗證標準）

### 信號/槽慣例
- 跨執行緒（QThread → 主執行緒）：PyQt6 自動使用 QueuedConnection，不需特別處理
- 避免在 slot 內呼叫 `exec()`（巢狀 event loop）；改用 `QTimer.singleShot(0, callback)`
- Workspace 間通訊一律透過 WorkspaceHost 的訊號連線，不應直接互相引用

### 新增 Recipe 類型
1. 在 `src/core/recipes/` 建立新 class 繼承 `BaseRecipe`
2. 實作 5 個 abstract methods（Stage 2-5）
3. 在 `RecipeRegistry.get()` 加入 `recipe_type` 對應
4. 在 `RecipeWorkspace` 的 type combo 加入新選項
5. 新增對應測試至 `tests/`

### 測試規範
```bash
# 執行不依賴 numpy/cv2 的測試（17 項，本環境可跑）
pytest tests/test_models.py tests/test_batch_run_store.py tests/test_history.py -v

# 完整測試（需 numpy + cv2 + scikit-image 環境）
pytest tests/ -v
# tests/test_cmg_analyzer.py       — 原始 CMG 演算法（11 項）
# tests/test_models.py             — 資料模型 round-trip（6 項）
# tests/test_recipe_base.py        — CMGRecipe pipeline + Registry（12 項）
# tests/test_measurement_engine.py — 相容層 + 輸出 + 引擎整合（8 項）
# tests/test_subpixel_refinement.py— 次像素精細化
# tests/test_batch_run_store.py    — 批次持久化（7 項）
# tests/test_recipe_validator.py   — Recipe 驗證（4 項）
# tests/test_history.py            — 歷史統計（4 項）
```

### 重要實作注意事項（Bug Fix Series 後）

| 項目 | 規則 |
|------|------|
| `analyze()` gap edge | `upper.y1` / `lower.y0`（不可改回 `cy±height/2`，兩者不等） |
| Recipe path re-flag | 精化後及 range filter 後均用 `_flag_global_minmax(all_measurements)`（全圖單一 MIN/MAX）；`analyze()` Step 5 同樣用 global |
| Cards path `bbox` | `(min_x, ub.y1, max_x, lb.y0)`（gap 邊緣，不含 blob 本身高度） |
| `center_y` 精化後 | `compute_metrics()` 在 `records.append(rec)` 前若 `y_upper_edge` 有值則覆寫 `rec.center_y` |
| `store_meta` | Cards 路徑的 `apply_yedge_subpixel_to_cuts()` 必須 `store_meta=True`（Detail CD 需要） |
| DataFrame 欄位 | `records_to_dataframe()` 輸出 `cut_id`/`column_id`（不是 `cmg_id`/`col_id`）；13 欄標準順序 |
| Index recipe_ids | `BatchRunStore` 儲存時 index entry 含 `recipe_ids`；`get_stats_for_recipe()` 以此快速跳過無關記錄 |

---

## 已知問題與待修項目

| 嚴重度 | 位置 | 說明 | 狀態 |
|--------|------|------|------|
| 已修復 | batch_review_dialog.py | `QWidget` 未匯入導致批次閃退 | ✅ |
| 已修復 | main_window.py | 巢狀 `exec()` 不穩定 | ✅ |
| 已修復 | batch_dialog.py | `cancelled` 為 class 變數 | ✅ |
| 已修復 | mg_detector.py | Two-pass X-proj 受 PEPI 偏向，Auto-detect 失效 | ✅ F2 |
| 已修復 | report_generator.py | matplotlib 未安裝時 HTML 匯出崩潰 | ✅ G2-4 |
| 已修復 | cmg_recipe.py | `_card_to_descriptor()` 缺 17 個 col_mask/range 欄位 | ✅ G2-1 |
| 已修復 | cmg_analyzer.py | MIN/MAX 只標 1 筆，未標前 3 小 / 前 3 大 | ✅ B-Bug1 |
| 已修復 | measurement_engine.py | 空 cuts 時 cmg_id_offset 不累加，造成衝突 | ✅ B-Bug2 |
| 已修復 | review_workspace.py | 批次導航卡在 separator 列 | ✅ B-Bug3 |
| 已修復 | results_panel.py | feature_id 解析靜默失敗 | ✅ B-Bug4 |
| 已修復 | csv/excel_exporter.py | 頂層 pandas import 造成啟動崩潰 | ✅ B-Bug5 |
| 已修復 | review_workspace.py | 批次 > 1000 張時導航對應錯誤影像（_entry_index_map） | ✅ |
| 已修復 | recipe_workspace.py | Duplicate Recipe 後按 Save 覆蓋原始 Recipe | ✅ |
| 已修復 | cmg_analyzer.py | `analyze()` gap edge 用 `cy±height/2` 而非 bbox 邊緣（A1） | ✅ |
| 已修復 | cmg_recipe.py | 精化失敗時 cd_px 未回落 bbox 值（A2） | ✅ |
| 已修復 | cmg_recipe.py | Recipe 路徑 re-flag 用 global minmax，不一致 Cards 路徑（F1） | ✅ |
| 已修復 | measure_workspace.py | Cards 路徑 bbox 含整個 blob 高度，center_y 偏移（G1） | ✅ |
| 已修復 | cmg_recipe.py | 精化成功後 center_y 未更新，Excel cd_line_y_px 偏移（B1） | ✅ |
| 已修復 | measure_workspace.py | Cards 路徑 Detail CD 無反應（store_meta=False）（G2） | ✅ |
| 已修復 | measure_workspace.py | Edge Locator 無提示「參數僅本次有效」（I2） | ✅ |
| 已修復 | measure_workspace.py | Mask 模式顯示舊 mask，_run_preview 未更新（Q1） | ✅ |
| 已修復 | batch_run_store.py | get_stats_for_recipe 大量歷史記錄卡頓，缺快速跳過（L2） | ✅ |
| 已修復 | measure_validate_dialog.py | Compare to Reference N 顯示不準（V5/V6） | ✅ |
| 已修復 | _common.py / excel_exporter.py | CSV/Excel 欄位命名：cmg_id→cut_id, col_id→column_id（W1） | ✅ |
| 已修復 | models.py | JSON round-trip 後 extra_metrics bbox fields 為 list 非 tuple（C1） | ✅ |
| 已修復 | batch_run_store.py | Windows 路徑差異導致 index 每次全量重建（C2） | ✅ |
| 已修復 | measurement_engine.py | abort_check 時 batch.end_time 未設定（C3） | ✅ |
| 已修復 | cmg_recipe.py | 非配對 fallback upper/lower_sample_ys 空 list 導致 Detail CD 錯位（C4） | ✅ |
| 已修復 | workspace_host.py | TAB 常數未文件化、AGENTS.md 描述 8 workspace 但只有 6 個（M1） | ✅ |
| 已修復 | review_workspace.py | _batch_records 快取無上限（M2） | ✅ |
| 已修復 | batch_workspace.py | 進度條第二次執行從綠色開始（M3） | ✅ |
| 已修復 | cmg_recipe.py | _smooth_strip_2d docstring 不準確（M4） | ✅ |
| 已修復 | excel_exporter.py | _filter_meas_by_mode groupby 前未 dropna（M5） | ✅ |
| 已修復 | test_subpixel_refinement.py | TestEdgeMethodSelection 仍用舊 key "subpixel"（M6） | ✅ |
| 已修復 | cmg_recipe.py | 精化後 re-flag 用 per-cut _flag_top3，每圖多組 MIN/MAX（M7） | ✅ |
| 已修復 | annotator.py | draw_overlays_multi 缺 _flag_global_minmax 就地修改警告（m1） | ✅ |
| 已修復 | preprocessor.py | apply_column_strip_mask 結果全零時無警告（m2） | ✅ |
| 已修復 | batch_run_store.py | _append_to_index 在 index stale 時用空 list 遺失舊條目（m3） | ✅ |
| 待修 | review_workspace.py | Review 工作流程為基礎版，缺 Accept/Reject 操作 | 待修 |
| 待修 | annotator.py | X-CD 標注 overlay 座標對齊待驗證 | 待修 |
| Phase C | measure/batch | Worker 數可調已實作，但無上限保護 | 待改善 |
| Phase D | recipe_registry.py | Recipe 以 JSON 檔案儲存，Phase D 遷移至 SQLite | 規劃中 |

---

## 交接事項

### 目前狀態總結（2026-04-20）

#### Phase A — 架構升級（已完成）

1. **不破壞現有功能**：`cmg_analyzer.py`、`preprocessor.py`、`mg_detector.py`、`annotator.py` 核心演算法完全保留。現有 batch_dialog.py / batch_review_dialog.py / control_panel.py / styles.py 保留，透過相容層橋接新架構。
2. **新架構入口點**：使用者操作流程改為 Browse → Recipe → Measure → Review → Batch → Report 六工作區。舊版功能在 MeasureWorkspace 的「Legacy Cards」路徑仍然完全可用。
3. **Recipe 持久化**：建立的 Recipe 儲存於 `~/.mmh/recipes/`，Calibration 儲存於 `~/.mmh/calibrations/`。
4. **MeasurementRecord 為新核心**：所有新功能應基於 `MeasurementRecord` 建構，不再使用 `YCDMeasurement` / `CMGCut` 作為主要傳遞格式。

#### Phase F2 — X-Proj 相位偵測（已完成）

- `detect_mg_column_centers_twopass()` 已由 `detect_mg_column_centers_pitch_phase()` 取代
- 新演算法：已知 MG pitch → 對 X-proj reshape 成 `(N, pitch_px)` 矩陣 → argmax 相位 → 等間距正規網格
- 優點：全局最優，PEPI 貢獻被平均消除；三處 pipeline call site 已同步更新

#### Phase G2 — 六項新功能（已完成）

| 編號 | 功能 | 主要檔案 |
|------|------|---------|
| G2-1 | Measure「Save Cards as Recipe」一鍵轉存 | `measure_workspace.py`, `cmg_recipe.py` |
| G2-2 | Results/Review 表格表頭點擊數字排序 | `results_panel.py` |
| G2-3 | Batch Run 早期進度提示（Preparing/Submitted） | `batch_dialog.py` |
| G2-4 | HTML 匯出 matplotlib 容錯 + 圖片匯出進度條 | `report_generator.py`, `report_workspace.py` |
| G2-5 | Recipe 編輯器改為 QTabWidget 四 Tab 佈局 | `recipe_workspace.py` |
| G2-6 | Annotated 數值標籤字體縮小、間距加緊 | `annotator.py` |

#### Phase C（部分完成，2026-04-23）

| 功能 | 說明 | 主要檔案 |
|------|------|---------|
| Batch 即時 Overlay 輸出 | subprocess 內每張圖寫 `<stem>_annotated.png`；UI 新增 checkbox + 資料夾選擇；progress callback 升級為第 5 個參數傳遞 `result_dict` | `measurement_engine.py`, `batch_workspace.py` |
| TC 路徑向量化 | `_refine_yedge_threshold_crossing_batch()` 一次提取 2D strip，向量化 MA + sign-change；預期 4–5× 加速（13000 張 20–30 min → 4–8 min） | `cmg_recipe.py` |
| Gradient 路徑向量化 | `_refine_yedge_subpixel_batch()` 共用 `_extract_strip()` + `_smooth_strip_2d()` 提取 2D strip，`np.abs(np.diff())` 向量化 abs-gradient，逐欄 peak 偵測 + 二次型內插；預期 2–3× 加速；合計目標 3–6 min | `cmg_recipe.py` |

### Phase B 開發重點（下一步）

按 vNext 規格書優先度：
1. **Batch result cache**：`BatchRunRecord` 已持有結果，需將其持久化至磁碟（JSON 或 SQLite），使 export 不需重跑分析
2. **Review 工作流程完善**：ReviewWorkspace 加入 Accept / Reject / Mark False Detect 操作，並記錄 review log
3. **Workspace UI 細化**：ReportWorkspace 加入嵌入式 matplotlib 直方圖；BatchWorkspace 加入 retry 失敗影像功能

### 重要檔案路徑

```
使用者資料目錄（運行時建立）：
  ~/.mmh/recipes/          — 儲存的 MeasurementRecipe（JSON）
  ~/.mmh/calibrations/     — 儲存的 CalibrationProfile（JSON）

專案文件：
  SESSION_LOG.md           — 每次變更的 session 記錄（必填）
  AGENTS.md                — 本文件（開發指南）
  README.md                — 使用者說明文件
  docs/MMH_vNext_規格書    — vNext 規格書（原稿在桌面）
```

### 注意事項

- **不要修改** `cmg_analyzer.py` 中的演算法邏輯，除非有充分的測試支撐
- 新增 Recipe 類型前，請先確認 `BaseRecipe` 的 6-stage pipeline 是否滿足需求；若需擴充 pipeline（如新增 Stage），請同步更新 `BaseRecipe` 並確保 `CMGRecipe` 不受影響
- `src/_compat.py` 是過渡期產物，Phase B 之後應逐步減少對它的依賴
- Windows 上 `ProcessPoolExecutor` 需要 `if __name__ == "__main__":` 保護（`main.py` 已處理），新增的 worker 函式必須放在模組頂層（picklable）
