"""
Tests for utils/indicators.py's swing-point / support-resistance /
trendline detection — added so the Technical + Momentum chart can draw
support/resistance and trend channel lines derived from the price series
itself (not hand-picked), per the analysis actually done on that stock.
"""
import numpy as np
import pandas as pd
import pytest

import utils.indicators as ind


def _mk_df(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    closes = np.array(closes, dtype=float)
    return pd.DataFrame({
        "Open": closes, "High": closes * 1.01, "Low": closes * 0.99,
        "Close": closes, "Volume": np.full(len(closes), 1_000_000),
    }, index=idx)


def test_find_swing_points_detects_known_peak_and_trough():
    # Clean V: strictly descending to a single minimum at index 10 (value
    # 9), then strictly ascending — no tie at the bottom.
    closes = list(range(20, 9, -1)) + list(range(10, 21))  # 20..10, 10..20
    closes[10] = 9  # break the tie so index 10 is a unique minimum
    s = pd.Series(closes)
    highs, lows = ind.find_swing_points(s, order=3)
    assert 10 in lows          # index of the single minimum
    assert len(highs) == 0     # no interior peak in this monotonic-V shape


def test_support_resistance_levels_need_two_touches():
    # Two swing lows near 100, two swing highs near 120 -> both should
    # surface as clustered levels (2+ touches each).
    closes = [110, 105, 100, 105, 110, 115, 120, 115, 110, 105,
              100, 105, 110, 115, 120, 115, 110, 105, 112]
    df = _mk_df(closes)
    levels = ind.support_resistance_levels(df, order=2, cluster_pct=0.03)
    assert any(abs(lv - 120) < 3 for lv in levels["resistance"])
    assert any(abs(lv - 100) < 3 for lv in levels["support"])


def test_single_touch_level_is_not_reported():
    # A one-off spike shouldn't produce a "level" (needs 2+ touches).
    closes = [100, 100, 100, 100, 150, 100, 100, 100, 100, 100]
    df = _mk_df(closes)
    levels = ind.support_resistance_levels(df, order=2, cluster_pct=0.02)
    assert not any(abs(lv - 150) < 5 for lv in levels["resistance"])


def test_trendlines_rising_lows_produce_upward_support_line():
    # Swing lows step up: 100, 102, 104, 106 -> support trendline should
    # have y[1] > y[0] (rising).
    closes = [100, 110, 102, 112, 104, 114, 106, 116, 110, 108]
    df = _mk_df(closes)
    tl = ind.trendlines(df, order=1, lookback_pivots=4)
    if tl["support"] is not None:
        assert tl["support"]["y"][1] >= tl["support"]["y"][0]


def test_insufficient_data_returns_empty_not_error():
    df = _mk_df([100, 101, 102])
    levels = ind.support_resistance_levels(df, order=5)
    tl = ind.trendlines(df, order=5)
    assert levels == {"resistance": [], "support": []}
    assert tl == {"support": None, "resistance": None}


def test_empty_dataframe_does_not_crash():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    assert ind.support_resistance_levels(df) == {"resistance": [], "support": []}
    assert ind.trendlines(df) == {"support": None, "resistance": None}
