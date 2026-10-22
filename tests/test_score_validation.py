"""
Tests for modules/score_validation.py's bucket_analysis(). Monkeypatches
load_json and _forward_return so no filesystem/network access is needed —
this is pure bucketing/aggregation logic being verified.
"""
import datetime

import modules.score_validation as sv


def test_buckets_use_config_aligned_boundaries_and_average_correctly(monkeypatch):
    oldest_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    old_date = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    recent_date = datetime.date.today().isoformat()   # too fresh — must be excluded

    fake_history = {
        "AAPL": [
            {"date": oldest_date, "score": 8.7},   # -> Strong Buy bucket
            {"date": old_date,    "score": 3.0},   # -> Avoid bucket
            {"date": recent_date, "score": 9.9},   # excluded: younger than min_age_days
        ],
    }
    monkeypatch.setattr(sv, "load_json", lambda path, default=None: fake_history)

    date_to_return = {oldest_date: 5.0, old_date: -2.0, recent_date: 1.0}

    def fake_forward_return(symbol, from_date, horizon_days):
        return date_to_return.get(from_date)

    monkeypatch.setattr(sv, "_forward_return", fake_forward_return)

    result = sv.bucket_analysis(horizon_days=30, min_age_days=30)

    assert result["n_total"] == 2   # the too-recent entry is excluded
    by_label = {b["label"]: b for b in result["buckets"]}
    assert by_label["Strong Buy (>=8.5)"]["n"] == 1
    assert by_label["Strong Buy (>=8.5)"]["avg_return"] == 5.0
    assert by_label["Strong Buy (>=8.5)"]["win_rate"] == 100.0
    assert by_label["Avoid (<3.5)"]["n"] == 1
    assert by_label["Avoid (<3.5)"]["avg_return"] == -2.0
    assert by_label["Avoid (<3.5)"]["win_rate"] == 0.0
    # oldest_record reflects the TRUE earliest date, even though that
    # particular entry may or may not survive the cutoff filter.
    assert result["oldest_record"] == oldest_date


def test_empty_history_returns_zero_samples(monkeypatch):
    monkeypatch.setattr(sv, "load_json", lambda path, default=None: {})
    result = sv.bucket_analysis()
    assert result["n_total"] == 0
    assert result["oldest_record"] is None
    assert all(b["n"] == 0 for b in result["buckets"])


def test_forward_return_none_excludes_the_sample(monkeypatch):
    old_date = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    monkeypatch.setattr(sv, "load_json", lambda path, default=None:
                        {"AAPL": [{"date": old_date, "score": 7.5}]})
    monkeypatch.setattr(sv, "_forward_return", lambda symbol, from_date, horizon_days: None)
    result = sv.bucket_analysis()
    assert result["n_total"] == 0
