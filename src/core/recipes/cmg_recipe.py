"""CMG Y-CD / X-CD recipe — wraps existing CMG pipeline without modifying it.

Delegations:
  Stage 2 → preprocessor.preprocess()
  Stage 3 → mg_detector.detect_blobs()
  Stage 4 → coordinate back-rotation for X-axis images
  Stage 5 → cmg_analyzer.analyze()  → MeasurementRecord list
  Stage 6 → annotator.draw_overlays()
"""
from __future__ import annotations

import uuid
from typing import Any, NamedTuple

import cv2
import numpy as np

from ..models import ImageRecord, MeasurementRecord
from ..recipe_base import BaseRecipe, MeasurementRecipe, RecipeConfig
from ..cmg_analyzer import _flag_top3

# Tolerance for float equality in MIN/MAX comparisons (subpixel values are never
# exact integers, so direct == is unsafe after refinement).
_FLOAT_EPS = 1e-6


class _SubpixelResult(NamedTuple):
    """Return value from _refine_yedge_subpixel().

    fallback_reason is "" on success; one of the reason codes below on failure:
      "invalid_image"      – image is None or wrong ndim
      "small_window"       – search window < 3 rows
      "flat_profile"       – profile contrast < 1 DN
      "weak_gradient"      – peak gradient below relative threshold
      "ambiguous_peak"     – two comparable peaks detected
      "proximity_violation"– refined position too far from y_guess
    """
    y_refined: float
    fallback_reason: str
    peak_strength: float       # peak_val / p_range  (0 on fallback)
    second_peak_ratio: float   # second_val / peak_val  (0 on fallback)
    shift_px: float            # y_refined - y_guess  (0 on fallback)


class CMGRecipe(BaseRecipe):
    """Wraps the existing CMG pipeline as a BaseRecipe implementation."""

    def __init__(
        self,
        descriptor: MeasurementRecipe | None = None,
        legacy_card: dict | None = None,
    ):
        if descriptor is not None:
            self._descriptor = descriptor
        elif legacy_card is not None:
            self._descriptor = CMGRecipe._card_to_descriptor(legacy_card)
        else:
            raise ValueError("Provide either descriptor or legacy_card")

    # ── Identity ──────────────────────────────────────────────────────────────

    @property
    def recipe_id(self) -> str:
        return self._descriptor.recipe_id

    @property
    def recipe_descriptor(self) -> MeasurementRecipe:
        return self._descriptor

    # ── Stage 2: preprocess ───────────────────────────────────────────────────

    def preprocess(self, raw: np.ndarray, context: dict) -> np.ndarray:
        from ..preprocessor import preprocess, PreprocessParams
        pc = self._descriptor.preprocess_config
        axis = self._descriptor.axis_mode.upper()

        roi = (
            cv2.rotate(raw, cv2.ROTATE_90_CLOCKWISE)
            if axis == "X"
            else raw
        )

        params = PreprocessParams(
            gl_min=pc.get("gl_min", 100),
            gl_max=pc.get("gl_max", 220),
            gauss_kernel=pc.get("gauss_kernel", 3),
            morph_open_k=pc.get("morph_open_k", 3),
            morph_close_k=pc.get("morph_close_k", 5),
            use_clahe=pc.get("use_clahe", True),
            clahe_clip=pc.get("clahe_clip", 2.0),
            clahe_grid=pc.get("clahe_grid", 8),
            vert_erode_k=int(pc.get("vert_erode_k", 0)),
            vert_erode_iter=int(pc.get("vert_erode_iter", 1)),
        )
        mask_roi = preprocess(roi, params)

        if axis == "X":
            mask_ori = cv2.rotate(mask_roi, cv2.ROTATE_90_COUNTERCLOCKWISE)
        else:
            mask_ori = mask_roi

        context["roi"] = roi
        context["mask_roi"] = mask_roi
        context["mask"] = mask_ori
        return mask_ori

    # ── Stage 3: detect_features ──────────────────────────────────────────────

    def detect_features(self, mask: np.ndarray, context: dict) -> list:
        from ..mg_detector import detect_blobs, detect_mg_column_centers_pitch_phase, regularize_blobs_to_columns
        from ..preprocessor import apply_column_strip_mask
        dc = self._descriptor.detector_config
        min_area = dc.get("min_area", None)
        mask_roi = context.get("mask_roi", mask)
        col_centers: list[int] = []

        edge_margin = int(dc.get("col_mask_edge_margin_px", 0))
        half_w = int(dc.get("col_mask_width_px", 22)) // 2
        col_margin = int(dc.get("col_mask_margin_px", 4))
        pitch_px = int(dc.get("col_mask_pitch_px", 44))

        # Strategy 2a: X-projection phase detection → auto-detect MG column centers
        if dc.get("xproj_enabled", False):
            col_centers = detect_mg_column_centers_pitch_phase(
                mask_roi,
                pitch_px=pitch_px,
                smooth_k=int(dc.get("xproj_smooth_k", 5)),
                min_height_frac=float(dc.get("xproj_peak_min_frac", 0.3)),
                edge_margin_px=edge_margin,
            )
            context["mg_col_centers"] = col_centers

        # Strategy 1: X-Column Strip Masking → sever EPI lateral bridge
        if dc.get("col_mask_enabled", False):
            if not col_centers:
                col_centers = context.get("mg_col_centers", [])
            if dc.get("col_mask_auto_centers", False) and not col_centers:
                col_centers = detect_mg_column_centers_pitch_phase(
                    mask_roi,
                    pitch_px=pitch_px,
                    smooth_k=int(dc.get("xproj_smooth_k", 5)),
                    min_height_frac=float(dc.get("xproj_peak_min_frac", 0.3)),
                    edge_margin_px=edge_margin,
                )
            if not col_centers:  # fallback to manual grid
                start_x = int(dc.get("col_mask_start_x", 0))
                pitch = int(dc.get("col_mask_pitch_px", 44))
                w = mask_roi.shape[1]
                if pitch > 0 and start_x < w:
                    col_centers = list(range(start_x, w, pitch))
            mask_roi = apply_column_strip_mask(mask_roi, col_centers, half_w, col_margin, edge_margin)
            context["mask_roi_stripped"] = mask_roi
            context["mg_col_centers"] = col_centers

        blobs = detect_blobs(mask_roi, min_area=min_area)

        # Geometric filters (0 = disabled)
        min_ar = float(dc.get("min_aspect_ratio", 0.0))
        max_ar = float(dc.get("max_aspect_ratio", 0.0))
        min_w  = int(dc.get("min_width", 0))
        max_w  = int(dc.get("max_width", 0))
        min_h  = int(dc.get("min_height", 0))
        if any([min_ar, max_ar, min_w, max_w, min_h]):
            filtered = []
            for b in blobs:
                ar = b.height / max(b.width, 1)
                if min_ar and ar < min_ar:
                    continue
                if max_ar and ar > max_ar:
                    continue
                if min_w and b.width < min_w:
                    continue
                if max_w and b.width > max_w:
                    continue
                if min_h and b.height < min_h:
                    continue
                filtered.append(b)
            blobs = filtered

        # Border blob exclusion (edge_locator_config["border_margin_px"], 0 = disabled)
        _border_px = int(self._descriptor.edge_locator_config.get("border_margin_px", 0))
        if _border_px > 0:
            _h, _w = mask_roi.shape[:2]
            blobs = [b for b in blobs
                     if b.x0 >= _border_px and b.y0 >= _border_px
                     and b.x1 <= _w - _border_px and b.y1 <= _h - _border_px]

        # Pitch Grid Regularization: snap blobs onto layout grid, normalize X bounds
        if dc.get("col_mask_enabled", False) and dc.get("col_mask_regularize", False) and col_centers:
            tol    = int(dc.get("col_mask_pitch_tol_px", 5))
            norm_x = bool(dc.get("col_mask_normalize_x", True))
            blobs  = regularize_blobs_to_columns(blobs, col_centers, half_w, tol, norm_x)

        context["blobs_roi"] = blobs
        return blobs

    # ── Stage 4: locate_edges ─────────────────────────────────────────────────

    def locate_edges(self, features: list, context: dict) -> list:
        # For X-CD: keep blobs in rotated space so analyze() finds Y-gaps there
        # (those Y-gaps correspond to X-gaps in original image space).
        # Back-rotation to original coordinates happens after analysis in compute_metrics().
        context["blobs_ori"] = features
        return features

    # ── Stage 5: compute_metrics ──────────────────────────────────────────────

    def compute_metrics(
        self,
        edge_features: list,
        image_record: ImageRecord,
        context: dict,
    ) -> list[MeasurementRecord]:
        from ..cmg_analyzer import analyze
        nm_per_pixel = image_record.pixel_size_nm
        axis = self._descriptor.axis_mode.upper()

        ec = self._descriptor.edge_locator_config
        cuts = analyze(
            edge_features,
            nm_per_pixel,
            x_overlap_ratio=ec.get("x_overlap_ratio", 0.5),
            y_cluster_tol=ec.get("y_cluster_tol", 10),
        )

        # ── Y-edge refinement (Y-CD only) ────────────────────────────────────
        # ycd_edge_method controls which method is used:
        #   "subpixel" (default) – gradient-based subpixel refinement on raw image
        #   "bbox"               – keep original bounding-box integer edges
        # X-CD path is completely untouched.
        if axis == "Y":
            raw_img = context.get("raw")
            _edge_method = str(ec.get("ycd_edge_method", "threshold_crossing")).lower()
            if raw_img is not None and _edge_method in ("subpixel", "threshold_crossing"):
                _sp           = ec   # edge_locator_config carries all knobs
                _half_col     = int  (_sp.get("subpixel_half_col",      3))
                _search_half  = int  (_sp.get("subpixel_search_half",  10))
                _proximity    = int  (_sp.get("subpixel_proximity",     5))
                _smooth_k     = int  (_sp.get("subpixel_smooth_k",      5))
                _grad_frac    = float(_sp.get("subpixel_min_grad_frac", 0.10))
                _peak_ratio   = float(_sp.get("subpixel_peak_ratio",    0.60))
                _threshold_frac = float(_sp.get("threshold_frac",       0.5))
                # Stable X anchors from pitch-phase detection (may be empty)
                _col_centers  = context.get("mg_col_centers", [])

                # Delegate refine + MIN/MAX re-flag to shared helper
                apply_yedge_subpixel_to_cuts(
                    cuts, raw_img, nm_per_pixel,
                    method=_edge_method,
                    half_col=_half_col, search_half=_search_half,
                    proximity=_proximity, smooth_k=_smooth_k,
                    min_grad_frac=_grad_frac, peak_ratio=_peak_ratio,
                    threshold_frac=_threshold_frac,
                    col_centers=_col_centers, store_meta=True,
                )

        # For X-CD: blobs were analyzed in rotated space; back-rotate blob
        # coordinates now so annotations are drawn in original image space.
        if axis == "X":
            orig_h = context["raw"].shape[0]
            for cut in cuts:
                for m in cut.measurements:
                    m.upper_blob = _rot_blob_to_ori(m.upper_blob, orig_h)
                    m.lower_blob = _rot_blob_to_ori(m.lower_blob, orig_h)

        # Range filter — applied here so batch (Recipe path) behaves identically to
        # the legacy-cards path in measure_workspace / batch_dialog.
        dc = self._descriptor.detector_config
        if dc.get("range_enabled", False):
            from ..cmg_analyzer import CMGCut as _CMGCut
            min_px = float(dc.get("min_line_px", 0.0))
            max_px = float(dc.get("max_line_px", 0.0))
            filtered = []
            for cut in cuts:
                kept = [
                    m for m in cut.measurements
                    if (min_px <= 0 or m.cd_px >= min_px)
                    and (max_px <= 0 or m.cd_px <= max_px)
                ]
                if kept:
                    filtered.append(_CMGCut(cmg_id=cut.cmg_id, measurements=kept))
            cuts = filtered
            # Re-flag per cut using top-3 logic
            for cut in cuts:
                _flag_top3(cut.measurements)

        context["cmg_cuts"] = cuts

        _STATUS = {"MIN": "min", "MAX": "max", "": "normal"}
        records: list[MeasurementRecord] = []

        for cut in cuts:
            for m in cut.measurements:
                m.axis = axis
                m.state_name = self._descriptor.recipe_name
                m.structure_name = self._descriptor.structure_name

                ub, lb = m.upper_blob, m.lower_blob
                if axis == "X":
                    # After back-rotation ub/lb are left/right blobs; bbox = the gap
                    left_b, right_b = (ub, lb) if ub.cx <= lb.cx else (lb, ub)
                    bbox: tuple[int, int, int, int] = (
                        int(left_b.x1),
                        int(min(left_b.y0, right_b.y0)),
                        int(right_b.x0),
                        int(max(left_b.y1, right_b.y1)),
                    )
                else:
                    bbox = (
                        int(min(ub.x0, lb.x0)),
                        int(ub.y1),
                        int(max(ub.x1, lb.x1)),
                        int(lb.y0),
                    )

                struct = self._descriptor.structure_name or "STRUCT"
                rec = MeasurementRecord(
                    measurement_id=str(uuid.uuid4()),
                    image_id=image_record.image_id,
                    recipe_id=self.recipe_id,
                    feature_type=f"{struct}_GAP",
                    feature_id=f"feat{m.cmg_id}_col{m.col_id}",
                    bbox=bbox,
                    center_x=float((bbox[0] + bbox[2]) / 2),
                    center_y=float((bbox[1] + bbox[3]) / 2),
                    axis=axis,
                    raw_px=float(m.cd_px),
                    calibrated_nm=float(m.cd_nm),
                    status=_STATUS.get(m.flag, "normal"),
                    cmg_id=int(m.cmg_id),
                    col_id=int(m.col_id),
                    flag=m.flag,
                    state_name=m.state_name,
                    structure_name=self._descriptor.structure_name,
                    extra_metrics={
                        "upper_bbox": (int(ub.x0), int(ub.y0), int(ub.x1), int(ub.y1)),
                        "lower_bbox": (int(lb.x0), int(lb.y0), int(lb.x1), int(lb.y1)),
                        **getattr(m, "_refine_meta", {}),
                    },
                )
                records.append(rec)

        return records

    # ── Stage 6: render_annotations ──────────────────────────────────────────

    def render_annotations(
        self,
        raw: np.ndarray,
        mask: np.ndarray,
        records: list[MeasurementRecord],
        context: dict,
        opts: Any = None,
    ) -> np.ndarray:
        from ..annotator import draw_overlays
        cuts = context.get("cmg_cuts", [])
        if not cuts:
            return cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
        return draw_overlays(raw, mask, cuts, opts)

    # ── Legacy helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _card_to_descriptor(card: dict) -> MeasurementRecipe:
        """Convert a legacy ControlPanel card dict → MeasurementRecipe."""
        axis = str(card.get("axis", "Y")).upper()
        axis_mode = "X" if axis.startswith("X") else "Y"
        struct = str(card.get("structure_name", "CMG"))
        recipe_type = f"{struct}_{axis_mode}CD"
        return MeasurementRecipe(
            recipe_id=str(uuid.uuid4()),
            recipe_name=str(card.get("name", "Unnamed")),
            recipe_type=recipe_type,
            structure_name=struct,
            axis_mode=axis_mode,
            preprocess_config=RecipeConfig(data={
                "gl_min": int(card.get("gl_min", 100)),
                "gl_max": int(card.get("gl_max", 220)),
                "gauss_kernel": int(card.get("gauss_kernel", 3)),
                "morph_open_k": int(card.get("morph_open_k", 3)),
                "morph_close_k": int(card.get("morph_close_k", 5)),
                "use_clahe": bool(card.get("use_clahe", True)),
                "clahe_clip": float(card.get("clahe_clip", 2.0)),
                "clahe_grid": int(card.get("clahe_grid", 8)),
                "vert_erode_k": int(card.get("vert_erode_k", 0)),
                "vert_erode_iter": int(card.get("vert_erode_iter", 1)),
            }),
            detector_config=RecipeConfig(data={
                "min_area": card.get("min_area"),
                "min_aspect_ratio": float(card.get("min_aspect_ratio", 0.0)),
                "max_aspect_ratio": float(card.get("max_aspect_ratio", 0.0)),
                "min_width": int(card.get("min_width", 0)),
                "max_width": int(card.get("max_width", 0)),
                "min_height": int(card.get("min_height", 0)),
                "col_mask_enabled":      bool(card.get("col_mask_enabled", False)),
                "col_mask_auto_centers": bool(card.get("col_mask_auto_centers", False)),
                "xproj_smooth_k":        int(card.get("xproj_smooth_k", 5)),
                "xproj_min_pitch_px":    int(card.get("xproj_min_pitch_px", 30)),
                "xproj_peak_min_frac":   float(card.get("xproj_peak_min_frac", 0.3)),
                "col_mask_start_x":      int(card.get("col_mask_start_x", 0)),
                "col_mask_pitch_px":     int(card.get("col_mask_pitch_px", 44)),
                "col_mask_width_px":     int(card.get("col_mask_width_px", 22)),
                "col_mask_margin_px":    int(card.get("col_mask_margin_px", 4)),
                "col_mask_edge_margin_px": int(card.get("col_mask_edge_margin_px", 0)),
                "col_mask_regularize":   bool(card.get("col_mask_regularize", False)),
                "col_mask_pitch_tol_px": int(card.get("col_mask_pitch_tol_px", 5)),
                "col_mask_normalize_x":  bool(card.get("col_mask_normalize_x", True)),
                "range_enabled":         bool(card.get("range_enabled", False)),
                "min_line_px":           float(card.get("min_line_px", 0.0)),
                "max_line_px":           float(card.get("max_line_px", 0.0)),
            }),
            edge_locator_config=RecipeConfig(data={
                "x_overlap_ratio":        float(card.get("x_overlap_ratio",        0.5)),
                "y_cluster_tol":          int  (card.get("y_cluster_tol",          10)),
                "ycd_edge_method":        str  (card.get("ycd_edge_method",        "threshold_crossing")),
                "threshold_frac":         float(card.get("threshold_frac",         0.5)),
                "subpixel_half_col":      int  (card.get("subpixel_half_col",      3)),
                "subpixel_search_half":   int  (card.get("subpixel_search_half",   10)),
                "subpixel_proximity":     int  (card.get("subpixel_proximity",     5)),
                "subpixel_smooth_k":      int  (card.get("subpixel_smooth_k",      5)),
                "subpixel_min_grad_frac": float(card.get("subpixel_min_grad_frac", 0.10)),
                "subpixel_peak_ratio":    float(card.get("subpixel_peak_ratio",    0.60)),
                "border_margin_px":       int  (card.get("border_margin_px",       0)),
            }),
        )


# ── Subpixel refinement helpers ──────────────────────────────────────────────


def _build_fallback_reason(up: _SubpixelResult, lo: _SubpixelResult) -> str:
    """Combine per-edge fallback reasons into one string for extra_metrics."""
    parts = []
    if up.fallback_reason:
        parts.append(f"up:{up.fallback_reason}")
    if lo.fallback_reason:
        parts.append(f"lo:{lo.fallback_reason}")
    return ",".join(parts)


def apply_yedge_subpixel_to_cuts(
    cuts: list,
    raw_img,
    nm_per_pixel: float,
    method: str = "threshold_crossing",
    half_col: int = 3,
    search_half: int = 10,
    proximity: int = 5,
    smooth_k: int = 5,
    min_grad_frac: float = 0.10,
    peak_ratio: float = 0.60,
    threshold_frac: float = 0.5,
    col_centers: list | None = None,
    store_meta: bool = True,
) -> None:
    """Apply Y-edge refinement in place to a list of CMGCut objects.

    method:
      "threshold_crossing" (default) – intensity threshold at threshold_frac of
                                        the local contrast range
      "subpixel"                      – gradient peak + quadratic interpolation

    Modifies m.cd_px / m.cd_nm and m.y_upper_edge / m.y_lower_edge on each
    YCDMeasurement, then re-flags MIN/MAX per cut.
    Optionally stores debug info as m._refine_meta (used by compute_metrics()).

    Safe to call from outside CMGRecipe — measure_workspace uses this for the
    legacy-cards path so both paths share the same refinement logic.
    """
    _centers = col_centers or []

    for cut in cuts:
        for m in cut.measurements:
            ub, lb = m.upper_blob, m.lower_blob
            blob_cx = (ub.cx + lb.cx) / 2.0
            if _centers:
                x_ctr = float(min(_centers, key=lambda c, _b=blob_cx: abs(c - _b)))
            else:
                x_ctr = blob_cx

            y_up = float(ub.y1)
            y_lo = float(lb.y0)

            if method == "threshold_crossing":
                up_res = _refine_yedge_threshold_crossing(
                    raw_img, x_ctr, y_up,
                    half_col=half_col, search_half=search_half,
                    proximity=proximity, smooth_k=smooth_k,
                    threshold_frac=threshold_frac,
                )
                lo_res = _refine_yedge_threshold_crossing(
                    raw_img, x_ctr, y_lo,
                    half_col=half_col, search_half=search_half,
                    proximity=proximity, smooth_k=smooth_k,
                    threshold_frac=threshold_frac,
                )
            else:  # "subpixel" — gradient peak
                up_res = _refine_yedge_subpixel(
                    raw_img, x_ctr, y_up,
                    half_col=half_col, search_half=search_half,
                    proximity=proximity, smooth_k=smooth_k,
                    min_grad_frac=min_grad_frac, peak_ratio_thr=peak_ratio,
                )
                lo_res = _refine_yedge_subpixel(
                    raw_img, x_ctr, y_lo,
                    half_col=half_col, search_half=search_half,
                    proximity=proximity, smooth_k=smooth_k,
                    min_grad_frac=min_grad_frac, peak_ratio_thr=peak_ratio,
                )

            cd_ref = lo_res.y_refined - up_res.y_refined
            if cd_ref > 0.0:
                m.cd_px = cd_ref
                m.cd_nm = cd_ref * nm_per_pixel
                m.y_upper_edge = up_res.y_refined
                m.y_lower_edge = lo_res.y_refined
                _refine_used = True
                _fallback_reason = _build_fallback_reason(up_res, lo_res)
            else:
                _refine_used = False
                _both_ok = (not up_res.fallback_reason
                            and not lo_res.fallback_reason)
                _fallback_reason = (
                    "non_positive_gap" if _both_ok
                    else _build_fallback_reason(up_res, lo_res)
                )

            if store_meta:
                m._refine_meta = {
                    "upper_edge_refined": up_res.y_refined,
                    "lower_edge_refined": lo_res.y_refined,
                    "refine_used": _refine_used,
                    "refine_fallback_reason": _fallback_reason,
                    "upper_peak_strength": up_res.peak_strength,
                    "lower_peak_strength": lo_res.peak_strength,
                    "upper_second_peak_ratio": up_res.second_peak_ratio,
                    "lower_second_peak_ratio": lo_res.second_peak_ratio,
                    "upper_refine_shift_px": up_res.shift_px,
                    "lower_refine_shift_px": lo_res.shift_px,
                }

    # Re-flag MIN/MAX per cut using top-3 logic
    for cut in cuts:
        _flag_top3(cut.measurements)


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _refine_yedge_subpixel(
    image: np.ndarray,
    x_center: float,
    y_guess: float,
    half_col: int = 3,
    search_half: int = 10,
    proximity: int = 5,
    smooth_k: int = 5,
    min_grad_frac: float = 0.10,
    peak_ratio_thr: float = 0.60,
) -> _SubpixelResult:
    """Refine a Y-edge position to subpixel precision using gradient-based detection.

    Extracts a narrow column profile from the raw grayscale image around
    (x_center, y_guess), finds the dominant gradient peak with quality checks,
    and applies quadratic subpixel interpolation.

    Constraints enforced:
    - Relative gradient threshold (min_grad_frac × profile contrast range)
    - Peak dominance: rejects profiles with multiple comparable peaks
    - Proximity: refined result must lie within ±proximity px of y_guess
    - Search window strictly bounded to ±search_half px of y_guess

    Returns _SubpixelResult with fallback_reason="" on success, or a reason
    code string on failure (y_refined == y_guess in that case).
    """
    _fallback = lambda reason: _SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)

    if image is None or image.ndim < 2:
        return _fallback("invalid_image")

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    # Step 1: narrow column strip around x_center
    x0 = max(0, int(x_center) - half_col)
    x1 = min(w, int(x_center) + half_col + 1)
    if x1 - x0 < 1:
        return _fallback("invalid_image")

    # Step 2: Y search window strictly bounded to ±search_half px
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi - y_lo
    if n < 3:
        return _fallback("small_window")

    # Step 3: 1D profile — mean intensity over X strip
    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)

    # Step 4: relative gradient threshold — profile must have visible contrast
    p_range = float(profile.max() - profile.min())
    if p_range < 1.0:           # essentially flat region → no edge to find
        return _fallback("flat_profile")
    min_grad_abs = min_grad_frac * p_range

    # Step 5: moving-average smoothing
    k = smooth_k | 1            # ensure odd kernel
    if n >= k:
        kernel = np.ones(k, dtype=np.float64) / k
        profile = np.convolve(profile, kernel, mode='same')

    # Step 6: absolute gradient
    abs_grad = np.abs(np.gradient(profile))

    # Step 7: search interior only (avoid convolution boundary artefacts).
    # Margin must be k//2+1 so that abs_grad values that depend on zero-padded
    # smoothed samples are excluded (np.convolve 'same' contaminates k//2 samples
    # on each side, and np.gradient then propagates one more index outward).
    margin = max(1, k // 2 + 1)
    lo_m = margin
    hi_m = min(max(lo_m + 1, n - margin), n)
    search_slice = abs_grad[lo_m:hi_m]
    if len(search_slice) < 1:
        return _fallback("small_window")

    peak_in_slice = int(np.argmax(search_slice))
    peak_local = peak_in_slice + lo_m
    peak_val = abs_grad[peak_local]

    # Step 8: relative gradient threshold check
    if peak_val < min_grad_abs:
        return _fallback("weak_gradient")

    # Step 9: peak dominance check.
    # A smoothed step edge creates a gradient plateau of width ≈ k-1 samples, so
    # the exclusion zone must be wide enough to cover it: ±(k//2+1) from the peak.
    _excl_r = k // 2 + 2   # half-width on the right (exclusive upper bound offset)
    _excl_l = k // 2 + 1   # half-width on the left
    mask = np.ones(len(search_slice), dtype=bool)
    excl_lo = max(0, peak_in_slice - _excl_l)
    excl_hi = min(len(search_slice), peak_in_slice + _excl_r)
    mask[excl_lo:excl_hi] = False
    second_val = float(search_slice[mask].max()) if mask.any() else 0.0
    if mask.any() and second_val > peak_ratio_thr * peak_val:
        return _fallback("ambiguous_peak")  # multiple peaks of similar height

    # Step 10: quadratic subpixel interpolation on gradient peak
    if 0 < peak_local < n - 1:
        a = abs_grad[peak_local - 1]
        b = abs_grad[peak_local]
        c = abs_grad[peak_local + 1]
        denom = a - 2.0 * b + c
        delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        peak_sub = float(peak_local) + delta
    else:
        peak_sub = float(peak_local)

    # Clamp to search window
    peak_sub = max(0.0, min(float(n - 1), peak_sub))
    refined = float(y_lo) + peak_sub

    # Step 11: proximity constraint — refined must stay close to initial guess
    if abs(refined - y_guess) > proximity:
        return _fallback("proximity_violation")

    peak_strength = peak_val / (p_range + 1e-12)
    ratio = second_val / peak_val if peak_val > 0 else 0.0
    return _SubpixelResult(refined, "", peak_strength, ratio, refined - y_guess)


def _refine_yedge_threshold_crossing(
    image: np.ndarray,
    x_center: float,
    y_guess: float,
    half_col: int = 3,
    search_half: int = 10,
    proximity: int = 8,
    smooth_k: int = 3,
    threshold_frac: float = 0.5,
) -> _SubpixelResult:
    """Refine a Y-edge by finding where intensity crosses a threshold level.

    threshold = I_min + (I_max - I_min) * threshold_frac

    I_max and I_min are the extrema of the smoothed 1D profile within the
    search window.  The crossing closest to y_guess is returned.  Industry
    standard uses threshold_frac=0.5 (50 % of the local contrast range).

    Fallback reasons (y_refined == y_guess on failure):
      "invalid_image"      – image None or wrong ndim
      "small_window"       – search window < 3 rows
      "flat_profile"       – profile contrast < 1 DN
      "no_crossing"        – threshold not crossed anywhere in window
      "proximity_violation"– closest crossing too far from y_guess
    """
    _fallback = lambda reason: _SubpixelResult(y_guess, reason, 0.0, 0.0, 0.0)

    if image is None or image.ndim < 2:
        return _fallback("invalid_image")

    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    # Step 1: narrow column strip
    x0 = max(0, int(x_center) - half_col)
    x1 = min(w, int(x_center) + half_col + 1)
    if x1 - x0 < 1:
        return _fallback("invalid_image")

    # Step 2: Y search window
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi - y_lo
    if n < 3:
        return _fallback("small_window")

    # Step 3: 1D profile — mean intensity over X strip
    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)

    # Step 4: contrast check
    p_range = float(profile.max() - profile.min())
    if p_range < 1.0:
        return _fallback("flat_profile")

    # Step 5: moving-average smoothing
    k = smooth_k | 1
    if n >= k:
        kernel = np.ones(k, dtype=np.float64) / k
        profile = np.convolve(profile, kernel, mode='same')

    # Step 6: threshold level from smoothed profile extrema
    i_max = float(profile.max())
    i_min = float(profile.min())
    threshold = i_min + (i_max - i_min) * threshold_frac

    # Step 7: find all crossings, keep the one closest to y_guess
    best_crossing: float | None = None
    best_dist = float('inf')
    for i in range(n - 1):
        a, b_val = profile[i], profile[i + 1]
        # Crossed when the two samples straddle the threshold (or one equals it)
        if (a - threshold) * (b_val - threshold) <= 0:
            denom = b_val - a
            t = (threshold - a) / denom if abs(denom) > 1e-12 else 0.5
            t = max(0.0, min(1.0, t))
            crossing = float(y_lo) + i + t
            dist = abs(crossing - y_guess)
            if dist < best_dist:
                best_dist = dist
                best_crossing = crossing

    if best_crossing is None:
        return _fallback("no_crossing")

    # Step 8: proximity constraint
    if abs(best_crossing - y_guess) > proximity:
        return _fallback("proximity_violation")

    contrast = (i_max - i_min) / (i_max + 1e-12)
    return _SubpixelResult(best_crossing, "", contrast, 0.0, best_crossing - y_guess)


def _rot_blob_to_ori(b: Any, orig_h: int) -> Any:
    """Convert a blob from 90°-CW-rotated space back to original image space."""
    from ..mg_detector import Blob
    ox0 = int(b.y0)
    oy0 = int(orig_h - b.x1)
    ox1 = int(b.y1)
    oy1 = int(orig_h - b.x0)
    return Blob(
        label=b.label,
        x0=ox0, y0=oy0, x1=ox1, y1=oy1,
        area=b.area,
        cx=float(b.cy),
        cy=float(orig_h - b.cx),
    )
