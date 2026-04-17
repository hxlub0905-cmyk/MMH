"""Pre-processing pipeline: blur → CLAHE → GL-range mask → morphological ops."""

from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class PreprocessParams:
    gl_min: int = 100            # lower GL bound (inclusive); pixels in [gl_min, gl_max] = MG
    gl_max: int = 220            # upper GL bound (inclusive)
    gauss_kernel: int = 3        # Gaussian blur kernel size (must be odd)
    morph_open_k: int = 3        # morphological open kernel size
    morph_close_k: int = 5       # morphological close kernel size
    use_clahe: bool = True       # apply CLAHE contrast normalisation
    clahe_clip: float = 2.0
    clahe_grid: int = 8


def preprocess(img: np.ndarray, params: PreprocessParams) -> np.ndarray:
    """Return binary uint8 mask (255 = MG, 0 = background)."""
    # 1. Gaussian blur
    k = params.gauss_kernel | 1
    blurred = cv2.GaussianBlur(img, (k, k), 0)

    # 2. CLAHE for brightness normalisation
    if params.use_clahe:
        clahe = cv2.createCLAHE(
            clipLimit=params.clahe_clip,
            tileGridSize=(params.clahe_grid, params.clahe_grid),
        )
        blurred = clahe.apply(blurred)

    # 3. GL range mask: keep pixels in [gl_min, gl_max]
    gl_lo = max(0, min(params.gl_min, params.gl_max))
    gl_hi = min(255, max(params.gl_min, params.gl_max))
    mask = cv2.inRange(blurred, gl_lo, gl_hi)

    # 4. Morphological open (remove small noise)
    ok = params.morph_open_k | 1
    kernel_o = cv2.getStructuringElement(cv2.MORPH_RECT, (ok, ok))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_o)

    # 5. Morphological close (fill small holes)
    ck = params.morph_close_k | 1
    kernel_c = cv2.getStructuringElement(cv2.MORPH_RECT, (ck, ck))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_c)

    return mask
