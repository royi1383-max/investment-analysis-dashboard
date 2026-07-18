"""
Sector & Peer comparison module.
"""
import pandas as pd
import numpy as np
import streamlit as st
from utils.cache import get_ticker_info, get_price_history
from config import PEER_GROUPS


def _get_peers(symbol: str, info: dict) -> list[str]:
    if symbol.upper() in PEER_GROUPS:
        return PEER_GROUPS[symbol.upper()]
    # Fallback: ask Claude Haiku for direct competitors
    try:
        from config import ANTHROPIC_API_KEY
        if not ANTHROPIC_API_KEY:
            return []
        import json as _json
        from utils.claude_client import get_client, extract_json, ENGLISH_ENFORCEMENT
        client = get_client()
        if client is None:
            return []
        name     = info.get("longName", symbol)
        sector   = info.get("sector", "")
        industry = info.get("industry", "")
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content":
                f"List 5 US-listed stock ticker symbols that are direct peers of {name} ({symbol}), "
                f"sector: {sector}, industry: {industry}. "
                f"{ENGLISH_ENFORCEMENT} "
                f"Return ONLY a JSON array, e.g. [\"CRM\",\"NOW\",\"SAP\"]. No explanation."}],
        )
        peers = _json.loads(extract_json(msg.content[0].text))
        if isinstance(peers, list):
            return [p.upper() for p in peers if isinstance(p, str)][:5]
    except Exception:
        pass
    return []


def _perf(symbol: str, days: int) -> float | None:
    df = get_price_history(symbol, period="1y")
    if df.empty or len(df) < days + 1:
        return None
    close = df["Close"].squeeze()
    return float(close.iloc[-1] / close.iloc[-days] - 1)


@st.cache_data(ttl=3600, show_spinner=False)
def analyze(symbol: str) -> dict:
    info  = get_ticker_info(symbol)
    peers = _get_peers(symbol, info)

    symbols = [symbol.upper()] + [p for p in peers if p != symbol.upper()][:5]

    rows = []
    for sym in symbols:
        i = get_ticker_info(sym)
        r1m  = _perf(sym, 21)
        r3m  = _perf(sym, 63)
        r1y  = _perf(sym, 252)
        rows.append({
            "Ticker":       sym,
            "Name":         i.get("shortName", sym),
            "Market Cap":   i.get("marketCap"),
            "P/S":          (i.get("marketCap", 0) / i.get("totalRevenue", 1)) if i.get("totalRevenue") else None,
            "Fwd P/E":      i.get("forwardPE"),
            "PEG":          i.get("pegRatio"),
            "Rev Growth":   i.get("revenueGrowth"),
            "Gross Margin": i.get("grossMargins"),
            "1M Return":    r1m,
            "3M Return":    r3m,
            "1Y Return":    r1y,
        })

    df = pd.DataFrame(rows)

    # Score: how does ticker rank among peers on Rev Growth + 3M momentum?
    score = 5
    if len(df) > 1 and "Rev Growth" in df.columns:
        ticker_row = df[df["Ticker"] == symbol.upper()]
        if not ticker_row.empty:
            rev_rank = df["Rev Growth"].rank(ascending=True, na_option="bottom")
            mom_rank = df["3M Return"].rank(ascending=True, na_option="bottom")
            n = len(df)
            idx = ticker_row.index[0]
            rev_pct = rev_rank[idx] / n
            mom_pct = mom_rank[idx] / n
            score = round((rev_pct * 0.6 + mom_pct * 0.4) * 9 + 1, 2)

    return {
        "score":  score,
        "df":     df,
        "peers":  peers,
    }
