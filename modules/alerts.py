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
    try:
        if not ALERTS_FILE.exists():
            return []
        return json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_alerts(alerts: list[dict]) -> None:
    try:
        ALERTS_FILE.write_text(
            json.dumps(alerts, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


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
        c = ph["Close"].squeeze()
        d = c.diff()
        g = d.clip(lower=0).rolling(14).mean()
        l = (-d.clip(upper=0)).rolling(14).mean()
        rs = g / l.replace(0, np.nan)
        rsi = float(100 - 100 / (1 + rs.iloc[-1]))
        return round(rsi, 1)
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
