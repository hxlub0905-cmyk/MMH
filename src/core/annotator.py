"""Draw CD measurement overlays on a SEM image.

Annotated mode: measurement lines + tick marks + CD labels only.
No mask overlay — that belongs to the separate "Mask" view mode.

Colours:
  MIN Y-CD  →  red   #e05555
  MAX Y-CD  →  blue  #5588ee
  Normal    →  cyan  #44aadd
"""

from __future__ import annotations
import cv2
import numpy as np
from .cmg_analyzer import CMGCut, YCDMeasurement

_COLOUR = {
    "MIN": (85, 85, 224),     # BGR red
    "MAX": (238, 136, 85),    # BGR blue
    "":   (221, 170, 68),     # BGR cyan
}
_TICK_HALF   = 6    # px half-width of tick mark
_LINE_W      = 1
_LABEL_PAD_X = 8    # gap between measurement line and label
_LABEL_PAD_Y = 4    # vertical nudge for label text baseline
_BG_ALPHA    = 0.65


def draw_overlays(
    img_gray: np.ndarray,
    _mask: np.ndarray,        # accepted for API compatibility, not used here
    cuts: list[CMGCut],
) -> np.ndarray:
    """Return annotated BGR image (measurement lines + labels, no mask)."""
    canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)
    h = img_gray.shape[0]
    fs = _font_scale(h)

    for cut in cuts:
        for m in cut.measurements:
            _draw_measurement(canvas, m, _COLOUR.get(m.flag, _COLOUR[""]), fs)

    return canvas


# ── drawing helpers ────────────────────────────────────────────────────────────

def _font_scale(img_h: int) -> float:
    return max(0.38, img_h / 1400)


def _draw_measurement(
    canvas: np.ndarray,
    m: YCDMeasurement,
    colour: tuple[int, int, int],
    fs: float,
) -> None:
    ub, lb = m.upper_blob, m.lower_blob

    # x_mid: centre of the X-overlap between upper and lower blobs
    x_mid = int((max(ub.x0, lb.x0) + min(ub.x1, lb.x1)) / 2)
    y_top = ub.y1        # bottom edge of upper MG
    y_bot = lb.y0        # top edge of lower MG

    if y_bot <= y_top:
        return

    # ── vertical measurement line ─────────────────────────────────────────
    cv2.line(canvas, (x_mid, y_top), (x_mid, y_bot), colour, _LINE_W, cv2.LINE_AA)

    # ── tick marks ────────────────────────────────────────────────────────
    cv2.line(canvas, (x_mid - _TICK_HALF, y_top),
             (x_mid + _TICK_HALF, y_top), colour, _LINE_W, cv2.LINE_AA)
    cv2.line(canvas, (x_mid - _TICK_HALF, y_bot),
             (x_mid + _TICK_HALF, y_bot), colour, _LINE_W, cv2.LINE_AA)

    # ── label ─────────────────────────────────────────────────────────────
    text = f"{m.y_cd_nm:.1f} nm"
    if m.flag:
        text = f"[{m.flag}] {text}"

    font     = cv2.FONT_HERSHEY_SIMPLEX
    th       = max(1, round(fs))
    (tw, th_px), baseline = cv2.getTextSize(text, font, fs, th)

    # position: right of the measurement line, vertically centred in gap
    y_label  = int((y_top + y_bot) / 2) + th_px // 2
    x_label  = x_mid + _TICK_HALF + _LABEL_PAD_X

    # dark pill background for contrast
    pad = 3
    x1b, y1b = x_label - pad, y_label - th_px - pad
    x2b, y2b = x_label + tw + pad, y_label + baseline + pad

    # clamp to canvas bounds
    H, W = canvas.shape[:2]
    x1b, y1b = max(0, x1b), max(0, y1b)
    x2b, y2b = min(W - 1, x2b), min(H - 1, y2b)

    # blend dark background
    roi = canvas[y1b:y2b, x1b:x2b]
    if roi.size > 0:
        dark = np.zeros_like(roi)
        cv2.addWeighted(dark, _BG_ALPHA, roi, 1 - _BG_ALPHA, 0, roi)
        canvas[y1b:y2b, x1b:x2b] = roi

    # text
    cv2.putText(canvas, text, (x_label, y_label),
                font, fs, (0, 0, 0), th + 1, cv2.LINE_AA)
    cv2.putText(canvas, text, (x_label, y_label),
                font, fs, colour, th, cv2.LINE_AA)
