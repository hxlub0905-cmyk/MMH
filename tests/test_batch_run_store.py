"""Tests for BatchRunStore persistence."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core.models import BatchRunRecord, MultiDatasetBatchRun
from src.core.batch_run_store import BatchRunStore


def _make_batch(batch_id: str = "test-batch-1", start_time: str = "2026-01-01T00:00:00+00:00") -> BatchRunRecord:
    return BatchRunRecord(
        batch_id=batch_id,
        input_folder="/test/folder",
        recipe_ids=["recipe-1"],
        total_images=5,
        success_count=4,
        fail_count=1,
        start_time=start_time,
        end_time="2026-01-01T00:01:00+00:00",
        worker_count=2,
        dataset_label="TestDataset",
        output_manifest={"results": []},
    )


def _make_multi(run_id: str = "multi-run-1", start_time: str = "2026-01-02T00:00:00+00:00") -> MultiDatasetBatchRun:
    mbr = MultiDatasetBatchRun(
        run_id=run_id,
        start_time=start_time,
        end_time="2026-01-02T00:02:00+00:00",
        worker_count=2,
    )
    mbr.datasets = [
        _make_batch("batch-a", "2026-01-02T00:00:00+00:00"),
        _make_batch("batch-b", "2026-01-02T00:00:30+00:00"),
    ]
    return mbr


class TestBatchRunStore:
    def test_save_and_load_single(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        batch = _make_batch()
        path = store.save(batch)
        assert path.exists()

        loaded = store.load(str(path))
        assert isinstance(loaded, BatchRunRecord)
        assert loaded.batch_id == batch.batch_id
        assert loaded.input_folder == batch.input_folder
        assert loaded.total_images == batch.total_images
        assert loaded.success_count == batch.success_count
        assert loaded.fail_count == batch.fail_count
        assert loaded.start_time == batch.start_time

    def test_save_and_load_multi(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        mbr = _make_multi()
        path = store.save_multi(mbr)
        assert path.exists()

        loaded = store.load(str(path))
        assert isinstance(loaded, MultiDatasetBatchRun)
        assert loaded.run_id == mbr.run_id
        assert len(loaded.datasets) == 2
        assert loaded.datasets[0].batch_id == "batch-a"
        assert loaded.datasets[1].batch_id == "batch-b"

    def test_list_runs_sorted(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        # Older batch
        store.save(_make_batch("old-batch", "2026-01-01T00:00:00+00:00"))
        # Newer batch
        store.save(_make_batch("new-batch", "2026-02-01T00:00:00+00:00"))

        summaries = store.list_runs()
        assert len(summaries) == 2
        # list_runs returns descending by start_time
        assert summaries[0]["start_time"] > summaries[1]["start_time"]
        assert summaries[0]["batch_id"] == "new-batch"

    def test_delete(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        batch = _make_batch()
        path = store.save(batch)
        assert len(store.list_runs()) == 1

        deleted = store.delete(str(path))
        assert deleted is True
        assert len(store.list_runs()) == 0

    def test_delete_nonexistent(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        result = store.delete(str(tmp_path / "nonexistent.json"))
        assert result is False

    def test_get_stats_for_recipe_empty(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        stats = store.get_stats_for_recipe(None)
        assert stats == []

    def test_get_stats_for_recipe_no_measurements(self, tmp_path):
        store = BatchRunStore(runs_dir=tmp_path)
        store.save(_make_batch())
        stats = store.get_stats_for_recipe(None)
        # Batch has empty results → no stats entries
        assert stats == []
