"""BatchRunStore — 批次結果的持久化管理器。"""
from __future__ import annotations

import json
from pathlib import Path

from .models import BatchRunRecord, MultiDatasetBatchRun

RUNS_DIR = Path.home() / ".mmh" / "runs"
_INDEX_FILE = "_index.json"


class BatchRunStore:
    def __init__(self, runs_dir: Path | None = None):
        self._dir = runs_dir or RUNS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Index helpers ─────────────────────────────────────────────────────────

    @property
    def _index_path(self) -> Path:
        return self._dir / _INDEX_FILE

    def _read_index(self) -> list[dict] | None:
        """Return cached summaries from index, or None if index is stale/missing."""
        ip = self._index_path
        if not ip.exists():
            return None
        try:
            entries: list[dict] = json.loads(ip.read_text(encoding="utf-8"))
            # Validate that every file_path in the index still exists
            paths_in_index = {e["file_path"] for e in entries}
            actual_files = {
                str(f) for f in self._dir.glob("*.json")
                if f.name != _INDEX_FILE
            }
            if paths_in_index != actual_files:
                return None  # stale — rebuild
            return entries
        except Exception:
            return None

    def _rebuild_index(self) -> list[dict]:
        """Read all run files and write a fresh _index.json with only summary fields."""
        summaries = []
        for f in self._dir.glob("*.json"):
            if f.name == _INDEX_FILE:
                continue
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("type") == "multi_dataset":
                    summaries.append({
                        "batch_id": f"multi_{d['run_id']}",
                        "run_id": d["run_id"],
                        "type": "multi",
                        "start_time": d.get("start_time", ""),
                        "total_images": sum(
                            ds.get("total_images", 0) for ds in d.get("datasets", [])
                        ),
                        "success_count": sum(
                            ds.get("success_count", 0) for ds in d.get("datasets", [])
                        ),
                        "fail_count": sum(
                            ds.get("fail_count", 0) for ds in d.get("datasets", [])
                        ),
                        "input_folder": f"{len(d.get('datasets', []))} datasets",
                        "file_path": str(f),
                        "recipe_ids": [],
                    })
                else:
                    summaries.append({
                        "batch_id": d.get("batch_id", ""),
                        "type": "single",
                        "start_time": d.get("start_time", ""),
                        "total_images": d.get("total_images", 0),
                        "success_count": d.get("success_count", 0),
                        "fail_count": d.get("fail_count", 0),
                        "input_folder": d.get("input_folder", ""),
                        "dataset_label": d.get("dataset_label", ""),
                        "file_path": str(f),
                        "recipe_ids": d.get("recipe_ids", []),
                    })
            except Exception:
                continue
        try:
            self._index_path.write_text(
                json.dumps(summaries, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
        return summaries

    def _append_to_index(self, entry: dict) -> None:
        """Add a single entry to the index (fast path after save)."""
        existing = self._read_index() or []
        # Remove any stale entry with the same file_path then append fresh one
        existing = [e for e in existing if e.get("file_path") != entry.get("file_path")]
        existing.append(entry)
        try:
            self._index_path.write_text(
                json.dumps(existing, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _remove_from_index(self, file_path: str) -> None:
        """Remove an entry from the index after deletion."""
        existing = self._read_index()
        if existing is None:
            return
        updated = [e for e in existing if e.get("file_path") != file_path]
        try:
            self._index_path.write_text(
                json.dumps(updated, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, batch_run: BatchRunRecord) -> Path:
        """儲存單一批次結果，回傳儲存路徑。"""
        path = self._dir / f"{batch_run.batch_id}.json"
        path.write_text(
            json.dumps(batch_run.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._append_to_index({
            "batch_id": batch_run.batch_id,
            "type": "single",
            "start_time": batch_run.start_time,
            "total_images": batch_run.total_images,
            "success_count": batch_run.success_count,
            "fail_count": batch_run.fail_count,
            "input_folder": getattr(batch_run, "input_folder", ""),
            "dataset_label": getattr(batch_run, "dataset_label", ""),
            "file_path": str(path),
            "recipe_ids": list(batch_run.recipe_ids) if batch_run.recipe_ids else [],
        })
        return path

    def save_multi(self, mbr: MultiDatasetBatchRun) -> Path:
        """儲存多資料集批次結果。"""
        payload = {
            "type": "multi_dataset",
            "run_id": mbr.run_id,
            "start_time": mbr.start_time,
            "end_time": mbr.end_time,
            "worker_count": mbr.worker_count,
            "datasets": [ds.to_dict() for ds in mbr.datasets],
        }
        path = self._dir / f"multi_{mbr.run_id}.json"
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._append_to_index({
            "batch_id": f"multi_{mbr.run_id}",
            "run_id": mbr.run_id,
            "type": "multi",
            "start_time": mbr.start_time,
            "total_images": mbr.total_images,
            "success_count": mbr.success_count,
            "fail_count": mbr.fail_count,
            "input_folder": f"{len(mbr.datasets)} datasets",
            "file_path": str(path),
            "recipe_ids": [],
        })
        return path

    def list_runs(self) -> list[dict]:
        """回傳所有歷史批次的摘要清單，依時間倒序排列。

        Uses _index.json as a fast cache; falls back to full file scan when stale.
        """
        summaries = self._read_index()
        if summaries is None:
            summaries = self._rebuild_index()
        return sorted(summaries, key=lambda x: x.get("start_time", ""), reverse=True)

    def load(self, file_path: str) -> BatchRunRecord | MultiDatasetBatchRun:
        """從磁碟載入批次結果，自動判斷 single / multi 類型。"""
        d = json.loads(Path(file_path).read_text(encoding="utf-8"))
        if d.get("type") == "multi_dataset":
            mbr = MultiDatasetBatchRun(
                run_id=d["run_id"],
                start_time=d.get("start_time", ""),
                end_time=d.get("end_time", ""),
                worker_count=int(d.get("worker_count", 1)),
            )
            mbr.datasets = [BatchRunRecord.from_dict(ds) for ds in d.get("datasets", [])]
            return mbr
        else:
            return BatchRunRecord.from_dict(d)

    def delete(self, file_path: str) -> bool:
        p = Path(file_path)
        if p.exists():
            p.unlink()
            self._remove_from_index(file_path)
            return True
        return False

    def get_stats_for_recipe(
        self,
        recipe_id: str | None = None,
        _summaries: list[dict] | None = None,
    ) -> list[dict]:
        """Extract CD stats per batch run, optionally filtered by recipe_id.

        Returns list of dicts (sorted by start_time ascending):
          {start_time, mean_nm, std_nm, n, label, file_path}
        """
        import statistics as _stats
        results = []
        base = _summaries if _summaries is not None else self.list_runs()
        for summary in reversed(base):  # list_runs is desc, reverse → asc for chart
            if recipe_id and recipe_id not in summary.get("recipe_ids", []):
                continue
            fp = summary["file_path"]
            try:
                d = json.loads(Path(fp).read_text(encoding="utf-8"))
                datasets = (
                    d.get("datasets", [])
                    if d.get("type") == "multi_dataset"
                    else [d]
                )
                vals: list[float] = []
                for ds in datasets:
                    for r in ds.get("output_manifest", {}).get("results", []):
                        for m in r.get("measurements", []):
                            if recipe_id and m.get("recipe_id") != recipe_id:
                                continue
                            if m.get("status") not in ("rejected",):
                                try:
                                    vals.append(float(m["calibrated_nm"]))
                                except (KeyError, TypeError, ValueError):
                                    pass
                if not vals:
                    continue
                mean_nm = _stats.mean(vals)
                std_nm = _stats.stdev(vals) if len(vals) > 1 else 0.0
                results.append({
                    "start_time": summary.get("start_time", ""),
                    "mean_nm": round(mean_nm, 4),
                    "std_nm": round(std_nm, 4),
                    "n": len(vals),
                    "label": summary.get("dataset_label") or summary.get("input_folder", ""),
                    "file_path": fp,
                })
            except Exception:
                continue
        return results
