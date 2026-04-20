"""Shared helper: flatten batch results into a pandas DataFrame."""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from ..core.models import ImageRecord, MeasurementRecord


def results_to_dataframe(results: list[dict], nm_per_pixel: float) -> pd.DataFrame:
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


_RECORD_SCHEMA = [
    "image_file", "nm_per_pixel", "cmg_id", "col_id", "y_cd_px", "y_cd_nm",
    "flag", "upper_bbox", "lower_bbox", "status", "error",
    "recipe_id", "recipe_name", "axis",
]


def records_to_dataframe(
    records: list["MeasurementRecord"],
    image_records: list["ImageRecord"] | None = None,
) -> pd.DataFrame:
    """Convert MeasurementRecord list → DataFrame with the same schema as results_to_dataframe.

    Enables new-style code paths to use the same exporters without conversion.
    """
    img_map = {ir.image_id: ir for ir in (image_records or [])}
    rows = []
    for r in records:
        ir = img_map.get(r.image_id)
        rows.append({
            "image_file": Path(ir.file_path).name if ir else r.image_id,
            "nm_per_pixel": float(ir.pixel_size_nm) if ir else 1.0,
            "cmg_id": r.cmg_id,
            "col_id": r.col_id,
            "y_cd_px": round(float(r.raw_px), 3),
            "y_cd_nm": round(float(r.calibrated_nm), 3),
            "flag": r.flag,
            "upper_bbox": str(r.extra_metrics.get("upper_bbox", "")),
            "lower_bbox": str(r.extra_metrics.get("lower_bbox", "")),
            "status": "OK",
            "error": "",
            "recipe_id": r.recipe_id,
            "recipe_name": r.state_name,
            "axis": r.axis,
        })
    if not rows:
        return pd.DataFrame(columns=_RECORD_SCHEMA)
    return pd.DataFrame(rows)
