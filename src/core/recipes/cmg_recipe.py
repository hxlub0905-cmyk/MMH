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
from typing import Any

import cv2
import numpy as np

from ..models import ImageRecord, MeasurementRecord
from ..recipe_base import BaseRecipe, MeasurementRecipe, RecipeConfig


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

        # ── Subpixel Y-edge refinement (Y-CD only) ───────────────────────────
        # Replaces pixel-level bbox edges with gradient-based subpixel edges
        # from the raw grayscale image.  X-CD is completely untouched.
        if axis == "Y":
            raw_img = context.get("raw")
            if raw_img is not None:
                _sp = ec  # reuse edge_locator_config for optional overrides
                _half_col    = int(_sp.get("subpixel_half_col",    3))
                _search_half = int(_sp.get("subpixel_search_half", 10))
                _smooth_k    = int(_sp.get("subpixel_smooth_k",    5))
                _min_grad    = float(_sp.get("subpixel_min_grad",  5.0))

                for cut in cuts:
                    for m in cut.measurements:
                        ub, lb = m.upper_blob, m.lower_blob
                        x_ctr = (ub.cx + lb.cx) / 2.0
                        # Reuse same initial-guess formula as cmg_analyzer.analyze()
                        y_up = ub.cy + (ub.height / 2.0)
                        y_lo = lb.cy - (lb.height / 2.0)

                        up_ref = _refine_yedge_subpixel(
                            raw_img, x_ctr, y_up,
                            half_col=_half_col, search_half=_search_half,
                            smooth_k=_smooth_k, min_grad=_min_grad,
                        )
                        lo_ref = _refine_yedge_subpixel(
                            raw_img, x_ctr, y_lo,
                            half_col=_half_col, search_half=_search_half,
                            smooth_k=_smooth_k, min_grad=_min_grad,
                        )

                        cd_ref = lo_ref - up_ref
                        if cd_ref > 0.0:   # sanity: gap must remain positive
                            m.cd_px = cd_ref
                            m.cd_nm = cd_ref * nm_per_pixel

                # Re-flag MIN/MAX per cut based on refined values
                for cut in cuts:
                    if len(cut.measurements) >= 2:
                        vals = [m.cd_px for m in cut.measurements]
                        mn, mx = min(vals), max(vals)
                        for m in cut.measurements:
                            m.flag = (
                                "MIN" if m.cd_px == mn else
                                "MAX" if m.cd_px == mx else ""
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
            all_m = [m for c in cuts for m in c.measurements]
            if len(all_m) >= 2:
                mn = min(m.cd_px for m in all_m)
                mx = max(m.cd_px for m in all_m)
                for m in all_m:
                    m.flag = "MIN" if m.cd_px == mn else ("MAX" if m.cd_px == mx else "")

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
        )


# ── Coordinate helpers ────────────────────────────────────────────────────────

def _refine_yedge_subpixel(
    image: np.ndarray,
    x_center: float,
    y_guess: float,
    half_col: int = 3,
    search_half: int = 10,
    smooth_k: int = 5,
    min_grad: float = 5.0,
) -> float:
    """Refine a Y-edge position to subpixel precision using gradient-based detection.

    Extracts a narrow column profile from the raw grayscale image around
    (x_center, y_guess), computes absolute gradient, finds the peak, and
    applies quadratic subpixel interpolation.

    Returns a float refined Y position, or y_guess on any failure/fallback.
    """
    if image is None or image.ndim < 2:
        return y_guess

    # Handle 3-channel images
    img = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    # Step 1: narrow column ROI around x_center
    x0 = max(0, int(x_center) - half_col)
    x1 = min(w, int(x_center) + half_col + 1)
    if x1 - x0 < 1:
        return y_guess

    # Step 2: Y search window clamped to image bounds
    y_lo = max(0, int(round(y_guess)) - search_half)
    y_hi = min(h, int(round(y_guess)) + search_half + 1)
    n = y_hi - y_lo
    if n < 3:
        return y_guess

    # Step 3: 1D profile — mean intensity over X strip
    profile = img[y_lo:y_hi, x0:x1].astype(np.float64).mean(axis=1)

    # Step 4: moving-average smoothing
    k = smooth_k | 1  # ensure odd
    if n >= k:
        kernel = np.ones(k, dtype=np.float64) / k
        profile = np.convolve(profile, kernel, mode='same')

    # Step 5: absolute gradient
    abs_grad = np.abs(np.gradient(profile))

    # Step 6: find argmax (avoid convolution edge artefacts)
    margin = max(1, k // 2)
    lo_m = margin
    hi_m = max(lo_m + 1, n - margin)
    peak_local = int(np.argmax(abs_grad[lo_m:hi_m])) + lo_m

    # Step 7: fallback if gradient too weak
    if abs_grad[peak_local] < min_grad:
        return y_guess

    # Step 8: quadratic subpixel interpolation on gradient peak
    if 0 < peak_local < n - 1:
        a = abs_grad[peak_local - 1]
        b = abs_grad[peak_local]
        c = abs_grad[peak_local + 1]
        denom = a - 2.0 * b + c
        delta = 0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0
        peak_sub = float(peak_local) + delta
    else:
        peak_sub = float(peak_local)

    # Clamp to window then return absolute Y
    peak_sub = max(0.0, min(float(n - 1), peak_sub))
    return float(y_lo) + peak_sub


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
