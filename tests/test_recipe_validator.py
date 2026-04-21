"""Tests for RecipeValidator."""
from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core.models import (
    GoldenSampleEntry, ValidationResult, MeasurementRecord, ImageRecord
)
from src.core.recipe_validator import RecipeValidator


def _make_meas_record(cmg_id: int, col_id: int, calibrated_nm: float) -> MeasurementRecord:
    return MeasurementRecord(
        measurement_id="test-id",
        image_id="img-id",
        recipe_id="recipe-id",
        feature_type="CMG_GAP",
        feature_id=f"feat{cmg_id}_col{col_id}",
        bbox=(0, 0, 10, 10),
        center_x=5.0,
        center_y=5.0,
        axis="Y",
        raw_px=float(calibrated_nm),
        calibrated_nm=float(calibrated_nm),
        cmg_id=cmg_id,
        col_id=col_id,
    )


class _StubRecipe:
    """Stub recipe that returns a fixed set of measurements."""
    def __init__(self, records: list[MeasurementRecord]):
        self._records = records

    def run_pipeline(self, ir: ImageRecord):
        class _Result:
            pass
        r = _Result()
        r.records = self._records
        return r


class TestRecipeValidator:
    def test_validator_finds_correct_measurement(self, tmp_path):
        """Known reference; bias should be measured - reference."""
        reference_nm = 100.0
        measured_nm = 100.5
        recipe = _StubRecipe([_make_meas_record(0, 0, measured_nm)])
        validator = RecipeValidator(recipe)

        # Create a dummy image file so ImageRecord.from_path doesn't crash
        img_path = str(tmp_path / "test.png")
        import numpy as np
        import cv2
        cv2.imwrite(img_path, np.zeros((64, 64), dtype=np.uint8))

        entry = GoldenSampleEntry(
            file_path=img_path,
            reference_nm=reference_nm,
            cmg_id=0,
            col_id=0,
        )
        results = validator.run([entry])
        assert len(results) == 1
        r = results[0]
        assert r.success
        assert r.measured_nm == pytest.approx(measured_nm)
        assert r.bias_nm == pytest.approx(measured_nm - reference_nm)

    def test_validator_handles_missing_measurement(self, tmp_path):
        """cmg_id/col_id not found → result.success is False."""
        recipe = _StubRecipe([_make_meas_record(0, 0, 100.0)])
        validator = RecipeValidator(recipe)

        img_path = str(tmp_path / "test.png")
        import numpy as np
        import cv2
        cv2.imwrite(img_path, np.zeros((64, 64), dtype=np.uint8))

        entry = GoldenSampleEntry(
            file_path=img_path,
            reference_nm=100.0,
            cmg_id=99,   # non-existent
            col_id=99,
        )
        results = validator.run([entry])
        assert len(results) == 1
        assert not results[0].success
        assert "No measurement found" in results[0].error

    def test_compute_stats_empty(self):
        """Empty or all-failed results → no crash, n=0."""
        stats = RecipeValidator.compute_stats([])
        assert stats["n"] == 0

        failed = ValidationResult(
            file_path="x.png", reference_nm=100.0,
            measured_nm=None, bias_nm=None, error="fail"
        )
        stats = RecipeValidator.compute_stats([failed])
        assert stats["n"] == 0
        assert stats["n_fail"] == 1

    def test_compute_stats_values(self):
        """Known bias list → verify mean_bias calculation."""
        biases = [1.0, 2.0, 3.0]
        results = [
            ValidationResult(
                file_path=f"{i}.png",
                reference_nm=100.0,
                measured_nm=100.0 + b,
                bias_nm=b,
            )
            for i, b in enumerate(biases)
        ]
        stats = RecipeValidator.compute_stats(results)
        assert stats["n"] == 3
        assert stats["mean_bias_nm"] == pytest.approx(2.0)
        assert stats["n_fail"] == 0
