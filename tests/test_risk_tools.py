"""
Regression tests for modules/risk_tools.py — in particular risk_of_ruin(),
which had a real bug: the even-money (classic) formula was used to drive the
verdict even when win/loss sizes were asymmetric, producing 100% "risk of
ruin" for a setup with clearly positive expectancy. These tests pin the
corrected behavior so it can't silently regress.
"""
from modules.risk_tools import risk_of_ruin, murphy_checklist, MURPHY_CHECKLIST


def test_positive_expectancy_with_asymmetric_payoff_has_low_ruin():
    # win_rate=0.45, payoff=2 (8% win / 4% loss) -> expectancy = 0.45*2-0.55 = +0.35R
    # The even-money formula alone would (wrongly) say ruin is certain here.
    r = risk_of_ruin(win_rate=0.45, avg_win_pct=8.0, avg_loss_pct=4.0, risk_per_trade_pct=1.0)
    assert r["error"] is None
    assert r["expectancy_r"] > 0
    assert r["payoff_ror_pct"] < 1.0          # the fixed, correct number
    assert r["classic_ror_pct"] == 100.0      # even-money formula disagrees — shown for contrast only


def test_negative_expectancy_is_near_certain_ruin():
    r = risk_of_ruin(win_rate=0.30, avg_win_pct=8.0, avg_loss_pct=4.0, risk_per_trade_pct=1.0)
    assert r["expectancy_r"] < 0
    assert r["payoff_ror_pct"] == 100.0
    assert "NEGATIVE EXPECTANCY" in r["verdict"]


def test_equal_payoff_matches_classic_even_money_formula():
    # When avg_win == avg_loss (payoff=1), the generalized formula must reduce
    # to the classic even-money gambler's ruin result.
    r = risk_of_ruin(win_rate=0.55, avg_win_pct=4.0, avg_loss_pct=4.0, risk_per_trade_pct=1.0)
    assert abs(r["payoff_ror_pct"] - r["classic_ror_pct"]) < 0.5


def test_invalid_inputs_return_error():
    assert risk_of_ruin(0, 8, 4, 1)["error"] is not None
    assert risk_of_ruin(1, 8, 4, 1)["error"] is not None
    assert risk_of_ruin(0.5, 0, 4, 1)["error"] is not None
    assert risk_of_ruin(0.5, 8, 0, 1)["error"] is not None
    assert risk_of_ruin(0.5, 8, 4, 0)["error"] is not None


def test_murphy_checklist_scores_only_answered_items():
    answers = {0: True, 1: True, 2: False}
    r = murphy_checklist(answers)
    assert r["total"] == 3
    assert r["passed"] == 2
    assert r["pct"] == round(2 / 3 * 100)


def test_murphy_checklist_empty_answers():
    r = murphy_checklist({})
    assert r["total"] == 0
    assert r["verdict"] == "Not yet answered"
    assert r["items"] is MURPHY_CHECKLIST
