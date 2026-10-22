"""
Tests for the pure, price-only pieces of modules/backtester.py — signal
generation and segment metrics — using synthetic price series so these run
without network access. run_backtest()/run_backtest_walkforward() themselves
hit yfinance and are exercised via the app UI instead of here.
"""
import numpy as np
import pandas as pd
import pytest

from modules.backtester import (
    _sma_signals, _technical_consensus_signals, _signal_for, _segment_metrics,
    STRATEGIES,
)


def _make_close(n=400, trend=0.0006, vol=0.01, seed=1) -> pd.Series:
    rng = np.random.default_rng(seed)
    rets = rng.normal(trend, vol, n)
    prices = 100 * np.cumprod(1 + rets)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.Series(prices, index=idx)


def test_technical_consensus_signal_values_are_valid():
    close = _make_close()
    sig = _technical_consensus_signals(close)
    assert set(sig.unique()).issubset({-1, 0, 1})
    assert len(sig) == len(close)


def test_technical_consensus_too_short_history_returns_flat():
    close = _make_close(n=100)
    sig = _technical_consensus_signals(close)
    assert (sig == 0).all()


def test_uptrend_produces_more_long_than_short_consensus_signals():
    close = _make_close(trend=0.003, vol=0.008)   # strong, low-noise uptrend
    sig = _technical_consensus_signals(close)
    assert (sig == 1).sum() > (sig == -1).sum()


def test_signal_for_dispatches_to_same_result_as_direct_call():
    close = _make_close()
    p = STRATEGIES["SMA Crossover"]
    direct = _sma_signals(close, p["fast"], p["slow"])
    via_dispatch = _signal_for("SMA Crossover", close, p)
    pd.testing.assert_series_equal(direct, via_dispatch)


def test_signal_for_unknown_strategy_raises():
    with pytest.raises(ValueError):
        _signal_for("Not A Real Strategy", _make_close(), {})


def test_segment_metrics_zero_signal_gives_zero_return():
    close = _make_close()
    flat_signal = pd.Series(0, index=close.index)
    m = _segment_metrics(close, flat_signal, close.index, capital=10_000)
    assert m["total_return"] == 0.0
    assert m["sharpe"] == 0.0


def test_segment_metrics_always_long_matches_buy_and_hold():
    close = _make_close()
    always_long = pd.Series(1, index=close.index)
    m = _segment_metrics(close, always_long, close.index, capital=10_000)
    # shift(1) means day-1 return is excluded from both strategy and the
    # benchmark reference here uses full-period return — allow a loose bound
    assert abs(m["total_return"] - m["benchmark_return"]) < 0.05
