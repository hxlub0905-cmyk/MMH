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


def _gaussian_filter1d(profile: np.ndarray, sigma: float) -> np.ndarray:
    """Apply a 1-D Gaussian LPF using numpy convolution (no scipy dependency)."""
    k = max(3, int(6 * sigma) | 1)          # odd kernel, at least 3 wide
    x = np.arange(k, dtype=np.float64) - k // 2
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    return np.convolve(profile, kernel, mode='same')

from ..models import ImageRecord, MeasurementRecord
from ..recipe_base import BaseRecipe, MeasurementRecipe, RecipeConfig
from ..cmg_analyzer import _flag_global_minmax, _flag_top3

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
        #   "gradient"           – gradient-based subpixel refinement on raw image
        #   "threshold_crossing" – intensity threshold at threshold_frac of local contrast
        #   "bbox"               – keep original bounding-box integer edges
        # X-CD path is completely untouched.
        if axis == "Y":
            raw_img = context.get("raw")
            _edge_method = str(ec.get("ycd_edge_method", "threshold_crossing")).lower()
            if _edge_method == "subpixel":
                _edge_method = "gradient"  # backward compat for old recipes
            if raw_img is not None and _edge_method in ("gradient", "threshold_crossing"):
                _sp           = ec   # edge_locator_config carries all knobs
                _half_col     = int  (_sp.get("subpixel_half_col",      3))
                _search_half  = int  (_sp.get("subpixel_search_half",  10))
                _proximity    = int  (_sp.get("subpixel_proximity",     5))
                _smooth_k     = int  (_sp.get("subpixel_smooth_k",      5))
                _grad_frac    = float(_sp.get("subpixel_min_grad_frac", 0.10))
                _peak_ratio   = float(_sp.get("subpixel_peak_ratio",    0.60))
                _threshold_frac = float(_sp.get("threshold_frac",       0.5))
                _sample_mode  = _sp.get("sample_lines_mode", "all")
                if isinstance(_sample_mode, str) and _sample_mode != "all":
                    try:
                        _sample_mode = int(_sample_mode)
                    except ValueError:
                        _sample_mode = "all"
                _agg_method   = str(_sp.get("aggregate_method", "median")).lower()
                _lpf_enabled  = bool(_sp.get("profile_lpf_enabled", False))
                _lpf_sigma    = float(_sp.get("profile_lpf_sigma", 1.0))
                _x_inset      = int (_sp.get("x_inset_px", 0))
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
                    sample_lines_mode=_sample_mode,
                    aggregate_method=_agg_method,
                    profile_lpf_enabled=_lpf_enabled,
                    profile_lpf_sigma=_lpf_sigma,
                    x_inset=_x_inset,
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
            # Re-flag per-cut TOP3 after range filter
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
                if m.y_upper_edge is not None and m.y_lower_edge is not None:
                    rec.center_y = float((m.y_upper_edge + m.y_lower_edge) / 2)
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
                "sample_lines_mode":      card.get("sample_lines_mode",            "all"),
                "aggregate_method":       str  (card.get("aggregate_method",       "median")),
                "profile_lpf_enabled":    bool (card.get("profile_lpf_enabled",    False)),
                "profile_lpf_sigma":      float(card.get("profile_lpf_sigma",      1.0)),
                "subpixel_half_col":      int  (card.get("subpixel_half_col",      3)),
                "subpixel_search_half":   int  (card.get("subpixel_search_half",   10)),
                "subpixel_proximity":     int  (card.get("subpixel_proximity",     5)),
                "subpixel_smooth_k":      int  (card.get("subpixel_smooth_k",      5)),
                "subpixel_min_grad_frac": float(card.get("subpixel_min_grad_frac", 0.10)),
                "subpixel_peak_ratio":    float(card.get("subpixel_peak_ratio",    0.60)),
                "border_margin_px":       int  (card.get("border_margin_px",       0)),
                "x_inset_px":             int  (card.get("x_inset_px",             0)),
            }),
        )


# ── Subpixel refinement helpers ──────────────────────────────────────────────


def _compute_sample_xs(x_start: int, x_end: int, mode) -> list[int]:
    """Return list of x positions to sample in [x_start, x_end).

    mode: "all" → every integer; int N → N evenly spaced positions.
    """
    xs = list(range(int(x_start), int(x_end)))
    if not xs:
        return xs
    if mode == "all" or not isinstance(mode, int):
        return xs
    N = max(1, min(int(mode), len(xs)))
    if N >= len(xs):
        return xs
    indices = [int(round(i)) for i in np.linspace(0, len(xs) - 1, N)]
    return [xs[i] for i in indices]


def _aggregate_values(vals: list, method: str) -> float:
    """Aggregate float list using method: median/mean/min/max."""
    if not vals:
        return 0.0
    m = method.lower()
    if m == "mean":
        return float(np.mean(vals))
    if m == "min":
        return float(np.min(vals))
    if m == "max":
        return float(np.max(vals))
    return float(np.median(vals))  # default: median


def _build_fallback_reason(up: _SubpixelResult, lo: _SubpixelResult) -> str:
    """Combine per-edge fallback reasons into one string for extra_metrics."""
    parts = []
    if up.fallback_reason:
        parts.append(f"up:{up.fallback_reason}")
    if lo.fallback_reason:
        parts.append(f"lo:{lo.fallback_reason}")
    return ",".join(parts)


def _collect_edge_by_columns(
    image: np.ndarray,
    x_start: int,
    x_end: int,
    y_guess: float,
    method: str,
    search_half: int,
    proximity: int,
    smooth_k: int,
    min_grad_frac: float,
    peak_ratio_thr: float,
    threshold_frac: float,
    profile_lpf_sigma: float = 0.0,
) -> tuple[float, list[float], list[float], list[float]]:
    """Scan every X column in [x_start, x_end) independently.

    Each column is processed as a single-pixel-wide strip (half_col=0).
    Successful results (no fallback) are collected; their median is returned
    as the final edge position.

    Returns:
        y_edge           – np.median of valid_ys, or y_guess if all columns failed
        valid_ys         – list of successful y_refined values
        peak_strengths   – peak_strength for each valid column
        second_peak_ratios – second_peak_ratio for each valid column
    """
    valid_ys: list[float] = []
    peak_strengths: list[float] = []
    second_peak_ratios: list[float] = []

    for x in range(int(x_start), int(x_end)):
        if method == "threshold_crossing":
            res = _refine_yedge_threshold_crossing(
                image, float(x), y_guess,
                half_col=0,
                search_half=search_half,
                proximity=proximity,
                smooth_k=smooth_k,
                threshold_frac=threshold_frac,
                profile_lpf_sigma=profile_lpf_sigma,
            )
        else:  # "gradient"
            res = _refine_yedge_subpixel(
                image, float(x), y_guess,
                half_col=0,
                search_half=search_half,
                proximity=proximity,
                smooth_k=smooth_k,
                min_grad_frac=min_grad_frac,
                peak_ratio_thr=peak_ratio_thr,
                profile_lpf_sigma=profile_lpf_sigma,
            )
        if not res.fallback_reason:
            valid_ys.append(res.y_refined)
            peak_strengths.append(res.peak_strength)
            second_peak_ratios.append(res.second_peak_ratio)

    y_edge = float(np.median(valid_ys)) if valid_ys else y_guess
    return y_edge, valid_ys, peak_strengths, second_peak_ratios


def apply_yedge_subpixel_to_cuts(
    cuts: list,
    raw_img,
    nm_per_pixel: float,
    method: str = "threshold_crossing",
    half_col: int = 3,       # kept for API compatibility; no longer used
    search_half: int = 10,
    proximity: int = 5,
    smooth_k: int = 5,
    min_grad_frac: float = 0.10,
    peak_ratio: float = 0.60,
    threshold_frac: float = 0.5,
    col_centers: list | None = None,  # kept for API compatibility; no longer used
    store_meta: bool = True,
    sample_lines_mode = "all",      # "all" or int N: configurable vertical sampling
    aggregate_method: str = "median",  # "median"/"mean"/"min"/"max"
    profile_lpf_enabled: bool = False,  # apply Gaussian LPF to 1D profile before MA
    profile_lpf_sigma: float = 1.0,     # Gaussian sigma in pixels
    x_inset: int = 0,              # px to exclude from each side of the blob X overlap
) -> None:
    """Apply Y-edge refinement in place to a list of CMGCut objects.

    method:
      "threshold_crossing" – intensity threshold at threshold_frac of local contrast
      "gradient"           – gradient peak + quadratic interpolation (formerly "subpixel")

    When blobs overlap in X, paired sampling is used: the same N x-positions are
    scanned for both the upper and lower edges, yielding per-sample CD values that
    are stored in _refine_meta for the Detail CD view.  When blobs do not overlap,
    independent sampling falls back to the original column-scan approach.

    Modifies m.cd_px / m.cd_nm and m.y_upper_edge / m.y_lower_edge on each
    YCDMeasurement, then re-flags global MIN/MAX.
    Optionally stores debug info as m._refine_meta (used by compute_metrics()).
    """
    _lpf_sigma = float(profile_lpf_sigma) if profile_lpf_enabled else 0.0

    for cut in cuts:
        for m in cut.measurements:
            ub, lb = m.upper_blob, m.lower_blob

            y_up = float(ub.y1)
            y_lo = float(lb.y0)

            x_ov_start = int(max(ub.x0, lb.x0))
            x_ov_end   = int(min(ub.x1, lb.x1))
            # Shrink the sampling zone inward by x_inset on each side so that
            # edge columns at the boundary of one blob are not sampled.
            if x_inset > 0:
                x_ov_start = min(x_ov_start + x_inset, x_ov_end)
                x_ov_end   = max(x_ov_end   - x_inset, x_ov_start)
            use_paired = x_ov_start < x_ov_end

            winning_sample_x: int | None = None   # set below for min/max paired path

            if use_paired:
                # Paired sampling: same x positions for both edges
                sample_xs: list[int] = _compute_sample_xs(x_ov_start, x_ov_end, sample_lines_mode)
                upper_sample_ys: list = []
                lower_sample_ys: list = []
                up_ys: list[float] = []
                lo_ys: list[float] = []
                up_ps: list[float] = []
                lo_ps: list[float] = []
                up_spr: list[float] = []
                lo_spr: list[float] = []
                individual_cds_nm: list[float] = []

                for x in sample_xs:
                    fx = float(x)
                    if method == "threshold_crossing":
                        up_res = _refine_yedge_threshold_crossing(
                            raw_img, fx, y_up, half_col=0,
                            search_half=search_half, proximity=proximity,
                            smooth_k=smooth_k, threshold_frac=threshold_frac,
                            profile_lpf_sigma=_lpf_sigma)
                        lo_res = _refine_yedge_threshold_crossing(
                            raw_img, fx, y_lo, half_col=0,
                            search_half=search_half, proximity=proximity,
                            smooth_k=smooth_k, threshold_frac=threshold_frac,
                            profile_lpf_sigma=_lpf_sigma)
                    else:  # "gradient"
                        up_res = _refine_yedge_subpixel(
                            raw_img, fx, y_up, half_col=0,
                            search_half=search_half, proximity=proximity,
                            smooth_k=smooth_k, min_grad_frac=min_grad_frac,
                            peak_ratio_thr=peak_ratio,
                            profile_lpf_sigma=_lpf_sigma)
                        lo_res = _refine_yedge_subpixel(
                            raw_img, fx, y_lo, half_col=0,
                            search_half=search_half, proximity=proximity,
                            smooth_k=smooth_k, min_grad_frac=min_grad_frac,
                            peak_ratio_thr=peak_ratio,
                            profile_lpf_sigma=_lpf_sigma)

                    up_y_i = up_res.y_refined if not up_res.fallback_reason else None
                    lo_y_i = lo_res.y_refined if not lo_res.fallback_reason else None
                    upper_sample_ys.append(up_y_i)
                    lower_sample_ys.append(lo_y_i)

                    if up_y_i is not None:
                        up_ys.append(up_y_i)
                        up_ps.append(up_res.peak_strength)
                        up_spr.append(up_res.second_peak_ratio)
                    if lo_y_i is not None:
                        lo_ys.append(lo_y_i)
                        lo_ps.append(lo_res.peak_strength)
                        lo_spr.append(lo_res.second_peak_ratio)
                    if up_y_i is not None and lo_y_i is not None:
                        cd_i = (lo_y_i - up_y_i) * nm_per_pixel
                        if cd_i > 0:
                            individual_cds_nm.append(cd_i)

                up_y = _aggregate_values(up_ys, aggregate_method) if up_ys else y_up
                lo_y = _aggregate_values(lo_ys, aggregate_method) if lo_ys else y_lo

                # For min/max: the two lists are aggregated independently above, which
                # can pair edges from different sample positions (giving a wrong CD).
                # Re-derive by finding the paired sample with the actual min/max gap.
                winning_sample_x: int | None = None
                agg_lower = aggregate_method.lower()
                if agg_lower in ("min", "max") and upper_sample_ys and lower_sample_ys:
                    valid_pairs = [
                        (i, upper_sample_ys[i], lower_sample_ys[i])
                        for i in range(min(len(sample_xs), len(upper_sample_ys), len(lower_sample_ys)))
                        if upper_sample_ys[i] is not None
                        and lower_sample_ys[i] is not None
                        and lower_sample_ys[i] > upper_sample_ys[i]
                    ]
                    if valid_pairs:
                        key_fn = (min if agg_lower == "min" else max)
                        best = key_fn(valid_pairs, key=lambda t: t[2] - t[1])
                        winning_sample_x = sample_xs[best[0]]
                        up_y = best[1]
                        lo_y = best[2]
            else:
                # Blobs don't overlap in X: independent column scan (fallback)
                sample_xs = list(range(int(ub.x0), int(ub.x1)))
                upper_sample_ys = []
                lower_sample_ys = []
                individual_cds_nm = []
                up_y, up_ys, up_ps, up_spr = _collect_edge_by_columns(
                    raw_img, ub.x0, ub.x1, y_up, method,
                    search_half, proximity, smooth_k,
                    min_grad_frac, peak_ratio, threshold_frac,
                    profile_lpf_sigma=_lpf_sigma,
                )
                lo_y, lo_ys, lo_ps, lo_spr = _collect_edge_by_columns(
                    raw_img, lb.x0, lb.x1, y_lo, method,
                    search_half, proximity, smooth_k,
                    min_grad_frac, peak_ratio, threshold_frac,
                    profile_lpf_sigma=_lpf_sigma,
                )

            cd_ref = lo_y - up_y
            if cd_ref > 0.0:
                m.cd_px = cd_ref
                m.cd_nm = cd_ref * nm_per_pixel
                m.y_upper_edge = up_y
                m.y_lower_edge = lo_y
                _refine_used = True
                _parts = []
                if not up_ys:
                    _parts.append("up:all_columns_fallback")
                if not lo_ys:
                    _parts.append("lo:all_columns_fallback")
                _fallback_reason = ",".join(_parts)
            else:
                _refine_used = False
                bbox_cd = float(lb.y0) - float(ub.y1)
                if bbox_cd > 0:
                    m.cd_px = bbox_cd
                    m.cd_nm = bbox_cd * nm_per_pixel
                _parts = []
                if not up_ys:
                    _parts.append("up:all_columns_fallback")
                if not lo_ys:
                    _parts.append("lo:all_columns_fallback")
                _fallback_reason = ",".join(_parts) if _parts else "non_positive_gap"

            if store_meta:
                m._refine_meta = {
                    "upper_edge_refined": up_y,
                    "lower_edge_refined": lo_y,
                    "refine_used": _refine_used,
                    "refine_fallback_reason": _fallback_reason,
                    "upper_peak_strength":    float(np.median(up_ps))  if up_ps  else 0.0,
                    "lower_peak_strength":    float(np.median(lo_ps))  if lo_ps  else 0.0,
                    "upper_second_peak_ratio": float(np.median(up_spr)) if up_spr else 0.0,
                    "lower_second_peak_ratio": float(np.median(lo_spr)) if lo_spr else 0.0,
                    "upper_refine_shift_px":  up_y - y_up,
                    "lower_refine_shift_px":  lo_y - y_lo,
                    "upper_n_valid_x":        len(up_ys),
                    "lower_n_valid_x":        len(lo_ys),
                    "upper_spread_y_std":     float(np.std(up_ys)) if len(up_ys) > 1 else 0.0,
                    "lower_spread_y_std":     float(np.std(lo_ys)) if len(lo_ys) > 1 else 0.0,
                    # Per-sample data for Detail CD view
                    "sample_xs":          sample_xs,
                    "upper_sample_ys":    upper_sample_ys,
                    "lower_sample_ys":    lower_sample_ys,
                    "individual_cds_nm":  individual_cds_nm,
                    "aggregate_method":   aggregate_method,
                    # X position of the winning sample (min/max only; None for mean/median)
                    "winning_sample_x":   winning_sample_x,
                }

    # Re-flag per-cut TOP3 after Y-edge refinement
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
    profile_lpf_sigma: float = 0.0,
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

    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
    if profile_lpf_sigma > 0.0:
        profile = _gaussian_filter1d(profile, profile_lpf_sigma)

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
    profile_lpf_sigma: float = 0.0,
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

    # Step 3b: optional Gaussian LPF pre-filter (applied before moving-average)
    if profile_lpf_sigma > 0.0:
        profile = _gaussian_filter1d(profile, profile_lpf_sigma)

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
