"""Tests for measurement engine, compat layer, and output records path (Phase A)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pytest

from src.core.models import ImageRecord, MeasurementRecord
from src._compat import serialise_cuts_from_records, records_to_legacy_cuts


# ── Compat: serialise_cuts_from_records ───────────────────────────────────────

def _make_record(cmg_id=0, col_id=0, flag="", axis="Y", raw_px=10.0, nm=20.0) -> MeasurementRecord:
    return MeasurementRecord(
        measurement_id=str(uuid.uuid4()),
        image_id="img-1",
        recipe_id="r-1",
        feature_type="CMG_GAP",
        feature_id=f"cmg{cmg_id}_col{col_id}",
        bbox=(0, 10, 100, 20),
        center_x=50.0, center_y=15.0,
        axis=axis,
        raw_px=raw_px,
        calibrated_nm=nm,
        flag=flag,
        status={"MIN": "min", "MAX": "max", "": "normal"}[flag],
        cmg_id=cmg_id,
        col_id=col_id,
        state_name="test",
        extra_metrics={
            "upper_bbox": (0, 5, 100, 10),
            "lower_bbox": (0, 20, 100, 25),
        },
    )


def test_serialise_cuts_groups_by_cmg_id():
    records = [
        _make_record(cmg_id=0, col_id=0),
        _make_record(cmg_id=0, col_id=1),
        _make_record(cmg_id=1, col_id=0),
    ]
    cuts = serialise_cuts_from_records(records)
    assert len(cuts) == 2
    assert cuts[0]["cmg_id"] == 0
    assert len(cuts[0]["measurements"]) == 2
    assert cuts[1]["cmg_id"] == 1
    assert len(cuts[1]["measurements"]) == 1


def test_serialise_cuts_preserves_values():
    rec = _make_record(cmg_id=2, col_id=3, flag="MIN", raw_px=5.5, nm=11.0)
    cuts = serialise_cuts_from_records([rec])
    m = cuts[0]["measurements"][0]
    assert m["cmg_id"] == 2
    assert m["col_id"] == 3
    assert m["flag"] == "MIN"
    assert m["y_cd_px"] == pytest.approx(5.5)
    assert m["y_cd_nm"] == pytest.approx(11.0)
    assert m["upper_bbox"] == (0, 5, 100, 10)


def test_serialise_cuts_json_safe():
    records = [_make_record()]
    cuts = serialise_cuts_from_records(records)
    json.dumps(cuts)  # must not raise


# ── Compat: records_to_legacy_cuts ───────────────────────────────────────────

def test_records_to_legacy_cuts_structure():
    records = [
        _make_record(cmg_id=0, col_id=0, flag="MIN"),
        _make_record(cmg_id=0, col_id=1, flag="MAX"),
    ]
    from src.core.cmg_analyzer import CMGCut
    cuts = records_to_legacy_cuts(records)
    assert len(cuts) == 1
    assert isinstance(cuts[0], CMGCut)
    assert cuts[0].cmg_id == 0
    assert len(cuts[0].measurements) == 2


def test_records_to_legacy_cuts_values():
    rec = _make_record(cmg_id=1, col_id=2, raw_px=7.0, nm=14.0, flag="MAX")
    from src.core.cmg_analyzer import CMGCut
    cuts = records_to_legacy_cuts([rec])
    m = cuts[0].measurements[0]
    assert m.cmg_id == 1
    assert m.col_id == 2
    assert m.cd_px == pytest.approx(7.0)
    assert m.cd_nm == pytest.approx(14.0)
    assert m.flag == "MAX"


# ── Output: records_to_dataframe ─────────────────────────────────────────────

def test_records_to_dataframe_columns():
    from src.output._common import records_to_dataframe
    records = [_make_record(cmg_id=0, col_id=0, raw_px=5.0, nm=10.0)]
    df = records_to_dataframe(records)
    assert "y_cd_nm" in df.columns
    assert "y_cd_px" in df.columns
    assert "flag" in df.columns
    assert len(df) == 1
    assert df["y_cd_nm"].iloc[0] == pytest.approx(10.0)


def test_records_to_dataframe_with_image_records():
    from src.output._common import records_to_dataframe
    ir = ImageRecord.from_path("/data/test.tif", pixel_size_nm=2.5)
    rec = MeasurementRecord(
        measurement_id=str(uuid.uuid4()),
        image_id=ir.image_id,
        recipe_id="r",
        feature_type="CMG_GAP", feature_id="cmg0_col0",
        bbox=(0, 0, 10, 10), center_x=5.0, center_y=5.0,
        axis="Y", raw_px=4.0, calibrated_nm=10.0,
        cmg_id=0, col_id=0, flag="",
    )
    df = records_to_dataframe([rec], [ir])
    assert df["image_file"].iloc[0] == "test.tif"
    assert df["nm_per_pixel"].iloc[0] == pytest.approx(2.5)


# ── Full pipeline: engine.run_single ─────────────────────────────────────────

def test_engine_run_single_on_real_image(tmp_path):
    """Integration test: engine.run_single returns PipelineResult with records."""
    import cv2
    from src.core.recipe_registry import RecipeRegistry
    from src.core.measurement_engine import MeasurementEngine

    img = np.zeros((200, 100), dtype=np.uint8)
    img[20:60, 10:90] = 180
    img[100:140, 10:90] = 180
    img_path = tmp_path / "test.tif"
    cv2.imwrite(str(img_path), img)

    registry = RecipeRegistry(recipe_dir=tmp_path / "recipes")
    desc = registry.create_default_cmg()
    recipe = registry.get(desc.recipe_id)
    engine = MeasurementEngine(registry)

    ir = ImageRecord.from_path(str(img_path), pixel_size_nm=2.0)
    result = engine.run_single(ir, recipe)

    assert result.success
    assert len(result.records) > 0
    for rec in result.records:
        assert rec.calibrated_nm == pytest.approx(rec.raw_px * 2.0, rel=1e-6)
