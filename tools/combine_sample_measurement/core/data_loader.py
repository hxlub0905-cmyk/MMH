"""Data loading for Combine Sample Measurement tool.

Loads MMH measurement Excel files and matching KLARF files,
combines them into a single DataFrame with full coordinate information.

Coordinate system (same as klarf_exporter.py):
  Image  : origin top-left, Y↓
  KLARF  : origin die-corner (bottom-left), Y↑
  new_xrel = orig_xrel + (cd_line_x_px - W/2) * nm_per_pixel
  new_yrel = orig_yrel - (cd_line_y_px - H/2) * nm_per_pixel   ← minus intentional
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
import pandas as pd

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.core.klarf_parser import KlarfParser


@dataclass
class DatasetEntry:
    name: str
    excel_path: str
    image_folder: str
    klarf_path: str
    parsed_klarf: dict[str, Any] = field(default_factory=dict, repr=False)


# ── Public API ────────────────────────────────────────────────────────────────

def load_dataset(
    entry: DatasetEntry,
    phase_cb: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Parse one dataset's Excel + KLARF, return (df, parsed_klarf).

    Coordinate calculation (new_xrel/new_yrel) is NOT done here —
    it is deferred to Step 4 so it runs only for the final sampled rows.

    phase_cb(msg) – called at each major phase for status display.
    """
    excel_path   = Path(entry.excel_path)
    image_folder = Path(entry.image_folder)
    klarf_path   = Path(entry.klarf_path)

    if phase_cb:
        phase_cb("讀取 Excel…")
    df = _read_excel(excel_path)

    df["source_dataset"] = entry.name
    df["image_path"] = df["image_file"].apply(
        lambda fn: str(image_folder / fn) if fn else ""
    )

    if phase_cb:
        phase_cb("解析 KLARF…")
    parsed = KlarfParser().parse(klarf_path)
    entry.parsed_klarf = parsed
    lookup = build_klarf_lookup(parsed)

    if phase_cb:
        phase_cb("配對 KLARF 座標…")
    old_dids, orig_xrels, orig_yrels = [], [], []
    for _, row in df.iterrows():
        stem = Path(str(row.get("image_file", ""))).stem.lower()
        hit  = lookup.get(stem)
        if hit:
            old_dids.append(hit["defect_id"])
            orig_xrels.append(hit["xrel"])
            orig_yrels.append(hit["yrel"])
        else:
            old_dids.append("")
            orig_xrels.append(float("nan"))
            orig_yrels.append(float("nan"))

    df["old_did"]    = old_dids
    df["orig_xrel"]  = orig_xrels
    df["orig_yrel"]  = orig_yrels
    # new coords deferred — will be computed in Step 4 for sampled rows only
    df["new_xrel"]   = float("nan")
    df["new_yrel"]   = float("nan")
    df["laplacian_score"] = float("nan")
    df["keep"]    = True
    df["new_did"] = -1

    return df, parsed


def combine_datasets(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True)


def compute_quality_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Compute Laplacian variance for each row's image; update laplacian_score."""
    df = df.copy()
    scores: list[float] = []
    for _, row in df.iterrows():
        path = str(row.get("image_path", ""))
        scores.append(_laplacian_var(path))
    df["laplacian_score"] = scores
    return df


def build_klarf_lookup(parsed: dict[str, Any]) -> dict[str, dict]:
    """stem (lowercase) → {defect_id, xrel, yrel, full_defect}."""
    lookup: dict[str, dict] = {}
    for defect in parsed.get("defects", []):
        fn   = defect.get("_image_filename", "")
        stem = Path(fn).stem.lower() if fn else ""
        if not stem:
            continue
        try:
            xrel = float(defect.get("XREL", defect.get("xrel", 0)) or 0)
            yrel = float(defect.get("YREL", defect.get("yrel", 0)) or 0)
        except (TypeError, ValueError):
            xrel, yrel = 0.0, 0.0
        did = defect.get("DEFECTID", defect.get("defectid", ""))
        lookup[stem] = {
            "defect_id":   did,
            "xrel":        xrel,
            "yrel":        yrel,
            "full_defect": defect,
        }
    return lookup


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_excel(path: Path) -> pd.DataFrame:
    """Read MMH Excel; try 'All Measurements' sheet first, else first sheet."""
    try:
        df = pd.read_excel(path, sheet_name="All Measurements", engine="openpyxl")
    except Exception:
        df = pd.read_excel(path, sheet_name=0, engine="openpyxl")

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    renames = {
        "image": "image_file",
        "filename": "image_file",
        "file": "image_file",
        "cd_(nm)": "cd_nm",
        "cd_(px)": "cd_px",
        "nm/pixel": "nm_per_pixel",
        "nm_per_px": "nm_per_pixel",
    }
    df = df.rename(columns=renames)

    for col in ["image_file", "axis", "recipe_name", "flag", "status"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    for col in ["cd_nm", "cd_px", "nm_per_pixel", "cd_line_x_px", "cd_line_y_px"]:
        if col not in df.columns:
            df[col] = float("nan")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


_img_size_cache: dict[str, tuple[int, int]] = {}


def _get_image_size(image_path: str) -> tuple[int, int] | None:
    """Return (W, H) by reading only the image header — never the full pixel data."""
    cached = _img_size_cache.get(image_path)
    if cached:
        return cached
    # PIL reads only the IFD/header for TIFF; milliseconds vs. seconds for cv2.imread
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            w, h = im.size
        if len(_img_size_cache) > 2000:
            _img_size_cache.clear()
        _img_size_cache[image_path] = (w, h)
        return (w, h)
    except Exception:
        pass
    # Fallback: cv2 (slow, but handles formats PIL cannot)
    try:
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        h, w = img.shape[:2]
        _img_size_cache[image_path] = (w, h)
        return (w, h)
    except Exception:
        return None


def compute_new_coords(
    df: pd.DataFrame,
    progress_cb: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    new_xrels, new_yrels = [], []
    total = len(df)
    for i, (_, row) in enumerate(df.iterrows()):
        if progress_cb:
            progress_cb(i, total)

        orig_xrel  = row.get("orig_xrel",  float("nan"))
        orig_yrel  = row.get("orig_yrel",  float("nan"))
        image_path = str(row.get("image_path", ""))
        nm_per_px  = float(row.get("nm_per_pixel", 0) or 0)
        cx_px      = float(row.get("cd_line_x_px", 0) or 0)
        cy_px      = float(row.get("cd_line_y_px", 0) or 0)

        if pd.isna(orig_xrel) or pd.isna(orig_yrel) or nm_per_px <= 0:
            new_xrels.append(float("nan"))
            new_yrels.append(float("nan"))
            continue

        wh = _get_image_size(image_path)
        if wh is None:
            new_xrels.append(float("nan"))
            new_yrels.append(float("nan"))
            continue

        W, H = wh
        dx_nm = (cx_px - W / 2) * nm_per_px
        dy_nm = (cy_px - H / 2) * nm_per_px
        new_xrels.append(float(orig_xrel) + dx_nm)
        new_yrels.append(float(orig_yrel) - dy_nm)   # ⚠ minus intentional

    df = df.copy()
    df["new_xrel"] = new_xrels
    df["new_yrel"] = new_yrels
    return df


def _laplacian_var(image_path: str) -> float:
    """Return Laplacian variance (sharpness metric). 0.0 on failure."""
    if not image_path:
        return 0.0
    try:
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return 0.0
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        if img.dtype != np.uint8:
            img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        img = cv2.medianBlur(img, 5)
        lap = cv2.Laplacian(img.astype(np.float64), cv2.CV_64F)
        return float(lap.var())
    except Exception:
        return 0.0
