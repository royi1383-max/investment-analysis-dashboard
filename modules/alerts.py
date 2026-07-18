"""
Alert System — persistent price/RSI/score alerts stored in .alerts.json.

Alert types:
  PRICE_ABOVE  — notify when price crosses above threshold
  PRICE_BELOW  — notify when price drops below threshold
  RSI_ABOVE    — notify when RSI crosses above threshold (overbought warning)
  RSI_BELOW    — notify when RSI crosses below threshold (oversold / buy zone)
  SCORE_ABOVE  — notify when Weekly Score exceeds threshold

Alerts survive app restarts. Triggered alerts are deactivated and kept in history.
"""
import json
import numpy as np
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

from utils.cache import get_ticker_info, get_price_history

ALERTS_FILE = Path(__file__).parent.parent / ".alerts.json"

ALERT_TYPES = {
    "PRICE_ABOVE": "Price rises above $",
    "PRICE_BELOW": "Price falls below $",
    "RSI_ABOVE":   "RSI crosses above",
    "RSI_BELOW":   "RSI crosses below",
}


# ── Persistence ───────────────────────────────────────────────────────────────

def load_alerts() -> list[dict]:
    from utils.persist import load_json
    return load_json(ALERTS_FILE, default=[])


def save_alerts(alerts: list[dict]) -> None:
    from utils.persist import save_json
    save_json(ALERTS_FILE, alerts)


def add_alert(symbol: str, alert_type: str, threshold: float, note: str = "") -> None:
    alerts = load_alerts()
    alerts.append({
        "id":           datetime.now().isoformat(),
        "symbol":       symbol.upper().strip(),
        "type":         alert_type,
        "threshold":    threshold,
        "note":         note,
        "active":       True,
        "created_at":   datetime.now().strftime("%d/%m/%Y %H:%M"),
        "triggered_at": None,
        "triggered_val": None,
    })
    save_alerts(alerts)


def delete_alert(alert_id: str) -> None:
    alerts = [a for a in load_alerts() if a.get("id") != alert_id]
    save_alerts(alerts)


def clear_history() -> None:
    alerts = [a for a in load_alerts() if a.get("active")]
    save_alerts(alerts)


# ── RSI helper ────────────────────────────────────────────────────────────────

def _current_rsi(symbol: str) -> float | None:
    try:
        ph = get_price_history(symbol, period="3mo")
        if ph.empty or len(ph) < 15:
            return None
        from utils.indicators import rsi_last
        return rsi_last(ph["Close"].squeeze())
    except Exception:
        return None


# ── Check all active alerts ───────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)   # check every 5 minutes
def _fetch_price(symbol: str) -> float:
    info = get_ticker_info(symbol)
    return float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)


def check_alerts() -> list[dict]:
    """
    Evaluate all active alerts against current market data.
    Returns list of newly triggered alerts.
    Deactivates them in the JSON file.
    """
    alerts  = load_alerts()
    triggered = []
    updated   = False

    for a in alerts:
        if not a.get("active"):
            continue

        sym       = a["symbol"]
        threshold = float(a["threshold"])
        atype     = a["type"]
        current   = None

        try:
            if atype in ("PRICE_ABOVE", "PRICE_BELOW"):
                current = _fetch_price(sym)
            elif atype in ("RSI_ABOVE", "RSI_BELOW"):
                current = _current_rsi(sym)

            if current is None:
                continue

            fired = (
                (atype == "PRICE_ABOVE" and current >= threshold) or
                (atype == "PRICE_BELOW" and current <= threshold) or
                (atype == "RSI_ABOVE"   and current >= threshold) or
                (atype == "RSI_BELOW"   and current <= threshold)
            )

            if fired:
                a["active"]        = False
                a["triggered_at"]  = datetime.now().strftime("%d/%m/%Y %H:%M")
                a["triggered_val"] = round(current, 2)
                triggered.append({**a})
                updated = True

        except Exception:
            pass

    if updated:
        save_alerts(alerts)

    return triggered


# ── Automatic earnings-soon notifications ─────────────────────────────────────
# Scans watchlist + paper-portfolio holdings against the Finnhub earnings
# calendar. One-shot per (symbol, earnings_date) — remembered in .alerts.json
# under "seen_earnings" entries so the same report doesn't re-notify.

def _tracked_symbols() -> list[str]:
    """All symbols the user follows: watchlist + paper portfolio holdings."""
    syms: set[str] = set()
    try:
        from utils.persist import load_json
        base = Path(__file__).parent.parent
        wl = load_json(base / ".watchlist.json", default={})
        for s in (wl.get("symbols") or "").split(","):
            if s.strip():
                syms.add(s.strip().upper())
        pp = load_json(base / ".paper_portfolios.json", default={})
        for p in (pp.get("portfolios") or {}).values():
            syms.update(k.upper() for k in (p.get("holdings") or {}).keys())
    except Exception:
        pass
    return sorted(syms)


def check_earnings_soon(days_ahead: int = 7) -> list[dict]:
    """Returns newly-detected upcoming earnings for tracked symbols.
    Each: {symbol, date, days_until, hour}. Marks them seen so each
    (symbol, date) notifies once."""
    try:
        from modules.finnhub_data import get_earnings_for_symbols
        syms = _tracked_symbols()
        if not syms:
            return []
        upcoming = get_earnings_for_symbols(tuple(syms), days_ahead)
        if not upcoming:
            return []

        alerts = load_alerts()
        seen = {(a.get("symbol"), a.get("earnings_date"))
                for a in alerts if a.get("type") == "EARNINGS_SEEN"}

        new_events = []
        today = datetime.now().date()
        for e in upcoming:
            key = (e["symbol"], e["date"])
            if key in seen or not e["date"]:
                continue
            try:
                days_until = (datetime.strptime(e["date"], "%Y-%m-%d").date() - today).days
            except Exception:
                continue
            if days_until < 0:
                continue
            new_events.append({
                "symbol":     e["symbol"],
                "date":       e["date"],
                "days_until": days_until,
                "hour":       {"bmo": "before open", "amc": "after close"}.get(e.get("hour", ""), ""),
            })
            alerts.append({
                "id":            datetime.now().isoformat() + e["symbol"],
                "type":          "EARNINGS_SEEN",
                "symbol":        e["symbol"],
                "earnings_date": e["date"],
                "active":        False,
                "created_at":    datetime.now().strftime("%d/%m/%Y %H:%M"),
            })
        if new_events:
            save_alerts(alerts)
        return new_events
    except Exception:
        return []
