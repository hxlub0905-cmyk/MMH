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


@dataclass
class YCDMeasurement:
    cmg_id: int
    col_id: int
    upper_blob: Blob
    lower_blob: Blob
    y_cd_px: float
    y_cd_nm: float
    flag: str = ""   # "MIN", "MAX", or ""
    axis: str = "Y"
    state_name: str = ""


@dataclass
class CMGCut:
    cmg_id: int
    measurements: list[YCDMeasurement] = field(default_factory=list)

    @property
    def y_cd_values(self) -> list[float]:
        return [m.y_cd_nm for m in self.measurements]

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
) -> list[CMGCut]:
    """Return CMG cuts with per-column Y-CD measurements."""
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
        y_cd_px: float
        mid_y: float           # used for clustering across columns

    gaps: list[Gap] = []
    for col_idx, (root, indices) in enumerate(columns.items()):
        sorted_blobs = sorted([blobs[i] for i in indices], key=lambda b: b.y0)
        for k in range(len(sorted_blobs) - 1):
            upper = sorted_blobs[k]
            lower = sorted_blobs[k + 1]
            upper_edge = upper.cy + (upper.height / 2.0)
            lower_edge = lower.cy - (lower.height / 2.0)
            y_cd_px = lower_edge - upper_edge
            if y_cd_px <= 0:
                continue   # blobs overlap — skip
            mid_y = (upper_edge + lower_edge) / 2.0
            gaps.append(
                Gap(
                    col_group=col_idx,
                    col_index=k,
                    upper=upper,
                    lower=lower,
                    y_cd_px=y_cd_px,
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
            y_cd_px=gap.y_cd_px,
            y_cd_nm=gap.y_cd_px * nm_per_pixel,
        )
        cmg_map[cid].measurements.append(meas)

    # ── Step 5: flag MIN / MAX per CMG cut ───────────────────────────────────
    cuts = sorted(cmg_map.values(), key=lambda c: c.cmg_id)
    for cut in cuts:
        if len(cut.measurements) < 2:
            continue
        vals = [m.y_cd_nm for m in cut.measurements]
        min_val, max_val = min(vals), max(vals)
        for m in cut.measurements:
            if m.y_cd_nm == min_val:
                m.flag = "MIN"
            elif m.y_cd_nm == max_val:
                m.flag = "MAX"

    return cuts
