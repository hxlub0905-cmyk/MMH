# SEM MM — BatchRunStore 改為 SQLite 儲存 Prompt
> 產生日期：2026-04-27
> 適用版本：Bug Fix Series Round2 之後（含 KLARF Export、nm/px 統一整合）

---

## 背景與動機

### 目前問題

`BatchRunStore` 目前將每次 batch 執行結果儲存為 JSON 檔案（`~/.mmh/runs/*.json`）。
當 batch 規模較大（例如 13000 張圖 × 每張 20 筆量測 = 26 萬筆資料）時，
`json.dumps()` 序列化加上 `write_text()` 磁碟寫入，即使放在 QThread 背景執行，
仍因 Python GIL 造成主執行緒明顯卡頓，使用者會感受到 UI 凍結數秒。

### 目標

將所有持久化改為 **SQLite**（Python 內建，不需安裝額外套件），達到：
1. **寫入速度大幅提升**：SQLite bulk insert 遠快於 JSON 序列化
2. **UI 不再卡頓**：寫入分批進行，GIL 競爭分散
3. **查詢效率提升**：`get_stats_for_recipe()` 從掃描所有 JSON 改為一行 SQL
4. **單一資料庫檔案**：`~/.mmh/runs.db`，不再散落一堆 JSON 檔案
5. **舊 JSON 檔案直接捨棄**（不做遷移）

---

## 資料庫規格

### 路徑

```
~/.mmh/runs.db
```

### Schema

```sql
-- ================================================================
-- Table 1: batch_runs（每個 batch 一行，meta 資料）
-- ================================================================
CREATE TABLE IF NOT EXISTS batch_runs (
    batch_id      TEXT PRIMARY KEY,
    type          TEXT NOT NULL,     -- 'single' | 'multi'
    run_id        TEXT,              -- multi 專用（multi_{uuid}），single 為 NULL
    parent_run_id TEXT,              -- multi 子 dataset 指向 parent multi run_id
    dataset_label TEXT DEFAULT '',
    input_folder  TEXT DEFAULT '',
    recipe_ids    TEXT DEFAULT '[]', -- JSON array 字串，例如 '["r1","r2"]'
    start_time    TEXT DEFAULT '',
    end_time      TEXT DEFAULT '',
    total_images  INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count    INTEGER DEFAULT 0,
    worker_count  INTEGER DEFAULT 1,
    error_log     TEXT DEFAULT '[]'  -- JSON array 字串
);

-- ================================================================
-- Table 2: image_results（每張圖一行）
-- ================================================================
CREATE TABLE IF NOT EXISTS image_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT NOT NULL,
    image_path    TEXT DEFAULT '',
    image_id      TEXT DEFAULT '',
    status        TEXT DEFAULT 'OK', -- 'OK' | 'FAIL'
    error         TEXT DEFAULT '',
    overlay_path  TEXT DEFAULT '',
    quality_score REAL,
    FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
);

-- ================================================================
-- Table 3: measurements（每筆量測一行，資料量最大）
-- ================================================================
CREATE TABLE IF NOT EXISTS measurements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id       TEXT NOT NULL,
    image_id       TEXT DEFAULT '',
    recipe_id      TEXT DEFAULT '',
    measurement_id TEXT DEFAULT '',
    feature_type   TEXT DEFAULT '',
    feature_id     TEXT DEFAULT '',
    axis           TEXT DEFAULT 'Y',
    raw_px         REAL DEFAULT 0.0,
    calibrated_nm  REAL DEFAULT 0.0,
    center_x       REAL DEFAULT 0.0,
    center_y       REAL DEFAULT 0.0,
    cmg_id         INTEGER DEFAULT 0,
    col_id         INTEGER DEFAULT 0,
    flag           TEXT DEFAULT '',
    status         TEXT DEFAULT 'normal',
    review_state   TEXT DEFAULT 'unreviewed',
    extra_metrics  TEXT DEFAULT '{}', -- JSON 字串（bbox 等不常查詢的雜項欄位）
    FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
);

-- ================================================================
-- Indexes（加速常用查詢）
-- ================================================================
CREATE INDEX IF NOT EXISTS idx_image_results_batch_id
    ON image_results(batch_id);

CREATE INDEX IF NOT EXISTS idx_measurements_batch_id
    ON measurements(batch_id);

CREATE INDEX IF NOT EXISTS idx_measurements_recipe_id
    ON measurements(recipe_id);

CREATE INDEX IF NOT EXISTS idx_measurements_calibrated_nm
    ON measurements(calibrated_nm);

CREATE INDEX IF NOT EXISTS idx_batch_runs_start_time
    ON batch_runs(start_time);

CREATE INDEX IF NOT EXISTS idx_batch_runs_parent_run_id
    ON batch_runs(parent_run_id);
```

---

## 對外 API 規格（必須與舊版相容）

### 變更項目

| 舊版 | 新版 | 說明 |
|------|------|------|
| `load(file_path: str)` | `load(batch_id: str)` | 改吃 batch_id |
| `delete(file_path: str)` | `delete(batch_id: str)` | 改吃 batch_id |
| `list_runs()` 回傳 `file_path` | `list_runs()` 回傳 `batch_id` 在 `"file_path"` 欄位 | 欄位名稱不變，值改為 batch_id（外部呼叫方透明相容） |

### 不變項目

```python
store.save(batch_run: BatchRunRecord) -> str          # 回傳 batch_id（原本回傳 Path）
store.save_multi(mbr: MultiDatasetBatchRun) -> str    # 回傳 batch_id
store.list_runs() -> list[dict]                       # 結構不變
store.load(batch_id: str) -> BatchRunRecord | MultiDatasetBatchRun
store.delete(batch_id: str) -> bool
store.get_stats_for_recipe(recipe_id, _summaries) -> list[dict]
```

### `list_runs()` 回傳 dict 結構

每個 dict 包含以下欄位（與舊版相同，`file_path` 欄位改存 `batch_id`）：

```python
{
    "batch_id":      str,   # batch_id 或 "multi_{run_id}"
    "type":          str,   # "single" | "multi"
    "start_time":    str,   # ISO 8601
    "total_images":  int,
    "success_count": int,
    "fail_count":    int,
    "input_folder":  str,
    "dataset_label": str,
    "file_path":     str,   # ← 改存 batch_id（供 load/delete 使用）
    "recipe_ids":    list[str],
}
```

---

## 實作規格

### 類別結構

```python
class BatchRunStore:
    def __init__(self, db_path: Path | None = None):
        """
        db_path 預設為 ~/.mmh/runs.db
        初始化時執行 CREATE TABLE IF NOT EXISTS（冪等，安全重複執行）
        使用 WAL mode 提升並發寫入效能：PRAGMA journal_mode=WAL
        使用 thread-local connection 確保多執行緒安全
        """

    def _get_conn(self) -> sqlite3.Connection:
        """
        取得目前執行緒的 connection（thread-local）。
        設定：
          - PRAGMA journal_mode = WAL
          - PRAGMA synchronous = NORMAL   （比 FULL 快，資料安全性足夠）
          - PRAGMA foreign_keys = ON
          - row_factory = sqlite3.Row
        """

    def save(self, batch_run: BatchRunRecord) -> str:
        """
        儲存單一批次結果，回傳 batch_id。

        寫入順序（在同一個 transaction 內）：
        1. INSERT OR REPLACE INTO batch_runs（meta）
        2. INSERT INTO image_results（每張圖一行）
        3. INSERT INTO measurements（每筆量測一行，用 executemany 批次插入）

        measurements 資料來源：
          result["measurements"] 是 MeasurementRecord.to_dict() 的列表
          直接從此 list 取欄位，不需要重新 deserialize

        extra_metrics 欄位：
          json.dumps(m.get("extra_metrics", {}), ensure_ascii=False, separators=(',',':'))

        回傳值：batch_run.batch_id
        """

    def save_multi(self, mbr: MultiDatasetBatchRun) -> str:
        """
        儲存多資料集批次結果，回傳 "multi_{run_id}"。

        寫入策略：
        1. 為 multi run 本身寫一行 batch_runs（type='multi', run_id=mbr.run_id）
        2. 為每個 dataset 寫一行 batch_runs（type='single', parent_run_id=mbr.run_id）
        3. 各 dataset 的 image_results 和 measurements 掛在 dataset 的 batch_id 下

        全部在同一個 transaction 內完成。
        """

    def list_runs(self) -> list[dict]:
        """
        只查詢 type='single' 或 type='multi'（不含子 dataset）的記錄。
        依 start_time 降序排列。

        SQL：
          SELECT * FROM batch_runs
          WHERE parent_run_id IS NULL
          ORDER BY start_time DESC
        """

    def load(self, batch_id: str) -> BatchRunRecord | MultiDatasetBatchRun:
        """
        依 batch_id 重建 BatchRunRecord 或 MultiDatasetBatchRun。

        判斷 type：
          SELECT type FROM batch_runs WHERE batch_id = ?

        若 type='multi'：
          1. 查詢所有 parent_run_id = batch_id 的子 dataset
          2. 為每個子 dataset 呼叫 _load_single(child_batch_id)
          3. 組合成 MultiDatasetBatchRun

        若 type='single'：
          呼叫 _load_single(batch_id)

        _load_single(batch_id) 的邏輯：
          1. SELECT * FROM batch_runs WHERE batch_id = ?
          2. SELECT * FROM image_results WHERE batch_id = ?
          3. 對每張圖：SELECT * FROM measurements WHERE batch_id = ? AND image_id = ?
          4. 組合成 BatchRunRecord，output_manifest["results"] 重建為舊格式 list
        """

    def delete(self, batch_id: str) -> bool:
        """
        刪除一筆記錄（CASCADE 刪除 image_results 和 measurements）。

        若為 multi type，同時刪除所有 parent_run_id = batch_id 的子 dataset。
        """

    def get_stats_for_recipe(
        self,
        recipe_id: str | None = None,
        _summaries: list[dict] | None = None,
    ) -> list[dict]:
        """
        計算各 batch 的 CD 統計，供 History Run Chart 使用。

        SQL（有 recipe_id 過濾）：
          SELECT
            br.batch_id,
            br.start_time,
            br.dataset_label,
            br.input_folder,
            AVG(m.calibrated_nm) as mean_nm,
            -- SQLite 沒有內建 stdev，用 Python statistics 計算
          FROM batch_runs br
          JOIN measurements m ON m.batch_id = br.batch_id
          WHERE m.status != 'rejected'
            AND (? IS NULL OR m.recipe_id = ?)
            AND br.parent_run_id IS NULL  -- 只算 top-level batch
          GROUP BY br.batch_id
          ORDER BY br.start_time ASC

        stdev 用 Python statistics.stdev() 計算（從 GROUP BY 結果取值列表）。

        回傳格式（與舊版相同）：
          [{"start_time", "mean_nm", "std_nm", "n", "label", "file_path"}, ...]
          file_path 欄位存 batch_id（與 list_runs 一致）
        """
```

---

## 需要同步修改的其他檔案

### `src/gui/workspaces/batch_workspace.py`

`_HistoryDialog` 和 `_on_history_selected()` 中：

```python
# 舊版
self.run_selected.emit(self._summaries[row]["file_path"])  # 傳 file_path
# ...
result = self._run_store.load(file_path)  # 吃 file_path

# 新版
self.run_selected.emit(self._summaries[row]["file_path"])  # 傳 batch_id（欄位名不變）
# ...
result = self._run_store.load(batch_id)  # 吃 batch_id
```

因為 `list_runs()` 的 `"file_path"` 欄位改存 batch_id，
`run_selected` signal 傳的值已經是 batch_id，
只需要確認 `_on_history_selected()` 把收到的值直接傳給 `store.load()` 即可。

### `src/gui/workspaces/report_workspace.py`

`load_from_file()` 改名為 `load_from_batch_id()`，或維持舊名但參數語意改變：

```python
def load_from_file(self, batch_id: str) -> None:  # 參數名改，語意改
    result = self._run_store.load(batch_id)
    # 其餘不變
```

### `src/gui/klarf_export_dialog.py`

`_on_history_selected()` 同上，確認傳入的是 batch_id 即可。

### `tests/test_batch_run_store.py` 與 `tests/test_history.py`

```python
# 舊版測試
store = BatchRunStore(runs_dir=tmp_path)
path = store.save(batch)
loaded = store.load(str(path))

# 新版測試
store = BatchRunStore(db_path=tmp_path / "test.db")
batch_id = store.save(batch)
loaded = store.load(batch_id)

# delete 測試
deleted = store.delete(batch_id)
assert deleted is True
```

---

## 實作注意事項

### 執行緒安全

SQLite 在 Python 中預設不是 thread-safe（`check_same_thread=True`）。
`_SaveWorker` 在 QThread 背景執行，需使用 thread-local connection：

```python
import threading

class BatchRunStore:
    def __init__(self, db_path=None):
        self._db_path = db_path or (Path.home() / ".mmh" / "runs.db")
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn
```

### WAL Mode

務必啟用 WAL（Write-Ahead Logging），允許讀寫並發，避免主執行緒讀取時被 QThread 的寫入鎖住：

```python
conn.execute("PRAGMA journal_mode=WAL")
```

### Batch Insert

measurements 用 `executemany()` 而非逐行 `execute()`，效能差異可達 10-100 倍：

```python
conn.executemany(
    "INSERT INTO measurements (batch_id, image_id, recipe_id, ...) VALUES (?, ?, ?, ...)",
    [(batch_id, m["image_id"], m["recipe_id"], ...) for m in all_measurements]
)
```

### output_manifest 重建

`load()` 重建的 `BatchRunRecord.output_manifest["results"]` 格式需與舊版一致，
供 `report_workspace.py` 的 `_LoadWorker` 使用：

```python
# output_manifest["results"] 中每個 result 的格式
{
    "image_path":  str,
    "image_id":    str,
    "status":      str,
    "error":       str,
    "measurements": [MeasurementRecord.to_dict(), ...],   # 從 measurements table 重建
    "cuts":        [],   # 舊格式，可為空（Report workspace 不使用此欄位）
    "overlay_path": str | None,
    "quality_score": float | None,
}
```

### `get_stats_for_recipe()` 的 stdev

SQLite 沒有內建 `STDEV` 函數。可以：
1. 先用 SQL 取得所有 `calibrated_nm` 值，再用 Python `statistics.stdev()` 計算
2. 或在 `_get_conn()` 時用 `conn.create_aggregate()` 自訂 stdev 聚合函數

建議選方案 1（更簡單）：

```python
rows = conn.execute("""
    SELECT br.batch_id, br.start_time, br.dataset_label, br.input_folder,
           m.calibrated_nm
    FROM batch_runs br
    JOIN measurements m ON m.batch_id = br.batch_id
    WHERE m.status != 'rejected'
      AND br.parent_run_id IS NULL
      AND (? IS NULL OR m.recipe_id = ?)
    ORDER BY br.start_time ASC, br.batch_id
""", (recipe_id, recipe_id)).fetchall()

# 用 Python 按 batch_id 分組後計算 mean/stdev
```

---

## 驗證步驟

```bash
# 1. 語法檢查
python3 -m py_compile src/core/batch_run_store.py

# 2. 單元測試（不需 numpy/cv2）
pytest tests/test_batch_run_store.py tests/test_history.py -v

# 3. 確認 DB 檔案產生
python3 -c "
from src.core.batch_run_store import BatchRunStore
from src.core.models import BatchRunRecord
store = BatchRunStore()
br = BatchRunRecord(
    batch_id='test-001',
    input_folder='/tmp',
    recipe_ids=['r1'],
    total_images=5,
    success_count=5,
    fail_count=0,
    start_time='2026-04-27T00:00:00+00:00',
)
bid = store.save(br)
print('saved:', bid)
runs = store.list_runs()
print('list_runs:', runs)
loaded = store.load(bid)
print('loaded:', loaded.batch_id)
store.delete(bid)
print('deleted, remaining:', len(store.list_runs()))
"

# 4. 確認 DB 路徑
ls -lh ~/.mmh/runs.db
```

---

## 不需要修改的檔案

以下檔案的邏輯完全不需要改動：

- `src/core/models.py`
- `src/core/measurement_engine.py`
- `src/core/recipes/cmg_recipe.py`
- `src/gui/workspaces/report_workspace.py`（`load_from_file()` 參數語意改但簽名不變）
- `src/output/` 所有匯出模組
- 所有核心演算法模組

---

## 重要注意事項

- **不做舊 JSON 遷移**：`~/.mmh/runs/*.json` 舊檔案直接忽略，不搬移也不刪除
- **WAL mode 必須啟用**：否則 QThread 寫入時會鎖住主執行緒的讀取
- **foreign_keys 必須啟用**：SQLite 預設關閉 foreign key 約束
- **`executemany` 批次插入**：measurements 資料量大，絕對不要用逐行 INSERT
- **`extra_metrics` 存 JSON 字串**：bbox 等複雜欄位不拆表，直接 `json.dumps()` 存為 TEXT
- **核心演算法不動**：`cmg_analyzer.py` 等核心模組完全不需要修改
