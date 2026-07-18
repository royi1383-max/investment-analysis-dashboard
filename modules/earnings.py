"""
Earnings Calendar — upcoming dates, EPS estimates, surprise history,
historical price reaction, BMO/AMC timing, and EPS trend data.
"""
import yfinance as yf
import pandas as pd
import streamlit as st
from datetime import date, datetime, timezone
from utils.cache import get_ticker_info, get_price_history


# ── BMO / AMC helper ──────────────────────────────────────────────────────────

def _detect_timing(ts) -> str:
    """
    'BMO' = Before Market Open (report time <= 12:00 UTC → pre-US-open)
    'AMC' = After Market Close (report time >= 14:00 UTC → post-US-close)
    '—'   = unknown
    """
    try:
        t = pd.Timestamp(ts)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        h = t.hour
        if h <= 10:
            return "BMO"
        if h >= 14:
            return "AMC"
    except Exception:
        pass
    return "—"


# ── Per-symbol earnings data ──────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_earnings_data(symbol: str) -> dict:
    """Full earnings profile for one symbol."""
    result = {"symbol": symbol}
    try:
        ticker = yf.Ticker(symbol)
        info   = get_ticker_info(symbol)
        result["name"]   = info.get("shortName", symbol)
        result["sector"] = info.get("sector", "")
        result["price"]  = info.get("currentPrice") or info.get("regularMarketPrice") or 0

        # ── Upcoming earnings date + timing ───────────────────────────────────
        try:
            cal = ticker.calendar
            if cal is not None:
                if isinstance(cal, dict):
                    raw_dates = cal.get("Earnings Date", [])
                    if not isinstance(raw_dates, list):
                        raw_dates = [raw_dates]
                    if raw_dates:
                        result["next_earnings"] = pd.Timestamp(raw_dates[0]).date()
                        result["timing"] = _detect_timing(raw_dates[0])
                    result["eps_estimate"] = cal.get("Earnings Average")
                    result["eps_high"]     = cal.get("Earnings High")
                    result["eps_low"]      = cal.get("Earnings Low")
                    result["rev_estimate"] = cal.get("Revenue Average")
                    result["rev_high"]     = cal.get("Revenue High")
                    result["rev_low"]      = cal.get("Revenue Low")
                elif hasattr(cal, "columns"):
                    if "Earnings Date" in cal.columns:
                        cal = cal.copy()
                        _ed_col = pd.to_datetime(cal["Earnings Date"])
                        if _ed_col.dt.tz is not None:
                            _ed_col = _ed_col.dt.tz_localize(None)
                        cal["Earnings Date"] = _ed_col
                        future = cal[_ed_col >= pd.Timestamp.now()]
                        if not future.empty:
                            row0 = future.sort_values("Earnings Date").iloc[0]
                            result["next_earnings"] = pd.Timestamp(row0["Earnings Date"]).date()
                            result["timing"] = _detect_timing(row0["Earnings Date"])
        except Exception:
            pass

        # ── Historical earnings + surprise + price reaction ───────────────────
        try:
            ed = ticker.earnings_dates
            if ed is not None and not ed.empty:
                rows = []
                eps_trend = []   # (date, reported_eps) pairs for trend chart
                for ts, row in ed.iterrows():
                    dt       = pd.Timestamp(ts).date()
                    eps_est  = row.get("EPS Estimate")
                    eps_act  = row.get("Reported EPS")
                    surprise = row.get("Surprise(%)")

                    # Price reaction: close on earnings day vs prior day
                    reaction = None
                    try:
                        ph = get_price_history(symbol, period="2y")
                        if not ph.empty:
                            c = ph["Close"].squeeze()
                            idx = c.index.normalize()
                            mask = idx.date == dt
                            if mask.any():
                                i = c.index[mask][0]
                                loc = c.index.get_loc(i)
                                if loc > 0:
                                    reaction = float(c.iloc[loc] / c.iloc[loc - 1] - 1) * 100
                    except Exception:
                        pass

                    rows.append({
                        "Date":              dt,
                        "EPS Estimate":      eps_est,
                        "Reported EPS":      eps_act,
                        "Surprise %":        round(float(surprise), 1) if pd.notna(surprise) else None,
                        "Price Reaction %":  round(reaction, 1)        if reaction is not None else None,
                    })

                    if pd.notna(eps_act):
                        eps_trend.append({"date": str(dt), "eps": round(float(eps_act), 2)})

                result["history"]   = rows[:8]
                result["eps_trend"] = list(reversed(eps_trend[:8]))  # oldest first

                # ── Beat stats from history ───────────────────────────────────
                beats = [r for r in rows if r.get("Surprise %") is not None]
                if beats:
                    n_beat   = sum(1 for r in beats if r["Surprise %"] > 0)
                    avg_surp = sum(r["Surprise %"] for r in beats) / len(beats)
                    react_n  = [r["Price Reaction %"] for r in beats
                                if r.get("Price Reaction %") is not None]
                    result["beat_rate"]    = round(n_beat / len(beats) * 100)
                    result["beat_n"]       = n_beat
                    result["beat_total"]   = len(beats)
                    result["avg_surprise"] = round(avg_surp, 1)
                    result["avg_reaction"] = round(sum(react_n) / len(react_n), 1) if react_n else None

        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return result


# ── Calendar (sorted list) ────────────────────────────────────────────────────

def get_calendar(symbols: list[str]) -> list[dict]:
    """
    Returns earnings data for all symbols with a known next earnings date,
    sorted soonest first (upcoming), then most recent past.
    """
    out = []
    for sym in symbols:
        d = get_earnings_data(sym)
        if d.get("next_earnings"):
            days = (d["next_earnings"] - date.today()).days
            d["days_until"] = days
            out.append(d)
    upcoming = sorted([r for r in out if r["days_until"] >= 0], key=lambda x: x["days_until"])
    past     = sorted([r for r in out if r["days_until"] <  0], key=lambda x: -x["days_until"])
    return upcoming + past
