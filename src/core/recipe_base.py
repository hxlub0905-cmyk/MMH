"""Abstract recipe interface and supporting data structures for MMH vNext.

Six-stage pipeline:
    load_image → preprocess → detect_features →
    locate_edges → compute_metrics → render_annotations
"""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from .models import ImageRecord, MeasurementRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Recipe config container ───────────────────────────────────────────────────

@dataclass
class RecipeConfig:
    """Generic key-value store for recipe parameters, serialisable to JSON."""
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def to_dict(self) -> dict[str, Any]:
        return dict(self.data)

    @staticmethod
    def from_dict(d: dict) -> "RecipeConfig":
        return RecipeConfig(data=dict(d))


# ── Recipe descriptor (serialisable to JSON) ──────────────────────────────────

@dataclass
class MeasurementRecipe:
    """Serialisable recipe descriptor, saved as JSON in ~/.mmh/recipes/."""
    recipe_id: str
    recipe_name: str
    recipe_type: str                      # "CMG_YCD" | "CMG_XCD"
    target_layer: str = ""
    feature_family: str = "CMG"
    axis_mode: str = "Y"                  # "Y" | "X"
    preprocess_config: RecipeConfig = field(default_factory=RecipeConfig)
    detector_config: RecipeConfig = field(default_factory=RecipeConfig)
    edge_locator_config: RecipeConfig = field(default_factory=RecipeConfig)
    metric_definition: RecipeConfig = field(default_factory=RecipeConfig)
    annotation_style: RecipeConfig = field(default_factory=RecipeConfig)
    export_schema: RecipeConfig = field(default_factory=RecipeConfig)
    version: int = 1
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipe_id": self.recipe_id,
            "recipe_name": self.recipe_name,
            "recipe_type": self.recipe_type,
            "target_layer": self.target_layer,
            "feature_family": self.feature_family,
            "axis_mode": self.axis_mode,
            "preprocess_config": self.preprocess_config.to_dict(),
            "detector_config": self.detector_config.to_dict(),
            "edge_locator_config": self.edge_locator_config.to_dict(),
            "metric_definition": self.metric_definition.to_dict(),
            "annotation_style": self.annotation_style.to_dict(),
            "export_schema": self.export_schema.to_dict(),
            "version": self.version,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "MeasurementRecipe":
        return MeasurementRecipe(
            recipe_id=d["recipe_id"],
            recipe_name=d.get("recipe_name", "Unnamed"),
            recipe_type=d.get("recipe_type", "CMG_YCD"),
            target_layer=d.get("target_layer", ""),
            feature_family=d.get("feature_family", "CMG"),
            axis_mode=d.get("axis_mode", "Y"),
            preprocess_config=RecipeConfig.from_dict(d.get("preprocess_config", {})),
            detector_config=RecipeConfig.from_dict(d.get("detector_config", {})),
            edge_locator_config=RecipeConfig.from_dict(d.get("edge_locator_config", {})),
            metric_definition=RecipeConfig.from_dict(d.get("metric_definition", {})),
            annotation_style=RecipeConfig.from_dict(d.get("annotation_style", {})),
            export_schema=RecipeConfig.from_dict(d.get("export_schema", {})),
            version=int(d.get("version", 1)),
            created_at=d.get("created_at", ""),
            modified_at=d.get("modified_at", ""),
        )


# ── Pipeline result ────────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    image_record: ImageRecord
    records: list[MeasurementRecord]
    raw: np.ndarray
    mask: np.ndarray
    annotated: np.ndarray
    context: dict = field(default_factory=dict)
    error: str = ""

    @property
    def success(self) -> bool:
        return not self.error and len(self.records) > 0


# ── Abstract base recipe ───────────────────────────────────────────────────────

class BaseRecipe(ABC):
    """Abstract base for all measurement recipes.

    Subclasses override the five abstract stages; Stage 1 and Stage 6 have
    default implementations that can be overridden if needed.
    """

    @property
    @abstractmethod
    def recipe_id(self) -> str: ...

    @property
    @abstractmethod
    def recipe_descriptor(self) -> MeasurementRecipe: ...

    # ── Stage 1 ───────────────────────────────────────────────────────────────
    def load_image(self, image_record: ImageRecord, context: dict) -> np.ndarray:
        """Return uint8 grayscale array."""
        from .image_loader import load_grayscale
        raw = load_grayscale(image_record.file_path)
        context["raw"] = raw
        return raw

    # ── Stage 2 ───────────────────────────────────────────────────────────────
    @abstractmethod
    def preprocess(self, raw: np.ndarray, context: dict) -> np.ndarray:
        """Return binary mask.  Must store result in context['mask']."""
        ...

    # ── Stage 3 ───────────────────────────────────────────────────────────────
    @abstractmethod
    def detect_features(self, mask: np.ndarray, context: dict) -> list:
        """Detect candidate features; return feature list."""
        ...

    # ── Stage 4 ───────────────────────────────────────────────────────────────
    @abstractmethod
    def locate_edges(self, features: list, context: dict) -> list:
        """Refine edge locations; return edge-located feature list."""
        ...

    # ── Stage 5 ───────────────────────────────────────────────────────────────
    @abstractmethod
    def compute_metrics(
        self,
        edge_features: list,
        image_record: ImageRecord,
        context: dict,
    ) -> list[MeasurementRecord]:
        """Convert edge features → MeasurementRecord list."""
        ...

    # ── Stage 6 ───────────────────────────────────────────────────────────────
    def render_annotations(
        self,
        raw: np.ndarray,
        mask: np.ndarray,
        records: list[MeasurementRecord],
        context: dict,
        opts: Any = None,
    ) -> np.ndarray:
        """Return annotated BGR image.  Default: returns raw as BGR."""
        import cv2
        return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)

    # ── Convenience runner ────────────────────────────────────────────────────
    def run_pipeline(
        self,
        image_record: ImageRecord,
        opts: Any = None,
    ) -> PipelineResult:
        """Execute all 6 stages and return a PipelineResult."""
        context: dict = {"image_record": image_record}
        try:
            raw = self.load_image(image_record, context)
            mask = self.preprocess(raw, context)
            features = self.detect_features(mask, context)
            edges = self.locate_edges(features, context)
            records = self.compute_metrics(edges, image_record, context)
            annotated = self.render_annotations(raw, mask, records, context, opts)
            image_record.analyzed_at = _now_iso()
            return PipelineResult(
                image_record=image_record,
                records=records,
                raw=raw,
                mask=mask,
                annotated=annotated,
                context=context,
            )
        except Exception as exc:
            empty = np.zeros((1, 1), dtype=np.uint8)
            return PipelineResult(
                image_record=image_record,
                records=[],
                raw=context.get("raw", empty),
                mask=context.get("mask", empty),
                annotated=empty,
                context=context,
                error=str(exc),
            )
