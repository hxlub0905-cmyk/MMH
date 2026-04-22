"""BatchRunStore — 批次結果的持久化管理器。"""
from __future__ import annotations

import json
from pathlib import Path

from .models import BatchRunRecord, MultiDatasetBatchRun

RUNS_DIR = Path.home() / ".mmh" / "runs"


class BatchRunStore:
    def __init__(self, runs_dir: Path | None = None):
        self._dir = runs_dir or RUNS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, batch_run: BatchRunRecord) -> Path:
        """儲存單一批次結果，回傳儲存路徑。"""
        path = self._dir / f"{batch_run.batch_id}.json"
        path.write_text(
            json.dumps(batch_run.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
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
        return path

    def list_runs(self) -> list[dict]:
        """回傳所有歷史批次的摘要清單，依時間倒序排列。"""
        summaries = []
        for f in self._dir.glob("*.json"):
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
                    })
            except Exception:
                continue
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
