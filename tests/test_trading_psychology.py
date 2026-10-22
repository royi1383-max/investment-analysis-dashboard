from modules.trading_psychology import bias_checklist, BIAS_CHECKLIST


def test_all_yes_is_perfect_score_no_flags():
    answers = {item["key"]: True for item in BIAS_CHECKLIST}
    r = bias_checklist(answers)
    assert r["passed"] == r["total"] == len(BIAS_CHECKLIST)
    assert r["pct"] == 100
    assert r["flags"] == []
    assert "CLEAR-HEADED" in r["verdict"]


def test_partial_no_answers_produce_matching_flags():
    keys = [item["key"] for item in BIAS_CHECKLIST]
    answers = {k: True for k in keys}
    # Flip two specific items to "no" (bias present)
    answers[keys[0]] = False
    answers[keys[3]] = False
    r = bias_checklist(answers)
    assert r["passed"] == len(keys) - 2
    assert len(r["flags"]) == 2
    assert BIAS_CHECKLIST[0]["bias"] in r["flags"]
    assert BIAS_CHECKLIST[3]["bias"] in r["flags"]


def test_empty_answers():
    r = bias_checklist({})
    assert r["total"] == 0
    assert r["pct"] is None


def test_unknown_keys_are_ignored():
    r = bias_checklist({"not_a_real_key": False})
    assert r["total"] == 0
