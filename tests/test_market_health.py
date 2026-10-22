"""
Tests for modules/market_health.py's new pieces: the generalized YoY flag
(replacing a hardcoded CPIAUCSL check so Core CPI reuses the same code
path), the 10Y-yield yfinance fallback, and the narrative snapshot builder
that feeds the dynamic Claude money-flow read.
"""
import json

import pandas as pd
import pytest

import modules.market_health as mh


def test_core_cpi_and_cpi_both_flagged_yoy():
    assert mh.INDICATORS["cpi"]["yoy"] is True
    assert mh.INDICATORS["core_cpi"]["yoy"] is True
    assert mh.INDICATORS["core_cpi"]["series"] == "CPILFESL"


def test_yield_10y_indicator_registered_and_not_double_counted():
    assert "yield_10y" in mh.INDICATORS
    assert "core_cpi" in mh.INDICATORS
    # Informational only — must not silently get folded into the composite
    # weighting (that would double-count inflation/rates against the
    # existing CPI and yield_curve weights).
    assert "yield_10y" not in mh.WEIGHTS
    assert "core_cpi" not in mh.WEIGHTS


def test_fetch_fred_yoy_flag_computes_display_value(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, obs):
            self._obs = obs
        def raise_for_status(self):
            pass
        def json(self):
            return {"observations": self._obs}

    def fake_get(url, params, timeout):
        calls["n"] += 1
        if params["limit"] == 5:
            return FakeResp([{"value": "310.0"}])
        # 15 monthly obs, oldest last; index 12 = "a year ago"
        obs = [{"value": str(310.0 - i * 0.1)} for i in range(15)]
        return FakeResp(obs)

    monkeypatch.setattr(mh.requests, "get", fake_get)
    monkeypatch.setattr(mh, "FRED_API_KEY", "fake-key")
    result = mh._fetch_fred(mh.INDICATORS["core_cpi"])
    assert result["value"] == 310.0
    assert "display_value" in result
    assert result["display_value"] > 0   # 310.0 vs 310.0-1.2 -> positive YoY%


def test_yield_10y_yf_fallback(monkeypatch):
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    fake_hist = pd.DataFrame({"Close": [45.0, 45.5, 46.0, 46.2, 46.5]}, index=idx)

    class FakeTicker:
        def history(self, period, interval):
            return fake_hist

    monkeypatch.setattr(mh.yf, "Ticker", lambda sym: FakeTicker())
    result = mh._fetch_yield_10y_yf()
    assert result["value"] == pytest.approx(4.65)
    assert result["approx"] is True


def test_narrative_snapshot_is_stable_json_for_same_inputs():
    data = {"vix": {"value": 17.0}}
    composite = {
        "score": 68.5, "label": "Cautiously Positive",
        "signals": {"vix": {"display": "17.0", "label": "Normal", "color": "green"}},
    }
    snap1 = mh._narrative_snapshot(data, composite)
    snap2 = mh._narrative_snapshot(data, composite)
    assert snap1 == snap2
    parsed = json.loads(snap1)
    assert parsed["composite_score"] == 68.5
    assert parsed["indicators"][0]["label"] == mh.INDICATORS["vix"]["label"]


def test_macro_narrative_without_api_key_returns_graceful_error(monkeypatch):
    monkeypatch.setattr(mh, "ANTHROPIC_API_KEY", "")
    mh.macro_narrative.clear()
    result = mh.macro_narrative(json.dumps({"composite_score": 50, "composite_label": "x", "indicators": []}))
    assert result["error"] is not None
