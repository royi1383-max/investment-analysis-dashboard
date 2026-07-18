"""
Paper Trading Portfolio — AI-managed multi-portfolio demo.

Data persisted in .paper_portfolios.json (project root).
3 default portfolios created on first run:
  Bull  🟢  risk-on   — growth / momentum / high-beta
  Bear  🔴  risk-off  — defensive / dividends / hedges
  Neutral ⚖️ neutral  — balanced / sector-diversified

Each portfolio is fully independent: its own cash, holdings, trade log,
equity history, and Claude journal.

Claude integration:
  • claude_trade_comment()  — Haiku, 2-3 sentences, fires immediately after a trade
  • claude_portfolio_review() — Sonnet, full graded review on demand
"""
import json
import math
import datetime
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Any

from config import ANTHROPIC_API_KEY
from utils.cache import get_ticker_info, get_price_history

# ─── Constants ────────────────────────────────────────────────────────────────

_PP_FILE = Path(__file__).parent.parent / ".paper_portfolios.json"

_DEFAULT_CAPITAL = 50_000.0

_DEFAULT_PORTFOLIOS = [
    {
        "name":        "Bull 🟢",
        "sentiment":   "risk-on",
        "description": "Growth + momentum, high beta",
    },
    {
        "name":        "Bear 🔴",
        "sentiment":   "risk-off",
        "description": "Defensive, low beta, dividends",
    },
    {
        "name":        "Neutral ⚖️",
        "sentiment":   "neutral",
        "description": "Balanced, sector diversified",
    },
]


# ─── Persistence via shared util (atomic writes, numpy-safe) ─────────────────
from utils.persist import load_json as _load_json, save_json as _save_json


# ─── Persistence ──────────────────────────────────────────────────────────────

def _empty_portfolio(name: str, sentiment: str, description: str,
                     capital: float = _DEFAULT_CAPITAL) -> dict:
    today = datetime.date.today().isoformat()
    return {
        "name":            name,
        "sentiment":       sentiment,
        "description":     description,
        "initial_capital": capital,
        "cash":            capital,
        "created_at":      today,
        "holdings":        {},
        "closed_positions": [],
        "equity_history":  [{"date": today, "total_value": capital, "cash": capital}],
        "claude_journal":  [],
    }


def load_all() -> dict:
    """Load all portfolios from disk. Creates defaults if file absent."""
    data = _load_json(_PP_FILE)
    if isinstance(data, dict) and data.get("portfolios"):
        return data

    # First run — create defaults
    portfolios = {
        p["name"]: _empty_portfolio(p["name"], p["sentiment"], p["description"])
        for p in _DEFAULT_PORTFOLIOS
    }
    data = {"active": _DEFAULT_PORTFOLIOS[0]["name"], "portfolios": portfolios}
    save_all(data)
    return data


def save_all(data: dict) -> None:
    _save_json(_PP_FILE, data)


def get_portfolio(data: dict, name: str) -> dict:
    return data["portfolios"].get(name, {})


def create_portfolio(data: dict, name: str, sentiment: str,
                     description: str, capital: float = _DEFAULT_CAPITAL) -> dict:
    name = name.strip()
    if not name or name in data["portfolios"]:
        return data
    data["portfolios"][name] = _empty_portfolio(name, sentiment, description, capital)
    data["active"] = name
    save_all(data)
    return data


def delete_portfolio(data: dict, name: str) -> dict:
    if name not in data["portfolios"] or len(data["portfolios"]) <= 1:
        return data
    del data["portfolios"][name]
    if data["active"] == name:
        data["active"] = next(iter(data["portfolios"]))
    save_all(data)
    return data


# ─── Trade logic ──────────────────────────────────────────────────────────────

def add_trade(pp: dict, symbol: str, action: str, shares: int,
              price: float, reason: str) -> tuple[dict, str]:
    """
    Execute a trade on a single portfolio dict.
    Returns (updated_pp, error_msg). error_msg is "" on success.
    """
    symbol = symbol.upper().strip()
    shares = int(shares)
    price  = float(price)
    today  = datetime.date.today().isoformat()

    if shares <= 0 or price <= 0:
        return pp, "Shares and price must be positive."

    if action == "BUY":
        cost = shares * price
        if cost > pp["cash"]:
            return pp, f"Insufficient cash (need ${cost:,.0f}, have ${pp['cash']:,.0f})."

        pp["cash"] -= cost
        if symbol in pp["holdings"]:
            h = pp["holdings"][symbol]
            total_shares = h["shares"] + shares
            h["avg_cost"] = (h["avg_cost"] * h["shares"] + price * shares) / total_shares
            h["shares"]   = total_shares
        else:
            pp["holdings"][symbol] = {
                "shares":   shares,
                "avg_cost": price,
                "entered_at": today,
            }
        # append transaction to holdings log
        pp["holdings"][symbol].setdefault("transactions", []).append({
            "id":     _uid(),
            "date":   today,
            "action": "BUY",
            "shares": shares,
            "price":  price,
            "reason": reason,
        })

    elif action == "SELL":
        if symbol not in pp["holdings"]:
            return pp, f"No position in {symbol}."
        h = pp["holdings"][symbol]
        if shares > h["shares"]:
            return pp, f"Only have {h['shares']} shares of {symbol}."

        proceeds  = shares * price
        avg_cost  = h["avg_cost"]
        pnl_usd   = (price - avg_cost) * shares
        pnl_pct   = (price / avg_cost - 1) * 100

        pp["cash"] += proceeds

        # Record closed position
        pp["closed_positions"].append({
            "symbol":       symbol,
            "entry_date":   h.get("entered_at", ""),
            "exit_date":    today,
            "entry_price":  round(avg_cost, 4),
            "exit_price":   round(price, 4),
            "shares":       shares,
            "pnl_usd":      round(pnl_usd, 2),
            "pnl_pct":      round(pnl_pct, 2),
            "reason":       reason,
        })

        h["shares"] -= shares
        h.setdefault("transactions", []).append({
            "id":     _uid(),
            "date":   today,
            "action": "SELL",
            "shares": shares,
            "price":  price,
            "reason": reason,
            "pnl_usd": round(pnl_usd, 2),
        })

        if h["shares"] == 0:
            del pp["holdings"][symbol]
    else:
        return pp, f"Unknown action: {action}"

    record_equity_snapshot(pp)
    return pp, ""


def _uid() -> str:
    return datetime.datetime.now().isoformat()


# ─── Portfolio valuation ───────────────────────────────────────────────────────

def get_current_value(pp: dict) -> dict:
    """Fetch live prices and compute portfolio value."""
    holdings_value = 0.0
    positions = []

    for sym, h in pp.get("holdings", {}).items():
        price_stale = False
        try:
            info  = get_ticker_info(sym)
            raw_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if raw_price is None:
                raise ValueError("no price")
            price = float(raw_price)
        except Exception:
            # Price feed failed — value at cost but FLAG it so UI doesn't show fake 0% P&L
            price = h["avg_cost"]
            price_stale = True

        val     = price * h["shares"]
        pnl_usd = (price - h["avg_cost"]) * h["shares"]
        pnl_pct = (price / h["avg_cost"] - 1) * 100 if h["avg_cost"] > 0 else 0.0

        holdings_value += val
        positions.append({
            "symbol":      sym,
            "shares":      h["shares"],
            "avg_cost":    h["avg_cost"],
            "price":       price,
            "value":       val,
            "pnl_usd":     pnl_usd,
            "pnl_pct":     pnl_pct,
            "price_stale": price_stale,
        })

    total      = pp["cash"] + holdings_value
    init       = pp.get("initial_capital", _DEFAULT_CAPITAL)
    pnl_total  = total - init
    pnl_pct_t  = (total / init - 1) * 100 if init > 0 else 0.0

    return {
        "total":          total,
        "cash":           pp["cash"],
        "holdings_value": holdings_value,
        "pnl_usd":        pnl_total,
        "pnl_pct":        pnl_pct_t,
        "positions":      positions,
    }


def record_equity_snapshot(pp: dict) -> None:
    """Append today's value to equity_history (only once per day)."""
    try:
        val  = get_current_value(pp)
        today = datetime.date.today().isoformat()
        hist  = pp.setdefault("equity_history", [])
        if hist and hist[-1]["date"] == today:
            hist[-1]["total_value"] = round(val["total"], 2)
            hist[-1]["cash"]        = round(val["cash"], 2)
        else:
            hist.append({
                "date":        today,
                "total_value": round(val["total"], 2),
                "cash":        round(val["cash"], 2),
            })
    except Exception:
        pass


def get_equity_curve(pp: dict) -> pd.DataFrame:
    hist = pp.get("equity_history", [])
    if not hist:
        return pd.DataFrame()
    df = pd.DataFrame(hist)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df


def get_closed_pnl(pp: dict) -> list[dict]:
    return pp.get("closed_positions", [])


# ─── Dividend accrual ──────────────────────────────────────────────────────────

def accrue_dividends(pp: dict) -> list[dict]:
    """
    Credit any dividends whose ex-date passed since each holding was entered
    and hasn't been credited yet. Mutates pp (cash + dividends_credited +
    claude_journal). Returns list of newly credited events:
      [{symbol, ex_date, dps, shares, total}]
    Caller is responsible for saving.
    """
    credited = pp.setdefault("dividends_credited", [])
    seen = {(d["symbol"], d["ex_date"]) for d in credited}
    new_events = []

    for sym, h in pp.get("holdings", {}).items():
        entered = h.get("entered_at")
        if not entered:
            continue
        try:
            import yfinance as yf
            divs = yf.Ticker(sym).dividends   # Series indexed by ex-date
            if divs is None or divs.empty:
                continue
            entered_ts = pd.Timestamp(entered)
            if divs.index.tz is not None:
                entered_ts = entered_ts.tz_localize(divs.index.tz)
            today_ts = pd.Timestamp.now(tz=divs.index.tz)
            for ex_date, dps in divs.items():
                if ex_date <= entered_ts or ex_date > today_ts:
                    continue
                ex_str = ex_date.strftime("%Y-%m-%d")
                if (sym, ex_str) in seen:
                    continue
                total = float(dps) * h["shares"]
                pp["cash"] += total
                event = {
                    "symbol":  sym,
                    "ex_date": ex_str,
                    "dps":     round(float(dps), 4),
                    "shares":  h["shares"],
                    "total":   round(total, 2),
                }
                credited.append(event)
                seen.add((sym, ex_str))
                new_events.append(event)
                pp.setdefault("claude_journal", []).append({
                    "date":   datetime.date.today().isoformat(),
                    "type":   "dividend",
                    "symbol": sym,
                    "text":   f"Dividend credited: {sym} paid ${dps:.4f}/share × "
                              f"{h['shares']} shares = ${total:.2f} (ex-date {ex_str})",
                })
        except Exception:
            continue

    if new_events:
        record_equity_snapshot(pp)
    return new_events


def total_dividends(pp: dict) -> float:
    return sum(d.get("total", 0) for d in pp.get("dividends_credited", []))


# ─── Multi-portfolio comparison ────────────────────────────────────────────────

def compare_portfolios(data: dict) -> pd.DataFrame:
    rows = []
    for name, pp in data["portfolios"].items():
        val  = get_current_value(pp)
        init = pp.get("initial_capital", _DEFAULT_CAPITAL)
        closed = pp.get("closed_positions", [])

        wins  = [c["pnl_pct"] for c in closed if c["pnl_pct"] > 0]
        losses = [c["pnl_pct"] for c in closed if c["pnl_pct"] < 0]

        best_trade = max(wins, default=0.0)

        # Approximate Sharpe from equity curve
        curve = get_equity_curve(pp)
        sharpe = _approx_sharpe(curve)

        rows.append({
            "Portfolio":     name,
            "Sentiment":     pp.get("sentiment", ""),
            "Total Return":  val["pnl_pct"],
            "Total P&L $":   val["pnl_usd"],
            "Holdings":      len(pp.get("holdings", {})),
            "Closed Trades": len(closed),
            "Win Rate":      len(wins) / len(closed) * 100 if closed else 0.0,
            "Best Trade %":  best_trade,
            "Sharpe":        sharpe,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _approx_sharpe(curve: pd.DataFrame) -> float:
    try:
        if curve.empty or len(curve) < 2:
            return 0.0
        ret = curve["total_value"].pct_change(fill_method=None).dropna()
        if ret.std() == 0:
            return 0.0
        return float((ret.mean() - 0.05 / 252) / ret.std() * math.sqrt(252))
    except Exception:
        return 0.0


# ─── Performance stats ─────────────────────────────────────────────────────────

def get_performance_stats(pp: dict) -> dict:
    closed = pp.get("closed_positions", [])
    if not closed:
        return {
            "win_rate": 0, "avg_win": 0, "avg_loss": 0,
            "best_trade": 0, "worst_trade": 0, "total_realized": 0,
        }
    wins   = [c["pnl_pct"] for c in closed if c["pnl_pct"] > 0]
    losses = [c["pnl_pct"] for c in closed if c["pnl_pct"] <= 0]
    total_realized = sum(c["pnl_usd"] for c in closed)
    return {
        "win_rate":      len(wins) / len(closed) * 100,
        "avg_win":       sum(wins) / len(wins) if wins else 0,
        "avg_loss":      sum(losses) / len(losses) if losses else 0,
        "best_trade":    max((c["pnl_pct"] for c in closed), default=0),
        "worst_trade":   min((c["pnl_pct"] for c in closed), default=0),
        "total_realized": total_realized,
    }


# ─── Claude integration ────────────────────────────────────────────────────────

from utils.claude_client import get_client as _get_client


def claude_trade_comment(symbol: str, action: str, shares: int, price: float,
                         reason: str, portfolio_name: str,
                         portfolio_summary: str) -> str:
    """
    2-3 sentence immediate reaction to a trade.
    Uses Haiku (fast, cheap).
    """
    client = _get_client()
    if not client:
        return ""
    try:
        prompt = (
            f"You are an AI portfolio manager commenting on a just-executed paper trade.\n\n"
            f"Portfolio: {portfolio_name}\n"
            f"Trade: {action} {shares} shares of {symbol} @ ${price:.2f}\n"
            f"Reason given: {reason}\n\n"
            f"Portfolio context: {portfolio_summary}\n\n"
            f"Write a 2-3 sentence comment on this trade: "
            f"acknowledge the rationale, note one key risk or opportunity, "
            f"and give brief context about why this fits (or doesn't fit) the portfolio's strategy.\n\n"
            f"IMPORTANT: Always respond in English regardless of the user's input language.\n"
            f"Respond with only the comment text, no headers or bullets."
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=220,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception:
        return ""


def _strip_json(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


@st.cache_data(ttl=1800, show_spinner=False)
def claude_portfolio_review(_fingerprint: str, holdings_json: str,
                             closed_json: str, market_ctx: str,
                             portfolio_name: str, sentiment: str) -> dict:
    """
    Full graded portfolio review.
    Uses Sonnet. Cached 30 min by _fingerprint (hash of portfolio state).
    """
    client = _get_client()
    if not client:
        return {"error": "No API key configured."}
    try:
        prompt = (
            f"You are an expert portfolio manager reviewing a paper trading portfolio.\n\n"
            f"Portfolio: {portfolio_name} (Strategy: {sentiment})\n"
            f"Market context: {market_ctx}\n\n"
            f"Current holdings:\n{holdings_json}\n\n"
            f"Recent closed positions:\n{closed_json}\n\n"
            f"Provide a comprehensive portfolio review. Return ONLY valid JSON matching exactly:\n"
            f'{{"overall_assessment": "string", "portfolio_grade": "A|B|C|D|F", '
            f'"what_worked": ["string"], "what_didnt": ["string"], '
            f'"lessons": ["string"], "current_risks": ["string"], '
            f'"suggested_actions": ["string"], "market_impact_notes": ["string"]}}\n\n'
            f"IMPORTANT: Always respond in English regardless of the user's input language.\n"
            f"Respond ONLY with the JSON object, no markdown fences."
        )
        resp = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1800,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_json(resp.content[0].text.strip())
        return json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse error: {e}"}
    except Exception as e:
        return {"error": str(e)}


def portfolio_fingerprint(pp: dict) -> str:
    """Stable hash of portfolio state for cache key."""
    key = json.dumps({
        "holdings":  pp.get("holdings", {}),
        "closed":    pp.get("closed_positions", []),
        "cash":      pp.get("cash", 0),
    }, sort_keys=True, default=str)
    return hashlib.md5(key.encode()).hexdigest()
