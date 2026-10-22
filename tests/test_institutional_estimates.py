"""
Tests for modules/institutional.py's get_eps_revenue_estimates() — the
Yahoo-Finance-sourced (yfinance) forward EPS/revenue consensus added to
fill the gap where Finnhub's and FMP's price-target/estimates endpoints
are premium-gated on this app's free-tier keys (verified live: both
return 402/403 even for a mega-cap). yfinance's own consensus tables have
no such gate and cover thinly-followed small-caps too.
"""
import pandas as pd
import pytest

import modules.institutional as inst


class _FakeTicker:
    def __init__(self, eps_trend=None, earnings_estimate=None, revenue_estimate=None):
        self.eps_trend = eps_trend
        self.earnings_estimate = earnings_estimate
        self.revenue_estimate = revenue_estimate


def test_relabels_periods_and_computes_revision(monkeypatch):
    eps_est = pd.DataFrame(
        {"avg": [1.0, 1.5, 6.0, 9.0], "low": [0.9, 1.4, 5.5, 8.0],
         "high": [1.1, 1.6, 6.5, 10.0], "numberOfAnalysts": [10, 9, 12, 12],
         "growth": [0.1, 0.2, 0.3, 0.4]},
        index=["0q", "+1q", "0y", "+1y"],
    )
    rev_est = pd.DataFrame(
        {"avg": [1e6, 2e6, 5e6, 8e6], "low": [9e5, 1.9e6, 4.5e6, 7e6],
         "high": [1.1e6, 2.1e6, 5.5e6, 9e6], "numberOfAnalysts": [10, 9, 12, 12],
         "growth": [0.1, 0.2, 0.3, 0.4]},
        index=["0q", "+1q", "0y", "+1y"],
    )
    eps_trend = pd.DataFrame(
        {"current": [1.0, 1.5, 6.0, 9.0], "90daysAgo": [0.9, 1.4, 5.5, 8.0]},
        index=["0q", "+1q", "0y", "+1y"],
    )
    monkeypatch.setattr(inst.yf, "Ticker",
                        lambda symbol: _FakeTicker(eps_trend, eps_est, rev_est))
    inst.get_eps_revenue_estimates.clear()
    result = inst.get_eps_revenue_estimates("TEST")

    assert result["error"] is None
    assert list(result["eps"].index) == ["This Quarter", "Next Quarter", "This Year", "Next Year"]
    assert list(result["revenue"].index) == ["This Quarter", "Next Quarter", "This Year", "Next Year"]
    # (6.0/5.5 - 1)*100 = 9.09..., (9.0/8.0 - 1)*100 = 12.5 -> avg 10.8
    assert result["eps_revision_pct"] == pytest.approx(10.8, abs=0.1)


def test_missing_data_returns_none_not_error(monkeypatch):
    monkeypatch.setattr(inst.yf, "Ticker",
                        lambda symbol: _FakeTicker(None, pd.DataFrame(), pd.DataFrame()))
    inst.get_eps_revenue_estimates.clear()
    result = inst.get_eps_revenue_estimates("TEST")
    assert result["error"] is None
    assert result["eps"] is None
    assert result["revenue"] is None
    assert result["eps_revision_pct"] is None


def test_ticker_exception_is_caught(monkeypatch):
    def _boom(symbol):
        raise RuntimeError("network down")
    monkeypatch.setattr(inst.yf, "Ticker", _boom)
    inst.get_eps_revenue_estimates.clear()
    result = inst.get_eps_revenue_estimates("TEST")
    assert result["error"] == "network down"
    assert result["eps"] is None
