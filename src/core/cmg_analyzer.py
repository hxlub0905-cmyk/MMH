"""CMG Y-CD analysis.

Given a list of MG blobs (vertical bright strips cut by a horizontal CMG):
1. Group blobs into columns by X-range overlap.
2. Within each column, adjacent blob pairs → candidate CMG gaps.
3. Cluster gap rows across columns → one CMG cut event per cluster.
4. Output per-CMG, per-column Y-CD measurements.
"""

from dataclasses import dataclass, field
from typing import Optional
import numpy as np
from .mg_detector import Blob

X_OVERLAP_MIN_RATIO = 0.5   # fraction of the narrower blob's width that must overlap
Y_CLUSTER_TOL = 10          # pixels; gaps within this Y-distance = same CMG cut

# CD measurement method keys
CD_METHOD_BBOX     = "bbox"         # binary blob bounding-box edges (default)
CD_METHOD_GRADIENT = "gradient"     # first-derivative peak on gray profile
CD_METHOD_GAUSSIAN = "gaussian_fit" # weighted centroid of gradient peak (sub-pixel)


def _profile_y(
    raw: np.ndarray,
    x0: int, x1: int,
    y0: int, y1: int,
) -> np.ndarray:
    """Return mean intensity profile along Y for columns [x0, x1)."""
    x0 = max(0, min(x0, raw.shape[1] - 1))
    x1 = max(x0 + 1, min(x1, raw.shape[1]))
    return raw[y0:y1, x0:x1].mean(axis=1).astype(float)


def _find_edge_y(
    raw: np.ndarray,
    x0: int, x1: int,
    approx_y: int,
    sign: int,
    method: str,
    window: int = 8,
) -> float:
    """Refine an edge Y position from the gray-level intensity profile.

    sign=+1  dark→bright transition (top edge of lower blob)
    sign=-1  bright→dark transition (bottom edge of upper blob)
    """
    y_lo = max(0, approx_y - window)
    y_hi = min(raw.shape[0], approx_y + window + 1)
    if y_hi <= y_lo:
        return float(approx_y)
    profile = _profile_y(raw, x0, x1, y_lo, y_hi)
    grad = np.gradient(profile)
    signed = sign * grad

    if method == CD_METHOD_GRADIENT:
        peak = int(np.argmax(signed))
        return float(y_lo + peak)

    # gaussian_fit — weighted centroid of the positive portion of the gradient peak
    weights = np.maximum(signed, 0.0)
    total = weights.sum()
    if total <= 0.0:
        return float(approx_y)
    positions = np.arange(len(weights), dtype=float) + y_lo
    return float(np.average(positions, weights=weights))


@dataclass
class YCDMeasurement:
    cmg_id: int
    col_id: int
    upper_blob: Blob
    lower_blob: Blob
    cd_px: float
    cd_nm: float
    flag: str = ""   # "MIN", "MAX", or ""
    axis: str = "Y"
    state_name: str = ""
    structure_name: str = ""


@dataclass
class CMGCut:
    cmg_id: int
    measurements: list[YCDMeasurement] = field(default_factory=list)

    @property
    def y_cd_values(self) -> list[float]:
        return [m.cd_nm for m in self.measurements]

    @property
    def min_nm(self) -> Optional[float]:
        return min(self.y_cd_values) if self.y_cd_values else None

    @property
    def max_nm(self) -> Optional[float]:
        return max(self.y_cd_values) if self.y_cd_values else None


# ── helpers ───────────────────────────────────────────────────────────────────

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def _x_overlap_ratio(a: Blob, b: Blob) -> float:
    overlap = min(a.x1, b.x1) - max(a.x0, b.x0)
    if overlap <= 0:
        return 0.0
    return overlap / min(a.width, b.width)


# ── main API ──────────────────────────────────────────────────────────────────

def analyze(
    blobs: list[Blob],
    nm_per_pixel: float,
    x_overlap_ratio: float = X_OVERLAP_MIN_RATIO,
    y_cluster_tol: int = Y_CLUSTER_TOL,
    raw: "np.ndarray | None" = None,
    cd_method: str = CD_METHOD_BBOX,
) -> list[CMGCut]:
    """Return CMG cuts with per-column Y-CD measurements.

    raw: optional gray-level image; required for gradient / gaussian_fit methods.
    cd_method: one of CD_METHOD_BBOX, CD_METHOD_GRADIENT, CD_METHOD_GAUSSIAN.
    """
    if len(blobs) < 2:
        return []

    n = len(blobs)

    # ── Step 1: group blobs into columns by X-range overlap ──────────────────
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _x_overlap_ratio(blobs[i], blobs[j]) >= x_overlap_ratio:
                uf.union(i, j)

    columns: dict[int, list[int]] = {}
    for idx in range(n):
        root = uf.find(idx)
        columns.setdefault(root, []).append(idx)

    # ── Step 2: within each column, find adjacent Y-gaps ────────────────────
    @dataclass
    class Gap:
        col_group: int
        col_index: int         # index within this column (0, 1, …)
        upper: Blob
        lower: Blob
        cd_px: float
        mid_y: float           # used for clustering across columns

    gaps: list[Gap] = []
    for col_idx, (root, indices) in enumerate(columns.items()):
        sorted_blobs = sorted([blobs[i] for i in indices], key=lambda b: b.y0)
        for k in range(len(sorted_blobs) - 1):
            upper = sorted_blobs[k]
            lower = sorted_blobs[k + 1]
            approx_upper = int(upper.cy + upper.height / 2.0)
            approx_lower = int(lower.cy - lower.height / 2.0)

            if raw is not None and cd_method != CD_METHOD_BBOX:
                ox0 = max(upper.x0, lower.x0)
                ox1 = min(upper.x1, lower.x1)
                if ox1 <= ox0:   # no X overlap — widen to union
                    ox0 = min(upper.x0, lower.x0)
                    ox1 = max(upper.x1, lower.x1)
                upper_edge = _find_edge_y(raw, ox0, ox1, approx_upper, sign=-1, method=cd_method)
                lower_edge = _find_edge_y(raw, ox0, ox1, approx_lower, sign=+1, method=cd_method)
            else:
                upper_edge = float(approx_upper)
                lower_edge = float(approx_lower)

            cd_px = lower_edge - upper_edge
            if cd_px <= 0:
                continue   # blobs overlap — skip
            mid_y = (upper_edge + lower_edge) / 2.0
            gaps.append(
                Gap(
                    col_group=col_idx,
                    col_index=k,
                    upper=upper,
                    lower=lower,
                    cd_px=cd_px,
                    mid_y=mid_y,
                )
            )

    if not gaps:
        return []

    # ── Step 3: cluster gaps by mid_y across columns → CMG cut events ────────
    gaps.sort(key=lambda g: g.mid_y)
    cmg_labels = [0] * len(gaps)
    cmg_id = 0
    cmg_labels[0] = cmg_id
    for i in range(1, len(gaps)):
        if gaps[i].mid_y - gaps[i - 1].mid_y > y_cluster_tol:
            cmg_id += 1
        cmg_labels[i] = cmg_id

    # ── Step 4: build CMGCut objects with Y-CD measurements ──────────────────
    cmg_map: dict[int, CMGCut] = {}
    col_counters: dict[int, int] = {}

    for gap, cid in zip(gaps, cmg_labels):
        if cid not in cmg_map:
            cmg_map[cid] = CMGCut(cmg_id=cid)
        col_key = (cid, gap.col_group)
        col_counters[col_key] = col_counters.get(col_key, -1) + 1
        meas = YCDMeasurement(
            cmg_id=cid,
            col_id=gap.col_group,
            upper_blob=gap.upper,
            lower_blob=gap.lower,
            cd_px=gap.cd_px,
            cd_nm=gap.cd_px * nm_per_pixel,
        )
        cmg_map[cid].measurements.append(meas)

    # ── Step 5: flag MIN / MAX per CMG cut ───────────────────────────────────
    cuts = sorted(cmg_map.values(), key=lambda c: c.cmg_id)
    for cut in cuts:
        if len(cut.measurements) < 2:
            continue
        vals = [m.cd_nm for m in cut.measurements]
        min_val, max_val = min(vals), max(vals)
        for m in cut.measurements:
            if m.cd_nm == min_val:
                m.flag = "MIN"
            elif m.cd_nm == max_val:
                m.flag = "MAX"

    return cuts
