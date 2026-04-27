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


class TestRegressionFixes:
    """Regression tests for Bug Fix Round3 (state_name persistence + multi-run stats)."""

    def _make_batch_with_labels(
        self,
        batch_id: str,
        state_name: str,
        structure_name: str,
        start_time: str = "2026-01-01T00:00:00+00:00",
    ) -> BatchRunRecord:
        meas = {
            "measurement_id": "m1",
            "image_id": "img1",
            "recipe_id": "recipe-A",
            "feature_type": "CMG_GAP",
            "feature_id": "feat0_col0",
            "bbox": [0, 0, 10, 10],
            "center_x": 5.0,
            "center_y": 5.0,
            "axis": "Y",
            "raw_px": 100.0,
            "calibrated_nm": 100.0,
            "edge_points": [],
            "confidence": 0.99,
            "status": "normal",
            "review_state": "unreviewed",
            "extra_metrics": {},
            "cmg_id": 1,
            "col_id": 2,
            "flag": "ok",
            "state_name": state_name,
            "structure_name": structure_name,
        }
        return BatchRunRecord(
            batch_id=batch_id,
            input_folder="/test",
            recipe_ids=["recipe-A"],
            total_images=1,
            success_count=1,
            fail_count=0,
            start_time=start_time,
            end_time=start_time,
            worker_count=1,
            dataset_label="ds",
            output_manifest={
                "results": [{
                    "image_path": "/test/img.png",
                    "image_id": "img1",
                    "status": "OK",
                    "measurements": [meas],
                }]
            },
        )

    def test_state_name_round_trips(self, tmp_path):
        """state_name and structure_name must survive save → load."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        batch = self._make_batch_with_labels("b1", "InSpec", "Gate")
        store.save(batch)
        loaded = store.load("b1")
        m = loaded.output_manifest["results"][0]["measurements"][0]
        assert m["state_name"] == "InSpec"
        assert m["structure_name"] == "Gate"

    def test_state_name_migration_defaults(self, tmp_path):
        """Rows saved before the migration columns existed default to empty string."""
        store = BatchRunStore(db_path=tmp_path / "test.db")
        # Simulate old-style save without the new columns by writing directly
        conn = store._get_conn()
        conn.execute(
            """INSERT INTO batch_runs
               (batch_id, type, dataset_label, input_folder, recipe_ids,
                start_time, end_time, total_images, success_count, fail_count,
                worker_count, error_log)
               VALUES ('b-old','single','','',  '[]',
                       '2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00',
                       1,1,0,1,'[]')"""
        )
        conn.execute(
            """INSERT INTO image_results
               (batch_id, image_path, image_id, status, error, overlay_path)
               VALUES ('b-old','/img.png','img1','OK','','')"""
        )
        conn.execute(
            """INSERT INTO measurements
               (batch_id, image_id, recipe_id, measurement_id, feature_type,
                feature_id, axis, raw_px, calibrated_nm, center_x, center_y,
                cmg_id, col_id, flag, status, review_state, extra_metrics)
               VALUES ('b-old','img1','r','m1','CMG_GAP',
                       'f','Y',100.0,100.0,5.0,5.0,0,0,'','normal','unreviewed','{}')"""
        )
        conn.commit()
        loaded = store.load("b-old")
        m = loaded.output_manifest["results"][0]["measurements"][0]
        assert m["state_name"] == ""
        assert m["structure_name"] == ""

    def test_multi_run_included_in_stats(self, tmp_path):
        """get_stats_for_recipe must include measurements from multi-dataset child runs."""
        from src.core.models import MultiDatasetBatchRun
        store = BatchRunStore(db_path=tmp_path / "test.db")
        mbr = MultiDatasetBatchRun(
            run_id="run-multi",
            start_time="2026-01-01T00:00:00+00:00",
            end_time="2026-01-01T00:01:00+00:00",
            worker_count=2,
        )
        mbr.datasets = [
            _make_batch_with_measurements("child-a", "recipe-A", 50.0, "2026-01-01T00:00:00+00:00"),
            _make_batch_with_measurements("child-b", "recipe-A", 60.0, "2026-01-01T00:00:30+00:00"),
        ]
        store.save_multi(mbr)
        stats = store.get_stats_for_recipe(None)
        # Both child datasets must appear (regression: parent_run_id IS NULL excluded them)
        assert len(stats) == 2
        means = {s["mean_nm"] for s in stats}
        assert 50.0 in means
        assert 60.0 in means
