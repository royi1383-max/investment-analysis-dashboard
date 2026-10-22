"""
Tests for modules/portfolio_optimizer.py using synthetic return data (no
network calls) via monkeypatching _returns_matrix, so these run fast and
deterministically in CI.
"""
import numpy as np
import pandas as pd
import pytest

import modules.portfolio_optimizer as po


@pytest.fixture
def synthetic_returns(monkeypatch):
    rng = np.random.default_rng(0)
    n = 250
    df = pd.DataFrame({
        "A": rng.normal(0.0008, 0.015, n),
        "B": rng.normal(0.0005, 0.010, n),
        "C": rng.normal(0.0003, 0.008, n),
        "D": rng.normal(0.0006, 0.020, n),
    })
    monkeypatch.setattr(po, "_returns_matrix", lambda symbols, period="2y": df)
    return df


def test_efficient_frontier_weights_sum_to_one(synthetic_returns):
    ef = po.efficient_frontier(("A", "B", "C", "D"))
    assert ef["error"] is None
    for portfolio in (ef["max_sharpe"], ef["min_vol"]):
        total = sum(portfolio["weights"].values())
        assert abs(total - 100.0) < 0.5   # weights reported as percentages


def test_efficient_frontier_weights_long_only(synthetic_returns):
    ef = po.efficient_frontier(("A", "B", "C", "D"))
    for portfolio in (ef["max_sharpe"], ef["min_vol"]):
        assert all(w >= -1e-6 for w in portfolio["weights"].values())


def test_min_vol_has_lower_or_equal_volatility_than_max_sharpe(synthetic_returns):
    ef = po.efficient_frontier(("A", "B", "C", "D"))
    assert ef["min_vol"]["vol_pct"] <= ef["max_sharpe"]["vol_pct"] + 1e-6


def test_efficient_frontier_requires_two_symbols():
    result = po.efficient_frontier(("SOLO",))
    assert result["error"] is not None


def test_pca_explained_variance_sums_near_total_for_full_components(synthetic_returns):
    pca = po.pca_factors(("A", "B", "C", "D"), n_components=4)
    assert pca["error"] is None
    assert sum(pca["explained_pct"]) == pytest.approx(100.0, abs=1.0)


def test_pca_requires_three_symbols():
    result = po.pca_factors(("A", "B"))
    assert result["error"] is not None


def test_pca_market_factor_matches_first_component(synthetic_returns):
    pca = po.pca_factors(("A", "B", "C", "D"))
    assert pca["market_factor_pct"] == pca["explained_pct"][0]
