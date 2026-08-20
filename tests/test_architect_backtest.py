import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))

study = pytest.importorskip("skew_rr_study")


def test_segment_stats_pairs_signal_and_null_and_clusters_by_date():
    rows = [("2026-01-02", 1, 0), ("2026-01-02", 0, 1),
            ("2026-01-03", 1, 0), ("2026-01-04", 1, 0)]
    out = study.segment_stats(rows, 1.0, 1.0)
    assert out["n"] == 4
    assert out["clusters"] == 3
    assert out["wr"] == 0.75
    assert out["null_wr"] == 0.25
    assert out["edge"] == 0.5


def test_empty_segment_is_data_missing_not_zero_performance():
    out = study.segment_stats([], 1.0, 1.0)
    assert out["n"] == 0
    assert out["wr"] is None
    assert out["edge"] is None
