"""Draw CD measurement overlays on a SEM image.

Overlay options (all toggleable):
  show_lines  – vertical measurement line + tick marks
  show_labels – numeric CD value (e.g. "12.5"), no unit, no prefix
  show_boxes  – bounding rectangles around upper / lower MG blobs

Colours (three only):
  MIN Y-CD  →  #d8894f  (orange)
  MAX Y-CD  →  #6ea8cf  (sky)
  Normal    →  #8ccaa6  (mint)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import cv2
import numpy as np
from .cmg_analyzer import CMGCut, YCDMeasurement

# BGR colours
_COL = {
    "MIN": (79, 137, 216),    # orange
    "MAX": (207, 168, 110),   # sky
    "":   (166, 202, 140),    # mint
}
_TICK_HALF = 5
_LINE_W    = 1
_BOX_W     = 1
_LABEL_MIN_DY = 6


@dataclass
class OverlayOptions:
    show_lines:  bool = True
    show_labels: bool = True
    show_boxes:  bool = True
    show_legend: bool = True
    show_detail: bool = False   # when True, show individual sampling lines instead of single line
    focus: tuple[int, int] | None = None


def draw_overlays(
    img_gray: np.ndarray,
    _mask: np.ndarray,
    cuts: list[CMGCut],
    opts: OverlayOptions | None = None,
    color_override: tuple | None = None,
) -> np.ndarray:
    """Return annotated BGR image.

    Args:
        color_override: When set, use this BGR color for *normal* measurements.
                        MIN and MAX measurements always use their designated colors.
    """
    if opts is None:
        opts = OverlayOptions()

    canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    h      = img_gray.shape[0]
    fs     = max(0.18, h / 3200)
    th     = max(1, round(fs))
    last_label_y: dict[int, int] = {}

    for cut in cuts:
        for m in cut.measurements:
            col = _COL.get(m.flag) if m.flag else (color_override if color_override is not None else _COL[""])
            if opts.show_detail:
                _draw_detail_measurements(canvas, m, col, fs, th, opts, last_label_y)
            else:
                _draw_measurement(canvas, m, col, fs, th, opts, last_label_y)

    if opts.show_legend:
        _draw_legend(canvas, fs)

    return canvas


def draw_overlays_multi(
    img_gray: np.ndarray,
    layers: list[tuple],
    opts: OverlayOptions | None = None,
) -> np.ndarray:
    """Render multiple cut layers, each with its own BGR color.

    Args:
        layers: list of (cuts, color_bgr) tuples — one per recipe/config.
                Normal measurements use the layer color; MIN/MAX always use
                their designated orange/sky colors for consistent highlighting.
    """
    if opts is None:
        opts = OverlayOptions()

    canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    h      = img_gray.shape[0]
    fs     = max(0.18, h / 3200)
    th     = max(1, round(fs))
    last_label_y: dict[int, int] = {}

    for cuts, color in layers:
        for cut in cuts:
            for m in cut.measurements:
                col = _COL.get(m.flag) if m.flag else color
                if opts.show_detail:
                    _draw_detail_measurements(canvas, m, col, fs, th, opts, last_label_y)
                else:
                    _draw_measurement(canvas, m, col, fs, th, opts, last_label_y)

    if opts.show_legend:
        _draw_legend(canvas, fs)

    return canvas


def _draw_measurement(
    canvas: np.ndarray,
    m: YCDMeasurement,
    col: tuple,
    fs: float,
    th: int,
    opts: OverlayOptions,
    last_label_y: dict[int, int],
) -> None:
    ub, lb = m.upper_blob, m.lower_blob
    axis = getattr(m, "axis", "Y")

    # ── bounding boxes ────────────────────────────────────────────────────────
    if opts.show_boxes:
        cv2.rectangle(canvas, (ub.x0, ub.y0), (ub.x1 - 1, ub.y1 - 1), col, _BOX_W)
        cv2.rectangle(canvas, (lb.x0, lb.y0), (lb.x1 - 1, lb.y1 - 1), col, _BOX_W)

    # ── measurement line + ticks ──────────────────────────────────────────────
    if opts.show_lines:
        line_w = _LINE_W + 1 if opts.focus == (m.cmg_id, m.col_id) else _LINE_W
        line_col = (40, 120, 240) if opts.focus == (m.cmg_id, m.col_id) else col
        if axis == "X":
            left, right = (ub, lb) if ub.cx <= lb.cx else (lb, ub)
            x_l = left.x1
            x_r = right.x0
            if x_r <= x_l:
                return
            y_mid = int((max(left.y0, right.y0) + min(left.y1, right.y1)) / 2)
            cv2.line(canvas, (x_l, y_mid), (x_r, y_mid), line_col, line_w, cv2.LINE_AA)
            cv2.line(canvas, (x_l, y_mid - _TICK_HALF),
                     (x_l, y_mid + _TICK_HALF), line_col, line_w, cv2.LINE_AA)
            cv2.line(canvas, (x_r, y_mid - _TICK_HALF),
                     (x_r, y_mid + _TICK_HALF), line_col, line_w, cv2.LINE_AA)
        else:
            # Prefer subpixel-refined edge positions when available so the
            # measurement line spans exactly the gap being reported.
            y_top = int(round(m.y_upper_edge)) if m.y_upper_edge is not None else ub.y1
            y_bot = int(round(m.y_lower_edge)) if m.y_lower_edge is not None else lb.y0
            if y_bot <= y_top:
                return
            x_mid = int((max(ub.x0, lb.x0) + min(ub.x1, lb.x1)) / 2)
            cv2.line(canvas, (x_mid, y_top), (x_mid, y_bot), line_col, line_w, cv2.LINE_AA)
            cv2.line(canvas, (x_mid - _TICK_HALF, y_top),
                     (x_mid + _TICK_HALF, y_top), line_col, line_w, cv2.LINE_AA)
            cv2.line(canvas, (x_mid - _TICK_HALF, y_bot),
                     (x_mid + _TICK_HALF, y_bot), line_col, line_w, cv2.LINE_AA)

    # ── label: just the number, no unit, no tag, no background ───────────────
    if opts.show_labels:
        text   = f"{m.cd_nm:.1f}"
        font   = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th_px), _ = cv2.getTextSize(text, font, fs, th)
        if axis == "X":
            left, right = (ub, lb) if ub.cx <= lb.cx else (lb, ub)
            x_l = left.x1
            x_r = right.x0
            y_mid = int((max(left.y0, right.y0) + min(left.y1, right.y1)) / 2)
            x_lbl = int((x_l + x_r) / 2) - tw // 2
            y_lbl = y_mid - _TICK_HALF - 3
        else:
            y_top = int(round(m.y_upper_edge)) if m.y_upper_edge is not None else ub.y1
            y_bot = int(round(m.y_lower_edge)) if m.y_lower_edge is not None else lb.y0
            x_mid = int((max(ub.x0, lb.x0) + min(ub.x1, lb.x1)) / 2)
            x_lbl = x_mid + _TICK_HALF + 2
            y_lbl = int((y_top + y_bot) / 2) + th_px // 2
        H, W   = canvas.shape[:2]
        lane   = x_lbl // 30
        prev_y = last_label_y.get(lane)
        if prev_y is not None and abs(y_lbl - prev_y) < _LABEL_MIN_DY:
            y_lbl = min(H - 2, prev_y + _LABEL_MIN_DY)
        if 0 <= x_lbl + tw < W and 0 <= y_lbl < H:
            cv2.putText(canvas, text, (x_lbl, y_lbl),
                        font, fs, (0, 0, 0), th + 1, cv2.LINE_AA)
            cv2.putText(canvas, text, (x_lbl, y_lbl),
                        font, fs, col, th, cv2.LINE_AA)
            last_label_y[lane] = y_lbl


def _draw_detail_measurements(
    canvas: np.ndarray,
    m: YCDMeasurement,
    col: tuple,
    fs: float,
    th: int,
    opts: OverlayOptions,
    last_label_y: dict[int, int],
) -> None:
    """Draw individual per-sample CD lines for Detail CD mode.

    Falls back to _draw_measurement when no _refine_meta is available
    (BBox mode or old data loaded from JSON without sample info).
    """
    meta = getattr(m, "_refine_meta", None)
    if (meta is None
            or "sample_xs" not in meta
            or not meta.get("sample_xs")
            or not meta.get("individual_cds_nm")):
        _draw_measurement(canvas, m, col, fs, th, opts, last_label_y)
        return

    ub, lb = m.upper_blob, m.lower_blob
    axis = getattr(m, "axis", "Y")

    # Bounding boxes (same as normal mode)
    if opts.show_boxes:
        cv2.rectangle(canvas, (ub.x0, ub.y0), (ub.x1 - 1, ub.y1 - 1), col, _BOX_W)
        cv2.rectangle(canvas, (lb.x0, lb.y0), (lb.x1 - 1, lb.y1 - 1), col, _BOX_W)

    if axis != "Y":
        _draw_measurement(canvas, m, col, fs, th, opts, last_label_y)
        return

    sample_xs     = meta["sample_xs"]
    upper_ys      = meta.get("upper_sample_ys", [])
    lower_ys      = meta.get("lower_sample_ys", [])
    nm_per_pixel  = m.cd_nm / m.cd_px if (m.cd_px and m.cd_px > 0) else 1.0

    font = cv2.FONT_HERSHEY_SIMPLEX
    H, W = canvas.shape[:2]

    for i, x in enumerate(sample_xs):
        if i >= len(upper_ys) or i >= len(lower_ys):
            break
        up_y_i = upper_ys[i]
        lo_y_i = lower_ys[i]
        if up_y_i is None or lo_y_i is None:
            continue
        y_top = int(round(up_y_i))
        y_bot = int(round(lo_y_i))
        if y_bot <= y_top:
            continue

        if opts.show_lines:
            cv2.line(canvas, (x, y_top), (x, y_bot), col, _LINE_W, cv2.LINE_AA)

        if opts.show_labels:
            cd_i = (lo_y_i - up_y_i) * nm_per_pixel
            text = f"{cd_i:.1f}"
            (tw, th_px), _ = cv2.getTextSize(text, font, fs * 0.85, th)
            x_lbl = x + 2
            y_lbl = int((y_top + y_bot) / 2) + th_px // 2
            lane = x_lbl // 30
            prev_y = last_label_y.get(lane)
            if prev_y is not None and abs(y_lbl - prev_y) < _LABEL_MIN_DY:
                y_lbl = min(H - 2, prev_y + _LABEL_MIN_DY)
            if 0 <= x_lbl + tw < W and 0 <= y_lbl < H:
                cv2.putText(canvas, text, (x_lbl, y_lbl),
                            font, fs * 0.85, (0, 0, 0), th + 1, cv2.LINE_AA)
                cv2.putText(canvas, text, (x_lbl, y_lbl),
                            font, fs * 0.85, col, th, cv2.LINE_AA)
                last_label_y[lane] = y_lbl


def _draw_legend(canvas: np.ndarray, fs: float) -> None:
    H, W = canvas.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    items = [
        ("MIN Y-CD", _COL["MIN"]),
        ("MAX Y-CD", _COL["MAX"]),
        ("NORMAL", _COL[""]),
    ]
    pad = 5
    lh = 12                            # reduced from 16 → tighter line spacing
    box_w = 118
    box_h = pad * 2 + lh * len(items) + 2
    x0 = max(0, W - box_w - 8)
    y0 = 8
    overlay = canvas.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (255, 255, 255), -1)
    cv2.addWeighted(overlay, 0.78, canvas, 0.22, 0, canvas)
    cv2.rectangle(canvas, (x0, y0), (x0 + box_w, y0 + box_h), (200, 200, 200), 1)
    for i, (label, col) in enumerate(items):
        yy = y0 + pad + (i + 1) * lh - 2
        cv2.circle(canvas, (x0 + 10, yy - 3), 3, col, -1)
        cv2.putText(canvas, label, (x0 + 19, yy), font, max(0.30, fs * 0.9), (55, 55, 55), 1, cv2.LINE_AA)
