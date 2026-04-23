"""Shared helper: flatten batch results into a pandas DataFrame."""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.models import ImageRecord, MeasurementRecord


def results_to_dataframe(results: list[dict], nm_per_pixel: float):
    """Legacy format → pandas DataFrame (preserved for backward compatibility)."""
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
    """Convert MeasurementRecord list → clean DataFrame for rich Excel export.

    Columns: image_file, structure_name, axis, cd_px, cd_nm,
             cd_pos_x_px, cd_pos_y_px, flag, status, nm_per_pixel, recipe_name
             [dataset — only when dataset_label is non-empty]
    """
    import pandas as pd
    img_map = {ir.image_id: ir for ir in (image_records or [])}
    rows = []
    for r in records:
        ir = img_map.get(r.image_id)
        row: dict = {}
        if dataset_label:
            row["dataset"] = dataset_label
        row.update({
            "image_file":    Path(ir.file_path).name if ir else r.image_id,
            "structure_name": r.structure_name,
            "axis":          r.axis,
            "cd_px":         round(float(r.raw_px), 3),
            "cd_nm":         round(float(r.calibrated_nm), 3),
            "cd_pos_x_px":   round(float(r.center_x), 1),
            "cd_pos_y_px":   round(float(r.center_y), 1),
            "flag":          r.flag,
            "status":        r.status,
            "nm_per_pixel":  float(ir.pixel_size_nm) if ir else 1.0,
            "recipe_name":   r.state_name,
        })
        rows.append(row)
    return pd.DataFrame(rows)


def records_to_min_cd_dataframe(
    records: list["MeasurementRecord"],
    image_records: list["ImageRecord"] | None = None,
    dataset_label: str = "",
):
    """One row per image: the measurement with the minimum cd_nm.

    Columns: [dataset,] image_file, min_cd_nm, cd_pos_x_px, cd_pos_y_px,
             structure_name, recipe_name
    Sorted ascending by min_cd_nm.
    """
    import pandas as pd
    img_map = {ir.image_id: ir for ir in (image_records or [])}

    # Group records by image
    from collections import defaultdict
    by_image: dict[str, list] = defaultdict(list)
    for r in records:
        ir = img_map.get(r.image_id)
        img_name = Path(ir.file_path).name if ir else r.image_id
        by_image[img_name].append(r)

    rows = []
    for img_name, recs in by_image.items():
        valid = [r for r in recs if r.status not in ("rejected",)]
        if not valid:
            continue
        min_rec = min(valid, key=lambda r: float(r.calibrated_nm))
        ir = img_map.get(min_rec.image_id)
        row: dict = {}
        if dataset_label:
            row["dataset"] = dataset_label
        row.update({
            "image_file":    img_name,
            "min_cd_nm":     round(float(min_rec.calibrated_nm), 3),
            "cd_pos_x_px":   round(float(min_rec.center_x), 1),
            "cd_pos_y_px":   round(float(min_rec.center_y), 1),
            "structure_name": min_rec.structure_name,
            "recipe_name":   min_rec.state_name,
        })
        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("min_cd_nm").reset_index(drop=True)
    return df
