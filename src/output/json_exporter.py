"""Export measurement results to JSON."""

from __future__ import annotations
import json
from pathlib import Path


def export_json(results: list[dict], out_path: Path, nm_per_pixel: float) -> None:
    payload = {
        "nm_per_pixel": nm_per_pixel,
        "images": [],
    }
    for r in results:
        entry = {
            "image_file": Path(r["path"]).name,
            "status": r.get("status", "OK"),
            "error": r.get("error", ""),
            "cmg_cuts": r.get("cuts", []),
        }
        payload["images"].append(entry)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
