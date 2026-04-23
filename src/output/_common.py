"""Shared helper: flatten batch results into a pandas DataFrame."""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.models import ImageRecord, MeasurementRecord


def results_to_dataframe(results: list[dict], nm_per_pixel: float):
    import pandas as pd
    rows = []
    for r in results:
        img_name = Path(r["path"]).name
        status = r.get("status", "OK")
        if status != "OK" or not r.get("cuts"):
            rows.append({
                "image_file": img_name,
                "nm_per_pixel": nm_per_pixel,
                "cmg_id": None,
                "col_id": None,
                "y_cd_px": None,
                "y_cd_nm": None,
                "flag": None,
                "upper_bbox": None,
                "lower_bbox": None,
                "status": status,
                "error": r.get("error", ""),
            })
            continue
        for cut in r["cuts"]:
            for m in cut["measurements"]:
                rows.append({
                    "image_file": img_name,
                    "nm_per_pixel": nm_per_pixel,
                    "cmg_id": m["cmg_id"],
                    "col_id": m["col_id"],
                    "y_cd_px": round(m["y_cd_px"], 3),
                    "y_cd_nm": round(m["y_cd_nm"], 3),
                    "flag": m["flag"],
                    "upper_bbox": str(m["upper_bbox"]),
                    "lower_bbox": str(m["lower_bbox"]),
                    "status": "OK",
                    "error": "",
                })
    return pd.DataFrame(rows)


def records_to_dataframe(
    records: list["MeasurementRecord"],
    image_records: list["ImageRecord"] | None = None,
    dataset_label: str = "",
):
    """Convert MeasurementRecord list → DataFrame with the same schema as results_to_dataframe.

    Enables new-style code paths to use the same exporters without conversion.
    Includes CD line position (center_x/center_y) relative to image top-left.
    """
    import pandas as pd
    img_map = {ir.image_id: ir for ir in (image_records or [])}
    rows = []
    for r in records:
        ir = img_map.get(r.image_id)
        ub = r.extra_metrics.get("upper_bbox", None)
        lb = r.extra_metrics.get("lower_bbox", None)
        # Parse bbox tuples (stored as tuples or list from JSON)
        ub_t = tuple(int(v) for v in ub) if ub else None
        lb_t = tuple(int(v) for v in lb) if lb else None
        rows.append({
            "dataset": dataset_label,
            "image_file": Path(ir.file_path).name if ir else r.image_id,
            "nm_per_pixel": float(ir.pixel_size_nm) if ir else 1.0,
            "recipe_name": r.state_name,
            "axis": r.axis,
            "cut_id": r.cmg_id,
            "column_id": r.col_id,
            "cd_nm": round(float(r.calibrated_nm), 3),
            "cd_px": round(float(r.raw_px), 3),
            "flag": r.flag,
            # CD line centre position relative to image top-left (px)
            "cd_line_x_px": round(float(r.center_x), 1),
            "cd_line_y_px": round(float(r.center_y), 1),
            # Raw blob bounding boxes for spatial reference
            "upper_blob_x0": ub_t[0] if ub_t else None,
            "upper_blob_y0": ub_t[1] if ub_t else None,
            "upper_blob_x1": ub_t[2] if ub_t else None,
            "upper_blob_y1": ub_t[3] if ub_t else None,
            "lower_blob_x0": lb_t[0] if lb_t else None,
            "lower_blob_y0": lb_t[1] if lb_t else None,
            "lower_blob_x1": lb_t[2] if lb_t else None,
            "lower_blob_y1": lb_t[3] if lb_t else None,
            "status": r.status,
            # Legacy columns kept for backward compat
            "y_cd_px": round(float(r.raw_px), 3),
            "y_cd_nm": round(float(r.calibrated_nm), 3),
            "upper_bbox": str(r.extra_metrics.get("upper_bbox", "")),
            "lower_bbox": str(r.extra_metrics.get("lower_bbox", "")),
            "error": "",
            "recipe_id": r.recipe_id,
        })
    df = pd.DataFrame(rows)
    _CANON = [
        "dataset", "image_file", "nm_per_pixel", "recipe_name", "axis",
        "cut_id", "column_id", "cd_nm", "cd_px",
        "cd_line_x_px", "cd_line_y_px",
        "flag", "status",
    ]
    _extra = [c for c in df.columns if c not in _CANON]
    return df[[c for c in _CANON if c in df.columns] + _extra]
