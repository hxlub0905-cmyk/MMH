"""Unified data models for MMH vNext (Phase A).

All dataclasses are json.dumps-safe: no numpy types, no Path objects.
Legacy fields (cmg_id, col_id, flag, state_name) on MeasurementRecord
preserve backward-compatibility with ResultsPanel and annotator.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ImageRecord:
    image_id: str
    file_path: str
    source_folder: str
    wafer_id: str = ""
    lot_id: str = ""
    site_id: str = ""
    pixel_size_nm: float = 1.0
    magnification: float = 0.0
    detector_type: str = ""
    acquisition_metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    analyzed_at: str = ""

    @staticmethod
    def from_path(path: str | Path, pixel_size_nm: float = 1.0) -> "ImageRecord":
        p = Path(path)
        return ImageRecord(
            image_id=str(uuid.uuid4()),
            file_path=str(p),
            source_folder=str(p.parent),
            pixel_size_nm=pixel_size_nm,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_id": self.image_id,
            "file_path": self.file_path,
            "source_folder": self.source_folder,
            "wafer_id": self.wafer_id,
            "lot_id": self.lot_id,
            "site_id": self.site_id,
            "pixel_size_nm": float(self.pixel_size_nm),
            "magnification": float(self.magnification),
            "detector_type": self.detector_type,
            "acquisition_metadata": self.acquisition_metadata,
            "created_at": self.created_at,
            "analyzed_at": self.analyzed_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "ImageRecord":
        return ImageRecord(
            image_id=d["image_id"],
            file_path=d["file_path"],
            source_folder=d.get("source_folder", str(Path(d["file_path"]).parent)),
            wafer_id=d.get("wafer_id", ""),
            lot_id=d.get("lot_id", ""),
            site_id=d.get("site_id", ""),
            pixel_size_nm=float(d.get("pixel_size_nm", 1.0)),
            magnification=float(d.get("magnification", 0.0)),
            detector_type=d.get("detector_type", ""),
            acquisition_metadata=d.get("acquisition_metadata", {}),
            created_at=d.get("created_at", ""),
            analyzed_at=d.get("analyzed_at", ""),
        )


@dataclass
class MeasurementRecord:
    measurement_id: str
    image_id: str
    recipe_id: str
    feature_type: str
    feature_id: str
    bbox: tuple[int, int, int, int]
    center_x: float
    center_y: float
    axis: Literal["X", "Y"]
    raw_px: float
    calibrated_nm: float
    edge_points: list[tuple[float, float]] = field(default_factory=list)
    confidence: float = 1.0
    status: Literal["normal", "min", "max", "outlier", "rejected", "corrected"] = "normal"
    review_state: Literal["unreviewed", "accepted", "rejected"] = "unreviewed"
    extra_metrics: dict = field(default_factory=dict)
    # Legacy fields for ResultsPanel / annotator compatibility
    cmg_id: int = 0
    col_id: int = 0
    flag: str = ""
    state_name: str = ""
    structure_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "measurement_id": self.measurement_id,
            "image_id": self.image_id,
            "recipe_id": self.recipe_id,
            "feature_type": self.feature_type,
            "feature_id": self.feature_id,
            "bbox": list(self.bbox),
            "center_x": float(self.center_x),
            "center_y": float(self.center_y),
            "axis": self.axis,
            "raw_px": float(self.raw_px),
            "calibrated_nm": float(self.calibrated_nm),
            "edge_points": [[float(x), float(y)] for x, y in self.edge_points],
            "confidence": float(self.confidence),
            "status": self.status,
            "review_state": self.review_state,
            "extra_metrics": self.extra_metrics,
            "cmg_id": int(self.cmg_id),
            "col_id": int(self.col_id),
            "flag": self.flag,
            "state_name": self.state_name,
            "structure_name": self.structure_name,
        }

    @staticmethod
    def from_dict(d: dict) -> "MeasurementRecord":
        bbox_raw = d.get("bbox", [0, 0, 0, 0])
        # Restore bbox-like fields in extra_metrics from list → tuple after JSON round-trip.
        # JSON serialises tuples as arrays; callers downstream expect 4-int tuples.
        _extra = dict(d.get("extra_metrics", {}))
        for _key in ("upper_bbox", "lower_bbox"):
            if _key in _extra and isinstance(_extra[_key], list):
                _extra[_key] = tuple(int(v) for v in _extra[_key])
        return MeasurementRecord(
            measurement_id=d["measurement_id"],
            image_id=d["image_id"],
            recipe_id=d["recipe_id"],
            feature_type=d.get("feature_type", ""),
            feature_id=d.get("feature_id", ""),
            bbox=tuple(int(v) for v in bbox_raw),  # type: ignore[arg-type]
            center_x=float(d.get("center_x", 0.0)),
            center_y=float(d.get("center_y", 0.0)),
            axis=d.get("axis", "Y"),
            raw_px=float(d.get("raw_px", 0.0)),
            calibrated_nm=float(d.get("calibrated_nm", 0.0)),
            edge_points=[(float(p[0]), float(p[1])) for p in d.get("edge_points", [])],
            confidence=float(d.get("confidence", 1.0)),
            status=d.get("status", "normal"),
            review_state=d.get("review_state", "unreviewed"),
            extra_metrics=_extra,
            cmg_id=int(d.get("cmg_id", 0)),
            col_id=int(d.get("col_id", 0)),
            flag=d.get("flag", ""),
            state_name=d.get("state_name", ""),
            structure_name=d.get("structure_name", ""),
        )


@dataclass
class BatchRunRecord:
    batch_id: str
    input_folder: str
    recipe_ids: list[str]
    total_images: int = 0
    success_count: int = 0
    fail_count: int = 0
    start_time: str = ""
    end_time: str = ""
    worker_count: int = 1
    dataset_label: str = ""
    error_log: list[dict] = field(default_factory=list)
    output_manifest: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "input_folder": self.input_folder,
            "recipe_ids": self.recipe_ids,
            "total_images": self.total_images,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "worker_count": self.worker_count,
            "dataset_label": self.dataset_label,
            "error_log": self.error_log,
            "output_manifest": self.output_manifest,
        }

    @staticmethod
    def from_dict(d: dict) -> "BatchRunRecord":
        return BatchRunRecord(
            batch_id=d["batch_id"],
            input_folder=d.get("input_folder", ""),
            recipe_ids=d.get("recipe_ids", []),
            total_images=int(d.get("total_images", 0)),
            success_count=int(d.get("success_count", 0)),
            fail_count=int(d.get("fail_count", 0)),
            start_time=d.get("start_time", ""),
            end_time=d.get("end_time", ""),
            worker_count=int(d.get("worker_count", 1)),
            dataset_label=d.get("dataset_label", ""),
            error_log=d.get("error_log", []),
            output_manifest=d.get("output_manifest", {}),
        )


@dataclass
class GoldenSampleEntry:
    """單張 golden sample 的參考資料。"""
    file_path: str
    reference_nm: float
    cmg_id: int = 0
    col_id: int = 0
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "reference_nm": float(self.reference_nm),
            "cmg_id": self.cmg_id,
            "col_id": self.col_id,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: dict) -> "GoldenSampleEntry":
        return GoldenSampleEntry(
            file_path=d["file_path"],
            reference_nm=float(d["reference_nm"]),
            cmg_id=int(d.get("cmg_id", 0)),
            col_id=int(d.get("col_id", 0)),
            notes=d.get("notes", ""),
        )


@dataclass
class ValidationResult:
    """Recipe 驗證的單筆結果。"""
    file_path: str
    reference_nm: float
    measured_nm: float | None
    bias_nm: float | None
    error: str = ""

    @property
    def success(self) -> bool:
        return self.measured_nm is not None


@dataclass
class MultiDatasetBatchRun:
    """Aggregated result from running multiple (folder, recipe) dataset pairs."""
    run_id: str
    datasets: list[BatchRunRecord] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    worker_count: int = 1

    @property
    def total_images(self) -> int:
        return sum(d.total_images for d in self.datasets)

    @property
    def success_count(self) -> int:
        return sum(d.success_count for d in self.datasets)

    @property
    def fail_count(self) -> int:
        return sum(d.fail_count for d in self.datasets)
