"""
Tests for modules/risk_metrics.py's compute_risk(), in particular the
Calmar Ratio and Ulcer Index additions. Monkeypatches _daily_returns so no
network access is needed; expected values are independently recomputed in
this file (not copy-pasted from the implementation) to actually catch
formula drift — e.g. the earlier real bug where sqrt/mean were applied in
the wrong order (mean-absolute-drawdown instead of RMS drawdown).
"""
import numpy as np
import pandas as pd
import pytest

import modules.risk_metrics as rm


@pytest.fixture
def synthetic_returns(monkeypatch):
    rng = np.random.default_rng(7)
    n = 80
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    a = pd.Series(rng.normal(0.001, 0.02, n), index=idx)
    b = pd.Series(rng.normal(0.0005, 0.015, n), index=idx)
    spy = pd.Series(rng.normal(0.0004, 0.01, n), index=idx)

    def fake_daily_returns(symbol):
        return {"A": a, "B": b, "SPY": spy}.get(symbol, pd.Series(dtype=float))

    monkeypatch.setattr(rm, "_daily_returns", fake_daily_returns)
    return a, b, spy


def _expected_calmar_and_ulcer(port_rets: np.ndarray) -> tuple[float, float]:
    """Independent reference implementation — deliberately not sharing code
    with modules/risk_metrics.py, so a bug in one is unlikely to also be in
    the other."""
    equity = np.cumprod(1 + port_rets)
    running_peak = np.maximum.accumulate(equity)
    drawdown_pct = (equity - running_peak) / running_peak * 100
    max_dd_pct = drawdown_pct.min()
    ann_ret_pct = port_rets.mean() * 252 * 100
    calmar = ann_ret_pct / abs(max_dd_pct)
    ulcer = np.sqrt(np.mean(drawdown_pct ** 2))
    return calmar, ulcer


def test_calmar_and_ulcer_match_independent_reference(synthetic_returns):
    a, b, _spy = synthetic_returns
    result = rm.compute_risk(["A", "B"], [0.5, 0.5])
    assert "error" not in result

    port_rets = (0.5 * a.values + 0.5 * b.values)
    exp_calmar, exp_ulcer = _expected_calmar_and_ulcer(port_rets)

    assert result["calmar_ratio"] == pytest.approx(exp_calmar, abs=0.02)
    assert result["ulcer_index"] == pytest.approx(exp_ulcer, abs=0.05)


def test_ulcer_index_is_never_negative(synthetic_returns):
    result = rm.compute_risk(["A", "B"], [0.5, 0.5])
    assert result["ulcer_index"] >= 0


def test_ulcer_index_near_zero_for_monotonic_uptrend(monkeypatch):
    # A pure uptrend has ~no drawdown -> Ulcer Index must be ~0, not an
    # exploded value from dividing by floating-point noise near zero.
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    up = pd.Series(0.01, index=idx)   # constant positive daily return, never down
    spy = pd.Series(0.0005, index=idx)
    monkeypatch.setattr(rm, "_daily_returns",
                        lambda s: {"A": up, "B": up, "SPY": spy}.get(s, pd.Series(dtype=float)))
    result = rm.compute_risk(["A", "B"], [0.5, 0.5])
    assert "error" not in result
    assert result["ulcer_index"] == pytest.approx(0.0, abs=1e-6)
    assert result["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-6)
    assert abs(result["sharpe_approx"]) < 1e6   # must not explode from near-zero vol


def test_insufficient_symbols_returns_error(monkeypatch):
    idx = pd.date_range("2024-01-01", periods=40, freq="B")
    monkeypatch.setattr(rm, "_daily_returns",
                        lambda s: pd.Series(0.001, index=idx) if s == "A" else pd.Series(dtype=float))
    result = rm.compute_risk(["A"], [1.0])
    assert "error" in result
