"""Tests for unified data models (Phase A)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from src.core.models import ImageRecord, MeasurementRecord, BatchRunRecord


# ── ImageRecord ───────────────────────────────────────────────────────────────

def test_image_record_from_path_creates_uuid():
    ir = ImageRecord.from_path("/some/folder/image.tif", pixel_size_nm=2.5)
    assert ir.image_id
    uuid.UUID(ir.image_id)  # raises if invalid


def test_image_record_from_path_sets_fields():
    ir = ImageRecord.from_path("/some/folder/image.tif", pixel_size_nm=2.5)
    assert ir.file_path == str(Path("/some/folder/image.tif"))
    assert ir.source_folder == str(Path("/some/folder"))
    assert ir.pixel_size_nm == 2.5


def test_image_record_round_trip():
    ir = ImageRecord.from_path("/tmp/test.tif", pixel_size_nm=1.23)
    d = ir.to_dict()
    json_str = json.dumps(d)  # must not raise
    ir2 = ImageRecord.from_dict(json.loads(json_str))
    assert ir2.image_id == ir.image_id
    assert ir2.pixel_size_nm == pytest.approx(1.23)
    assert ir2.file_path == ir.file_path


# ── MeasurementRecord ─────────────────────────────────────────────────────────

def test_measurement_record_round_trip():
    rec = MeasurementRecord(
        measurement_id=str(uuid.uuid4()),
        image_id="img-001",
        recipe_id="recipe-001",
        feature_type="CMG_GAP",
        feature_id="cmg0_col0",
        bbox=(10, 20, 30, 40),
        center_x=20.0,
        center_y=30.0,
        axis="Y",
        raw_px=12.5,
        calibrated_nm=31.25,
        flag="MIN",
        status="min",
        cmg_id=0,
        col_id=0,
        state_name="Test Recipe",
    )
    d = rec.to_dict()
    json_str = json.dumps(d)  # must not raise
    rec2 = MeasurementRecord.from_dict(json.loads(json_str))
    assert rec2.measurement_id == rec.measurement_id
    assert rec2.raw_px == pytest.approx(12.5)
    assert rec2.calibrated_nm == pytest.approx(31.25)
    assert rec2.bbox == (10, 20, 30, 40)
    assert rec2.flag == "MIN"
    assert rec2.status == "min"


def test_measurement_record_flag_to_status_mapping():
    # MIN flag → status "min", MAX flag → "max"
    for flag, expected_status in [("MIN", "min"), ("MAX", "max"), ("", "normal")]:
        rec = MeasurementRecord(
            measurement_id=str(uuid.uuid4()),
            image_id="x", recipe_id="x", feature_type="CMG_GAP", feature_id="x",
            bbox=(0, 0, 1, 1), center_x=0.5, center_y=0.5, axis="Y",
            raw_px=1.0, calibrated_nm=1.0,
            flag=flag,
            status={"MIN": "min", "MAX": "max", "": "normal"}[flag],
        )
        assert rec.status == expected_status


# ── BatchRunRecord ────────────────────────────────────────────────────────────

def test_batch_run_record_round_trip():
    br = BatchRunRecord(
        batch_id=str(uuid.uuid4()),
        input_folder="/data/batch1",
        recipe_ids=["r1", "r2"],
        total_images=50,
        success_count=48,
        fail_count=2,
        worker_count=4,
    )
    d = br.to_dict()
    json_str = json.dumps(d)
    br2 = BatchRunRecord.from_dict(json.loads(json_str))
    assert br2.batch_id == br.batch_id
    assert br2.total_images == 50
    assert br2.fail_count == 2
    assert br2.recipe_ids == ["r1", "r2"]
