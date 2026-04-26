"""BatchRunStore — 批次結果的 SQLite 持久化管理器（Phase D）。

所有歷史 batch 結果以 SQLite 儲存於 ~/.mmh/runs.db。
舊版 ~/.mmh/runs/*.json 檔案直接忽略，不做遷移。
"""
from __future__ import annotations

import json
import sqlite3
import statistics as _stats
import threading
from collections import defaultdict
from pathlib import Path

from .models import BatchRunRecord, MultiDatasetBatchRun

DB_PATH = Path.home() / ".mmh" / "runs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batch_runs (
    batch_id      TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    run_id        TEXT,
    parent_run_id TEXT,
    dataset_label TEXT DEFAULT '',
    input_folder  TEXT DEFAULT '',
    recipe_ids    TEXT DEFAULT '[]',
    start_time    TEXT DEFAULT '',
    end_time      TEXT DEFAULT '',
    total_images  INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count    INTEGER DEFAULT 0,
    worker_count  INTEGER DEFAULT 1,
    error_log     TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS image_results (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id      TEXT NOT NULL,
    image_path    TEXT DEFAULT '',
    image_id      TEXT DEFAULT '',
    status        TEXT DEFAULT 'OK',
    error         TEXT DEFAULT '',
    overlay_path  TEXT DEFAULT '',
    quality_score REAL,
    FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
);

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
    extra_metrics  TEXT DEFAULT '{}',
    FOREIGN KEY (batch_id) REFERENCES batch_runs(batch_id)
);

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
"""

_INSERT_MEAS = """
INSERT INTO measurements
    (batch_id, image_id, recipe_id, measurement_id,
     feature_type, feature_id, axis, raw_px, calibrated_nm,
     center_x, center_y, cmg_id, col_id, flag,
     status, review_state, extra_metrics)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""

_INSERT_IMG = """
INSERT INTO image_results
    (batch_id, image_path, image_id, status, error, overlay_path, quality_score)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def _meas_tuple(batch_id: str, m: dict) -> tuple:
    return (
        batch_id,
        m.get("image_id", ""),
        m.get("recipe_id", ""),
        m.get("measurement_id", ""),
        m.get("feature_type", ""),
        m.get("feature_id", ""),
        m.get("axis", "Y"),
        float(m.get("raw_px", 0.0)),
        float(m.get("calibrated_nm", 0.0)),
        float(m.get("center_x", 0.0)),
        float(m.get("center_y", 0.0)),
        int(m.get("cmg_id", 0)),
        int(m.get("col_id", 0)),
        m.get("flag", ""),
        m.get("status", "normal"),
        m.get("review_state", "unreviewed"),
        _j(m.get("extra_metrics", {})),
    )


class BatchRunStore:
    def __init__(self, db_path: Path | None = None):
        """
        db_path 預設為 ~/.mmh/runs.db。
        初始化時建立所有資料表與索引（冪等）。
        使用 thread-local connection 確保多執行緒安全。
        """
        self._db_path = db_path or DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """取得目前執行緒的 SQLite connection（WAL + NORMAL sync + FK ON）。"""
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, batch_run: BatchRunRecord) -> str:
        """儲存單一批次結果，回傳 batch_id。

        寫入順序（同一 transaction）：
        1. INSERT OR REPLACE INTO batch_runs
        2. INSERT INTO image_results
        3. executemany INTO measurements
        """
        conn = self._get_conn()
        results = batch_run.output_manifest.get("results", [])

        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO batch_runs
                   (batch_id, type, dataset_label, input_folder, recipe_ids,
                    start_time, end_time, total_images, success_count, fail_count,
                    worker_count, error_log)
                   VALUES (?, 'single', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    batch_run.batch_id,
                    batch_run.dataset_label,
                    batch_run.input_folder,
                    _j(list(batch_run.recipe_ids)),
                    batch_run.start_time,
                    batch_run.end_time,
                    batch_run.total_images,
                    batch_run.success_count,
                    batch_run.fail_count,
                    batch_run.worker_count,
                    _j(batch_run.error_log),
                ),
            )
            conn.executemany(
                _INSERT_IMG,
                [
                    (
                        batch_run.batch_id,
                        r.get("image_path", ""),
                        r.get("image_id", ""),
                        r.get("status", "OK"),
                        r.get("error", ""),
                        r.get("overlay_path") or "",
                        r.get("quality_score"),
                    )
                    for r in results
                ],
            )
            all_meas = [
                _meas_tuple(batch_run.batch_id, m)
                for r in results
                for m in r.get("measurements", [])
            ]
            if all_meas:
                conn.executemany(_INSERT_MEAS, all_meas)

        return batch_run.batch_id

    def save_multi(self, mbr: MultiDatasetBatchRun) -> str:
        """儲存多資料集批次結果，回傳 "multi_{run_id}"。

        全部在同一 transaction 內完成：
        1. parent multi row in batch_runs
        2. 每個 dataset 一行 batch_runs（parent_run_id → parent）
        3. 各 dataset 的 image_results + measurements
        """
        parent_batch_id = f"multi_{mbr.run_id}"
        conn = self._get_conn()

        with conn:
            conn.execute(
                """INSERT OR REPLACE INTO batch_runs
                   (batch_id, type, run_id, dataset_label, input_folder, recipe_ids,
                    start_time, end_time, total_images, success_count, fail_count,
                    worker_count, error_log)
                   VALUES (?, 'multi', ?, '', ?, '[]', ?, ?, ?, ?, ?, ?, '[]')""",
                (
                    parent_batch_id,
                    mbr.run_id,
                    f"{len(mbr.datasets)} datasets",
                    mbr.start_time,
                    mbr.end_time,
                    mbr.total_images,
                    mbr.success_count,
                    mbr.fail_count,
                    mbr.worker_count,
                ),
            )
            for ds in mbr.datasets:
                results = ds.output_manifest.get("results", [])
                conn.execute(
                    """INSERT OR REPLACE INTO batch_runs
                       (batch_id, type, parent_run_id, dataset_label, input_folder,
                        recipe_ids, start_time, end_time, total_images, success_count,
                        fail_count, worker_count, error_log)
                       VALUES (?, 'single', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        ds.batch_id,
                        parent_batch_id,
                        ds.dataset_label,
                        ds.input_folder,
                        _j(list(ds.recipe_ids)),
                        ds.start_time,
                        ds.end_time,
                        ds.total_images,
                        ds.success_count,
                        ds.fail_count,
                        ds.worker_count,
                        _j(ds.error_log),
                    ),
                )
                conn.executemany(
                    _INSERT_IMG,
                    [
                        (
                            ds.batch_id,
                            r.get("image_path", ""),
                            r.get("image_id", ""),
                            r.get("status", "OK"),
                            r.get("error", ""),
                            r.get("overlay_path") or "",
                            r.get("quality_score"),
                        )
                        for r in results
                    ],
                )
                all_meas = [
                    _meas_tuple(ds.batch_id, m)
                    for r in results
                    for m in r.get("measurements", [])
                ]
                if all_meas:
                    conn.executemany(_INSERT_MEAS, all_meas)

        return parent_batch_id

    def list_runs(self) -> list[dict]:
        """回傳所有 top-level batch 的摘要，依時間倒序。

        'file_path' 欄位存 batch_id，供 load/delete 透明使用，
        維持與舊版呼叫方（batch_workspace、report_workspace）相容。
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT batch_id, type, dataset_label, input_folder, recipe_ids,
                      start_time, total_images, success_count, fail_count
               FROM batch_runs
               WHERE parent_run_id IS NULL
               ORDER BY start_time DESC"""
        ).fetchall()
        return [
            {
                "batch_id":      r["batch_id"],
                "type":          r["type"],
                "start_time":    r["start_time"],
                "total_images":  r["total_images"],
                "success_count": r["success_count"],
                "fail_count":    r["fail_count"],
                "input_folder":  r["input_folder"],
                "dataset_label": r["dataset_label"],
                "file_path":     r["batch_id"],  # ← stores batch_id for transparent use
                "recipe_ids":    json.loads(r["recipe_ids"] or "[]"),
            }
            for r in rows
        ]

    def load(self, batch_id: str) -> BatchRunRecord | MultiDatasetBatchRun:
        """依 batch_id 重建 BatchRunRecord 或 MultiDatasetBatchRun。"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM batch_runs WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"batch_id not found: {batch_id}")
        if row["type"] == "multi":
            return self._load_multi(batch_id, row, conn)
        return self._load_single(batch_id, conn)

    def _load_single(
        self, batch_id: str, conn: sqlite3.Connection
    ) -> BatchRunRecord:
        row = conn.execute(
            "SELECT * FROM batch_runs WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"batch_id not found: {batch_id}")

        img_rows = conn.execute(
            "SELECT * FROM image_results WHERE batch_id = ? ORDER BY id",
            (batch_id,),
        ).fetchall()

        results = []
        for ir in img_rows:
            img_id = ir["image_id"]
            meas_rows = conn.execute(
                """SELECT * FROM measurements
                   WHERE batch_id = ? AND image_id = ?
                   ORDER BY id""",
                (batch_id, img_id),
            ).fetchall()
            measurements = [
                {
                    "measurement_id": m["measurement_id"],
                    "image_id":       m["image_id"],
                    "recipe_id":      m["recipe_id"],
                    "feature_type":   m["feature_type"],
                    "feature_id":     m["feature_id"],
                    "axis":           m["axis"],
                    "raw_px":         m["raw_px"],
                    "calibrated_nm":  m["calibrated_nm"],
                    "center_x":       m["center_x"],
                    "center_y":       m["center_y"],
                    "cmg_id":         m["cmg_id"],
                    "col_id":         m["col_id"],
                    "flag":           m["flag"],
                    "status":         m["status"],
                    "review_state":   m["review_state"],
                    "extra_metrics":  json.loads(m["extra_metrics"] or "{}"),
                    # Required MeasurementRecord fields not stored separately
                    "bbox":           [0, 0, 0, 0],
                    "edge_points":    [],
                    "confidence":     1.0,
                    "state_name":     "",
                    "structure_name": "",
                }
                for m in meas_rows
            ]
            results.append({
                "image_path":    ir["image_path"],
                "image_id":      ir["image_id"],
                "status":        ir["status"],
                "error":         ir["error"],
                "measurements":  measurements,
                "cuts":          [],
                "overlay_path":  ir["overlay_path"] or None,
                "quality_score": ir["quality_score"],
            })

        return BatchRunRecord(
            batch_id=row["batch_id"],
            input_folder=row["input_folder"],
            recipe_ids=json.loads(row["recipe_ids"] or "[]"),
            total_images=row["total_images"],
            success_count=row["success_count"],
            fail_count=row["fail_count"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            worker_count=row["worker_count"],
            dataset_label=row["dataset_label"],
            error_log=json.loads(row["error_log"] or "[]"),
            output_manifest={"results": results},
        )

    def _load_multi(
        self,
        batch_id: str,
        parent_row: sqlite3.Row,
        conn: sqlite3.Connection,
    ) -> MultiDatasetBatchRun:
        child_rows = conn.execute(
            """SELECT batch_id FROM batch_runs
               WHERE parent_run_id = ?
               ORDER BY start_time""",
            (batch_id,),
        ).fetchall()
        mbr = MultiDatasetBatchRun(
            run_id=parent_row["run_id"] or batch_id,
            start_time=parent_row["start_time"],
            end_time=parent_row["end_time"],
            worker_count=parent_row["worker_count"],
        )
        for child in child_rows:
            ds = self._load_single(child["batch_id"], conn)
            mbr.datasets.append(ds)
        return mbr

    def delete(self, batch_id: str) -> bool:
        """刪除一筆記錄（含 image_results / measurements）。

        若為 multi type，同時刪除所有子 dataset 記錄。
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT type FROM batch_runs WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return False

        with conn:
            if row["type"] == "multi":
                child_ids = [
                    r["batch_id"]
                    for r in conn.execute(
                        "SELECT batch_id FROM batch_runs WHERE parent_run_id = ?",
                        (batch_id,),
                    ).fetchall()
                ]
                for cid in child_ids:
                    conn.execute("DELETE FROM measurements WHERE batch_id = ?", (cid,))
                    conn.execute("DELETE FROM image_results WHERE batch_id = ?", (cid,))
                    conn.execute("DELETE FROM batch_runs WHERE batch_id = ?", (cid,))
            conn.execute("DELETE FROM measurements WHERE batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM image_results WHERE batch_id = ?", (batch_id,))
            conn.execute("DELETE FROM batch_runs WHERE batch_id = ?", (batch_id,))
        return True

    def get_stats_for_recipe(
        self,
        recipe_id: str | None = None,
        _summaries: list[dict] | None = None,
    ) -> list[dict]:
        """計算各 batch 的 CD 統計，供 History Run Chart 使用。

        回傳格式（與舊版相同，依 start_time 升序）：
          [{"start_time", "mean_nm", "std_nm", "n", "label", "file_path"}, ...]
          file_path 欄位存 batch_id（與 list_runs 一致）。
        """
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT br.batch_id, br.start_time, br.dataset_label, br.input_folder,
                      m.calibrated_nm
               FROM batch_runs br
               JOIN measurements m ON m.batch_id = br.batch_id
               WHERE m.status != 'rejected'
                 AND br.parent_run_id IS NULL
                 AND (? IS NULL OR m.recipe_id = ?)
               ORDER BY br.start_time ASC, br.batch_id""",
            (recipe_id, recipe_id),
        ).fetchall()

        # Group by batch_id using Python (SQLite has no built-in STDEV)
        groups: dict[str, list[float]] = defaultdict(list)
        meta: dict[str, tuple[str, str, str]] = {}
        for r in rows:
            bid = r["batch_id"]
            groups[bid].append(float(r["calibrated_nm"]))
            if bid not in meta:
                meta[bid] = (r["start_time"], r["dataset_label"], r["input_folder"])

        results = []
        for bid, vals in groups.items():
            start_time, dataset_label, input_folder = meta[bid]
            mean_nm = _stats.mean(vals)
            std_nm = _stats.stdev(vals) if len(vals) > 1 else 0.0
            results.append({
                "start_time": start_time,
                "mean_nm":    round(mean_nm, 4),
                "std_nm":     round(std_nm, 4),
                "n":          len(vals),
                "label":      dataset_label or input_folder,
                "file_path":  bid,
            })

        results.sort(key=lambda x: x["start_time"])
        return results
