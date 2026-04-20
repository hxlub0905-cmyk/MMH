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


def detect_mg_column_centers_pitch_phase(
    mask: np.ndarray,
    pitch_px: int,
    smooth_k: int = 5,
    min_height_frac: float = 0.3,
    edge_margin_px: int = 0,
) -> list[int]:
    """Pitch-anchored phase detection of MG column centers.

    Exploits the physical constraint that MG columns have a fixed, known pitch.
    Finds the phase offset φ ∈ [0, pitch_px) that maximises the mean X-projection
    energy at positions φ, φ+pitch, φ+2·pitch, … then returns a regular grid.

    All returned centers are guaranteed to be exactly pitch_px apart.
    Falls back to empty list only if the mask is blank or pitch_px ≤ 0.
    """
    if pitch_px <= 0:
        return []
    x_proj = mask.sum(axis=0).astype(float)
    if smooth_k > 1:
        pad = smooth_k // 2
        x_padded = np.pad(x_proj, pad, mode="edge")
        x_proj = np.convolve(x_padded, np.ones(smooth_k) / smooth_k, mode="valid")
    if x_proj.max() == 0:
        return []
    W = len(x_proj)
    # Vectorised phase search: reshape into (N, pitch_px), take mean per phase column
    pad_len = (-W) % pitch_px
    x_padded2 = np.pad(x_proj, (0, pad_len), mode="constant", constant_values=0.0)
    phase_means = x_padded2.reshape(-1, pitch_px).mean(axis=0)
    best_offset = int(np.argmax(phase_means))
    # Generate perfectly regular grid from best phase
    centers = list(range(best_offset, W, pitch_px))
    threshold = float(x_proj.max()) * min_height_frac
    centers = [c for c in centers if x_proj[c] >= threshold]
    if edge_margin_px > 0:
        centers = [c for c in centers if edge_margin_px <= c < W - edge_margin_px]
    return centers


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
