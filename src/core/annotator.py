"""Draw CD measurement overlays on a SEM image.

Overlay options (all toggleable):
  show_lines  – vertical measurement line + tick marks
  show_labels – numeric CD value (e.g. "12.5"), no unit, no prefix
  show_boxes  – bounding rectangles around upper / lower MG blobs

Colours (three only):
  MIN Y-CD  →  #e05555  (red)
  MAX Y-CD  →  #5588ee  (blue)
  Normal    →  #44aadd  (cyan)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import cv2
import numpy as np
from .cmg_analyzer import CMGCut, YCDMeasurement

# BGR colours
_COL = {
    "MIN": (85,  85, 224),    # red
    "MAX": (238, 136, 85),    # blue
    "":   (221, 170, 68),     # cyan
}
_TICK_HALF = 5
_LINE_W    = 1
_BOX_W     = 1


@dataclass
class OverlayOptions:
    show_lines:  bool = True
    show_labels: bool = True
    show_boxes:  bool = True


def draw_overlays(
    img_gray: np.ndarray,
    _mask: np.ndarray,
    cuts: list[CMGCut],
    opts: OverlayOptions | None = None,
) -> np.ndarray:
    """Return annotated BGR image."""
    if opts is None:
        opts = OverlayOptions()

    canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    h      = img_gray.shape[0]
    fs     = max(0.32, h / 1600)
    th     = max(1, round(fs))

    for cut in cuts:
        for m in cut.measurements:
            col = _COL.get(m.flag, _COL[""])
            _draw_measurement(canvas, m, col, fs, th, opts)

    return canvas


def _draw_measurement(
    canvas: np.ndarray,
    m: YCDMeasurement,
    col: tuple,
    fs: float,
    th: int,
    opts: OverlayOptions,
) -> None:
    ub, lb = m.upper_blob, m.lower_blob
    y_top  = ub.y1
    y_bot  = lb.y0
    if y_bot <= y_top:
        return
    x_mid  = int((max(ub.x0, lb.x0) + min(ub.x1, lb.x1)) / 2)

    # ── bounding boxes ────────────────────────────────────────────────────────
    if opts.show_boxes:
        cv2.rectangle(canvas, (ub.x0, ub.y0), (ub.x1 - 1, ub.y1 - 1), col, _BOX_W)
        cv2.rectangle(canvas, (lb.x0, lb.y0), (lb.x1 - 1, lb.y1 - 1), col, _BOX_W)

    # ── measurement line + ticks ──────────────────────────────────────────────
    if opts.show_lines:
        cv2.line(canvas, (x_mid, y_top), (x_mid, y_bot), col, _LINE_W, cv2.LINE_AA)
        cv2.line(canvas, (x_mid - _TICK_HALF, y_top),
                 (x_mid + _TICK_HALF, y_top), col, _LINE_W, cv2.LINE_AA)
        cv2.line(canvas, (x_mid - _TICK_HALF, y_bot),
                 (x_mid + _TICK_HALF, y_bot), col, _LINE_W, cv2.LINE_AA)

    # ── label: just the number, no unit, no tag, no background ───────────────
    if opts.show_labels:
        text   = f"{m.y_cd_nm:.1f}"
        font   = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th_px), _ = cv2.getTextSize(text, font, fs, th)
        x_lbl  = x_mid + _TICK_HALF + 4
        y_lbl  = int((y_top + y_bot) / 2) + th_px // 2
        H, W   = canvas.shape[:2]
        if 0 <= x_lbl + tw < W and 0 <= y_lbl < H:
            cv2.putText(canvas, text, (x_lbl, y_lbl),
                        font, fs, (0, 0, 0), th + 1, cv2.LINE_AA)
            cv2.putText(canvas, text, (x_lbl, y_lbl),
                        font, fs, col, th, cv2.LINE_AA)
