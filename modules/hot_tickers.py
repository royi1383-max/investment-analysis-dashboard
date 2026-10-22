"""
"What's hot right now" ticker suggestions that change with the market.

Sources (all optional, each fails independently):
  • Yahoo Finance predefined screeners (most active / day gainers) — no API key
  • Finnhub earnings calendar — only if FINNHUB_API_KEY is set; limited to the
    dashboard's own tracked universe so the list stays relevant

These are *attention* signals (volume, price move, upcoming event), not buy
signals. A big one-day move says little about whether a stock is a good investment.
"""
import sys

import streamlit as st
import yfinance as yf

from config import RADAR_TICKERS, WEEKLY_UNIVERSE

MIN_MARKET_CAP = 2_000_000_000   # skip micro-caps: their one-day moves are mostly noise


def pick_quotes(quotes: list[dict], limit: int = 8, min_cap: float = MIN_MARKET_CAP) -> list[dict]:
    """Keep liquid, sizeable names from a Yahoo screener result and format them for display."""
    picked = []
    for q in quotes:
        symbol = q.get("symbol")
        if not symbol or "." in symbol or "-" in symbol:   # skip foreign listings / share classes
            continue
        if (q.get("marketCap") or 0) < min_cap:
            continue
        picked.append({"symbol": symbol, "name": q.get("shortName") or "",
                       "change_pct": q.get("regularMarketChangePercent")})
        if len(picked) == limit:
            break
    return picked


def earnings_in_universe(calendar: list[dict], universe: set[str], limit: int = 8) -> list[dict]:
    """Earnings events for tracked tickers, soonest first."""
    rows = [e for e in calendar if e.get("symbol") in universe]
    rows.sort(key=lambda e: e.get("date", ""))
    return [{"symbol": e["symbol"], "date": e.get("date", "")} for e in rows[:limit]]


@st.cache_data(ttl=900, show_spinner=False)
def _screen(kind: str) -> list[dict]:
    try:
        return pick_quotes(yf.screen(kind, count=25).get("quotes", []))
    except Exception as e:
        print(f"[hot_tickers] screen({kind}) failed: {e}", file=sys.stderr)
        return []


def get_hot_tickers() -> dict[str, list[dict]]:
    """{section title: [{symbol, ...}]}; sections with no data are left out."""
    sections = {
        "Most active": _screen("most_actives"),
        "Top gainers": _screen("day_gainers"),
    }
    try:
        from modules.finnhub_data import get_earnings_calendar
        sections["Earnings in the next 7 days"] = earnings_in_universe(
            get_earnings_calendar(7), {*WEEKLY_UNIVERSE, *RADAR_TICKERS})
    except Exception as e:
        print(f"[hot_tickers] earnings failed: {e}", file=sys.stderr)
    return {title: rows for title, rows in sections.items() if rows}
