"""Backward-compatibility helpers for Phase A migration.

Converts new MeasurementRecord objects to the legacy dict/dataclass
formats consumed by BatchReviewDialog, _common.py, and exporters.
"""
from __future__ import annotations

from collections import defaultdict

from .core.models import MeasurementRecord  # noqa: F401


def serialise_cuts_from_records(records: list[MeasurementRecord]) -> list[dict]:
    """Convert MeasurementRecord list → legacy cuts dict format.

    Output schema (same as batch_dialog._serialise_cuts):
    [
      {
        "cmg_id": int,
        "measurements": [
          {
            "cmg_id": int,
            "col_id": int,
            "y_cd_px": float,
            "y_cd_nm": float,
            "flag": str,
            "axis": str,
            "state_name": str,
            "upper_bbox": (x0, y0, x1, y1),
            "lower_bbox": (x0, y0, x1, y1),
          }
        ]
      }
    ]
    """
    cut_map: dict[int, list[dict]] = defaultdict(list)
    for r in records:
        upper_bbox = r.extra_metrics.get("upper_bbox", (0, 0, 0, 0))
        lower_bbox = r.extra_metrics.get("lower_bbox", (0, 0, 0, 0))
        cut_map[r.cmg_id].append({
            "cmg_id": r.cmg_id,
            "col_id": r.col_id,
            "y_cd_px": float(r.raw_px),
            "y_cd_nm": float(r.calibrated_nm),
            "flag": r.flag,
            "axis": r.axis,
            "state_name": r.state_name,
            "upper_bbox": tuple(int(v) for v in upper_bbox),
            "lower_bbox": tuple(int(v) for v in lower_bbox),
        })
    return [
        {"cmg_id": cid, "measurements": meas}
        for cid, meas in sorted(cut_map.items())
    ]


def records_to_legacy_cuts(records: list[MeasurementRecord]) -> list:
    """Convert MeasurementRecord list → CMGCut dataclass list.

    Used by MeasureWorkspace / ReviewWorkspace to feed ResultsPanel.show_results(),
    which still expects list[CMGCut].
    """
    from .core.cmg_analyzer import CMGCut, YCDMeasurement
    from .core.mg_detector import Blob

    cut_map: dict[int, list[YCDMeasurement]] = defaultdict(list)
    for r in records:
        upper_b = r.extra_metrics.get("upper_bbox", (r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[1] + 1))
        lower_b = r.extra_metrics.get("lower_bbox", (r.bbox[0], r.bbox[3] - 1, r.bbox[2], r.bbox[3]))

        def _make_blob(bb: tuple) -> Blob:
            x0, y0, x1, y1 = int(bb[0]), int(bb[1]), int(bb[2]), int(bb[3])
            return Blob(
                label=0,
                x0=x0, y0=y0, x1=x1, y1=y1,
                area=max(1, (x1 - x0) * (y1 - y0)),
                cx=float((x0 + x1) / 2),
                cy=float((y0 + y1) / 2),
            )

        upper_edge = r.extra_metrics.get("upper_edge_refined")
        lower_edge = r.extra_metrics.get("lower_edge_refined")
        refine_used = r.extra_metrics.get("refine_used", False)

        m = YCDMeasurement(
            cmg_id=r.cmg_id,
            col_id=r.col_id,
            upper_blob=_make_blob(upper_b),
            lower_blob=_make_blob(lower_b),
            cd_px=float(r.raw_px),
            cd_nm=float(r.calibrated_nm),
            flag=r.flag,
            axis=r.axis,
            state_name=r.state_name,
            structure_name=getattr(r, "structure_name", ""),
            y_upper_edge=float(upper_edge) if refine_used and upper_edge is not None else None,
            y_lower_edge=float(lower_edge) if refine_used and lower_edge is not None else None,
        )
        # Restore _refine_meta so Detail CD view can draw individual sample lines
        _refine_keys = (
            "sample_xs", "upper_sample_ys", "lower_sample_ys",
            "individual_cds_nm", "aggregate_method", "winning_sample_x",
        )
        _meta = {k: r.extra_metrics[k] for k in _refine_keys if k in r.extra_metrics}
        if _meta:
            m._refine_meta = _meta
        cut_map[r.cmg_id].append(m)

    return [
        CMGCut(cmg_id=cid, measurements=meas)
        for cid, meas in sorted(cut_map.items())
    ]
