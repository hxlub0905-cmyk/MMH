"""Unit tests for the CMG Y-CD analysis algorithm."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.core.mg_detector import Blob
from src.core.cmg_analyzer import analyze, _x_overlap_ratio


def _blob(label, x0, y0, x1, y1):
    return Blob(label=label, x0=x0, y0=y0, x1=x1, y1=y1,
                area=(x1-x0)*(y1-y0), cx=(x0+x1)/2, cy=(y0+y1)/2)


class TestXOverlapRatio:
    def test_full_overlap(self):
        a = _blob(0, 10, 0, 20, 10)
        b = _blob(1, 10, 20, 20, 30)
        assert _x_overlap_ratio(a, b) == pytest.approx(1.0)

    def test_no_overlap(self):
        a = _blob(0, 0, 0, 10, 10)
        b = _blob(1, 20, 0, 30, 10)
        assert _x_overlap_ratio(a, b) == 0.0

    def test_partial_overlap(self):
        a = _blob(0, 0, 0, 20, 10)   # width=20
        b = _blob(1, 10, 0, 30, 10)  # width=20, overlap=10
        assert _x_overlap_ratio(a, b) == pytest.approx(0.5)


class TestAnalyze:
    def test_empty(self):
        assert analyze([], nm_per_pixel=1.0) == []

    def test_single_blob(self):
        blobs = [_blob(0, 0, 0, 50, 100)]
        assert analyze(blobs, nm_per_pixel=1.0) == []

    def test_single_cmg_two_columns(self):
        """2 columns, 1 CMG cut each → 1 CMG cut with 2 measurements."""
        blobs = [
            _blob(0, 0,   0, 20, 40),   # col0 upper
            _blob(1, 0,  50, 20, 90),   # col0 lower  gap=10px
            _blob(2, 30,  0, 50, 40),   # col1 upper
            _blob(3, 30, 50, 50, 90),   # col1 lower  gap=10px
        ]
        cuts = analyze(blobs, nm_per_pixel=2.0)
        assert len(cuts) == 1
        cut = cuts[0]
        assert len(cut.measurements) == 2
        for m in cut.measurements:
            assert m.cd_px == pytest.approx(10.0)
            assert m.cd_nm == pytest.approx(20.0)

    def test_min_max_flagging(self):
        """top-3 MIN and top-3 MAX flagged per CMGCut (6-column scenario, no overlap)."""
        # 6 columns → gaps 10,11,12,13,14,15 px; bottom-3 → MIN, top-3 → MAX
        blobs = []
        gaps = [10, 11, 12, 13, 14, 15]
        for i, g in enumerate(gaps):
            x0, x1 = i * 30, i * 30 + 20
            blobs.append(_blob(i * 2,     x0,  0,  x1,  40))   # upper
            blobs.append(_blob(i * 2 + 1, x0, 40 + g, x1, 40 + g + 40))  # lower
        cuts = analyze(blobs, nm_per_pixel=1.0)
        assert len(cuts) == 1
        by_gap = {m.cd_px: m.flag for m in cuts[0].measurements}
        for g in gaps[:3]:
            assert by_gap[float(g)] == "MIN", f"gap={g} expected MIN"
        for g in gaps[3:]:
            assert by_gap[float(g)] == "MAX", f"gap={g} expected MAX"

    def test_min_max_flagging_two_meas(self):
        """With only 2 measurements both unique values fall in bottom-3 → both MIN."""
        blobs = [
            _blob(0, 0,   0, 20, 40),
            _blob(1, 0,  50, 20, 90),   # gap=10px
            _blob(2, 30,  0, 50, 40),
            _blob(3, 30, 55, 50, 90),   # gap=15px
        ]
        cuts = analyze(blobs, nm_per_pixel=1.0)
        assert len(cuts) == 1
        flags = [m.flag for m in cuts[0].measurements]
        assert all(f == "MIN" for f in flags), "2-measurement cut: both values → MIN"

    def test_two_cmg_cuts(self):
        """Single column with 3 blobs → 2 CMG cuts."""
        blobs = [
            _blob(0, 0,   0, 20,  30),   # upper
            _blob(1, 0,  40, 20,  70),   # middle  gap1=10px
            _blob(2, 0, 100, 20, 130),   # lower   gap2=30px
        ]
        cuts = analyze(blobs, nm_per_pixel=1.0)
        assert len(cuts) == 2
        y_cds = sorted(m.cd_px for cut in cuts for m in cut.measurements)
        assert y_cds == pytest.approx([10.0, 30.0])

    def test_nm_conversion(self):
        blobs = [
            _blob(0, 0,   0, 20, 40),
            _blob(1, 0,  50, 20, 90),  # gap=10px
        ]
        cuts = analyze(blobs, nm_per_pixel=5.0)
        assert cuts[0].measurements[0].cd_nm == pytest.approx(50.0)

    def test_overlapping_blobs_skipped(self):
        """Blobs that overlap in Y should not produce negative Y-CD."""
        blobs = [
            _blob(0, 0, 0, 20, 50),
            _blob(1, 0, 40, 20, 90),   # overlaps first blob in Y
        ]
        cuts = analyze(blobs, nm_per_pixel=1.0)
        # May return a cut if gap > 0 after sorting, or empty — just must not crash
        for cut in cuts:
            for m in cut.measurements:
                assert m.cd_px > 0
