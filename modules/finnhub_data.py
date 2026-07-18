"""
Finnhub integration — analyst ratings, price targets, news,
EPS estimates, earnings surprises, insider transactions.
Free tier: 60 calls/min. Key at finnhub.io.
"""
import finnhub
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from config import FINNHUB_API_KEY

_POSITIVE_WORDS = {
    "beat", "beats", "surpass", "surge", "soar", "rally", "gain", "rise",
    "strong", "record", "upgrade", "buy", "outperform", "growth", "profit",
    "bullish", "breakout", "all-time", "high", "exceed", "top",
}
_NEGATIVE_WORDS = {
    "miss", "misses", "fall", "drop", "decline", "loss", "cut", "lower",
    "weak", "downgrade", "sell", "underperform", "layoff", "lawsuit",
    "bearish", "warning", "risk", "concern", "slow", "disappoint",
}


def _client():
    if not FINNHUB_API_KEY:
        return None
    return finnhub.Client(api_key=FINNHUB_API_KEY)


def _sentiment(headline: str) -> str:
    words = set(headline.lower().split())
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    if pos > neg:   return "positive"
    if neg > pos:   return "negative"
    return "neutral"


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all(symbol: str) -> dict:
    c = _client()
    if not c:
        return {"error": "FINNHUB_API_KEY not configured"}

    result = {}

    # ── Analyst recommendations ───────────────────────────────────────────────
    try:
        recs = c.recommendation_trends(symbol)
        if recs:
            latest = recs[0]
            total = (latest.get("strongBuy", 0) + latest.get("buy", 0) +
                     latest.get("hold", 0) + latest.get("sell", 0) +
                     latest.get("strongSell", 0))
            bulls = latest.get("strongBuy", 0) + latest.get("buy", 0)
            bears = latest.get("sell", 0) + latest.get("strongSell", 0)
            result["recommendations"] = {
                "strong_buy":  latest.get("strongBuy", 0),
                "buy":         latest.get("buy", 0),
                "hold":        latest.get("hold", 0),
                "sell":        latest.get("sell", 0),
                "strong_sell": latest.get("strongSell", 0),
                "total":       total,
                "bulls":       bulls,
                "bears":       bears,
                "bull_pct":    round(bulls / total * 100, 1) if total else 0,
                "period":      latest.get("period", ""),
                "consensus":   _consensus_label(bulls, bears, total),
                "consensus_color": _consensus_color(bulls, bears, total),
            }
    except Exception as e:
        result["rec_error"] = str(e)

    # ── Price targets ─────────────────────────────────────────────────────────
    try:
        pt = c.price_target(symbol)
        result["price_target"] = {
            "low":        pt.get("targetLow"),
            "high":       pt.get("targetHigh"),
            "mean":       pt.get("targetMean"),
            "median":     pt.get("targetMedian"),
            "analysts":   pt.get("numberOfAnalysts", 0),
            "last_updated": pt.get("lastUpdated", ""),
        }
    except Exception as e:
        result["pt_error"] = str(e)

    # ── EPS estimates ─────────────────────────────────────────────────────────
    try:
        eps_est = c.eps_estimates(symbol, freq="quarterly")
        if eps_est and eps_est.get("data"):
            rows = []
            for e in eps_est["data"][:6]:
                rows.append({
                    "Period":         e.get("period", ""),
                    "EPS Estimate":   e.get("epsAvg"),
                    "EPS High":       e.get("epsHigh"),
                    "EPS Low":        e.get("epsLow"),
                    "# Analysts":     e.get("numberAnalysts", 0),
                })
            result["eps_estimates"] = pd.DataFrame(rows)
    except Exception as e:
        result["eps_error"] = str(e)

    # ── Earnings surprises ────────────────────────────────────────────────────
    try:
        surprises = c.company_earnings(symbol, limit=8)
        if surprises:
            rows = []
            for s in surprises:
                actual   = s.get("actual")
                estimate = s.get("estimate")
                surprise_pct = None
                if actual is not None and estimate and estimate != 0:
                    surprise_pct = (actual - estimate) / abs(estimate) * 100
                rows.append({
                    "Period":       s.get("period", ""),
                    "Actual EPS":   actual,
                    "Estimate":     estimate,
                    "Surprise %":   surprise_pct,
                })
            result["earnings_surprises"] = pd.DataFrame(rows)
    except Exception as e:
        result["surp_error"] = str(e)

    # ── Revenue estimates ─────────────────────────────────────────────────────
    try:
        rev_est = c.revenue_estimates(symbol, freq="quarterly")
        if rev_est and rev_est.get("data"):
            rows = []
            for r in rev_est["data"][:6]:
                rows.append({
                    "Period":           r.get("period", ""),
                    "Rev Estimate ($B)": round(r.get("revenueAvg", 0) / 1e9, 2) if r.get("revenueAvg") else None,
                    "Rev High ($B)":    round(r.get("revenueHigh", 0) / 1e9, 2) if r.get("revenueHigh") else None,
                    "Rev Low ($B)":     round(r.get("revenueLow", 0) / 1e9, 2) if r.get("revenueLow") else None,
                    "# Analysts":       r.get("numberAnalysts", 0),
                })
            result["rev_estimates"] = pd.DataFrame(rows)
    except Exception as e:
        result["rev_error"] = str(e)

    # ── News ──────────────────────────────────────────────────────────────────
    try:
        to_date   = datetime.today().strftime("%Y-%m-%d")
        from_date = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
        news = c.company_news(symbol, _from=from_date, to=to_date)
        if news:
            rows = []
            for n in news[:20]:
                ts = n.get("datetime", 0)
                date_str = datetime.fromtimestamp(ts).strftime("%b %d") if ts else ""
                headline = n.get("headline", "")
                rows.append({
                    "date":      date_str,
                    "headline":  headline,
                    "source":    n.get("source", ""),
                    "url":       n.get("url", ""),
                    "sentiment": _sentiment(headline),
                    "summary":   n.get("summary", "")[:200] if n.get("summary") else "",
                })
            result["news"] = rows
    except Exception as e:
        result["news_error"] = str(e)

    # ── Insider transactions ──────────────────────────────────────────────────
    try:
        insiders = c.stock_insider_transactions(symbol)
        if insiders and insiders.get("data"):
            rows = []
            for t in insiders["data"][:15]:
                rows.append({
                    "Name":       t.get("name", ""),
                    "Title":      t.get("officerTitle", ""),
                    "Type":       "BUY" if t.get("transactionCode") in ("P", "A") else "SELL",
                    "Shares":     t.get("share", 0),
                    "Price":      t.get("transactionPrice"),
                    "Value ($K)": round(t.get("share", 0) * (t.get("transactionPrice") or 0) / 1e3, 1),
                    "Date":       t.get("transactionDate", ""),
                })
            result["insiders"] = pd.DataFrame(rows)
    except Exception as e:
        result["insider_error"] = str(e)

    return result


def _consensus_label(bulls: int, bears: int, total: int) -> str:
    if total == 0: return "N/A"
    pct = bulls / total
    if pct >= 0.70: return "Strong Buy"
    if pct >= 0.55: return "Buy"
    if pct >= 0.40: return "Hold"
    if pct >= 0.25: return "Sell"
    return "Strong Sell"


def _consensus_color(bulls: int, bears: int, total: int) -> str:
    if total == 0: return "#556070"
    pct = bulls / total
    if pct >= 0.70: return "#16c784"
    if pct >= 0.55: return "#a3e635"
    if pct >= 0.40: return "#f0b90b"
    if pct >= 0.25: return "#f97316"
    return "#ea3a44"


# ── Earnings Calendar (for automatic earnings-soon alerts) ────────────────────

@st.cache_data(ttl=21600, show_spinner=False)   # 6h — calendar changes rarely
def get_earnings_calendar(days_ahead: int = 10) -> list[dict]:
    """Upcoming earnings in the next `days_ahead` days.
    Returns [{symbol, date, hour, eps_estimate}] — empty list on failure."""
    c = _client()
    if not c:
        return []
    try:
        frm = datetime.now().strftime("%Y-%m-%d")
        to  = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        cal = c.earnings_calendar(_from=frm, to=to, symbol="", international=False)
        out = []
        for e in cal.get("earningsCalendar", []):
            out.append({
                "symbol":       (e.get("symbol") or "").upper(),
                "date":         e.get("date", ""),
                "hour":         e.get("hour", ""),        # bmo / amc / dmh
                "eps_estimate": e.get("epsEstimate"),
            })
        return out
    except Exception:
        return []


@st.cache_data(ttl=21600, show_spinner=False)
def get_earnings_for_symbols(symbols: tuple, days_ahead: int = 10) -> list[dict]:
    """Filter the market-wide earnings calendar to the given symbols."""
    watch = {s.upper() for s in symbols}
    return [e for e in get_earnings_calendar(days_ahead) if e["symbol"] in watch]


# ── Insider Sentiment (MSPR) ──────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)   # 12h — monthly data
def get_insider_sentiment(symbol: str) -> list[dict]:
    """Finnhub insider sentiment (MSPR: -100..100, monthly).
    Positive MSPR = insiders net buying. Returns last 12 months,
    [{year, month, mspr, change}] oldest-first — empty list on failure."""
    c = _client()
    if not c:
        return []
    try:
        frm = (datetime.now() - timedelta(days=395)).strftime("%Y-%m-%d")
        to  = datetime.now().strftime("%Y-%m-%d")
        data = c.stock_insider_sentiment(symbol, frm, to)
        rows = data.get("data", [])
        rows.sort(key=lambda r: (r.get("year", 0), r.get("month", 0)))
        return [{
            "year":   r.get("year"),
            "month":  r.get("month"),
            "mspr":   r.get("mspr"),
            "change": r.get("change"),
        } for r in rows[-12:]]
    except Exception:
        return []
