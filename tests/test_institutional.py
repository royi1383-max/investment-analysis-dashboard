"""
Tests for modules/institutional.py's routine-vs-discretionary insider-sell
split. yfinance's insider data carries no SEC Form 4 transaction code and
no 10b5-1 checkbox, so a scheduled-plan tax sale and a deliberate
open-market dump both just read "Sale at price X per share." The one
signal that survives: a scheduled plan sells the *same share count*
repeatedly. This is what the split detects, so a big pile of routine
selling (e.g. an exec's 10b5-1 plan) doesn't drag the score down the same
way a genuine one-off discretionary dump would.
"""
import pandas as pd
import pytest

import modules.institutional as inst


def _mk_insider_df(rows):
    return pd.DataFrame(rows, columns=["Insider", "Position", "Text", "Shares", "Value"])


@pytest.fixture
def patch_deps(monkeypatch):
    def _apply(insider_df, inst_df=None, info=None):
        monkeypatch.setattr(inst, "get_insider_transactions", lambda symbol: insider_df)
        monkeypatch.setattr(inst, "get_institutional_holders",
                            lambda symbol: inst_df if inst_df is not None else pd.DataFrame())
        monkeypatch.setattr(inst, "get_ticker_info", lambda symbol: info or {})
    return _apply


def test_repeating_share_count_is_classified_routine(patch_deps):
    # One insider sells the exact same 27,500-share count 4x (a 10b5-1-style
    # signature) plus one genuinely different one-off sale.
    rows = [
        ("CHENG", "CTO", "Sale at price 200 per share.", 27500, 5_500_000),
        ("CHENG", "CTO", "Sale at price 205 per share.", 27500, 5_637_500),
        ("CHENG", "CTO", "Sale at price 210 per share.", 27500, 5_775_000),
        ("CHENG", "CTO", "Sale at price 215 per share.", 27500, 5_912_500),
        ("CHENG", "CTO", "Sale at price 220 per share.", 90000, 19_800_000),
    ]
    patch_deps(_mk_insider_df(rows))
    result = inst.analyze("TEST")
    assert result["sell_value_routine"] == pytest.approx(22_825_000)
    assert result["sell_value_discretionary"] == pytest.approx(19_800_000)
    assert result["routine_sell_pct"] == pytest.approx(53.0, abs=1)


def test_one_off_sales_are_all_discretionary(patch_deps):
    rows = [
        ("A", "CEO", "Sale at price 100 per share.", 1000, 100_000),
        ("B", "CFO", "Sale at price 50 per share.",  2000, 100_000),
    ]
    patch_deps(_mk_insider_df(rows))
    result = inst.analyze("TEST")
    assert result["sell_value_routine"] == 0
    assert result["sell_value_discretionary"] == pytest.approx(200_000)


def test_heavy_routine_selling_does_not_trigger_bearish_flag(patch_deps):
    # A large repeating-pattern sale pile should NOT fire "Heavy discretionary
    # insider selling detected" — that flag is discretionary-only by design.
    rows = [(f"X", "CTO", "Sale at price 100 per share.", 50000, 5_000_000)] * 5
    patch_deps(_mk_insider_df(rows))
    result = inst.analyze("TEST")
    assert not any("Heavy discretionary insider selling" in msg for _, msg in result["signals"])
    assert any("repeating-share-count" in msg for _, msg in result["signals"])


def test_genuine_large_one_off_sale_still_flags_bearish(patch_deps):
    rows = [("Y", "CEO", "Sale at price 100 per share.", 200000, 20_000_000)]
    patch_deps(_mk_insider_df(rows))
    result = inst.analyze("TEST")
    assert any("Heavy discretionary insider selling" in msg for _, msg in result["signals"])


def test_stock_gifts_excluded_from_buy_and_sell(patch_deps):
    rows = [("Z", "CEO", "Stock Gift at price 0.00 per share.", 5000, 0)]
    patch_deps(_mk_insider_df(rows))
    result = inst.analyze("TEST")
    assert result["buy_value"] == 0
    assert result["sell_value"] == 0


def test_empty_insider_df_is_neutral(patch_deps):
    patch_deps(pd.DataFrame())
    result = inst.analyze("TEST")
    assert result["scores"]["Insider Activity"] == 5
    assert result["routine_sell_pct"] is None
