"""KLARF Top-N exporter.

Reads an input KLARF 1.8 file (flat or hierarchical), matches each defect to
its SEM MM measurement result, sorts matched defects by CD value (ascending or
descending), takes the top-N, corrects XREL/YREL to the gap centre, and writes
a new KLARF in the same format as the input.

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

import logging
from pathlib import Path
from typing import Any

from .klarf_parser import KlarfParser
from .klarf_writer import KlarfWriter

_log = logging.getLogger(__name__)


class KlarfTopNExporter:
    """Export a KLARF filtered to the top-N defects by CD measurement value."""

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
        klarf_path  = Path(klarf_path)
        output_path = Path(output_path)

        # ── Step 1: parse input KLARF ─────────────────────────────────────────
        parsed = KlarfParser().parse(klarf_path)
        _log.debug(
            "[exporter] Parsed KLARF '%s': format=%s, defects=%d, columns=%s",
            klarf_path.name,
            parsed.get("format_type", "?"),
            len(parsed.get("defects", [])),
            parsed.get("defect_columns", []),
        )

        # ── Step 2: build lookup table from batch results ─────────────────────
        lookup = _build_lookup(batch_run, ascending)
        _log.debug(
            "[exporter] Lookup built: %d unique image stems → %s",
            len(lookup),
            list(lookup.keys())[:10],   # show first 10 stems
        )

        if not lookup:
            _log.warning(
                "[exporter] Lookup is EMPTY — no measurements found in batch_run. "
                "batch_run type=%s", type(batch_run).__name__,
            )

        # ── Step 3: match each defect to a measurement ────────────────────────
        matched: list[dict[str, Any]] = []
        unmatched_stems: list[str] = []

        all_defects = parsed.get("defects", [])
        _log.debug("[exporter] Matching %d defects against lookup...", len(all_defects))

        for defect_idx, defect in enumerate(all_defects):
            image_filename = defect.get("_image_filename", "")
            stem = Path(image_filename).stem.lower() if image_filename else ""

            meas = lookup.get(stem)
            if meas is None:
                unmatched_stems.append(stem or "<no image info>")
                _log.debug(
                    "[exporter]   defect[%d] stem=%r → MISS (lookup has no entry)",
                    defect_idx, stem,
                )
                continue

            # ── Step 4: read image dimensions ─────────────────────────────────
            image_path = meas.get("image_path", "")
            wh = _get_image_size(image_path)
            if wh is None:
                unmatched_stems.append(stem)
                _log.warning(
                    "[exporter]   defect[%d] stem=%r → MISS (image size unreadable: %r)",
                    defect_idx, stem, image_path,
                )
                continue
            W, H = wh

            # ── Step 5: coordinate conversion ────────────────────────────────
            center_x    = float(meas.get("center_x",    W / 2))
            center_y    = float(meas.get("center_y",    H / 2))
            nm_per_pixel = float(meas.get("nm_per_pixel", 1.0))

            dx_px = center_x - W / 2
            dy_px = center_y - H / 2
            dx_nm = dx_px * nm_per_pixel
            dy_nm = dy_px * nm_per_pixel

            try:
                xrel_orig = float(defect.get("XREL", defect.get("xrel", 0)))
                yrel_orig = float(defect.get("YREL", defect.get("yrel", 0)))
            except (TypeError, ValueError):
                xrel_orig, yrel_orig = 0.0, 0.0

            xrel_new = xrel_orig + dx_nm
            yrel_new = yrel_orig - dy_nm   # ⚠️ minus is intentional

            matched.append({
                "defect":        defect,
                "calibrated_nm": float(meas.get("calibrated_nm", 0.0)),
                "image_stem":    stem,
                "image_path":    image_path,
                "xrel_orig":     xrel_orig,
                "yrel_orig":     yrel_orig,
                "xrel_new":      xrel_new,
                "yrel_new":      yrel_new,
                "nm_per_pixel":  nm_per_pixel,
            })
            _log.debug(
                "[exporter]   defect[%d] stem=%r → MATCH "
                "(cd=%.2f nm, xrel %g→%g, yrel %g→%g)",
                defect_idx, stem,
                float(meas.get("calibrated_nm", 0.0)),
                xrel_orig, xrel_new, yrel_orig, yrel_new,
            )

        _log.debug(
            "[exporter] Match summary: total=%d matched=%d unmatched=%d",
            len(all_defects), len(matched), len(unmatched_stems),
        )

        # ── Step 6: sort and take top-N ───────────────────────────────────────
        matched.sort(key=lambda x: x["calibrated_nm"], reverse=not ascending)
        if top_n < len(matched):
            selected = matched[:top_n]
        else:
            selected = matched

        _log.debug(
            "[exporter] top_n=%d, selected=%d defects for output",
            top_n, len(selected),
        )

        # ── Step 7: build output defect list ──────────────────────────────────
        output_defects: list[dict[str, Any]] = []
        preview_rows:   list[dict[str, Any]] = []

        for item in selected:
            d = dict(item["defect"])
            xrel_key = next((k for k in d if k.lower() == "xrel"), None)
            yrel_key = next((k for k in d if k.lower() == "yrel"), None)
            if xrel_key:
                d[xrel_key] = str(int(round(item["xrel_new"])))
            if yrel_key:
                d[yrel_key] = str(int(round(item["yrel_new"])))
            output_defects.append(d)

            preview_rows.append({
                "defect_id":    d.get("DEFECTID", d.get("defectid", "")),
                "image_stem":   item["image_stem"],
                "image_path":   item.get("image_path", ""),
                "ycd_nm":       item["calibrated_nm"],
                "xrel_orig":    item["xrel_orig"],
                "yrel_orig":    item["yrel_orig"],
                "xrel_new":     item["xrel_new"],
                "yrel_new":     item["yrel_new"],
                "nm_per_pixel": item["nm_per_pixel"],
            })

        # ── Step 8: write output KLARF ────────────────────────────────────────
        if not dry_run:
            KlarfWriter().write(parsed, output_defects, output_path)

        cd_values = [r["ycd_nm"] for r in preview_rows]
        min_cd = min(cd_values) if cd_values else 0.0
        max_cd = max(cd_values) if cd_values else 0.0

        return {
            "exported_count":  len(selected),
            "unmatched_count": len(unmatched_stems),
            "unmatched_images": unmatched_stems,
            "min_ycd_nm":      min_cd,
            "max_ycd_nm":      max_cd,
            "output_path":     str(output_path),
            "preview_rows":    preview_rows,
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
        _log.debug(
            "[exporter] _build_lookup: MultiDatasetBatchRun with %d datasets, "
            "%d total results",
            len(batch_run.datasets), len(all_results),
        )
    elif isinstance(batch_run, BatchRunRecord):
        all_results.extend(batch_run.output_manifest.get("results", []))
        _log.debug(
            "[exporter] _build_lookup: BatchRunRecord with %d results",
            len(all_results),
        )
    else:
        _log.warning(
            "[exporter] _build_lookup: batch_run type %s is not recognised "
            "(expected BatchRunRecord or MultiDatasetBatchRun) — lookup will be empty",
            type(batch_run).__name__,
        )

    lookup: dict[str, dict[str, Any]] = {}
    for result in all_results:
        image_path   = result.get("image_path", "")
        stem         = Path(image_path).stem.lower()
        measurements = result.get("measurements", [])
        _log.debug(
            "[exporter]   result stem=%r, measurements=%d",
            stem, len(measurements),
        )

        for meas_dict in measurements:
            try:
                m = MeasurementRecord.from_dict(meas_dict)
            except Exception as exc:
                _log.warning(
                    "[exporter]   MeasurementRecord.from_dict FAILED for stem=%r: %s",
                    stem, exc,
                )
                continue

            if m.raw_px and m.raw_px > 0:
                nm_per_pixel = m.calibrated_nm / m.raw_px
            else:
                # raw_px=0 無法計算比例尺；略過座標調整（Bug B4）
                _log.warning(
                    "[exporter]   raw_px=0 for stem=%r meas_id=%s — "
                    "cannot compute nm/px, coordinate adjustment will be skipped",
                    stem, m.measurement_id,
                )
                nm_per_pixel = 0.0

            entry = {
                "image_path":    image_path,
                "center_x":      m.center_x,
                "center_y":      m.center_y,
                "calibrated_nm": m.calibrated_nm,
                "nm_per_pixel":  nm_per_pixel,
            }

            existing = lookup.get(stem)
            if existing is None:
                lookup[stem] = entry
            else:
                if ascending and entry["calibrated_nm"] < existing["calibrated_nm"]:
                    lookup[stem] = entry
                elif not ascending and entry["calibrated_nm"] > existing["calibrated_nm"]:
                    lookup[stem] = entry

    _log.debug("[exporter] _build_lookup done: %d stems in lookup", len(lookup))
    return lookup


_size_cache: dict[str, tuple[int, int]] = {}
_SIZE_CACHE_MAX = 500  # 超過此數量就清空，避免長時間使用記憶體無限增長（Bug B2）


def _get_image_size(image_path: str) -> tuple[int, int] | None:
    """Return (W, H) of an image, cached by path."""
    if not image_path:
        _log.debug("[exporter] _get_image_size: empty path")
        return None
    cached = _size_cache.get(image_path)
    if cached is not None:
        return cached
    try:
        import cv2
        img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
        if img is None:
            _log.warning(
                "[exporter] _get_image_size: cv2.imread returned None for %r "
                "(file missing or unreadable)",
                image_path,
            )
            return None
        h, w = img.shape[:2]
        if len(_size_cache) >= _SIZE_CACHE_MAX:
            _size_cache.clear()
        _size_cache[image_path] = (w, h)
        _log.debug("[exporter] _get_image_size: %r → (%d, %d)", image_path, w, h)
        return (w, h)
    except Exception as exc:
        _log.warning("[exporter] _get_image_size EXCEPTION for %r: %s", image_path, exc)
        return None
