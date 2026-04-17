"""Draw measurement overlays on a grayscale SEM image.

Colours (BGR):
  MG mask overlay  – cyan   (255, 255,   0)  semi-transparent
  Normal gap line  – green  (  0, 255,   0)
  MIN Y-CD line    – red    (  0,   0, 255)
  MAX Y-CD line    – blue   (255,   0,   0)
  Bounding box     – matches line colour
  Label text       – white with dark outline
"""

from __future__ import annotations
import cv2
import numpy as np
from .cmg_analyzer import CMGCut, YCDMeasurement

_COLOUR = {
    "MIN": (0, 0, 255),     # red
    "MAX": (255, 0, 0),     # blue
    "":    (0, 200, 0),     # green
}
_MASK_COLOUR = np.array([255, 255, 0], dtype=np.uint8)   # cyan
_MASK_ALPHA = 0.35
_LINE_THICKNESS = 1
_BOX_THICKNESS = 1


def _font_scale(img_h: int) -> float:
    return max(0.35, img_h / 1200)


def draw_overlays(
    img_gray: np.ndarray,
    mask: np.ndarray,
    cuts: list[CMGCut],
) -> np.ndarray:
    """Return annotated BGR image with mask overlay + measurement annotations."""
    canvas = cv2.cvtColor(img_gray, cv2.COLOR_GRAY2BGR)

    # ── cyan mask overlay ────────────────────────────────────────────────────
    overlay = canvas.copy()
    mg_pixels = mask > 0
    overlay[mg_pixels] = _MASK_COLOUR
    cv2.addWeighted(overlay, _MASK_ALPHA, canvas, 1 - _MASK_ALPHA, 0, canvas)

    h = img_gray.shape[0]
    fs = _font_scale(h)

    for cut in cuts:
        for m in cut.measurements:
            colour = _COLOUR.get(m.flag, _COLOUR[""])
            _draw_measurement(canvas, m, colour, fs)

    return canvas


def _draw_measurement(
    canvas: np.ndarray,
    m: YCDMeasurement,
    colour: tuple[int, int, int],
    font_scale: float,
) -> None:
    ub, lb = m.upper_blob, m.lower_blob

    # bounding boxes for upper and lower blobs
    cv2.rectangle(canvas, (ub.x0, ub.y0), (ub.x1 - 1, ub.y1 - 1), colour, _BOX_THICKNESS)
    cv2.rectangle(canvas, (lb.x0, lb.y0), (lb.x1 - 1, lb.y1 - 1), colour, _BOX_THICKNESS)

    # vertical measurement line at mid-X of the overlapping region
    x_mid = int((max(ub.x0, lb.x0) + min(ub.x1, lb.x1)) / 2)
    y_top = ub.y1
    y_bot = lb.y0
    cv2.line(canvas, (x_mid, y_top), (x_mid, y_bot), colour, _LINE_THICKNESS)

    # tick marks
    tick = max(3, int(font_scale * 6))
    cv2.line(canvas, (x_mid - tick, y_top), (x_mid + tick, y_top), colour, _LINE_THICKNESS)
    cv2.line(canvas, (x_mid - tick, y_bot), (x_mid + tick, y_bot), colour, _LINE_THICKNESS)

    # label
    label = f"{m.y_cd_nm:.1f}nm"
    if m.flag:
        label = f"[{m.flag}] {label}"
    y_label = int((y_top + y_bot) / 2)
    _put_text(canvas, label, (x_mid + tick + 2, y_label), font_scale, colour)


def _put_text(
    canvas: np.ndarray,
    text: str,
    org: tuple[int, int],
    scale: float,
    colour: tuple[int, int, int],
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    thickness = max(1, int(scale * 1.5))
    # dark outline for readability
    cv2.putText(canvas, text, org, font, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(canvas, text, org, font, scale, colour, thickness, cv2.LINE_AA)
