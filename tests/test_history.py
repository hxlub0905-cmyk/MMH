"""Tests for history / BatchRunStore.get_stats_for_recipe."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core.models import BatchRunRecord
from src.core.batch_run_store import BatchRunStore


def _make_batch_with_measurements(
    batch_id: str,
    recipe_id: str,
    calibrated_nm: float,
    start_time: str,
) -> BatchRunRecord:
    """Create a BatchRunRecord with one measurement in output_manifest."""
    meas = {
        "measurement_id": "m1",
        "image_id": "img1",
        "recipe_id": recipe_id,
        "feature_type": "CMG_GAP",
        "feature_id": "feat0_col0",
        "bbox": [0, 0, 10, 10],
        "center_x": 5.0,
        "center_y": 5.0,
        "axis": "Y",
        "raw_px": calibrated_nm,
        "calibrated_nm": calibrated_nm,
        "edge_points": [],
        "confidence": 1.0,
        "status": "normal",
        "review_state": "unreviewed",
        "extra_metrics": {},
        "cmg_id": 0,
        "col_id": 0,
        "flag": "",
        "state_name": "",
        "structure_name": "",
    }
    return BatchRunRecord(
        batch_id=batch_id,
        input_folder="/test",
        recipe_ids=[recipe_id],
        total_images=1,
        success_count=1,
        fail_count=0,
        start_time=start_time,
        end_time=start_time,
        worker_count=1,
        dataset_label=f"label-{batch_id}",
        output_manifest={
            "results": [{
                "image_path": "/test/img.png",
                "image_id": "img1",
                "status": "OK",
                "measurements": [meas],
            }]
        },
    )


class TestGetStatsForRecipe:
    def test_get_stats_for_recipe_empty(self, tmp_path):
        """No history → empty list, no crash."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        stats = store.get_stats_for_recipe(None)
        assert stats == []

    def test_get_stats_for_recipe_no_filter(self, tmp_path):
        """Two batches with measurements → two stat entries."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        store.save(_make_batch_with_measurements(
            "b1", "recipe-A", 100.0, "2026-01-01T00:00:00+00:00"
        ))
        store.save(_make_batch_with_measurements(
            "b2", "recipe-A", 110.0, "2026-01-02T00:00:00+00:00"
        ))
        stats = store.get_stats_for_recipe(None)
        assert len(stats) == 2
        means = {s["mean_nm"] for s in stats}
        assert 100.0 in means
        assert 110.0 in means

    def test_get_stats_for_recipe_filters(self, tmp_path):
        """Two batches with different recipe_ids → filter keeps only matching."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        store.save(_make_batch_with_measurements(
            "b1", "recipe-A", 100.0, "2026-01-01T00:00:00+00:00"
        ))
        store.save(_make_batch_with_measurements(
            "b2", "recipe-B", 200.0, "2026-01-02T00:00:00+00:00"
        ))
        stats_a = store.get_stats_for_recipe("recipe-A")
        assert len(stats_a) == 1
        assert stats_a[0]["mean_nm"] == pytest.approx(100.0)

        stats_b = store.get_stats_for_recipe("recipe-B")
        assert len(stats_b) == 1
        assert stats_b[0]["mean_nm"] == pytest.approx(200.0)

    def test_get_stats_sorted_ascending(self, tmp_path):
        """Stats are returned in ascending start_time order."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        store.save(_make_batch_with_measurements(
            "b1", "recipe-A", 100.0, "2026-01-02T00:00:00+00:00"
        ))
        store.save(_make_batch_with_measurements(
            "b2", "recipe-A", 110.0, "2026-01-01T00:00:00+00:00"
        ))
        stats = store.get_stats_for_recipe(None)
        assert len(stats) == 2
        assert stats[0]["start_time"] <= stats[1]["start_time"]
