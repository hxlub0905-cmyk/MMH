# SEM MM — 待修復 Bug 清單 Prompt
> 產生日期：2026-04-27
> 適用版本：Bug Fix Series Round2 之後（含 KLARF Export、nm/px 統一整合）

---

## 背景說明

請你作為 SEM MM 專案的 AI 開發助手，依照以下清單逐一修復 Bug。
每修復一項請：
1. 在 `SESSION_LOG.md` 最上方新增 session 記錄
2. 執行 `python3 -m py_compile <修改的檔案>` 確認語法無誤
3. 若該 Bug 有對應測試，執行 `pytest tests/ -v` 確認通過

專案架構請參考 `AGENTS.md`，核心演算法（`cmg_analyzer.py`）請勿修改。

---

## 高優先修復項目

---

### [H1] `measurement_engine.py` — `cv2.imwrite` 無回傳值檢查

**位置**：`src/core/measurement_engine.py`，函式 `_worker_run_image()`

**問題描述**：
`cv2.imwrite()` 在寫入失敗時（磁碟滿、路徑不存在、權限不足）只會靜默回傳 `False`，
不會拋出例外。目前程式碼沒有檢查回傳值，直接把路徑存入 `result["overlay_path"]`，
導致下游以為 overlay 圖片存在，但實際上檔案並不存在。

**目前程式碼**：
```python
cv2.imwrite(out_path, annotated)
result["overlay_path"] = out_path
```

**修正方式**：
```python
ret = cv2.imwrite(out_path, annotated)
if not ret:
    raise IOError(f"cv2.imwrite 寫入失敗，請確認路徑與磁碟空間：{out_path}")
result["overlay_path"] = out_path
```

**影響範圍**：`src/core/measurement_engine.py`

---

### [H2] `batch_run_store.py` — `save()` 非原子寫入

**位置**：`src/core/batch_run_store.py`，函式 `save()` 與 `save_multi()`

**問題描述**：
目前直接使用 `path.write_text(...)` 寫入，若寫入過程中程式崩潰（例如強制關閉、
斷電），會產生損毀的 JSON 檔案，下次載入時直接報錯。
應改為先寫入 `.tmp` 暫存檔，確認寫入完成後再用 `os.replace()` 原子替換。

**目前程式碼**：
```python
path.write_text(
    json.dumps(batch_run.to_dict(), indent=2, ensure_ascii=False),
    encoding="utf-8",
)
```

**修正方式**：
```python
import os

tmp_path = path.with_suffix(".json.tmp")
tmp_path.write_text(
    json.dumps(batch_run.to_dict(), ensure_ascii=False, separators=(',', ':')),
    encoding="utf-8",
)
os.replace(tmp_path, path)   # 原子操作，寫入完成才替換
```

**注意**：同時移除 `indent=2`，改用 `separators=(',', ':')` 壓縮格式，
可大幅減少檔案大小與序列化時間（對 13000 張圖的 batch 影響尤其明顯）。

**影響範圍**：`src/core/batch_run_store.py`（`save()` 與 `save_multi()` 兩處）

---

### [H3] `image_loader.py` — `img.ptp()` NumPy 2.0 已移除

**位置**：`src/core/image_loader.py`，函式 `load_grayscale()`

**問題描述**：
`ndarray.ptp()` 方法在 NumPy 2.0 中已被正式移除（deprecated since 1.x）。
目前在處理非 uint8 影像時使用此方法，在 NumPy 2.0 環境下會直接 `AttributeError` 崩潰。

**目前程式碼**：
```python
img = ((img - img.min()) / (img.ptp() + 1e-9) * 255).astype(np.uint8)
```

**修正方式**：
```python
img = ((img - img.min()) / ((img.max() - img.min()) + 1e-9) * 255).astype(np.uint8)
```

**影響範圍**：`src/core/image_loader.py`

---

## 中優先修復項目

---

### [M1] `report_workspace.py` — `ExportDialog` tasks 為空時無任何提示

**位置**：`src/gui/workspaces/report_workspace.py`，函式 `_export_dialog_clicked()`

**問題描述**：
當使用者在 Export Dialog 中沒有勾選任何格式（或所有格式都因條件不符被跳過），
`tasks` list 為空，函式直接 `return` 結束，使用者完全不知道為何沒有任何動作發生。

**目前程式碼**：
```python
if not tasks:
    return
```

**修正方式**：
```python
if not tasks:
    QMessageBox.information(
        self,
        "未選擇任何輸出格式",
        "請至少勾選一種匯出格式（Excel、JSON、HTML 或圖片）。",
    )
    return
```

**影響範圍**：`src/gui/workspaces/report_workspace.py`

---

### [M2] `batch_dialog.py` — X 軸 Blob 座標轉換與 `_rot_blob_to_ori` 不一致（差 1px）

**位置**：`src/gui/batch_dialog.py`，函式 `_process_one()` 中 X 軸 blob 轉換段落

**問題描述**：
Legacy batch dialog 在處理 X-CD 時，blob 座標從旋轉空間轉回原始影像空間的公式，
與 `cmg_recipe.py` 的 `_rot_blob_to_ori()` 函式不一致，導致差 1px 的系統性偏移。

**目前程式碼**（`batch_dialog.py`）：
```python
blobs = [Blob(
    label=b.label,
    x0=b.y0, y0=(h - 1) - (b.x1 - 1),
    x1=b.y1, y1=(h - 1) - b.x0 + 1,
    area=b.area, cx=b.cy, cy=(h - 1) - b.cx
) for b in blobs]
```

**`_rot_blob_to_ori()` 的正確公式**（`cmg_recipe.py`）：
```python
ox0 = int(b.y0)
oy0 = int(orig_h - b.x1)
ox1 = int(b.y1)
oy1 = int(orig_h - b.x0)
```

**修正方式**：
在 `batch_dialog.py` 頂部 import `_rot_blob_to_ori`，並將 blob 轉換改為：
```python
from ..core.recipes.cmg_recipe import _rot_blob_to_ori
# ...
if axis.startswith("X"):
    blobs = [_rot_blob_to_ori(b, h) for b in blobs]
```

**影響範圍**：`src/gui/batch_dialog.py`

---

### [M3] `file_tree_panel.py` — 缺少 `root_path()` 方法，file count 永不顯示

**位置**：`src/gui/file_tree_panel.py`

**問題描述**：
`browse_workspace.py` 的 `_update_file_count()` 呼叫 `self._tree.root_path()`，
但 `FileTreePanel` 類別從未實作此方法。
目前靠 `hasattr` 保護不會崩潰，但 file count 標籤永遠顯示空白。

**目前程式碼**（`file_tree_panel.py`）：
缺少 `root_path()` 方法，且 `set_root()` 沒有記錄 root 路徑。

**修正方式**：
```python
class FileTreePanel(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Path | None = None   # 新增
        # ... 其餘不變

    def set_root(self, folder: str | Path) -> None:
        self.clear()
        self._root = Path(folder)        # 新增：記錄 root
        self._populate(self.invisibleRootItem(), self._root)
        self.expandAll()

    def root_path(self) -> Path | None:  # 新增方法
        return self._root
```

**影響範圍**：`src/gui/file_tree_panel.py`

---

### [M4] `report_generator.py` — HTML 報告 fail_list 未做 `html.escape()`

**位置**：`src/output/report_generator.py`，函式 `_render_html()`

**問題描述**：
失敗影像的檔名（`fail_list`）直接插入 HTML，若路徑包含 `<`、`>`、`&` 等字元，
會造成 HTML 版面破裂，甚至產生 XSS 風險（若路徑來自外部輸入）。

**目前程式碼**：
```python
fail_items = "".join(f"<li>{name}</li>" for name in fail_list) or "<li>None</li>"
```

**修正方式**：
```python
import html as _html
fail_items = "".join(
    f"<li>{_html.escape(name)}</li>" for name in fail_list
) or "<li>None</li>"
```

同時檢查 `generate_multi_dataset_report()` 中 dataset label 是否也需要 escape：
```python
# 修正前
f"<h2>{label}</h2>"
# 修正後
f"<h2>{_html.escape(label)}</h2>"
```

**影響範圍**：`src/output/report_generator.py`

---

## 低優先修復項目

---

### [L1] `recipe_workspace.py` — `_save_recipe()` 廢棄 EC key 永久累積

**位置**：`src/gui/workspaces/recipe_workspace.py`，函式 `_save_recipe()`

**問題描述**：
`edge_locator_config` 使用 `**(desc.edge_locator_config.to_dict() if desc else {})` 
先展開舊有 key，再覆蓋 UI 控制的 key。這樣舊版 Recipe JSON 中的廢棄 key
（例如早期版本的 `"subpixel"` key）會永久保留在新存的 Recipe 中，
隨著版本迭代導致 key 越積越多。

**修正方式**：
定義 canonical key set，存檔時只保留已知 key：

```python
_EC_CANONICAL_KEYS = {
    "ycd_edge_method", "threshold_frac", "sample_lines_mode",
    "aggregate_method", "profile_lpf_enabled", "profile_lpf_sigma",
    "x_overlap_ratio", "y_cluster_tol", "border_margin_px", "x_inset_px",
    "subpixel_half_col", "subpixel_search_half", "subpixel_proximity",
    "subpixel_smooth_k", "subpixel_min_grad_frac", "subpixel_peak_ratio",
}

# _save_recipe() 中的 edge_locator_config 改為：
edge_locator_config=RecipeConfig(data={
    # 只保留 canonical keys（過濾廢棄 key）
    **{k: v for k, v in (desc.edge_locator_config.to_dict() if desc else {}).items()
       if k in _EC_CANONICAL_KEYS},
    # UI 控制的 key 直接覆蓋
    "ycd_edge_method":     self._edge_method.currentData(),
    "threshold_frac":      self._threshold_frac.value(),
    # ... 其餘不變
}),
```

**影響範圍**：`src/gui/workspaces/recipe_workspace.py`

---

### [L2] `klarf_exporter.py` — XREL/YREL 欄位名稱大小寫混合時靜默略過

**位置**：`src/core/klarf_exporter.py`，函式 `KlarfTopNExporter.export()` 中更新座標的段落

**問題描述**：
目前只比對全大寫（`"XREL"`）或全小寫（`"xrel"`），若 KLARF 廠商使用混合大小寫
（例如 `"Xrel"`、`"XRel"`），座標不會被更新，但也不會報錯，靜默略過。

**目前程式碼**：
```python
if "XREL" in d:
    d["XREL"] = str(int(round(item["xrel_new"])))
elif "xrel" in d:
    d["xrel"] = str(int(round(item["xrel_new"])))
```

**修正方式**：
```python
# 找出實際的 key 名稱（不分大小寫）
xrel_key = next((k for k in d if k.lower() == "xrel"), None)
yrel_key = next((k for k in d if k.lower() == "yrel"), None)

if xrel_key:
    d[xrel_key] = str(int(round(item["xrel_new"])))
if yrel_key:
    d[yrel_key] = str(int(round(item["yrel_new"])))
```

**同樣修正** `klarf_writer.py` 的 `_serialise_defect()` 中的欄位比對邏輯。

**影響範圍**：`src/core/klarf_exporter.py`、`src/core/klarf_writer.py`

---

### [L3] `measurement_engine.py` — `quality_score` 只在 FAIL 路徑設定

**位置**：`src/core/measurement_engine.py`，函式 `_worker_run_image()`

**問題描述**：
`quality_score` 在影像通過品質檢查（PASS）後不會被設定到 `result` dict，
導致 OK 結果的 result dict 缺少此 key，下游若嘗試讀取 `result["quality_score"]`
會 `KeyError`。

**目前程式碼**：
```python
result["quality_score"] = round(lap_score, 2)
thr = float(args.get("quality_lap_threshold", 140.0))
if lap_score < thr:
    result["status"] = "FAIL"
    result["error"] = (...)
    return result   # ← quality_score 有設定
# 之後沒有再設定 quality_score，OK 路徑的 result 缺此 key
```

**修正方式**：
`quality_score` 在品質檢查後立即設定，不論 PASS 或 FAIL 都保留：
```python
lap_score = check_lap_quality(_raw)
result["quality_score"] = round(lap_score, 2)   # 先設定，不論結果
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

## 修復後驗證步驟

```bash
# 1. 語法檢查（所有修改的檔案）
python3 -m py_compile src/core/measurement_engine.py
python3 -m py_compile src/core/batch_run_store.py
python3 -m py_compile src/core/image_loader.py
python3 -m py_compile src/core/klarf_exporter.py
python3 -m py_compile src/core/klarf_writer.py
python3 -m py_compile src/output/report_generator.py
python3 -m py_compile src/gui/file_tree_panel.py
python3 -m py_compile src/gui/batch_dialog.py
python3 -m py_compile src/gui/workspaces/report_workspace.py
python3 -m py_compile src/gui/workspaces/recipe_workspace.py

# 2. 執行不依賴 numpy/cv2 的測試
pytest tests/test_models.py tests/test_batch_run_store.py tests/test_history.py -v

# 3. 有 numpy+cv2 環境時執行完整測試
pytest tests/ -v
```

---

## 重要注意事項

- **KLARF YREL 換算必須維持減號**：`YREL_new = YREL_orig - dy_nm`，勿改為加號
- **`analyze()` gap edge** 必須使用 `upper.y1` / `lower.y0`（bbox 邊緣），不可改回 `cy ± height/2`
- **全圖 MIN/MAX re-flag** 必須使用 `_flag_global_minmax`，確保整張圖只有一個 MIN 和一個 MAX
- **核心演算法**（`cmg_analyzer.py`、`preprocessor.py`、`mg_detector.py`、`annotator.py`）除非有充分測試，否則不要修改
