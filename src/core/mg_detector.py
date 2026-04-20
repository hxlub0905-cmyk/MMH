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


def detect_mg_column_centers(
    mask: np.ndarray,
    smooth_k: int = 5,
    min_pitch_px: int = 30,
    min_height_frac: float = 0.3,
    edge_margin_px: int = 0,
) -> list[int]:
    """Detect MG column center X positions from X-axis projection of the mask.

    Returns a list of X pixel positions sorted left-to-right.

    edge_margin_px: exclude detected peaks within this many px of the image
    left/right boundary (avoids mislocated peaks caused by partial columns).
    """
    return _xproj_peaks(mask, smooth_k, min_pitch_px, min_height_frac, edge_margin_px)


def detect_mg_column_centers_twopass(
    mask: np.ndarray,
    smooth_k: int = 5,
    min_pitch_px: int = 30,
    min_height_frac: float = 0.3,
    edge_margin_px: int = 0,
    half_width: int = 11,
    margin: int = 4,
) -> list[int]:
    """Two-pass X-proj: eliminates PEPI-induced peak bias.

    Pass 1: X-proj on full mask  → rough centers (may be off by 1-3 px due to PEPI)
    Pass 2: Strip mask with 2× margin → X-proj on clean MG-only mask → accurate centers

    Falls back to Pass-1 result if Pass 2 returns no peaks.
    """
    rough = _xproj_peaks(mask, smooth_k, min_pitch_px, min_height_frac, edge_margin_px)
    if not rough:
        return []
    # Build a strip mask to isolate MG pixels (remove PEPI lateral bridges)
    strip = np.zeros_like(mask)
    hw = half_width + margin * 2          # extra-wide window for pass 1
    W = mask.shape[1]
    lft = max(edge_margin_px, 0)
    rgt = max(edge_margin_px, 0)
    for xc in rough:
        x0 = max(lft, xc - hw)
        x1 = min(W - rgt, xc + hw + 1)
        if x1 > x0:
            strip[:, x0:x1] = 255
    clean = cv2.bitwise_and(mask, strip)
    # Pass 2: no smoothing needed — PEPI already removed
    refined = _xproj_peaks(clean, smooth_k=1, min_pitch_px=min_pitch_px,
                            min_height_frac=min_height_frac, edge_margin_px=edge_margin_px)
    return refined if refined else rough


def _xproj_peaks(
    mask: np.ndarray,
    smooth_k: int,
    min_pitch_px: int,
    min_height_frac: float,
    edge_margin_px: int,
) -> list[int]:
    """Internal: find X-projection local maxima above threshold."""
    x_proj = mask.sum(axis=0).astype(float)
    if smooth_k > 1:
        pad = smooth_k // 2
        x_padded = np.pad(x_proj, pad, mode="edge")
        x_proj = np.convolve(x_padded, np.ones(smooth_k) / smooth_k, mode="valid")
    if x_proj.max() == 0:
        return []
    threshold = float(x_proj.max()) * min_height_frac
    candidates: list[int] = []
    for i in range(1, len(x_proj) - 1):
        if x_proj[i] >= threshold and x_proj[i] >= x_proj[i - 1] and x_proj[i] >= x_proj[i + 1]:
            candidates.append(i)
    if not candidates:
        return []
    centers: list[int] = []
    group_peak = candidates[0]
    for c in candidates[1:]:
        if c - group_peak < min_pitch_px:
            if x_proj[c] > x_proj[group_peak]:
                group_peak = c
        else:
            centers.append(group_peak)
            group_peak = c
    centers.append(group_peak)
    if edge_margin_px > 0:
        W = mask.shape[1]
        centers = [c for c in centers if edge_margin_px <= c < W - edge_margin_px]
    return centers


def regularize_blobs_to_columns(
    blobs: list[Blob],
    col_centers: list[int],
    half_width: int,
    pitch_tol_px: int = 5,
    normalize_x: bool = True,
) -> list[Blob]:
    """Snap blobs onto a known pitch grid, discarding off-grid blobs.

    For each blob:
      1. Find the nearest col_center.
      2. Discard if |blob.cx - nearest_col| > pitch_tol_px (not on grid → noise/PEPI).
      3. If normalize_x: force x0 = col_center - half_width,
                               x1 = col_center + half_width + 1,
                               cx = float(col_center).
    Result: all BBOX_X identical width, all BBOX pitches = layout pitch.
    """
    if not blobs or not col_centers:
        return blobs

    from dataclasses import replace as _replace
    result: list[Blob] = []
    for b in blobs:
        nearest = min(col_centers, key=lambda xc: abs(b.cx - xc))
        if abs(b.cx - nearest) > pitch_tol_px:
            continue  # off-grid → discard
        if normalize_x:
            b = _replace(
                b,
                x0=max(0, nearest - half_width),
                x1=nearest + half_width + 1,
                cx=float(nearest),
            )
        result.append(b)
    return result


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
