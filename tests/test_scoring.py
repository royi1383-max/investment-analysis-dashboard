"""
Tests for modules/scoring.py's classify_pattern() — the quality-vs-
confirmation overlay added so a strong-fundamentals/weak-technical stock
(e.g. the CRDO case: fundamental 8.16, macro 8.0, technical 4.1,
momentum 3.82 -> final 6.21 HOLD) reads differently from a genuinely
mixed one, without changing compute()'s final score.
"""
import modules.scoring as scoring


def test_crdo_like_pattern_is_fundamentally_driven():
    breakdown = {"fundamental": 8.16, "technical": 4.1, "momentum": 3.82,
                 "smart_money": 5.8, "macro": 8.0, "relative": 7.0}
    result = scoring.classify_pattern(breakdown)
    assert result["pattern"] == "FUNDAMENTALLY-DRIVEN — AWAITING CONFIRMATION"
    assert result["quality"] == 8.08
    assert result["confirmation"] == 3.96


def test_momentum_without_fundamentals_is_flagged():
    breakdown = {"fundamental": 3.0, "technical": 8.5, "momentum": 8.0,
                 "smart_money": 5.0, "macro": 4.0, "relative": 7.0}
    result = scoring.classify_pattern(breakdown)
    assert result["pattern"] == "MOMENTUM WITHOUT FUNDAMENTAL SUPPORT"


def test_broad_bullish_alignment():
    breakdown = {"fundamental": 8.0, "technical": 8.0, "momentum": 8.0,
                 "smart_money": 7.0, "macro": 8.0, "relative": 7.0}
    result = scoring.classify_pattern(breakdown)
    assert result["pattern"] == "BROAD ALIGNMENT — BULLISH"


def test_broad_bearish_alignment():
    breakdown = {"fundamental": 3.0, "technical": 3.0, "momentum": 3.0,
                 "smart_money": 4.0, "macro": 3.0, "relative": 4.0}
    result = scoring.classify_pattern(breakdown)
    assert result["pattern"] == "BROAD ALIGNMENT — BEARISH"


def test_genuinely_mixed_has_no_dominant_story():
    breakdown = {"fundamental": 6.0, "technical": 5.5, "momentum": 5.0,
                 "smart_money": 5.0, "macro": 6.0, "relative": 5.5}
    result = scoring.classify_pattern(breakdown)
    assert result["pattern"] == "MIXED — NO DOMINANT STORY"


def test_missing_pillars_default_to_neutral_five():
    result = scoring.classify_pattern({})
    assert result["quality"] == 5.0
    assert result["confirmation"] == 5.0
    assert result["pattern"] == "MIXED — NO DOMINANT STORY"


def test_compute_final_score_unaffected_by_pattern_logic():
    # classify_pattern must be a pure read-side overlay — compute()'s own
    # output (what every ranking/screen in the app relies on) is untouched.
    result = scoring.compute(fundamental=8.16, technical=4.1, momentum=3.82,
                             smart_money=5.8, macro=8.0, relative=7.0)
    assert result["final"] == 6.21
    assert result["label"] == "Hold"


def test_action_plan_falling_knife_always_avoids():
    plan = scoring.action_plan(score_label="Watch", quadrant="FALLING KNIFE",
                               pattern="MIXED — NO DOMINANT STORY")
    assert "AVOID" in plan["action"]


def test_action_plan_leader_and_buy_says_hold_add():
    plan = scoring.action_plan(score_label="Buy", quadrant="LEADER",
                               pattern="BROAD ALIGNMENT — BULLISH")
    assert "HOLD" in plan["action"] or "ADD" in plan["action"]


def test_action_plan_crdo_pattern_gives_starter_position_with_levels():
    # The exact CRDO-shaped situation from item 5: fundamentally-driven,
    # awaiting confirmation, quadrant not yet a clean LEADER/FALLING KNIFE.
    plan = scoring.action_plan(
        score_label="Hold", quadrant="QUALITY ON SALE",
        pattern="FUNDAMENTALLY-DRIVEN — AWAITING CONFIRMATION",
        current_price=150.0, nearest_support=140.0, nearest_resistance=170.0,
        ma50=155.0,
    )
    assert "STARTER" in plan["action"] or "WAIT" in plan["action"]
    assert any("$155.00" in s for s in plan["steps"])
    assert any("$140.00" in s for s in plan["steps"])


def test_action_plan_momentum_without_quality_flags_no_averaging_down():
    plan = scoring.action_plan(score_label="Buy", quadrant="MOMENTUM WITHOUT QUALITY",
                               pattern="MOMENTUM WITHOUT FUNDAMENTAL SUPPORT")
    assert "TRADE" in plan["action"]
    assert any("average down" in s.lower() for s in plan["steps"])


def test_action_plan_handles_missing_price_levels_gracefully():
    plan = scoring.action_plan(score_label="Hold", quadrant="MIXED / TRANSITIONAL",
                               pattern="MIXED — NO DOMINANT STORY")
    assert plan["action"]
    assert isinstance(plan["steps"], list) and plan["steps"]
