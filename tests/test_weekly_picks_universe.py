"""
Tests for the Weekly Picks universe/ETF/quality-dip additions — the fixed
~223-ticker hand-curated universe was a closed circle; these add a live
S&P 500 union, a theme-ETF scan path, and a "quality on sale" carve-out
for stocks the strict swing filter would otherwise reject outright.
"""
import pandas as pd
import pytest

import modules.weekly_picks as wp


def test_full_stock_universe_unions_and_dedupes(monkeypatch):
    monkeypatch.setattr(wp, "_sp500_constituents", lambda: ["AAPL", "ZZZZ", "MSFT"])
    universe = wp._full_stock_universe()
    # WEEKLY_UNIVERSE already contains AAPL/MSFT — must not duplicate them,
    # and the genuinely new symbol (ZZZZ) must be appended.
    assert universe.count("AAPL") == 1
    assert universe.count("MSFT") == 1
    assert "ZZZZ" in universe
    assert len(universe) == len(set(universe))


def test_sp500_constituents_returns_empty_list_on_failure(monkeypatch):
    import urllib.request
    def _boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    wp._sp500_constituents.clear()
    assert wp._sp500_constituents() == []


def test_scan_etfs_filters_by_min_score(monkeypatch):
    fake_scores = {
        "SOXX": {"symbol": "SOXX", "name": "iShares Semi ETF", "price": 200.0,
                 "strength_score": 8.0, "grade": "Strong", "r1m": 5.0, "r3m": 10.0,
                 "rs1m": 2.0, "above_50": True, "above_200": True,
                 "breakout_score": 7.0, "breakout_setup": "NEW HIGH"},
        "WEAK": {"symbol": "WEAK", "name": "Weak ETF", "price": 50.0,
                 "strength_score": 3.0, "grade": "Weak", "r1m": -5.0, "r3m": -8.0,
                 "rs1m": -2.0, "above_50": False, "above_200": False,
                 "breakout_score": 4.0, "breakout_setup": ""},
    }
    monkeypatch.setattr(wp, "_score_etf", lambda sym: fake_scores.get(sym, {}))
    qualified = wp._scan_etfs(["SOXX", "WEAK", "MISSING"], min_score=6.5)
    syms = [q["symbol"] for q in qualified]
    assert syms == ["SOXX"]
    assert qualified[0]["category"] == "ETF_THEME"


def test_check_quality_dip_only_fires_on_quality_on_sale(monkeypatch):
    def fake_analyze(symbol):
        return {"QUAL": {"quadrant": "QUALITY ON SALE", "quality": 8.0,
                         "condition": 2.0, "guidance": "buy the dip"},
                "LEAD": {"quadrant": "LEADER"},
                "KNIFE": {"quadrant": "FALLING KNIFE"}}.get(symbol, {"error": "no data"})
    monkeypatch.setattr(wp.opportunity, "analyze", fake_analyze)
    assert wp._check_quality_dip("QUAL") is not None
    assert wp._check_quality_dip("QUAL")["quadrant"] == "QUALITY ON SALE"
    assert wp._check_quality_dip("LEAD") is None
    assert wp._check_quality_dip("KNIFE") is None
    assert wp._check_quality_dip("MISSING") is None


def test_etf_thesis_is_rule_based_and_shape_matches_expected_keys():
    etf = {"symbol": "SOXX", "weekly_score": 8.0, "grade": "Strong",
           "r1m": 5.0, "r3m": 10.0, "rs1m": 2.0, "above_200": True,
           "breakout_setup": "NEW HIGH"}
    thesis = wp._etf_thesis(etf)
    for key in ("action", "conviction", "quality_flag", "headline", "why_buy",
                "when_buy", "target_zone", "stop_loss", "key_risk"):
        assert key in thesis
    assert thesis["action"] == "BUY"   # score >= 7.5


def test_etf_thesis_watch_below_threshold():
    etf = {"symbol": "MEH", "weekly_score": 6.0, "grade": "Neutral",
           "r1m": 1.0, "r3m": 1.0, "rs1m": 0.0, "above_200": False,
           "breakout_setup": ""}
    thesis = wp._etf_thesis(etf)
    assert thesis["action"] == "WATCH"
