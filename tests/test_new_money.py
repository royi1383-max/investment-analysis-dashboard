"""New Money Allocator — pure allocation logic (no network)."""
import pytest

from modules import new_money as nm


def _rot(etf, label, cat="Broad Sectors", score=7.5, above_200=True, mom="↑",
         rs1m=3.0, rs3m=4.0, early=None):
    return {"etf": etf, "label": label, "category": cat, "score": score,
            "above_200": above_200, "momentum_dir": mom, "rs1m": rs1m, "rs3m": rs3m,
            "early_signal": early, "grade": "Strong ✅"}


ROT = [
    _rot("XLK", "Technology", score=8.0, rs1m=5),
    _rot("XLF", "Financials", score=7.0, rs1m=3),
    _rot("XLI", "Industrials", score=6.5, rs1m=2),
    _rot("XLE", "Energy", score=4.0, above_200=False, mom="↓", rs1m=-4),
    _rot("SMH", "Semiconductors", cat="AI & Compute", score=8.5, rs1m=7),
]


def _qos(t, sector="Technology", q=8.0, ready=4, quad="QUALITY ON SALE", dd=-25):
    return {"ticker": t, "name": t, "sector": sector, "quality": q, "readiness": ready,
            "quadrant": quad, "drawdown": dd, "n_support": 1, "n_negative": 0}


def _sum(plan):
    return sum(ln["amount"] for ln in plan["lines"])


def test_regime_bands():
    assert nm.regime_plan(80)["label"].startswith("Healthy")
    assert nm.regime_plan(50)["label"].startswith("Neutral")
    assert nm.regime_plan(10)["label"].startswith("Danger")
    assert nm.regime_plan(None)["label"].startswith("Neutral")
    # Weaker market → less deployed now, more tilt to quality-on-sale
    assert nm.regime_plan(80)["deploy_now_pct"] > nm.regime_plan(10)["deploy_now_pct"]
    assert nm.regime_plan(80)["mix"]["qos"] < nm.regime_plan(10)["mix"]["qos"]


@pytest.mark.parametrize("score", [85, 60, 45, 30, 5])
def test_every_dollar_is_assigned(score):
    plan = nm.allocate(10_000, score, ROT, [_qos("MSFT"), _qos("JPM", "Financial Services")], [])
    assert _sum(plan) == pytest.approx(10_000)


def test_weak_sector_never_bought_and_one_etf_per_sector():
    plan = nm.allocate(10_000, 80, ROT, [], [], {"categories": ["Broad Sectors", "AI & Compute"]})
    tickers = [ln["ticker"] for ln in plan["lines"] if ln["bucket"] == "sectors"]
    assert "XLE" not in tickers
    # SMH and XLK are both Technology exposure — only one of them
    assert not ("SMH" in tickers and "XLK" in tickers)


def test_sector_cap_redirects_to_other_sectors():
    holdings = [{"ticker": "AAPL", "value": 40_000, "sector": "Technology"},
                {"ticker": "VT", "value": 60_000}]
    plan = nm.allocate(10_000, 80, ROT, [_qos("MSFT")], holdings)
    bought = {ln["ticker"] for ln in plan["lines"]}
    assert "XLK" not in bought and "MSFT" not in bought     # tech is 36% > 30% cap
    assert any(s["ticker"] == "XLK" for s in plan["skipped"])
    assert _sum(plan) == pytest.approx(10_000)


def test_unready_qos_goes_to_watchlist_and_reserve():
    plan = nm.allocate(10_000, 30, ROT, [_qos("NKE", "Consumer Cyclical", ready=1)], [])
    assert not any(ln["bucket"] == "qos" for ln in plan["lines"])
    assert [w["ticker"] for w in plan["watchlist"]] == ["NKE"]
    reserve = next(ln for ln in plan["lines"] if ln["bucket"] == "reserve")
    assert reserve["amount"] > 10_000 * (1 - plan["deploy_now_pct"])  # QoS budget parked too


def test_position_cap_limits_starter():
    plan = nm.allocate(100_000, 10, [], [_qos("MSFT")], [])
    msft = next(ln for ln in plan["lines"] if ln["ticker"] == "MSFT")
    assert msft["amount"] <= 0.08 * 100_000 * 0.5 + 1e-6


def test_min_trade_from_commission():
    s = {"commission_usd": 5.0, "max_fee_pct": 0.5}
    assert nm.min_trade_size({**nm.DEFAULT_SETTINGS, **s}) == pytest.approx(1000)
    plan = nm.allocate(3_000, 80, ROT, [_qos("MSFT")], [], s)
    assert all(ln["amount"] >= 1000 - 1e-6 for ln in plan["lines"])
    assert _sum(plan) == pytest.approx(3_000)


def test_israeli_holdings_bucketed():
    exp = nm.holdings_exposure([{"ticker": "", "value": 500, "kind": "Israeli"},
                                {"ticker": "XLK", "value": 500}])
    assert exp["by_key"] == {"ISRAEL": 500, "XLK": 500}


def test_exposure_after_sums_to_100():
    holdings = [{"ticker": "AAPL", "value": 5_000, "sector": "Technology"}]
    plan = nm.allocate(5_000, 60, ROT, [_qos("JPM", "Financial Services")], holdings)
    assert sum(r["after_pct"] for r in plan["exposure"]) == pytest.approx(100)
