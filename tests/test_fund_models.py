"""
Tests for modules/fund_models.py's combined_verdict() aggregation logic —
the equal-weighted consensus that every Alpha Lab feature (Consensus Scanner,
the existing Analyze > Fund Models tab) reads from. Uses hand-built `fm`
dicts rather than live data, so these are pure, fast, and deterministic.
"""
from modules.fund_models import combined_verdict


def test_empty_input_returns_na():
    r = combined_verdict({})
    assert r["score"] is None
    assert r["label"] == "N/A"
    assert r["n_total"] == 0


def test_two_bullish_models_average_correctly():
    fm = {
        "buffett": {"passed": 8, "total": 10},          # -> 8.0
        "graham":  {"margin": 40},                       # -> 9 (margin >= 30)
    }
    r = combined_verdict(fm)
    assert r["n_total"] == 2
    assert r["score"] == round((8.0 + 9) / 2, 1)
    assert r["label"] == "BULLISH CONSENSUS"
    assert r["n_bullish"] == 2
    assert r["n_bearish"] == 0


def test_new_frameworks_feed_into_consensus():
    # Regression check: oshaughnessy/kirkpatrick must be picked up by
    # combined_verdict exactly like the original 15 guru checklists.
    fm = {
        "oshaughnessy": {"passed": 2, "total": 5},   # -> 4.0
        "kirkpatrick":  {"score": 3.0},              # -> 3.0
    }
    r = combined_verdict(fm)
    assert r["n_total"] == 2
    assert "O'Shaughnessy Cornerstone" in r["breakdown"]
    assert "Kirkpatrick RS" in r["breakdown"]
    assert r["breakdown"]["O'Shaughnessy Cornerstone"] == 4.0
    assert r["breakdown"]["Kirkpatrick RS"] == 3.0
    assert r["label"] == "LEAN BEARISH"   # avg 3.5 -> [3, 4.5) bucket
    assert r["n_bearish"] == 1            # kirkpatrick (3.0) <= 3
    assert r["n_neutral"] == 1            # oshaughnessy (4.0) is neither >=7 nor <=3


def test_missing_model_keys_are_silently_skipped():
    # A partial fm dict (e.g. some sub-model failed to fetch data) must not
    # crash combined_verdict — it should just score what's available.
    fm = {"buffett": {"passed": 5, "total": 10}, "not_a_real_model": {"whatever": 1}}
    r = combined_verdict(fm)
    assert r["n_total"] == 1
    assert r["score"] == 5.0


def test_score_is_clamped_to_1_10_range_via_component_scores():
    fm = {"greenblatt": {"verdict": "MAGIC FORMULA CANDIDATE — good business at a cheap price"}}
    r = combined_verdict(fm)
    assert 1.0 <= r["score"] <= 10.0
