"""Shared helper: flatten batch results into a pandas DataFrame."""

from __future__ import annotations
from pathlib import Path
import pandas as pd


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
