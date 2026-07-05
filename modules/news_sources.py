"""
Additional free news sources for the Unified News Feed — none require an API key.
Each fetcher returns rows in the same shape as finnhub_data's news rows:
{date, headline, source, url, sentiment, summary}
"""
import requests
import streamlit as st
from datetime import datetime

from modules.finnhub_data import _sentiment

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_yahoo_news(symbol: str) -> list[dict]:
    """Yahoo Finance news via yfinance — no API key needed."""
    try:
        import yfinance as yf
        raw = yf.Ticker(symbol).news or []
        rows = []
        for item in raw[:15]:
            c = item.get("content", {}) or {}
            title = c.get("title", "")
            if not title:
                continue
            pub = c.get("pubDate", "")
            try:
                date_str = datetime.fromisoformat(pub.replace("Z", "+00:00")).strftime("%b %d")
            except Exception:
                date_str = ""
            url = (c.get("canonicalUrl") or {}).get("url", "") or (c.get("clickThroughUrl") or {}).get("url", "")
            rows.append({
                "date": date_str,
                "headline": title,
                "source": (c.get("provider") or {}).get("displayName", "Yahoo Finance"),
                "url": url,
                "sentiment": _sentiment(title),
                "summary": (c.get("summary") or "")[:200],
            })
        return rows
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_seekingalpha_news(symbol: str) -> list[dict]:
    """Seeking Alpha per-ticker RSS feed — no API key needed."""
    try:
        import xml.etree.ElementTree as ET
        r = requests.get(f"https://seekingalpha.com/api/sa/combined/{symbol}.xml",
                          headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        rows = []
        for item in root.findall(".//item")[:15]:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = (item.findtext("link") or "").strip()
            pub_raw = (item.findtext("pubDate") or "").strip()
            try:
                date_str = datetime.strptime(pub_raw[:16], "%a, %d %b %Y").strftime("%b %d")
            except Exception:
                date_str = ""
            rows.append({
                "date": date_str,
                "headline": title,
                "source": "Seeking Alpha",
                "url": link,
                "sentiment": _sentiment(title),
                "summary": "",
            })
        return rows
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def fetch_stocktwits(symbol: str) -> list[dict]:
    """StockTwits public symbol stream — community sentiment, no API key needed."""
    try:
        r = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json",
                          headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        data = r.json()
        rows = []
        for m in data.get("messages", [])[:15]:
            body = (m.get("body") or "").strip()
            if not body:
                continue
            tag = ((m.get("entities") or {}).get("sentiment") or {}).get("basic", "")
            if tag == "Bullish":
                sentiment = "positive"
            elif tag == "Bearish":
                sentiment = "negative"
            else:
                sentiment = _sentiment(body)
            try:
                date_str = datetime.strptime(m.get("created_at", ""), "%Y-%m-%dT%H:%M:%SZ").strftime("%b %d")
            except Exception:
                date_str = ""
            rows.append({
                "date": date_str,
                "headline": body[:140],
                "source": "StockTwits",
                "url": f"https://stocktwits.com/symbol/{symbol}",
                "sentiment": sentiment,
                "summary": body[140:340] if len(body) > 140 else "",
            })
        return rows
    except Exception:
        return []
