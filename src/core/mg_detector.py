"""Detect MG blobs from a binary mask via connected components analysis."""

from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class Blob:
    label: int
    x0: int   # left
    y0: int   # top
    x1: int   # right (exclusive)
    y1: int   # bottom (exclusive)
    area: int
    cx: float  # centroid x
    cy: float  # centroid y

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0


def detect_blobs(mask: np.ndarray, min_area: int | None = None) -> list[Blob]:
    """Return list of MG blobs extracted from *mask*.

    min_area defaults to max(50, 0.01% of image area).
    """
    h, w = mask.shape
    if min_area is None:
        min_area = max(50, int(h * w * 0.0001))

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )

    blobs: list[Blob] = []
    for lbl in range(1, num_labels):  # skip background (label 0)
        area = int(stats[lbl, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x0 = int(stats[lbl, cv2.CC_STAT_LEFT])
        y0 = int(stats[lbl, cv2.CC_STAT_TOP])
        bw = int(stats[lbl, cv2.CC_STAT_WIDTH])
        bh = int(stats[lbl, cv2.CC_STAT_HEIGHT])
        blobs.append(
            Blob(
                label=lbl,
                x0=x0,
                y0=y0,
                x1=x0 + bw,
                y1=y0 + bh,
                area=area,
                cx=float(centroids[lbl, 0]),
                cy=float(centroids[lbl, 1]),
            )
        )
    return blobs
