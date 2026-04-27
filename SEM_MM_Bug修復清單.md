# SEM MM — Bug 修復清單
> 最後更新：2026-04-27（UI Improvements + Bug Fix B1–B6 之後）
> 適用版本：Bug Fix Round2 + Phase D SQLite + UI Improvements

---

## 背景說明

請你作為 SEM MM 專案的 AI 開發助手，依照以下清單逐一修復 Bug。
每修復一項請：
1. 在 `SESSION_LOG.md` 最上方新增 session 記錄
2. 執行 `python3 -m py_compile <修改的檔案>` 確認語法無誤
3. 若該 Bug 有對應測試，執行 `pytest tests/ -v` 確認通過

專案架構請參考 `AGENTS.md`，核心演算法（`cmg_analyzer.py`）請勿修改。

---

# 一、已修復清單（依完成日期排序，最新在上）

## 2026-04-27 — UI Improvements + Bug Fix B1–B6 ✅

| ID | 位置 | 簡述 |
|----|------|------|
| **功能一** | `klarf_export_dialog.py` | 「執行並輸出 KLARF」加進度條（脈動式） |
| **功能二** | `klarf_export_dialog.py` + `klarf_exporter.py` | 預覽表格選列連動 SEM 影像 + 原始/新座標十字 overlay |
| **功能三** | `control_panel.py` + `measure_workspace.py` | Recipe 選擇連動 ControlPanel Cards 自動帶出參數 |
| **功能四** | `workspace_host.py` | Run Single 不再自動跳轉至 Review，停留在 Measure |
| **B1** | `klarf_export_dialog.py` | Worker 訊號連接洩漏（重複觸發回呼） |
| **B2** | `klarf_exporter.py` | `_size_cache` 加 500 筆上限，避免記憶體無限增長 |
| **B3** | `batch_run_store.py` | 新增 `close()` 釋放 thread-local SQLite connection |
| **B4** | `klarf_exporter.py` | `raw_px=0` 時改為跳過座標調整並記錄警告 |
| **B5** | `klarf_export_dialog.py` | Stat card「第 N 筆 Y-CD」降冪排序時顯示正確邊界值 |
| **B6** | `measurement_engine.py` | Batch pool `future.result()` 捕捉例外，單筆崩潰不中止整批 |

## 2026-04-27 — Bug Fix Round2 ✅

| ID | 位置 | 簡述 |
|----|------|------|
| H1 | `measurement_engine.py` | `cv2.imwrite()` 失敗未檢查回傳值（overlay_path 假性存在） |
| H3 | `image_loader.py` | `ndarray.ptp()` 在 NumPy 2.0 已移除（改用 `max-min`） |
| M1 | `report_workspace.py` | Export Dialog tasks 為空時靜默 return，已加 QMessageBox 提示 |
| M2 | `batch_dialog.py` | X-CD blob 座標轉換與 `_rot_blob_to_ori` 不一致（差 1px） |
| M3 | `file_tree_panel.py` | 缺 `root_path()` 方法，file count 永遠空白 |
| M4 | `report_generator.py` | `fail_list` / dataset label 未 `html.escape()` 防 XSS |
| L1 | `recipe_workspace.py` | `_save_recipe()` 廢棄 EC key 永久累積，加入 `_EC_CANONICAL_KEYS` |
| L2 | `klarf_exporter.py` / `klarf_writer.py` | XREL/YREL 大小寫混合靜默略過，改用 `k.lower() == "xrel"` |

## 2026-04-26 — Phase D（SQLite 遷移）✅

| 項目 | 位置 | 簡述 |
|------|------|------|
| BatchRunStore SQLite | `batch_run_store.py` | JSON 檔案 → SQLite（WAL + thread-local + executemany） |
| 多執行緒 QThread 安全 | `batch_run_store.py` | `_local: threading.local()`，每執行緒獨立 connection |
| `get_stats_for_recipe` SQL JOIN | `batch_run_store.py` | 改用 SQL JOIN 取代 Python iteration |
| state_name / structure_name 持久化 | `batch_run_store.py` | 修補 ALTER TABLE 補欄位（向後相容） |

## 2026-04-26 — KLARF Export ✅

| 項目 | 位置 | 簡述 |
|------|------|------|
| KlarfTopNExporter | `klarf_exporter.py` | Top-N 篩選 + 座標補正 + 階層式格式支援 |
| nm/px 統一整合 | `cmg_recipe.py` 等 | Recipe 內建 `nm_per_pixel`，Measure / Batch / KLARF 全部沿用 |

## 2026-04-24 — Bug Fix C1–C4 / M1–M7 / m1–m3 ✅（精簡帶過）

含：bbox tuple 還原、Windows 路徑正規化、`end_time` finally 保證、Detail CD fallback、全域 MIN/MAX、LRU 上限、進度條重置、`dropna` 防 NaN、測試 key 更新等 14 項。

## 2026-04-23 — Bug Fix Series（首輪）✅（精簡帶過）

含：CD 計算一致性（A1/A2/F1/G1）、UX 修復（B1/G2/I2/Q1）、效能（L2）、Review 批次導航（> 1000 張）、Duplicate Recipe 覆蓋、CSV/Excel 欄位重命名等。

## 2026-04-21 — Phase B（持久化 + 驗證 + 歷史）✅（精簡帶過）

含：BatchRunStore JSON 持久化（已被 Phase D SQLite 取代）、RecipeValidator、HistoryWorkspace Run Chart、77 項測試。

## 2026-04-20 — Phase A / F2 / G2（架構升級）✅（精簡帶過）

含：Recipe 抽象化、統一資料模型、六工作區 GUI、Pitch-anchored 偵測、Save as Recipe、表格排序、Batch 早期進度等。

---

# 二、待修復清單

## 高優先

---

### [H2] `batch_run_store.py` — Recipe JSON 寫入仍非原子操作

**位置**：`src/core/recipe_registry.py`，`save()` 函式

**問題描述**：
雖然 BatchRunStore 已遷移至 SQLite（原子事務），但 `RecipeRegistry.save()` 仍直接使用
`path.write_text(...)` 寫入 Recipe JSON。若寫入過程中崩潰（強制關閉、斷電），
會產生損毀 JSON，下次啟動時 `_load_all()` 雖然有 try/except 包覆但會靜默丟失該 Recipe。

**目前程式碼**：
```python
path.write_text(
    json.dumps(descriptor.to_dict(), indent=2, ensure_ascii=False),
    encoding="utf-8",
)
```

**修正方式**：
```python
import os
tmp_path = path.with_suffix(".json.tmp")
tmp_path.write_text(
    json.dumps(descriptor.to_dict(), indent=2, ensure_ascii=False),
    encoding="utf-8",
)
os.replace(tmp_path, path)   # 原子操作
```

**注意**：Phase D 後 Recipe 預計也遷移至 SQLite，此修正屬於過渡期保護。

**影響範圍**：`src/core/recipe_registry.py`

---

### [H4] `measurement_engine.py` — `run_multi_batch` 自身 abort 中途無清理

**位置**：`src/core/measurement_engine.py`，`run_multi_batch()`

**問題描述**：
`run_multi_batch` 雖然在 `abort_check` 觸發時 `break` 跳出 dataset 迴圈，
但已經完成的 dataset 結果保留，未完成的 dataset 完全被丟棄，UI 端可能顯示
「批次中斷但缺少最後一個 dataset 的部分結果」。應在 `MultiDatasetBatchRun`
中標記 `aborted=True` 並寫入 `end_time`，讓 UI 能正確區分「正常完成」與「中斷」。

**修正方式**：
```python
@dataclass
class MultiDatasetBatchRun:
    # ... 既有欄位
    aborted: bool = False     # 新增

# run_multi_batch():
for i, ds in enumerate(datasets):
    if abort_check and abort_check():
        mbr.aborted = True
        break
    ...
mbr.end_time = datetime.now(timezone.utc).isoformat()
return mbr
```

**影響範圍**：`src/core/models.py`、`src/core/measurement_engine.py`、`src/gui/workspaces/batch_workspace.py`

---

## 中優先

---

### [M5] `batch_workspace.py` — `BatchRunStore.close()` 從未被呼叫

**位置**：`src/gui/workspaces/batch_workspace.py`、`workspace_host.py`

**問題描述**：
本次（2026-04-27）已新增 `BatchRunStore.close()` 方法，但無任何呼叫方使用它。
應在應用程式關閉時（`MainWindow.closeEvent`）或 batch worker 結束時呼叫，
否則 thread-local SQLite connection 仍會殘留至 process 終止。

**修正方式**（兩處擇一）：
```python
# 方式 A：MainWindow 關閉時
class MainWindow(QMainWindow):
    def closeEvent(self, event):
        self._workspace_host._run_store.close()
        super().closeEvent(event)

# 方式 B：BatchWorker 結束時（避免主線程遺留）
class _BatchWorker(QThread):
    def run(self):
        try:
            ...
        finally:
            # 若 BatchWorker 內有自己的 store 連線
            pass
```

**影響範圍**：`src/gui/main_window.py` 或 `src/gui/workspaces/batch_workspace.py`

---

### [M6] `klarf_export_dialog.py` — 影像預覽 nm_per_pixel=0 時十字落在中心，無警告

**位置**：`src/gui/klarf_export_dialog.py`，`_on_table_row_changed()`

**問題描述**：
本次（2026-04-27）的 B4 修正：當 `m.raw_px=0` 時 `nm_per_pixel` 改為 `0.0`。
影像預覽程式碼遇到 `nm_px <= 0` 時會把十字落在影像中心：
```python
if nm_px > 0:
    px = int(round(cx + xrel_nm / nm_px))
    py = int(round(cy - yrel_nm / nm_px))
else:
    px, py = int(cx), int(cy)
```
這會誤導使用者以為原始與新座標是同一點。應改為顯示警告文字而非繪製假座標。

**修正方式**：
```python
if nm_px <= 0:
    self._image_label.setText(
        f"⚠ 此 defect 的 nm/pixel 無法計算（raw_px=0），無法顯示座標 overlay。"
    )
    return
```

**影響範圍**：`src/gui/klarf_export_dialog.py`

---

### [M7] `control_panel.py` — `load_from_recipe_descriptor` 觸發雙重 preview

**位置**：`src/gui/control_panel.py`，`load_from_recipe_descriptor()`

**問題描述**：
本次（2026-04-27）功能三新增的 `load_from_recipe_descriptor()` 中：
1. 呼叫 `self._add_profile()` → `_add_profile` 結尾觸發 `self._emit()`（用預設值）
2. 設完所有 widget 值後再次 `self._emit()`（用 recipe 值）

兩次 emit 導致 MeasureWorkspace 跑兩次 preview，第一次用預設值會白做，
且高解析度影像下有可見閃爍。

**修正方式**：
在 `_add_profile` 內呼叫 `_emit()` 前加旗標，或在 `load_from_recipe_descriptor`
中暫時停用訊號：
```python
def load_from_recipe_descriptor(self, desc):
    self.blockSignals(True)
    try:
        # 既有清除/新增/設定流程
        ...
    finally:
        self.blockSignals(False)
    self._emit()
```

**影響範圍**：`src/gui/control_panel.py`

---

### [M8] `measure_workspace.py` — 切換 Recipe combo 直接覆蓋現有 Cards 設定

**位置**：`src/gui/workspaces/measure_workspace.py`，`_on_recipe_combo_changed()`

**問題描述**：
本次（2026-04-27）功能三完成後，使用者若已在 ControlPanel 手動細調 Cards 參數，
不小心點到 Recipe combo 切換 → 所有設定被覆蓋且無法復原。應加入確認對話框，
或記錄「未儲存修改」狀態並提示。

**修正方式**：
```python
def _on_recipe_combo_changed(self):
    if self._has_unsaved_card_changes():
        ans = QMessageBox.question(
            self, "覆蓋現有 Cards？",
            "切換 Recipe 將覆蓋目前 ControlPanel Cards 的所有設定，是否繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            # 還原 combo 至上次選擇
            self._recipe_combo.blockSignals(True)
            self._recipe_combo.setCurrentIndex(self._last_recipe_idx)
            self._recipe_combo.blockSignals(False)
            return
    # 既有流程
    ...
```

**影響範圍**：`src/gui/workspaces/measure_workspace.py`

---

### [M9] `klarf_export_dialog.py` — 高解析度 SEM 影像每次選列重新解碼

**位置**：`src/gui/klarf_export_dialog.py`，`_on_table_row_changed()`

**問題描述**：
本次（2026-04-27）功能二的影像預覽：每次選列都呼叫 `cv2.imread()`
重新讀檔解碼。SEM 影像常為 4096×4096 灰階 8-bit（~16 MB），
頻繁切換列時 CPU/IO 負擔可觀。

**修正方式**：
加入 LRU 快取（檔案 → 已解碼 ndarray），上限 8 張：
```python
from functools import lru_cache

@lru_cache(maxsize=8)
def _load_image_cached(path: str):
    import cv2
    return cv2.imread(path, cv2.IMREAD_UNCHANGED)
```
或在 dialog 內以 dict + FIFO 實作。

**影響範圍**：`src/gui/klarf_export_dialog.py`

---

### [M10] `klarf_parser.py` — 階層式 KLARF 多 `DefectRecordSpec` 區塊處理待驗證

**位置**：`src/core/klarf_parser.py`

**問題描述**：
2026-04-27 的 `bbfebe9` commit 加入階層式 KLARF 支援，但若 KLARF 檔案中有
多個 `DefectRecordSpec` 區塊（不同 Sample/Wafer），目前實作只解析第一個。
需以實際多 Sample KLARF 樣本驗證並補強。

**修正方式**：
新增測試樣本，逐一驗證每個 `DefectRecordSpec` 區塊都能被解析、合併到對應的
`SampleRecord` 下。

**影響範圍**：`src/core/klarf_parser.py`、`tests/test_klarf_parser.py`（待新增）

---

## 低優先

---

### [L3] `measurement_engine.py` — `quality_score` PASS 路徑未設定

**位置**：`src/core/measurement_engine.py`，`_worker_run_image()`

**問題描述**：
`quality_score` 在 PASS 路徑（影像通過品質檢查）後不會被設定到 `result` dict，
導致 OK 結果的 result dict 缺少此 key，下游若嘗試讀取 `result["quality_score"]`
會 KeyError。

**修正方式**：
```python
lap_score = check_lap_quality(_raw)
result["quality_score"] = round(lap_score, 2)   # 先設定，PASS/FAIL 都保留
thr = float(args.get("quality_lap_threshold", 140.0))
if lap_score < thr:
    result["status"] = "FAIL"
    result["error"] = (
        f"Low image quality: Laplacian var={lap_score:.1f} "
        f"< threshold {thr:.1f}"
    )
    return result
```

**影響範圍**：`src/core/measurement_engine.py`

---

### [L4] `image_viewer.py` — `nm_per_pixel=0` 時 ruler 計算可能除以零

**位置**：`src/gui/image_viewer.py`，ruler / measurement 計算邏輯

**問題描述**：
若 ImageRecord 的 `pixel_size_nm` 為 0（罕見但可能發生：未校正樣本 + 手動清空 spinbox），
ImageViewer 內的距離量測會除以 0 拋例外。應在 `set_nm_per_pixel()` 加入 guard
（`max(value, 1e-6)`）。

**影響範圍**：`src/gui/image_viewer.py`

---

### [L5] `klarf_export_dialog.py` — 含空白字元路徑可能 cv2.imread 失敗（Windows）

**位置**：`src/gui/klarf_export_dialog.py`、`klarf_exporter.py`

**問題描述**：
Windows 上若影像路徑含中文或特殊字元，`cv2.imread()` 可能返回 None
（cv2 對 UTF-8 路徑支援不完善）。應改用 `cv2.imdecode(np.fromfile(path, np.uint8), ...)`
讀取，繞過 cv2 路徑限制。

**修正方式**：
```python
def _imread_safe(path: str):
    import cv2, numpy as np
    try:
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
```

**影響範圍**：`src/gui/klarf_export_dialog.py`、`src/core/klarf_exporter.py`

---

### [L6] `recipe_workspace.py` — 空 Recipe combo 時 `currentData()` 為 None 缺保護

**位置**：`src/gui/workspaces/recipe_workspace.py`

**問題描述**：
若 `~/.mmh/recipes/` 為空，Recipe combo 沒有任何項目，部分流程呼叫
`currentData()` 取到 None 後直接拿來查找 registry，造成 AttributeError。
應一律先檢查 `is not None`。

**影響範圍**：`src/gui/workspaces/recipe_workspace.py`

---

### [L7] `annotator.py` — X-CD 標注 overlay 座標對齊待驗證

**位置**：`src/core/annotator.py`、`src/core/recipes/cmg_recipe.py`

**問題描述**：
X-CD 模式下 blob 經過 `_rot_blob_to_ori()` 反轉座標回原圖，但 annotator 繪製
overlay 時的座標是否完全對齊待驗證。需以 X-CD 實樣影像逐一比對 annotated PNG。

**影響範圍**：`src/core/annotator.py`

---

## 規劃中（Phase D / Phase E）

| 項目 | 描述 |
|------|------|
| Recipe SQLite 遷移 | `recipe_registry.py` 由 JSON 改為 SQLite（與 BatchRunStore 同步） |
| Plugin 介面 | `BaseRecipe` 擴充為可插拔，支援第三方 Recipe 動態載入 |
| Review Accept/Reject | ReviewWorkspace 加入 Accept / Reject / Mark False Detect 操作 |
| Worker 上限保護 | Batch Worker 數加上限（CPU × 2 或 16 取小者） |
| ValidationWorkspace 完善 | 黃金樣品驗證 UI 補完（目前後端已有，UI 待補） |
| HistoryWorkspace 完善 | 歷史趨勢 UI 加入更多篩選與比對 |

---

# 三、修復後驗證步驟

```bash
# 1. 語法檢查（所有修改的檔案）
python3 -m py_compile src/core/measurement_engine.py
python3 -m py_compile src/core/batch_run_store.py
python3 -m py_compile src/core/recipe_registry.py
python3 -m py_compile src/core/klarf_exporter.py
python3 -m py_compile src/core/klarf_writer.py
python3 -m py_compile src/core/klarf_parser.py
python3 -m py_compile src/core/image_loader.py
python3 -m py_compile src/output/report_generator.py
python3 -m py_compile src/gui/file_tree_panel.py
python3 -m py_compile src/gui/batch_dialog.py
python3 -m py_compile src/gui/control_panel.py
python3 -m py_compile src/gui/image_viewer.py
python3 -m py_compile src/gui/klarf_export_dialog.py
python3 -m py_compile src/gui/workspaces/measure_workspace.py
python3 -m py_compile src/gui/workspaces/recipe_workspace.py
python3 -m py_compile src/gui/workspaces/report_workspace.py
python3 -m py_compile src/gui/workspaces/batch_workspace.py
python3 -m py_compile src/gui/workspace_host.py

# 2. 執行不依賴 numpy/cv2 的測試
pytest tests/test_models.py tests/test_batch_run_store.py tests/test_history.py -v

# 3. 有 numpy+cv2 環境時執行完整測試
pytest tests/ -v
```

---

# 四、重要注意事項

- **KLARF YREL 換算必須維持減號**：`YREL_new = YREL_orig - dy_nm`，勿改為加號
- **`analyze()` gap edge** 必須使用 `upper.y1` / `lower.y0`（bbox 邊緣），不可改回 `cy ± height/2`
- **全圖 MIN/MAX re-flag** 必須使用 `_flag_global_minmax`，確保整張圖只有一個 MIN 和一個 MAX
- **核心演算法**（`cmg_analyzer.py`、`preprocessor.py`、`mg_detector.py`、`annotator.py`）除非有充分測試，否則不要修改
- **Run Single 不再跳轉至 Review**（2026-04-27 後）：MeasureWorkspace 結果就地顯示，Review 仍透過 `run_completed` 訊號同步資料但不切換 tab
- **ControlPanel `load_from_recipe_descriptor()`** 為 2026-04-27 新增方法：將 Recipe descriptor 套用到 cards，僅在 Measure workspace 切換 Recipe 時呼叫
- **`BatchRunStore.close()`** 為 2026-04-27 新增方法：釋放 thread-local SQLite connection，建議在 MainWindow.closeEvent 呼叫（M5 待修）
