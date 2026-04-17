"""Pre-processing pipeline: blur → CLAHE → threshold → morphological ops → blob filter."""

from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class PreprocessParams:
    threshold: int = 128          # GL threshold (0-255); pixels > threshold = MG
    gauss_kernel: int = 3         # Gaussian blur kernel size (must be odd)
    morph_open_k: int = 3         # morphological open kernel size
    morph_close_k: int = 5        # morphological close kernel size
    use_clahe: bool = True        # apply CLAHE contrast normalisation
    clahe_clip: float = 2.0
    clahe_grid: int = 8


def preprocess(img: np.ndarray, params: PreprocessParams) -> np.ndarray:
    """Return binary uint8 mask (255 = MG, 0 = background)."""
    # 1. Gaussian blur
    k = params.gauss_kernel | 1   # ensure odd
    blurred = cv2.GaussianBlur(img, (k, k), 0)

    # 2. CLAHE for brightness normalisation
    if params.use_clahe:
        clahe = cv2.createCLAHE(
            clipLimit=params.clahe_clip,
            tileGridSize=(params.clahe_grid, params.clahe_grid),
        )
        blurred = clahe.apply(blurred)

    # 3. Threshold
    _, mask = cv2.threshold(blurred, params.threshold, 255, cv2.THRESH_BINARY)

    # 4. Morphological open (remove small noise)
    ok = params.morph_open_k | 1
    kernel_o = cv2.getStructuringElement(cv2.MORPH_RECT, (ok, ok))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_o)

    # 5. Morphological close (fill small holes)
    ck = params.morph_close_k | 1
    kernel_c = cv2.getStructuringElement(cv2.MORPH_RECT, (ck, ck))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_c)

    return mask
