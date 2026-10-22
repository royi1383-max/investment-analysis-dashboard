"""
Tests for modules/options_pricing.py against known, hard mathematical
invariants (put-call parity, binomial->BSM convergence, American >= European,
implied-vol round-trip) rather than hardcoded magic numbers, so the tests
stay valid even if pricing parameters change.
"""
import numpy as np

from modules.options_pricing import (
    bsm_price, bsm_greeks, binomial_price, monte_carlo_price, implied_vol,
)

S, K, T, r, sigma = 100.0, 100.0, 0.5, 0.045, 0.25


def test_put_call_parity_holds_for_bsm():
    call = bsm_price(S, K, T, r, sigma, "call")
    put = bsm_price(S, K, T, r, sigma, "put")
    # C - P = S - K*exp(-rT), the textbook no-arbitrage identity
    assert abs((call - put) - (S - K * np.exp(-r * T))) < 1e-6


def test_binomial_converges_to_bsm_for_european():
    bsm = bsm_price(S, K, T, r, sigma, "call")
    binom = binomial_price(S, K, T, r, sigma, steps=500, kind="call", american=False)
    assert abs(bsm - binom) < 0.05


def test_american_put_worth_at_least_as_much_as_european_put():
    euro = binomial_price(S, K, T, r, sigma, steps=200, kind="put", american=False)
    amer = binomial_price(S, K, T, r, sigma, steps=200, kind="put", american=True)
    assert amer >= euro - 1e-9


def test_deep_itm_call_price_at_least_intrinsic():
    price = bsm_price(150, 100, T, r, sigma, "call")
    assert price >= 50 - 1e-6


def test_monte_carlo_price_within_a_few_std_errors_of_bsm():
    bsm = bsm_price(S, K, T, r, sigma, "call")
    mc = monte_carlo_price(S, K, T, r, sigma, "call", n_paths=100_000)
    assert abs(mc["price"] - bsm) < 4 * mc["std_error"]


def test_implied_vol_recovers_exact_input_sigma():
    price = bsm_price(S, K, T, r, sigma, "call")
    recovered = implied_vol(price, S, K, T, r, "call")
    assert recovered is not None
    assert abs(recovered - sigma) < 1e-4


def test_implied_vol_rejects_price_below_intrinsic():
    # A quoted price below intrinsic value is an arbitrage violation — should
    # return None rather than a bogus/negative implied vol.
    deep_itm_intrinsic = S - K + 10   # way in the money, understate the price
    assert implied_vol(1.0, 150, 100, T, r, "call") is None


def test_greeks_delta_bounded_and_sign_correct_by_type():
    g_call = bsm_greeks(S, K, T, r, sigma, "call")
    g_put = bsm_greeks(S, K, T, r, sigma, "put")
    assert 0 <= g_call["delta"] <= 1
    assert -1 <= g_put["delta"] <= 0
    assert g_call["gamma"] > 0 and g_put["gamma"] > 0   # gamma always positive, same for both
    assert g_call["vega"] > 0 and g_put["vega"] > 0     # vega always positive


def test_expired_or_degenerate_inputs_return_intrinsic_not_crash():
    assert bsm_price(S, K, 0, r, sigma, "call") == max(0.0, S - K)
    assert bsm_price(S, K, T, r, 0, "put") == max(0.0, K - S)
