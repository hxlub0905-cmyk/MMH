"""KLARF Top-N exporter.

Reads an input KLARF 1.8 file, matches each defect to its SEM MM measurement
result, sorts matched defects by CD value (ascending or descending), takes the
top-N, corrects XREL/YREL to the gap centre, and writes a new KLARF.

Coordinate system note
──────────────────────
Image coordinate system : origin at top-left, Y axis points DOWN.
KLARF coordinate system : origin at die corner (bottom-left), Y axis points UP.

Conversion (three steps):
  Step 1 — pixel offset from image centre:
      dx_px = center_x - W/2
      dy_px = center_y - H/2          (positive → gap below image centre)

  Step 2 — convert to nm:
      dx_nm = dx_px * nm_per_pixel
      dy_nm = dy_px * nm_per_pixel

  Step 3 — update KLARF coordinates:
      XREL_new = XREL_orig + dx_nm    (X axes are aligned → add)
      YREL_new = YREL_orig - dy_nm    ← MINUS because image Y↓ = KLARF Y↑
                                        dy_px>0 means gap is below image centre,
                                        i.e. smaller KLARF Y → subtract dy_nm.
      ⚠️  The minus sign on YREL is intentional — do NOT change to plus.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .klarf_parser import KlarfParser
from .klarf_writer import KlarfWriter


class KlarfTopNExporter:
    """Export a KLARF filtered to the top-N defects by CD measurement value.

    Parameters
    ----------
    ascending : bool
        True  → sort by CD ascending (smallest CD first — for finding CMGF risk).
        False → sort by CD descending (largest CD first).
    """

    def export(
        self,
        klarf_path: str | Path,
        batch_run: Any,                   # BatchRunRecord | MultiDatasetBatchRun
        top_n: int,
        output_path: str | Path,
        ascending: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run the export pipeline.

        Returns a result dict:
          exported_count   int
          unmatched_count  int
          unmatched_images list[str]  – image stems with no measurement
          min_ycd_nm       float      – smallest CD in exported set
          max_ycd_nm       float      – largest CD in exported set (Nth item)
          output_path      str
          preview_rows     list[dict] – for preview table
        """
        klarf_path = Path(klarf_path)
        output_path = Path(output_path)

        # ── Step 1: parse input KLARF ─────────────────────────────────────────
        parsed = KlarfParser().parse(klarf_path)

        # ── Step 2: build lookup table from batch results ─────────────────────
        # key = image stem (lower-case, no extension)
        # value = the measurement with the minimum (or max) calibrated_nm for that image
        lookup = _build_lookup(batch_run, ascending)

        # ── Step 3: match each defect to a measurement ────────────────────────
        matched: list[dict[str, Any]] = []
        unmatched_stems: list[str] = []

        for defect in parsed["defects"]:
            image_filename = defect.get("_image_filename", "")
            stem = Path(image_filename).stem.lower() if image_filename else ""

            meas = lookup.get(stem)
            if meas is None:
                unmatched_stems.append(stem or "<no image info>")
                continue

            # ── Step 4: read image dimensions ─────────────────────────────────
            image_path = meas.get("image_path", "")
            wh = _get_image_size(image_path)
            if wh is None:
                unmatched_stems.append(stem)
                continue
            W, H = wh

            # ── Step 5: coordinate conversion ────────────────────────────────
            center_x = float(meas.get("center_x", W / 2))
            center_y = float(meas.get("center_y", H / 2))
            nm_per_pixel = float(meas.get("nm_per_pixel", 1.0))

            # Step 5a: pixel offset from image centre
            dx_px = center_x - W / 2
            dy_px = center_y - H / 2

            # Step 5b: convert to nm
            dx_nm = dx_px * nm_per_pixel
            dy_nm = dy_px * nm_per_pixel

            # Step 5c: update KLARF coordinates
            # X axes are aligned — add dx_nm
            # Y axes are OPPOSITE (image Y↓, KLARF Y↑) — subtract dy_nm
            # ⚠️ YREL uses minus — do NOT change to plus
            try:
                xrel_orig = float(defect.get("XREL", defect.get("xrel", 0)))
                yrel_orig = float(defect.get("YREL", defect.get("yrel", 0)))
            except (TypeError, ValueError):
                xrel_orig, yrel_orig = 0.0, 0.0

            xrel_new = xrel_orig + dx_nm
            yrel_new = yrel_orig - dy_nm

            matched.append({
                "defect": defect,
                "calibrated_nm": float(meas.get("calibrated_nm", 0.0)),
                "image_stem": stem,
                "xrel_orig": xrel_orig,
                "yrel_orig": yrel_orig,
                "xrel_new": xrel_new,
                "yrel_new": yrel_new,
                "nm_per_pixel": nm_per_pixel,
            })

        # ── Step 6: sort and take top-N ───────────────────────────────────────
        matched.sort(key=lambda x: x["calibrated_nm"], reverse=not ascending)
        if top_n < len(matched):
            selected = matched[:top_n]
        else:
            selected = matched

        # ── Step 7: build output defect list ──────────────────────────────────
        output_defects: list[dict[str, Any]] = []
        preview_rows: list[dict[str, Any]] = []

        for item in selected:
            d = dict(item["defect"])
            # Update XREL / YREL columns (case-sensitive lookup, try both)
            if "XREL" in d:
                d["XREL"] = str(int(round(item["xrel_new"])))
            elif "xrel" in d:
                d["xrel"] = str(int(round(item["xrel_new"])))
            if "YREL" in d:
                d["YREL"] = str(int(round(item["yrel_new"])))
            elif "yrel" in d:
                d["yrel"] = str(int(round(item["yrel_new"])))
            output_defects.append(d)

            preview_rows.append({
                "defect_id": d.get("DEFECTID", d.get("defectid", "")),
                "image_stem": item["image_stem"],
                "ycd_nm": item["calibrated_nm"],
                "xrel_orig": item["xrel_orig"],
                "yrel_orig": item["yrel_orig"],
                "xrel_new": item["xrel_new"],
                "yrel_new": item["yrel_new"],
            })

        # ── Step 8: write output KLARF ────────────────────────────────────────
        if not dry_run:
            KlarfWriter().write(parsed, output_defects, output_path)

        cd_values = [r["ycd_nm"] for r in preview_rows]
        min_cd = min(cd_values) if cd_values else 0.0
        max_cd = max(cd_values) if cd_values else 0.0

        return {
            "exported_count": len(selected),
            "unmatched_count": len(unmatched_stems),
            "unmatched_images": unmatched_stems,
            "min_ycd_nm": min_cd,
            "max_ycd_nm": max_cd,
            "output_path": str(output_path),
            "preview_rows": preview_rows,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_lookup(batch_run: Any, ascending: bool) -> dict[str, dict[str, Any]]:
    """Build stem→best-measurement lookup from batch_run.output_manifest["results"].

    For each image, keep the measurement with the globally smallest (ascending)
    or largest (not ascending) calibrated_nm value.
    """
    from .models import BatchRunRecord, MultiDatasetBatchRun, MeasurementRecord

    all_results: list[dict[str, Any]] = []
    if isinstance(batch_run, MultiDatasetBatchRun):
        for ds in batch_run.datasets:
            all_results.extend(ds.output_manifest.get("results", []))
    elif isinstance(batch_run, BatchRunRecord):
        all_results.extend(batch_run.output_manifest.get("results", []))

    lookup: dict[str, dict[str, Any]] = {}
    for result in all_results:
        image_path = result.get("image_path", "")
        stem = Path(image_path).stem.lower()
        measurements = result.get("measurements", [])

        for meas_dict in measurements:
            try:
                m = MeasurementRecord.from_dict(meas_dict)
            except Exception:
                continue
            # Derive nm_per_pixel from the stored raw/nm values
            nm_per_pixel = 1.0
            if m.raw_px and m.raw_px > 0:
                nm_per_pixel = m.calibrated_nm / m.raw_px

            entry = {
                "image_path": image_path,
                "center_x": m.center_x,
                "center_y": m.center_y,
                "calibrated_nm": m.calibrated_nm,
                "nm_per_pixel": nm_per_pixel,
            }

            existing = lookup.get(stem)
            if existing is None:
                lookup[stem] = entry
            else:
                if ascending and entry["calibrated_nm"] < existing["calibrated_nm"]:
                    lookup[stem] = entry
                elif not ascending and entry["calibrated_nm"] > existing["calibrated_nm"]:
                    lookup[stem] = entry

    return lookup


_size_cache: dict[str, tuple[int, int]] = {}


def _get_image_size(image_path: str) -> tuple[int, int] | None:
    """Return (W, H) of an image, cached by path."""
    if not image_path:
        return None
    cached = _size_cache.get(image_path)
    if cached is not None:
        return cached
    try:
        import cv2
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return None
        h, w = img.shape[:2]
        _size_cache[image_path] = (w, h)
        return (w, h)
    except Exception:
        return None
