"""
Market Valuation Gauges — Shiller CAPE, Buffett Indicator, local Fear & Greed.

  • CAPE — scraped from multpl.com (Shiller's cyclically-adjusted P/E for the
    S&P 500). Historic mean ~17; >30 = historically expensive territory.
  • Buffett Indicator — Wilshire 5000 market cap ÷ US GDP (GDP via FRED when
    a key exists). ~100% historical fair zone; >180% = extreme.
  • Fear & Greed — CNN-style 0-100 composite built LOCALLY from five signals:
    VIX level, SPY momentum, market breadth (RSP vs SPY), credit appetite
    (HYG momentum), and safe-haven demand (gold vs its trend).

All graceful: any component that can't be fetched returns None and the UI
shows N/A instead of a fabricated number.
"""
import re
import urllib.request
import numpy as np
import streamlit as st

from config import FRED_API_KEY
from utils.cache import get_ticker_info, get_price_history
from utils.indicators import trailing_return


# ─── Shiller CAPE ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)
def get_shiller_cape() -> dict:
    """Current S&P 500 CAPE from multpl.com. Returns {cape, verdict, color}."""
    try:
        req = urllib.request.Request(
            "https://www.multpl.com/shiller-pe",
            headers={"User-Agent": "Mozilla/5.0 (InvestmentDashboard)"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
        m = re.search(r'Current Shiller PE Ratio[^0-9]*([0-9]{1,2}\.[0-9]{1,2})', html)
        if not m:
            m = re.search(r'<div id="current">.*?([0-9]{2}\.[0-9]{2})', html, re.S)
        if not m:
            return {"cape": None, "verdict": "Could not parse CAPE", "color": "#556070"}
        cape = float(m.group(1))
        if cape >= 35:
            v, c = ("EXTREME — top-decile valuations historically; 10y forward returns "
                    "from here have averaged near zero"), "#ea3a44"
        elif cape >= 28:
            v, c = ("EXPENSIVE — well above the ~17 historical mean; be selective, "
                    "valuation is a headwind for the decade"), "#f97316"
        elif cape >= 20:
            v, c = ("ABOVE AVERAGE — moderately rich vs history; stock-picking "
                    "matters more than beta here"), "#f0b90b"
        else:
            v, c = ("CHEAP vs HISTORY — below-average CAPE has preceded the best "
                    "10-year returns"), "#16c784"
        return {"cape": cape, "verdict": v, "color": c}
    except Exception as e:
        return {"cape": None, "verdict": f"Unavailable ({e})", "color": "#556070"}


# ─── Buffett Indicator ────────────────────────────────────────────────────────

@st.cache_data(ttl=43200, show_spinner=False)
def get_buffett_indicator() -> dict:
    """Wilshire 5000 / GDP. Needs FRED key for GDP; graceful N/A otherwise."""
    try:
        w = get_price_history("^W5000", period="5d")
        if w.empty:
            w = get_price_history("^FTW5000", period="5d")
        if w.empty:
            return {"ratio": None, "verdict": "Wilshire 5000 data unavailable", "color": "#556070"}
        wilshire = float(w["Close"].squeeze().iloc[-1])   # index level ≈ market cap in $B

        if not FRED_API_KEY:
            return {"ratio": None, "verdict": "Needs FRED_API_KEY for GDP", "color": "#556070"}
        import json as _json
        url = (f"https://api.stlouisfed.org/fred/series/observations?"
               f"series_id=GDP&api_key={FRED_API_KEY}&file_type=json&"
               f"sort_order=desc&limit=1")
        req = urllib.request.Request(url, headers={"User-Agent": "InvestmentDashboard"})
        data = _json.loads(urllib.request.urlopen(req, timeout=10).read())
        gdp_b = float(data["observations"][0]["value"])   # $ billions

        ratio = wilshire / gdp_b * 100
        if ratio >= 180:
            v, c = ("EXTREME — 'playing with fire' territory by Buffett's own words"), "#ea3a44"
        elif ratio >= 140:
            v, c = ("ELEVATED — market cap well ahead of the economy"), "#f97316"
        elif ratio >= 100:
            v, c = ("ABOVE FAIR — modestly rich vs GDP"), "#f0b90b"
        else:
            v, c = ("FAIR/CHEAP — market cap in line with or below the economy"), "#16c784"
        return {"ratio": round(ratio, 0), "verdict": v, "color": c}
    except Exception as e:
        return {"ratio": None, "verdict": f"Unavailable ({e})", "color": "#556070"}


# ─── Local Fear & Greed composite ─────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def get_fear_greed() -> dict:
    """0-100 composite from five locally-computed signals.
    0 = extreme fear · 100 = extreme greed. Components reported individually."""
    comps = {}

    # 1. VIX level (inverted: low VIX = greed)
    try:
        vix_info = get_ticker_info("^VIX")
        vix = float(vix_info.get("regularMarketPrice") or vix_info.get("currentPrice"))
        comps["VIX (fear gauge)"] = float(np.clip(100 - (vix - 10) * 4, 0, 100))
    except Exception:
        pass

    # 2. SPY momentum (1M return mapped)
    try:
        spy = get_price_history("SPY", period="6mo")["Close"].squeeze()
        r1m = trailing_return(spy, 21)
        if r1m is not None:
            comps["Momentum (SPY 1M)"] = float(np.clip(50 + r1m * 600, 0, 100))
    except Exception:
        pass

    # 3. Breadth: equal-weight vs cap-weight 1M (RSP beating SPY = healthy greed)
    try:
        rsp = get_price_history("RSP", period="6mo")["Close"].squeeze()
        r_rsp = trailing_return(rsp, 21)
        if r1m is not None and r_rsp is not None:
            comps["Breadth (RSP vs SPY)"] = float(np.clip(50 + (r_rsp - r1m) * 1200, 0, 100))
    except Exception:
        pass

    # 4. Credit appetite: HYG 1M momentum
    try:
        hyg = get_price_history("HYG", period="6mo")["Close"].squeeze()
        r_hyg = trailing_return(hyg, 21)
        if r_hyg is not None:
            comps["Credit appetite (HYG)"] = float(np.clip(50 + r_hyg * 1500, 0, 100))
    except Exception:
        pass

    # 5. Safe-haven demand: gold vs its own MA50 (gold bid = fear)
    try:
        gold = get_price_history("GC=F", period="6mo")["Close"].squeeze()
        if len(gold) >= 50:
            g_ext = float(gold.iloc[-1] / gold.rolling(50).mean().iloc[-1] - 1)
            comps["Safe haven (Gold vs trend)"] = float(np.clip(50 - g_ext * 800, 0, 100))
    except Exception:
        pass

    if not comps:
        return {"score": None, "label": "Unavailable", "color": "#556070", "components": {}}

    score = round(sum(comps.values()) / len(comps))
    if score >= 75:
        label, color = "EXTREME GREED", "#ea3a44"
        note = "Everyone is in the pool — historically a time to trim, not chase."
    elif score >= 58:
        label, color = "GREED", "#f97316"
        note = "Risk appetite is high; keep stops honest."
    elif score >= 42:
        label, color = "NEUTRAL", "#f0b90b"
        note = "No emotional edge either way — let the fundamentals decide."
    elif score >= 25:
        label, color = "FEAR", "#a3e635"
        note = "Discomfort is building — quality names go on sale in this zone."
    else:
        label, color = "EXTREME FEAR", "#16c784"
        note = "'Be greedy when others are fearful' — historically the best entry zone."
    return {"score": score, "label": label, "color": color,
            "note": note, "components": {k: round(v) for k, v in comps.items()}}
