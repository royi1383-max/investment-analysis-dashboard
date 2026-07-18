"""
Morning Briefing — "what changed since yesterday" in one glance.

Collects deterministically:
  • Market regime + valuation gauges (CAPE, Fear & Greed)
  • Tracked + paper portfolio values vs their last snapshot
  • Earnings in the next 7 days for tracked symbols
  • Score movers (composite score changes ≥0.7 over 30d)

Then Claude Haiku writes a 5-line human summary. Cached per calendar day
in .briefing.json — generated once each morning, instant afterwards.
"""
import json
import datetime
from pathlib import Path

from config import ANTHROPIC_API_KEY, FINNHUB_API_KEY
from utils.persist import load_json, save_json
from utils.claude_client import get_client, ENGLISH_ENFORCEMENT

_BR_FILE = Path(__file__).parent.parent / ".briefing.json"


def _collect() -> dict:
    facts = {"date": datetime.date.today().isoformat()}

    # Market regime + gauges
    try:
        from modules.market_context import get_regime
        r = get_regime()
        facts["regime"] = {"label": r.get("regime"), "score": r.get("score"),
                          "vix": r.get("signals", {}).get("vix")}
    except Exception:
        pass
    try:
        from modules.market_valuation import get_fear_greed, get_shiller_cape
        fg = get_fear_greed()
        facts["fear_greed"] = {"score": fg.get("score"), "label": fg.get("label")}
        cape = get_shiller_cape()
        facts["cape"] = cape.get("cape")
    except Exception:
        pass

    # Tracked portfolios: current vs last snapshot
    try:
        from modules.tracked_portfolio import load_all as tp_load
        rows = []
        for name, tp in tp_load().get("portfolios", {}).items():
            vh = tp.get("value_history", [])
            if len(vh) >= 2:
                prev, last = vh[-2]["value"], vh[-1]["value"]
                if prev:
                    rows.append({"name": name, "value": last,
                                 "chg_pct": round((last / prev - 1) * 100, 2)})
            elif vh:
                rows.append({"name": name, "value": vh[-1]["value"], "chg_pct": None})
        if rows:
            facts["tracked"] = rows
    except Exception:
        pass

    # Paper portfolios (same treatment)
    try:
        from modules.paper_portfolio import load_all as pp_load
        rows = []
        for name, pp in pp_load().get("portfolios", {}).items():
            eh = pp.get("equity_history", [])
            if len(eh) >= 2 and eh[-2].get("total_value"):
                rows.append({"name": name, "value": eh[-1]["total_value"],
                             "chg_pct": round((eh[-1]["total_value"] /
                                               eh[-2]["total_value"] - 1) * 100, 2)})
        if rows:
            facts["paper"] = rows
    except Exception:
        pass

    # Earnings next 7 days for tracked symbols
    if FINNHUB_API_KEY:
        try:
            from modules.alerts import _tracked_symbols
            from modules.finnhub_data import get_earnings_for_symbols
            syms = _tracked_symbols()
            if syms:
                facts["earnings_soon"] = get_earnings_for_symbols(tuple(syms), 7)[:8]
        except Exception:
            pass

    # Score movers
    try:
        from modules.score_history import get_movers
        movers = get_movers()
        if movers:
            facts["score_movers"] = movers[:6]
    except Exception:
        pass

    return facts


def get_briefing(force: bool = False) -> dict:
    """Daily-cached briefing: {date, facts, summary}."""
    today = datetime.date.today().isoformat()
    cached = load_json(_BR_FILE, default={})
    if not force and cached.get("date") == today and cached.get("summary"):
        return cached

    facts = _collect()
    summary = ""
    client = get_client() if ANTHROPIC_API_KEY else None
    if client:
        try:
            prompt = (
                "You are writing a MORNING BRIEFING for a retail investor's dashboard. "
                "Here is today's machine-collected state:\n\n"
                f"{json.dumps(facts, default=str, indent=1)}\n\n"
                "Write a crisp briefing: max 5 bullet lines, each one concrete and actionable-aware. "
                "Cover (only if data present): market regime + sentiment stance, portfolio moves worth "
                "noticing, upcoming earnings that need attention, score deteriorations/improvements. "
                "No fluff, no 'good morning'. If valuations are extreme, say what that means practically.\n"
                f"{ENGLISH_ENFORCEMENT}\n"
                "Respond with ONLY the bullet lines (markdown '- ' bullets)."
            )
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            summary = msg.content[0].text.strip()
        except Exception as e:
            summary = f"(AI summary unavailable: {e})"

    out = {"date": today, "facts": facts, "summary": summary}
    save_json(_BR_FILE, out)
    return out
