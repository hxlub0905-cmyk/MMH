"""Tests for recipe_base, CMGRecipe, and RecipeRegistry (Phase A)."""
from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

import numpy as np
import pytest

from src.core.recipe_base import MeasurementRecipe, RecipeConfig, PipelineResult
from src.core.recipes.cmg_recipe import CMGRecipe
from src.core.models import ImageRecord


# ── RecipeConfig ──────────────────────────────────────────────────────────────

def test_recipe_config_round_trip():
    cfg = RecipeConfig(data={"gl_min": 100, "gl_max": 220, "use_clahe": True})
    d = cfg.to_dict()
    cfg2 = RecipeConfig.from_dict(d)
    assert cfg2.get("gl_min") == 100
    assert cfg2.get("use_clahe") is True


# ── MeasurementRecipe ─────────────────────────────────────────────────────────

def test_measurement_recipe_round_trip():
    r = MeasurementRecipe(
        recipe_id=str(uuid.uuid4()),
        recipe_name="Test CMG",
        recipe_type="CMG_YCD",
        axis_mode="Y",
        preprocess_config=RecipeConfig(data={"gl_min": 80, "gl_max": 200}),
        version=2,
    )
    d = r.to_dict()
    json_str = json.dumps(d)
    r2 = MeasurementRecipe.from_dict(json.loads(json_str))
    assert r2.recipe_id == r.recipe_id
    assert r2.version == 2
    assert r2.preprocess_config.get("gl_min") == 80


# ── CMGRecipe from legacy card ────────────────────────────────────────────────

def test_cmg_recipe_from_y_card():
    card = {"name": "My Y Recipe", "axis": "Y", "gl_min": 90, "gl_max": 210}
    recipe = CMGRecipe(legacy_card=card)
    assert recipe.recipe_descriptor.recipe_type == "CMG_YCD"
    assert recipe.recipe_descriptor.axis_mode == "Y"
    assert recipe.recipe_descriptor.preprocess_config.get("gl_min") == 90


def test_cmg_recipe_from_x_card():
    card = {"name": "My X Recipe", "axis": "X", "gl_min": 50, "gl_max": 180}
    recipe = CMGRecipe(legacy_card=card)
    assert recipe.recipe_descriptor.recipe_type == "CMG_XCD"
    assert recipe.recipe_descriptor.axis_mode == "X"


def test_cmg_recipe_from_descriptor():
    desc = MeasurementRecipe(
        recipe_id=str(uuid.uuid4()),
        recipe_name="Descriptor Recipe",
        recipe_type="CMG_YCD",
        axis_mode="Y",
        preprocess_config=RecipeConfig(data={"gl_min": 100, "gl_max": 220}),
    )
    recipe = CMGRecipe(descriptor=desc)
    assert recipe.recipe_id == desc.recipe_id
    assert recipe.recipe_descriptor.recipe_name == "Descriptor Recipe"


def test_cmg_recipe_missing_args():
    with pytest.raises(ValueError):
        CMGRecipe()


# ── CMGRecipe pipeline with synthetic image ───────────────────────────────────

def _make_two_blob_image() -> np.ndarray:
    """Create a grayscale image with two bright horizontal bands (simulate MG blobs)."""
    img = np.zeros((200, 100), dtype=np.uint8)
    img[20:60, 10:90] = 180    # upper MG blob
    img[100:140, 10:90] = 180  # lower MG blob — gap of ~40px between blob centers
    return img


def _make_image_record(path: str) -> ImageRecord:
    return ImageRecord.from_path(path, pixel_size_nm=2.0)


def test_cmg_pipeline_with_real_image(tmp_path):
    """Write synthetic image to disk and run the full pipeline."""
    import cv2
    img = _make_two_blob_image()
    img_path = tmp_path / "test.tif"
    cv2.imwrite(str(img_path), img)

    ir = _make_image_record(str(img_path))
    recipe = CMGRecipe(legacy_card={"name": "test", "axis": "Y", "gl_min": 100, "gl_max": 220})
    result = recipe.run_pipeline(ir)

    assert result.raw.shape == img.shape
    assert result.mask.ndim == 2
    assert result.annotated.ndim == 3  # BGR
    assert result.annotated.shape[2] == 3


def test_cmg_pipeline_blank_image_fails_gracefully(tmp_path):
    """Blank image should return PipelineResult with empty records (success=False)."""
    import cv2
    img = np.zeros((100, 100), dtype=np.uint8)
    img_path = tmp_path / "blank.tif"
    cv2.imwrite(str(img_path), img)

    ir = _make_image_record(str(img_path))
    recipe = CMGRecipe(legacy_card={"name": "test", "axis": "Y", "gl_min": 100, "gl_max": 220})
    result = recipe.run_pipeline(ir)

    assert not result.success
    assert result.records == []


def test_cmg_pipeline_calibrated_nm_equals_px_times_scale(tmp_path):
    """calibrated_nm == raw_px * pixel_size_nm for all records."""
    import cv2
    img = _make_two_blob_image()
    img_path = tmp_path / "calib.tif"
    cv2.imwrite(str(img_path), img)

    nm_per_px = 3.0
    ir = ImageRecord.from_path(str(img_path), pixel_size_nm=nm_per_px)
    recipe = CMGRecipe(legacy_card={"name": "test", "axis": "Y", "gl_min": 100, "gl_max": 220})
    result = recipe.run_pipeline(ir)

    for rec in result.records:
        assert rec.calibrated_nm == pytest.approx(rec.raw_px * nm_per_px, rel=1e-6)


# ── RecipeRegistry ────────────────────────────────────────────────────────────

def test_recipe_registry_save_load(tmp_path):
    from src.core.recipe_registry import RecipeRegistry
    registry = RecipeRegistry(recipe_dir=tmp_path)

    desc = MeasurementRecipe(
        recipe_id=str(uuid.uuid4()),
        recipe_name="Saved Recipe",
        recipe_type="CMG_YCD",
        axis_mode="Y",
    )
    registry.save(desc)

    json_file = tmp_path / f"{desc.recipe_id}.json"
    assert json_file.exists()

    registry2 = RecipeRegistry(recipe_dir=tmp_path)
    found = registry2.get_descriptor(desc.recipe_id)
    assert found is not None
    assert found.recipe_name == "Saved Recipe"


def test_recipe_registry_get_returns_cmg_recipe(tmp_path):
    from src.core.recipe_registry import RecipeRegistry
    registry = RecipeRegistry(recipe_dir=tmp_path)

    desc = MeasurementRecipe(
        recipe_id=str(uuid.uuid4()),
        recipe_name="My CMG",
        recipe_type="CMG_YCD",
        axis_mode="Y",
    )
    registry.save(desc)

    recipe = registry.get(desc.recipe_id)
    assert recipe is not None
    assert isinstance(recipe, CMGRecipe)


def test_recipe_registry_import_from_card(tmp_path):
    from src.core.recipe_registry import RecipeRegistry
    registry = RecipeRegistry(recipe_dir=tmp_path)
    card = {"name": "Legacy Card", "axis": "Y", "gl_min": 80, "gl_max": 200}
    desc = registry.import_from_card(card)

    assert (tmp_path / f"{desc.recipe_id}.json").exists()
    assert desc.recipe_name == "Legacy Card"
