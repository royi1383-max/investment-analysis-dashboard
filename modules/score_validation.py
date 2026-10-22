"""
Score Validation — live forward-testing of the composite score against what
actually happened next.

This is deliberately NOT a backtest. modules/scoring.py's composite blends
fundamentals, and yfinance only exposes CURRENT fundamentals — there is no
point-in-time historical snapshot to backtest against without look-ahead
bias. Instead this reads .score_history.json (modules/score_history.py
already records one composite score per symbol per day) and checks, for
scores old enough to have a known outcome, what the stock's ACTUAL forward
return was. This is live, accumulating evidence — thin at first, and more
meaningful the longer the app has been used.
"""
import datetime
from pathlib import Path

import pandas as pd

from utils.persist import load_json
from utils.cache import get_price_history

_SH_FILE = Path(__file__).parent.parent / ".score_history.json"

# Same cut points as config.SCORE_LABELS, so buckets line up with the Buy/Hold/Avoid
# labels shown everywhere else in the app.
BUCKETS: list[tuple[str, float, float]] = [
    ("Strong Buy (>=8.5)", 8.5, 10.01),
    ("Buy (7-8.5)",        7.0, 8.5),
    ("Hold (5-7)",         5.0, 7.0),
    ("Watch (3.5-5)",      3.5, 5.0),
    ("Avoid (<3.5)",       0.0, 3.5),
]


def _forward_return(symbol: str, from_date: str, horizon_days: int) -> float | None:
    """Actual close-to-close return from `from_date` to ~horizon_days later
    (calendar days; matched to the nearest trading day on/after each date)."""
    try:
        ph = get_price_history(symbol, period="2y")
        if ph.empty:
            return None
        close = ph["Close"].squeeze()
        idx = close.index
        start_ts  = pd.Timestamp(from_date)
        target_ts = start_ts + pd.Timedelta(days=horizon_days)
        start_pos = idx.searchsorted(start_ts)
        end_pos   = idx.searchsorted(target_ts)
        if start_pos >= len(idx) or end_pos >= len(idx) or end_pos <= start_pos:
            return None
        p0, p1 = float(close.iloc[start_pos]), float(close.iloc[end_pos])
        if p0 <= 0:
            return None
        return (p1 / p0 - 1) * 100
    except Exception:
        return None


def bucket_analysis(horizon_days: int = 30, min_age_days: int = 30) -> dict:
    """
    For every recorded (symbol, date, score) at least `min_age_days` old,
    compute the forward return over `horizon_days` and bucket by score level.

    Returns:
      buckets        list[{label, n, avg_return, win_rate}]
      n_total        int   — samples with a computable forward return
      oldest_record  str|None — earliest date ever recorded, for context
      as_of          str   — today's date
    """
    data = load_json(_SH_FILE, default={})
    cutoff = datetime.date.today() - datetime.timedelta(days=min_age_days)
    rows: list[dict] = []
    oldest = None

    for symbol, history in data.items():
        for entry in history:
            try:
                d = datetime.date.fromisoformat(entry["date"])
            except Exception:
                continue
            if oldest is None or d < oldest:
                oldest = d
            if d > cutoff:
                continue
            fwd = _forward_return(symbol, entry["date"], horizon_days)
            if fwd is None:
                continue
            rows.append({"symbol": symbol, "date": entry["date"],
                        "score": entry["score"], "forward_return": fwd})

    bucket_out = []
    for label, lo, hi in BUCKETS:
        sub = [r for r in rows if lo <= r["score"] < hi]
        if not sub:
            bucket_out.append({"label": label, "n": 0, "avg_return": None, "win_rate": None})
            continue
        avg = sum(r["forward_return"] for r in sub) / len(sub)
        win = sum(1 for r in sub if r["forward_return"] > 0) / len(sub) * 100
        bucket_out.append({"label": label, "n": len(sub),
                           "avg_return": round(avg, 2), "win_rate": round(win, 1)})

    return {
        "buckets":       bucket_out,
        "n_total":       len(rows),
        "horizon_days":  horizon_days,
        "as_of":         datetime.date.today().isoformat(),
        "oldest_record": oldest.isoformat() if oldest else None,
        "rows":          rows,
    }
