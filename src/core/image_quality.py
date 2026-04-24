"""Image quality screening for SEM images.

Applied inside the batch worker *before* the CMG measurement pipeline runs.
Images that fail quality are returned immediately as FAIL without running
the (much heavier) recipe pipeline.

Primary metric: Laplacian variance after medianBlur(5).
  - medianBlur removes salt-and-pepper / shot noise so isolated pixels are
    not mistaken for genuine high-frequency edges.
  - Laplacian variance reflects true edge sharpness across the image.
"""
from __future__ import annotations

import cv2
import numpy as np

DEFAULT_LAP_THRESHOLD: float = 140.0


def check_lap_quality(img: np.ndarray) -> float:
    """Return Laplacian variance of *img* after median pre-filtering.

    Parameters
    ----------
    img : uint8 grayscale ndarray

    Returns
    -------
    float
        Laplacian variance; higher = sharper. Compare against a threshold
        (e.g. DEFAULT_LAP_THRESHOLD) to decide PASS/FAIL.
    """
    denoised = cv2.medianBlur(img, 5)
    lap = cv2.Laplacian(denoised.astype(np.float64), cv2.CV_64F)
    return float(lap.var())
