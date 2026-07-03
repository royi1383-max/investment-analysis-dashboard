"""
Market Regime Detection — reads live macro signals to classify
the current risk environment.

Regime:
  RISK-ON   — favorable conditions, broad scan qualifies
  NEUTRAL   — mixed signals, selective entry only
  RISK-OFF  — elevated risk, only strongest setups qualify

Signals used (all via yfinance, no API key needed):
  ^VIX   — fear gauge
  ^GSPC  — S&P 500 trend (MA50/MA200)
  ^TNX   — 10-year Treasury yield direction
  QQQ    — Nasdaq momentum
  ^IXIC  — Nasdaq composite
"""
import numpy as np
import streamlit as st
from utils.cache import get_ticker_info, get_price_history


@st.cache_data(ttl=900, show_spinner=False)
def get_regime() -> dict:
    signals = {}

    # ── VIX ──────────────────────────────────────────────────────────────────
    try:
        vix_info = get_ticker_info("^VIX")
        vix = float(vix_info.get("regularMarketPrice") or vix_info.get("currentPrice") or 20)
    except Exception:
        vix = 20.0
    signals["vix"] = round(vix, 2)

    # ── S&P 500 trend ─────────────────────────────────────────────────────────
    spy_data_ok = False
    try:
        spy = get_price_history("^GSPC", period="1y")
        c   = spy["Close"].squeeze()
        spy_price     = float(c.iloc[-1])
        spy_ma50      = float(c.rolling(50).mean().iloc[-1])
        spy_ma200     = float(c.rolling(200).mean().iloc[-1])
        spy_r1m       = float(c.iloc[-1] / c.iloc[-21] - 1) if len(c) >= 22 else 0.0
        spy_r3m       = float(c.iloc[-1] / c.iloc[-63] - 1) if len(c) >= 64 else 0.0
        spy_above_200 = spy_price > spy_ma200
        spy_above_50  = spy_price > spy_ma50
        spy_data_ok   = True
        signals.update({
            "spy_price": round(spy_price, 2),
            "spy_ma200": round(spy_ma200, 2),
            "spy_above_200": spy_above_200,
            "spy_above_50":  spy_above_50,
            "spy_r1m": round(spy_r1m, 4),
            "spy_r3m": round(spy_r3m, 4),
        })
    except Exception:
        signals.update({"spy_above_200": None, "spy_above_50": None, "spy_r1m": None, "spy_r3m": None})

    # ── 10-Year Treasury yield direction ──────────────────────────────────────
    try:
        tnx = get_price_history("^TNX", period="3mo")
        tc  = tnx["Close"].squeeze()
        tnx_now    = float(tc.iloc[-1])
        tnx_1m_ago = float(tc.iloc[-21]) if len(tc) >= 22 else tnx_now
        # Significant yield rise = headwind for growth
        tnx_rising = tnx_now > tnx_1m_ago * 1.04
        tnx_high   = tnx_now > 4.5    # absolute high = extra headwind
        signals.update({"tnx": round(tnx_now, 2), "tnx_rising": tnx_rising, "tnx_high": tnx_high})
    except Exception:
        signals.update({"tnx": 4.2, "tnx_rising": False, "tnx_high": False})

    # ── Nasdaq (QQQ) momentum ─────────────────────────────────────────────────
    qqq_data_ok = False
    try:
        qqq = get_price_history("QQQ", period="3mo")
        qc  = qqq["Close"].squeeze()
        qqq_r1m  = float(qc.iloc[-1] / qc.iloc[-21] - 1) if len(qc) >= 22 else 0.0
        qqq_ma50 = float(qc.rolling(50).mean().iloc[-1])
        qqq_above_50 = float(qc.iloc[-1]) > qqq_ma50
        qqq_data_ok  = True
        signals.update({"qqq_r1m": round(qqq_r1m, 4), "qqq_above_50": qqq_above_50})
    except Exception:
        signals.update({"qqq_r1m": None, "qqq_above_50": None})

    # ── Compute risk-on score (–5 to +8) ─────────────────────────────────────
    s = 0

    # VIX
    if vix < 16:    s += 2
    elif vix < 20:  s += 1
    elif vix > 30:  s -= 3
    elif vix > 25:  s -= 2
    elif vix > 22:  s -= 1

    # SPY trend (only scored when data is available)
    if spy_data_ok:
        if signals["spy_above_200"]: s += 2
        if signals["spy_above_50"]:  s += 1
        if (signals.get("spy_r1m") or 0) > 0.03: s += 1

    # Rates
    if signals["tnx_rising"]: s -= 1
    if signals["tnx_high"]:   s -= 1

    # Nasdaq leadership (only scored when data is available)
    if qqq_data_ok:
        if (signals.get("qqq_r1m") or 0) > 0.03: s += 1
        if signals["qqq_above_50"]:               s += 1

    # ── Classify ──────────────────────────────────────────────────────────────
    if s >= 5:
        regime        = "RISK-ON"
        regime_color  = "#16c784"
        regime_emoji  = "🟢"
        regime_desc   = "Market in uptrend, low fear — broad universe qualifies"
        # Entry thresholds for this regime
        thresholds = {"fundamental": 4.5, "technical": 4.5, "bull_pct": 48, "r3m_min": -0.08}
    elif s >= 1:
        regime        = "NEUTRAL"
        regime_color  = "#f0b90b"
        regime_emoji  = "🟡"
        regime_desc   = "Mixed signals — focus on quality names with clear setups"
        thresholds = {"fundamental": 5.0, "technical": 5.0, "bull_pct": 55, "r3m_min": -0.02}
    else:
        regime        = "RISK-OFF"
        regime_color  = "#ea3a44"
        regime_emoji  = "🔴"
        regime_desc   = "Elevated risk — only highest-quality, strong-momentum setups qualify"
        thresholds = {"fundamental": 6.0, "technical": 5.5, "bull_pct": 62, "r3m_min": 0.03}

    return {
        "regime":       regime,
        "regime_color": regime_color,
        "regime_emoji": regime_emoji,
        "regime_desc":  regime_desc,
        "score":        s,
        "thresholds":   thresholds,
        "signals":      signals,
    }
