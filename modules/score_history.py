"""
Score History — tracks each stock's composite score over time.

Every time Analyze computes a score, it's recorded here (once per day per
symbol). This surfaces DETERIORATION BEFORE PRICE: a score sliding from
8.2 → 6.9 over a month is a signal even while the chart still looks fine.

Persistence: .score_history.json  {symbol: [{date, score, fund, tech, mom}]}
"""
import datetime
from pathlib import Path

from utils.persist import load_json, save_json

_SH_FILE = Path(__file__).parent.parent / ".score_history.json"
_MAX_POINTS = 120   # per symbol (~6 months of daily analyzing)


def record(symbol: str, score: float, fund: float, tech: float, mom: float) -> None:
    """Record today's score for a symbol (overwrites same-day entry)."""
    try:
        data = load_json(_SH_FILE, default={})
        today = datetime.date.today().isoformat()
        rows = data.get(symbol, [])
        entry = {"date": today, "score": round(float(score), 2),
                 "fund": round(float(fund), 2), "tech": round(float(tech), 2),
                 "mom": round(float(mom), 2)}
        if rows and rows[-1].get("date") == today:
            rows[-1] = entry
        else:
            rows.append(entry)
        data[symbol] = rows[-_MAX_POINTS:]
        save_json(_SH_FILE, data)
    except Exception:
        pass


def get_history(symbol: str) -> list[dict]:
    data = load_json(_SH_FILE, default={})
    return data.get(symbol, [])


def get_delta(symbol: str, days: int = 30) -> dict | None:
    """Score change vs the closest record ≥`days` ago.
    Returns {then, now, delta, then_date} or None."""
    rows = get_history(symbol)
    if len(rows) < 2:
        return None
    try:
        cutoff = datetime.date.today() - datetime.timedelta(days=days)
        older = [r for r in rows if datetime.date.fromisoformat(r["date"]) <= cutoff]
        base = older[-1] if older else rows[0]
        now = rows[-1]
        if base["date"] == now["date"]:
            return None
        return {"then": base["score"], "now": now["score"],
                "delta": round(now["score"] - base["score"], 2),
                "then_date": base["date"]}
    except Exception:
        return None


def get_movers(min_abs_delta: float = 0.7) -> list[dict]:
    """Biggest score changes across all recorded symbols (for the briefing)."""
    data = load_json(_SH_FILE, default={})
    movers = []
    for sym in data:
        d = get_delta(sym, days=30)
        if d and abs(d["delta"]) >= min_abs_delta:
            movers.append({"symbol": sym, **d})
    movers.sort(key=lambda m: -abs(m["delta"]))
    return movers[:10]
