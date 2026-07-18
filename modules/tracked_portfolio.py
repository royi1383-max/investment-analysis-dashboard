"""
Tracked Portfolio — dynamic portfolio/index monitoring with rebalance engine.

Implements the "portfolio-analyzer" skill natively: once a portfolio is put
under tracking (from AI Screener's Build Portfolio or manual entry), the app
continuously evaluates:

  • Weight drift vs target allocation
  • Momentum (1M/3M), RSI extremes, momentum crashes
  • Position quality (score_position from portfolio_health)
  • Insider sentiment (Finnhub MSPR)
  • Concentration risk, market regime (VIX/SPY/TNX)

and produces:
  • Fired triggers per position
  • A mechanical, cost-aware rebalance plan (only trades that clear the
    drift threshold and minimum trade size; estimated transaction cost)
  • A Claude (Sonnet) rebalance review: TRIM/ADD/HOLD/EXIT/REPLACE per
    position with rationale, urgency, alpha ideas and risk flags

Persistence: .tracked_portfolios.json (atomic writes via utils.persist).
"""
import json
import datetime
import hashlib
import pandas as pd
import streamlit as st
from pathlib import Path

from config import ANTHROPIC_API_KEY, FINNHUB_API_KEY
from utils.cache import get_ticker_info, get_price_history
from utils.persist import load_json, save_json
from utils.indicators import rsi_last, trailing_return
from utils.claude_client import get_client, extract_json, ENGLISH_ENFORCEMENT

_TP_FILE = Path(__file__).parent.parent / ".tracked_portfolios.json"

DEFAULT_SETTINGS = {
    "drift_threshold_pct": 5.0,   # rebalance when |current - target| >= this
    "cost_bps": 10,               # assumed one-way transaction cost (0.10%)
    "min_trade_usd": 200,         # ignore dust trades
}


# ─── Persistence ──────────────────────────────────────────────────────────────

def load_all() -> dict:
    data = load_json(_TP_FILE, default={"portfolios": {}})
    if not isinstance(data, dict) or "portfolios" not in data:
        data = {"portfolios": {}}
    return data


def save_all(data: dict) -> None:
    save_json(_TP_FILE, data)


def create_from_positions(name: str, positions: list[dict], capital: float,
                          thesis: str = "", risk_level: str = "") -> tuple[dict, str]:
    """
    positions: [{ticker, weight (int %), role?, rationale?}]
    Fetches entry prices and stores virtual share counts.
    Returns (data, error). Error is "" on success.
    """
    data = load_all()
    name = name.strip()
    if not name:
        return data, "Portfolio name required."
    if name in data["portfolios"]:
        return data, f"'{name}' already exists — pick another name."

    total_w = sum(p.get("weight", 0) for p in positions)
    if not positions or total_w <= 0:
        return data, "No valid positions."

    holdings = {}
    for p in positions:
        sym = p["ticker"].upper().strip()
        w   = p.get("weight", 0) / total_w * 100   # normalize to 100
        try:
            info  = get_ticker_info(sym)
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
        except Exception:
            price = 0.0
        if price <= 0:
            return data, f"Could not fetch a price for {sym} — portfolio not created."
        alloc  = capital * w / 100
        holdings[sym] = {
            "target_weight": round(w, 2),
            "entry_price":   round(price, 4),
            "shares":        round(alloc / price, 6),
            "role":          p.get("role", ""),
            "rationale":     p.get("rationale", ""),
        }

    today = datetime.date.today().isoformat()
    data["portfolios"][name] = {
        "name":          name,
        "created_at":    today,
        "thesis":        thesis,
        "risk_level":    risk_level,
        "capital":       capital,
        "positions":     holdings,
        "settings":      dict(DEFAULT_SETTINGS),
        "rebalance_log": [],
        "value_history": [{"date": today, "value": capital}],
    }
    save_all(data)
    return data, ""


def delete_portfolio(data: dict, name: str) -> dict:
    if name in data["portfolios"]:
        del data["portfolios"][name]
        save_all(data)
    return data


def apply_rebalance(data: dict, name: str, plan: list[dict], note: str = "") -> dict:
    """Execute a mechanical rebalance plan: adjust virtual share counts back to
    target weights at current prices, log the event."""
    tp = data["portfolios"].get(name)
    if not tp:
        return data
    analysis = analyze(tp)
    total = analysis["total_value"]
    for row in analysis["positions"]:
        sym = row["symbol"]
        if sym in tp["positions"] and row["price"] > 0:
            target_val = total * tp["positions"][sym]["target_weight"] / 100
            tp["positions"][sym]["shares"] = round(target_val / row["price"], 6)
    tp["rebalance_log"].append({
        "date":    datetime.date.today().isoformat(),
        "actions": [{"symbol": a["symbol"], "action": a["action"],
                     "amount_usd": a["amount_usd"]} for a in plan],
        "est_cost": round(sum(abs(a["amount_usd"]) for a in plan) *
                          tp["settings"]["cost_bps"] / 10_000, 2),
        "note":    note,
    })
    save_all(data)
    return data


def record_snapshot(data: dict, name: str, total_value: float) -> None:
    tp = data["portfolios"].get(name)
    if not tp:
        return
    today = datetime.date.today().isoformat()
    hist = tp.setdefault("value_history", [])
    if hist and hist[-1]["date"] == today:
        hist[-1]["value"] = round(total_value, 2)
    else:
        hist.append({"date": today, "value": round(total_value, 2)})
    save_all(data)


# ─── Live analysis engine ─────────────────────────────────────────────────────

def _insider_recent(symbol: str) -> float | None:
    """Avg MSPR of last 3 months (None if unavailable)."""
    if not FINNHUB_API_KEY:
        return None
    try:
        from modules.finnhub_data import get_insider_sentiment
        rows = get_insider_sentiment(symbol)
        vals = [r["mspr"] for r in rows[-3:] if r.get("mspr") is not None]
        return round(sum(vals) / len(vals), 1) if vals else None
    except Exception:
        return None


def analyze(tp: dict) -> dict:
    """Full live analysis of a tracked portfolio. Network-heavy; UI caches result."""
    positions_out = []
    total_value = 0.0
    sector_values: dict[str, float] = {}

    for sym, h in tp.get("positions", {}).items():
        price_stale = False
        try:
            info  = get_ticker_info(sym)
            price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)
            if price <= 0:
                raise ValueError("no price")
        except Exception:
            price = h["entry_price"]
            price_stale = True

        value = price * h["shares"]
        total_value += value

        ph = get_price_history(sym, period="6mo")
        close = ph["Close"].squeeze() if not ph.empty else pd.Series(dtype=float)
        r1m = trailing_return(close, 21)
        r3m = trailing_return(close, 63)
        rsi = rsi_last(close)

        sector = "Unknown"
        fwd_pe = None
        try:
            sector = info.get("sector") or "Unknown"
            fwd_pe = info.get("forwardPE")
        except Exception:
            pass
        sector_values[sector] = sector_values.get(sector, 0) + value

        positions_out.append({
            "symbol":        sym,
            "name":          (info.get("shortName") if not price_stale else sym) or sym,
            "role":          h.get("role", ""),
            "target_weight": h["target_weight"],
            "entry_price":   h["entry_price"],
            "price":         price,
            "price_stale":   price_stale,
            "shares":        h["shares"],
            "value":         value,
            "ret_since_entry": (price / h["entry_price"] - 1) * 100 if h["entry_price"] > 0 else 0,
            "r1m":           r1m,
            "r3m":           r3m,
            "rsi":           rsi,
            "fwd_pe":        fwd_pe,
            "sector":        sector,
            "mspr":          _insider_recent(sym),
        })

    # Current weights + drift
    for row in positions_out:
        row["current_weight"] = row["value"] / total_value * 100 if total_value > 0 else 0
        row["drift"] = row["current_weight"] - row["target_weight"]

    # Position quality score (reuses portfolio_health)
    for row in positions_out:
        try:
            from modules.portfolio_health import score_position
            sp = score_position(row["symbol"])
            row["score"] = sp.get("score")
            row["score_label"] = sp.get("label", "")
        except Exception:
            row["score"], row["score_label"] = None, ""

    # Triggers per position
    for row in positions_out:
        t = []
        drift_th = tp.get("settings", {}).get("drift_threshold_pct", 5.0)
        if abs(row["drift"]) >= drift_th:
            t.append(("⚖️", f"Drift {row['drift']:+.1f}pp vs target"))
        if row["r1m"] is not None and row["r1m"] <= -0.12:
            t.append(("📉", f"Momentum crash: {row['r1m']*100:+.1f}% in 1M"))
        if row["r3m"] is not None and row["r3m"] >= 0.20:
            t.append(("🚀", f"Momentum leader: {row['r3m']*100:+.1f}% in 3M"))
        if row["rsi"] is not None and row["rsi"] >= 75:
            t.append(("🔥", f"Overbought (RSI {row['rsi']:.0f})"))
        if row["rsi"] is not None and row["rsi"] <= 30:
            t.append(("🧊", f"Oversold (RSI {row['rsi']:.0f})"))
        if row["mspr"] is not None and row["mspr"] <= -20:
            t.append(("👤", f"Insiders net selling (MSPR {row['mspr']:.0f})"))
        if row["mspr"] is not None and row["mspr"] >= 20:
            t.append(("👤", f"Insiders net buying (MSPR {row['mspr']:.0f})"))
        if row["score_label"] in ("TRIM", "EXIT"):
            t.append(("🏥", f"Health check: {row['score_label']}"))
        if row["current_weight"] >= 30:
            t.append(("⚠️", f"Concentration: {row['current_weight']:.0f}% of portfolio"))
        row["triggers"] = t

    # Market regime
    try:
        from modules.market_context import get_regime
        regime = get_regime()
    except Exception:
        regime = {}

    # Portfolio-level warnings
    warnings = []
    if positions_out:
        top = max(positions_out, key=lambda r: r["current_weight"])
        if top["current_weight"] >= 30:
            warnings.append(f"{top['symbol']} is {top['current_weight']:.0f}% of the portfolio — concentration risk")
    top_sector, top_sector_val = ("", 0.0)
    for s, v in sector_values.items():
        if v > top_sector_val:
            top_sector, top_sector_val = s, v
    if total_value > 0 and top_sector_val / total_value >= 0.5 and top_sector != "Unknown":
        warnings.append(f"{top_sector} is {top_sector_val/total_value*100:.0f}% of the portfolio — sector concentration")
    if regime.get("regime") == "RISK-OFF":
        warnings.append("Market regime is RISK-OFF — consider reducing high-beta exposure")

    init_cap = tp.get("capital", 0)
    return {
        "positions":     positions_out,
        "total_value":   total_value,
        "total_return":  (total_value / init_cap - 1) * 100 if init_cap > 0 else 0,
        "sector_weights": {s: v / total_value * 100 for s, v in sector_values.items()} if total_value else {},
        "regime":        regime,
        "warnings":      warnings,
        "n_triggers":    sum(len(r["triggers"]) for r in positions_out),
    }


# ─── Cost-aware mechanical rebalance plan ─────────────────────────────────────

def build_rebalance_plan(analysis: dict, tp: dict) -> dict:
    """
    Trades needed to restore target weights — but only where drift clears the
    threshold and trade size clears the minimum. Returns:
      {actions: [{symbol, action, amount_usd, drift}], turnover_usd,
       est_cost_usd, worth_it: bool, skipped: [..]}
    """
    s = tp.get("settings", DEFAULT_SETTINGS)
    drift_th  = s.get("drift_threshold_pct", 5.0)
    cost_bps  = s.get("cost_bps", 10)
    min_trade = s.get("min_trade_usd", 200)
    total     = analysis["total_value"]

    actions, skipped = [], []
    for row in analysis["positions"]:
        amount = -row["drift"] / 100 * total   # positive = BUY to restore
        if abs(row["drift"]) < drift_th:
            continue
        if abs(amount) < min_trade:
            skipped.append(f"{row['symbol']}: trade ${abs(amount):,.0f} below minimum")
            continue
        actions.append({
            "symbol":     row["symbol"],
            "action":     "BUY" if amount > 0 else "SELL",
            "amount_usd": round(amount, 2),
            "drift":      round(row["drift"], 2),
        })

    turnover = sum(abs(a["amount_usd"]) for a in actions)
    est_cost = turnover * cost_bps / 10_000
    # Worth doing if drift being corrected is meaningfully larger than cost drag
    worth_it = bool(actions) and est_cost < total * 0.002   # cost under 0.2% of portfolio

    return {
        "actions":      sorted(actions, key=lambda a: -abs(a["amount_usd"])),
        "turnover_usd": round(turnover, 2),
        "est_cost_usd": round(est_cost, 2),
        "worth_it":     worth_it,
        "skipped":      skipped,
    }


# ─── Claude rebalance advisor ─────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def claude_rebalance_review(_fp: str, positions_json: str, plan_json: str,
                            regime_str: str, thesis: str, warnings_str: str) -> dict:
    """Sonnet-powered advisor. Cached 30 min by portfolio fingerprint."""
    client = get_client()
    if client is None:
        return {"error": "No ANTHROPIC_API_KEY configured."}
    try:
        prompt = f"""You are a portfolio manager reviewing a TRACKED portfolio for rebalancing.
The goal: maximize alpha while keeping the portfolio balanced and high-quality.
Weigh transaction costs — recommend changes only when the expected benefit clearly exceeds cost and tax drag.

PORTFOLIO THESIS: {thesis or 'Not specified'}

MARKET CONTEXT: {regime_str}

PORTFOLIO WARNINGS: {warnings_str or 'None'}

POSITIONS (with live signals — drift vs target, momentum, RSI, insider MSPR, health score):
{positions_json}

MECHANICAL REBALANCE PLAN (drift-threshold based, cost-aware):
{plan_json}

Consider: momentum (keep winners running vs overbought risk), valuation (forward P/E),
insider activity, market regime, geopolitical/macro backdrop, position quality scores,
concentration. A position with strong momentum and quality may deserve MORE than target;
a deteriorating one may deserve EXIT even without drift.

{ENGLISH_ENFORCEMENT}
Respond ONLY with JSON:
{{
  "overall_assessment": "<2-3 sentences on portfolio state and whether to act now>",
  "urgency": "NONE|LOW|MEDIUM|HIGH",
  "actions": [
    {{"symbol": "<ticker>", "action": "HOLD|TRIM|ADD|EXIT|REPLACE",
      "new_target_weight": <number or null>,
      "reason": "<1-2 sentences, reference the specific signals>",
      "replacement_candidate": "<ticker or null — only for REPLACE>"}}
  ],
  "alpha_ideas": ["<1-2 concrete ideas to improve expected return>"],
  "risk_flags": ["<key risks in the current setup>"],
  "cost_note": "<is rebalancing now worth the transaction cost? one sentence>"
}}"""
        resp = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=2500,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(extract_json(resp.content[0].text))
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": str(e)}


def portfolio_fingerprint(tp: dict, analysis: dict) -> str:
    key = json.dumps({
        "pos": {r["symbol"]: [round(r["current_weight"], 1), round(r.get("r1m") or 0, 3)]
                for r in analysis["positions"]},
        "date": datetime.date.today().isoformat(),
    }, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()
