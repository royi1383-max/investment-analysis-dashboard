"""
Alpha Vantage integration — NEWS_SENTIMENT.

Real per-article, per-ticker sentiment SCORES (-1..+1) from AV's NLP engine —
a major upgrade over naive keyword matching. Free tier = 25 requests/day, so:
  • 24h cache per symbol (one request per symbol per day, max)
  • graceful rate-limit handling (AV returns a "Note"/"Information" JSON)

AV label bands: ≤-0.35 Bearish · ≤-0.15 Somewhat-Bearish · <0.15 Neutral ·
<0.35 Somewhat-Bullish · ≥0.35 Bullish
"""
import json
import urllib.request
import streamlit as st

from config import ALPHA_VANTAGE_API_KEY


def _label(score: float) -> tuple[str, str]:
    if score <= -0.35:  return "BEARISH", "#ea3a44"
    if score <= -0.15:  return "SOMEWHAT BEARISH", "#f97316"
    if score < 0.15:    return "NEUTRAL", "#f0b90b"
    if score < 0.35:    return "SOMEWHAT BULLISH", "#a3e635"
    return "BULLISH", "#16c784"


@st.cache_data(ttl=86400, show_spinner=False)
def news_sentiment(symbol: str) -> dict:
    """Aggregated AV news sentiment for one ticker.
    Returns {avg_score, label, color, n_articles, dist, top} or {error}."""
    if not ALPHA_VANTAGE_API_KEY:
        return {"error": "No ALPHA_VANTAGE_API_KEY configured."}
    try:
        url = ("https://www.alphavantage.co/query?function=NEWS_SENTIMENT"
               f"&tickers={symbol}&limit=50&apikey={ALPHA_VANTAGE_API_KEY}")
        req = urllib.request.Request(url, headers={"User-Agent": "InvestmentDashboard"})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())

        if "feed" not in data:
            note = data.get("Note") or data.get("Information") or "No data returned"
            return {"error": f"Alpha Vantage: {str(note)[:120]}"}

        scored = []
        for art in data["feed"]:
            for ts in art.get("ticker_sentiment", []):
                if ts.get("ticker", "").upper() == symbol.upper():
                    try:
                        rel = float(ts.get("relevance_score", 0))
                        sc  = float(ts.get("ticker_sentiment_score", 0))
                        if rel >= 0.10:   # skip barely-related mentions
                            scored.append({
                                "title": art.get("title", ""),
                                "source": art.get("source", ""),
                                "time": (art.get("time_published", "") or "")[:8],
                                "score": sc, "relevance": rel,
                            })
                    except Exception:
                        continue
        if not scored:
            return {"error": "No relevant scored articles found."}

        w_sum = sum(a["relevance"] for a in scored)
        avg = sum(a["score"] * a["relevance"] for a in scored) / w_sum if w_sum else 0
        label, color = _label(avg)
        dist = {"bullish": sum(1 for a in scored if a["score"] >= 0.15),
                "neutral": sum(1 for a in scored if -0.15 < a["score"] < 0.15),
                "bearish": sum(1 for a in scored if a["score"] <= -0.15)}
        scored.sort(key=lambda a: -a["relevance"])
        return {"avg_score": round(avg, 3), "label": label, "color": color,
                "n_articles": len(scored), "dist": dist,
                "top": scored[:5], "error": None}
    except Exception as e:
        return {"error": f"Alpha Vantage fetch failed: {e}"}
