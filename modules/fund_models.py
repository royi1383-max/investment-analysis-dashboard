"""
Fund Models — quantitative rulebooks of famous hedge-fund / trading approaches,
applied deterministically (no AI) to a stock or portfolio.

Stock-level models:
  • Minervini SEPA Trend Template — 7-point trend checklist
  • Turtle / Donchian breakout — 20d & 55d channel signals
  • Managed-Futures Trend Following — MA50/MA200 + 12-1 momentum
  • Druckenmiller-style momentum/macro alignment
  • Kelly Criterion position sizing — from monthly return distribution
  • Factor Profile — Value / Momentum / Quality / Low-Vol / Size scores (1-10)

Portfolio-level:
  • Risk Parity (Dalio) — inverse-volatility weights vs current weights

All functions take pre-fetched data where possible to stay cache-friendly.
"""
import numpy as np
import pandas as pd
import streamlit as st

from utils.cache import get_ticker_info, get_price_history
from utils.indicators import trailing_return


# ─── Minervini SEPA Trend Template ────────────────────────────────────────────

def minervini_template(close: pd.Series) -> dict:
    """7-point trend template. Returns {checks: [(label, passed)], passed, total, verdict}."""
    out = {"checks": [], "passed": 0, "total": 7, "verdict": "N/A"}
    if close is None or len(close) < 210:
        out["verdict"] = "Insufficient history (need ~1y)"
        return out

    price  = float(close.iloc[-1])
    ma50   = float(close.rolling(50).mean().iloc[-1])
    ma150  = float(close.rolling(150).mean().iloc[-1])
    ma200  = float(close.rolling(200).mean().iloc[-1])
    ma200_prev = float(close.rolling(200).mean().iloc[-21])
    hi52   = float(close.iloc[-252:].max()) if len(close) >= 252 else float(close.max())
    lo52   = float(close.iloc[-252:].min()) if len(close) >= 252 else float(close.min())

    checks = [
        ("Price above MA150 and MA200",          price > ma150 and price > ma200),
        ("MA150 above MA200",                    ma150 > ma200),
        ("MA200 trending up (vs 1M ago)",        ma200 > ma200_prev),
        ("MA50 above MA150 and MA200",           ma50 > ma150 and ma50 > ma200),
        ("Price above MA50",                     price > ma50),
        ("Price ≥ 30% above 52-week low",        price >= lo52 * 1.30),
        ("Price within 25% of 52-week high",     price >= hi52 * 0.75),
    ]
    out["checks"] = checks
    out["passed"] = sum(1 for _, ok in checks if ok)
    if out["passed"] == 7:
        out["verdict"] = "FULL PASS — institutional-grade uptrend (Stage 2)"
    elif out["passed"] >= 5:
        out["verdict"] = "PARTIAL — trend forming, watch the failing criteria"
    else:
        out["verdict"] = "FAIL — not in a Stage-2 uptrend; Minervini would not buy"
    return out


# ─── Turtle / Donchian breakout ───────────────────────────────────────────────

def turtle_signals(close: pd.Series) -> dict:
    """Classic Turtle rules: S1 = 20d breakout (exit 10d), S2 = 55d breakout (exit 20d)."""
    out = {"s1": "N/A", "s2": "N/A", "hi20": None, "hi55": None,
           "lo10": None, "lo20": None, "price": None}
    if close is None or len(close) < 60:
        return out
    price = float(close.iloc[-1])
    # Channels computed on data excluding today (breakout = today crosses yesterday's channel)
    prev = close.iloc[:-1]
    hi20 = float(prev.iloc[-20:].max());  lo10 = float(prev.iloc[-10:].min())
    hi55 = float(prev.iloc[-55:].max());  lo20 = float(prev.iloc[-20:].min())
    out.update({"price": price, "hi20": hi20, "hi55": hi55, "lo10": lo10, "lo20": lo20})

    out["s1"] = ("LONG BREAKOUT — price above 20d high" if price > hi20 else
                 "EXIT ZONE — price below 10d low" if price < lo10 else
                 f"IN CHANNEL — {((price/hi20)-1)*100:+.1f}% from 20d breakout")
    out["s2"] = ("LONG BREAKOUT — price above 55d high" if price > hi55 else
                 "EXIT ZONE — price below 20d low" if price < lo20 else
                 f"IN CHANNEL — {((price/hi55)-1)*100:+.1f}% from 55d breakout")
    return out


# ─── Managed-futures trend following ──────────────────────────────────────────

def trend_following(close: pd.Series) -> dict:
    """MA rules + 12-1 momentum (skip last month, standard academic construction)."""
    out = {"signal": "N/A", "detail": "", "mom_12_1": None}
    if close is None or len(close) < 260:
        out["detail"] = "Insufficient history (need ~1y)"
        return out
    price = float(close.iloc[-1])
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])
    mom_12_1 = float(close.iloc[-21] / close.iloc[-252] - 1)   # 12M momentum excluding last month
    out["mom_12_1"] = mom_12_1

    above = price > ma200
    golden = ma50 > ma200
    mom_pos = mom_12_1 > 0
    votes = sum([above, golden, mom_pos])
    if votes == 3:
        out["signal"] = "LONG"
        out["detail"] = "All trend rules aligned: price>MA200, MA50>MA200, 12-1 momentum positive"
    elif votes == 0:
        out["signal"] = "SHORT/AVOID"
        out["detail"] = "All trend rules bearish — a trend follower would be short or flat"
    else:
        out["signal"] = "MIXED"
        out["detail"] = (f"{votes}/3 rules bullish — "
                         f"price {'>' if above else '<'}MA200, "
                         f"MA50 {'>' if golden else '<'}MA200, "
                         f"12-1 momentum {mom_12_1*100:+.1f}%")
    return out


# ─── Kelly criterion position sizing ──────────────────────────────────────────

def kelly_sizing(close: pd.Series) -> dict:
    """Kelly fraction from monthly return distribution (5y max).
    f* = W - (1-W)/R where W=win rate, R=avg win/avg loss.
    Reported with half-Kelly (industry practice)."""
    out = {"kelly": None, "half_kelly": None, "win_rate": None,
           "payoff": None, "n_months": 0, "note": ""}
    if close is None or len(close) < 130:
        out["note"] = "Insufficient history"
        return out
    monthly = close.resample("ME").last().pct_change(fill_method=None).dropna() \
        if isinstance(close.index, pd.DatetimeIndex) else pd.Series(dtype=float)
    if len(monthly) < 12:
        out["note"] = "Insufficient monthly data"
        return out
    wins   = monthly[monthly > 0]
    losses = monthly[monthly < 0]
    if losses.empty or wins.empty:
        out["note"] = "Return distribution too one-sided to size"
        return out
    w = len(wins) / len(monthly)
    r = float(wins.mean() / abs(losses.mean()))
    kelly = w - (1 - w) / r
    out.update({
        "kelly":      round(kelly * 100, 1),
        "half_kelly": round(max(0.0, kelly / 2) * 100, 1),
        "win_rate":   round(w * 100, 1),
        "payoff":     round(r, 2),
        "n_months":   len(monthly),
        "note":       ("Negative Kelly — the historical edge is negative; "
                       "no position is mathematically justified" if kelly <= 0 else
                       "Half-Kelly is the practical cap — full Kelly overbets on estimation error"),
    })
    return out


# ─── Factor profile ───────────────────────────────────────────────────────────

def factor_profile(symbol: str, info: dict, close: pd.Series) -> dict:
    """Scores 1-10 per factor bucket. Which quant-fund style buckets fit this stock."""
    scores = {}

    # Value — forward PE and P/S (lower = higher score)
    fpe = info.get("forwardPE")
    ps  = None
    mc, rev = info.get("marketCap"), info.get("totalRevenue")
    if mc and rev and rev > 0:
        ps = mc / rev
    v = 5.0
    if fpe and fpe > 0:
        v = 9 if fpe < 12 else 7.5 if fpe < 18 else 6 if fpe < 25 else 4 if fpe < 40 else 2
    if ps is not None:
        ps_s = 9 if ps < 2 else 7 if ps < 5 else 5 if ps < 10 else 3 if ps < 20 else 1.5
        v = (v + ps_s) / 2
    scores["Value"] = round(v, 1)

    # Momentum — 12-1 and 6M
    mom = 5.0
    if close is not None and len(close) >= 260:
        m121 = float(close.iloc[-21] / close.iloc[-252] - 1)
        r6m  = trailing_return(close, 126) or 0
        mom  = 5 + m121 * 8 + r6m * 4
    scores["Momentum"] = round(max(1, min(10, mom)), 1)

    # Quality — gross margin, profit margin, ROE
    q_parts = []
    gm  = info.get("grossMargins")
    pm  = info.get("profitMargins")
    roe = info.get("returnOnEquity")
    if gm  is not None: q_parts.append(min(10, max(1, gm * 12)))
    if pm  is not None: q_parts.append(min(10, max(1, 5 + pm * 20)))
    if roe is not None: q_parts.append(min(10, max(1, 5 + roe * 12)))
    scores["Quality"] = round(sum(q_parts) / len(q_parts), 1) if q_parts else 5.0

    # Low Volatility — beta + realized vol
    lv = 5.0
    beta = info.get("beta")
    if beta is not None:
        lv = 9 if beta < 0.8 else 7 if beta < 1.0 else 5 if beta < 1.3 else 3 if beta < 1.8 else 1.5
    if close is not None and len(close) >= 63:
        ann_vol = float(close.pct_change(fill_method=None).iloc[-63:].std() * np.sqrt(252))
        vol_s = 9 if ann_vol < 0.20 else 7 if ann_vol < 0.30 else 5 if ann_vol < 0.45 else 3 if ann_vol < 0.65 else 1.5
        lv = (lv + vol_s) / 2
    scores["Low Vol"] = round(lv, 1)

    # Size — small caps score higher on the size factor
    sz = 5.0
    if mc:
        sz = 9 if mc < 2e9 else 7.5 if mc < 10e9 else 6 if mc < 50e9 else 4 if mc < 200e9 else 2
    scores["Size"] = round(sz, 1)

    # Style fit summary
    fits = []
    if scores["Momentum"] >= 7 and scores["Quality"] >= 6:
        fits.append("Momentum/growth funds (Driehaus-style)")
    if scores["Value"] >= 7:
        fits.append("Value funds (Klarman/Greenblatt-style)")
    if scores["Quality"] >= 7.5 and scores["Low Vol"] >= 6:
        fits.append("Quality-compounder funds (Akre/Terry Smith-style)")
    if scores["Low Vol"] >= 7:
        fits.append("Low-vol / defensive strategies")
    if scores["Size"] >= 7 and scores["Momentum"] >= 6:
        fits.append("Small-cap momentum strategies")
    if not fits:
        fits.append("No clean factor-bucket fit — falls between styles")

    return {"scores": scores, "style_fits": fits}


# ─── Druckenmiller-style verdict ──────────────────────────────────────────────

def druckenmiller_check(close: pd.Series, regime: dict) -> dict:
    """Druckenmiller rules of thumb: ride strong momentum WITH macro tailwind,
    concentrate when aligned, cut fast when the tape turns."""
    out = {"verdict": "N/A", "points": []}
    if close is None or len(close) < 130:
        return out
    r3m = trailing_return(close, 63)
    r6m = trailing_return(close, 126)
    ma50  = float(close.rolling(50).mean().iloc[-1])
    price = float(close.iloc[-1])
    regime_name = (regime or {}).get("regime", "NEUTRAL")

    mom_strong = (r3m or 0) > 0.10 and (r6m or 0) > 0.15
    tape_ok    = price > ma50
    macro_ok   = regime_name == "RISK-ON"

    pts = []
    pts.append(("✅" if mom_strong else "❌",
                f"Momentum: 3M {(r3m or 0)*100:+.1f}%, 6M {(r6m or 0)*100:+.1f}% "
                f"({'strong' if mom_strong else 'not strong enough'})"))
    pts.append(("✅" if tape_ok else "❌",
                f"Tape: price {'above' if tape_ok else 'below'} MA50 — "
                f"{'ride it' if tape_ok else 'never fight the tape'}"))
    pts.append(("✅" if macro_ok else "⚠️",
                f"Macro: regime is {regime_name} — "
                f"{'liquidity tailwind' if macro_ok else 'no clear macro tailwind'}"))
    out["points"] = pts

    n_ok = sum(1 for e, _ in pts if e == "✅")
    if n_ok == 3:
        out["verdict"] = "CONCENTRATE — momentum + tape + macro aligned. 'When you have conviction, bet big.'"
    elif n_ok == 2:
        out["verdict"] = "HOLD/PROBE — partial alignment. Normal position size, tighten stops."
    else:
        out["verdict"] = "STAND ASIDE — 'The first rule is capital preservation.' No edge here now."
    return out


# ─── Portfolio: Risk Parity (Dalio) ───────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def risk_parity_weights(symbols: tuple) -> dict:
    """Inverse-volatility weights (simplified risk parity, 6M daily vol).
    Returns {symbol: {vol_ann, rp_weight}} — empty on failure."""
    vols = {}
    for sym in symbols:
        try:
            ph = get_price_history(sym, period="6mo")
            c  = ph["Close"].squeeze()
            vol = float(c.pct_change(fill_method=None).dropna().std() * np.sqrt(252))
            if vol > 0:
                vols[sym] = vol
        except Exception:
            continue
    if not vols:
        return {}
    inv_sum = sum(1 / v for v in vols.values())
    return {s: {"vol_ann": round(v * 100, 1),
                "rp_weight": round((1 / v) / inv_sum * 100, 1)}
            for s, v in vols.items()}


# ─── Bundle for the Analyze tab ───────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def analyze_stock(symbol: str) -> dict:
    """Run all stock-level fund models for one symbol."""
    try:
        info = get_ticker_info(symbol)
        ph   = get_price_history(symbol, period="2y")
        close = ph["Close"].squeeze() if not ph.empty else None
        if close is None or close.empty:
            return {"error": f"No price history for {symbol}."}
        try:
            from modules.market_context import get_regime
            regime = get_regime()
        except Exception:
            regime = {}
        return {
            "minervini": minervini_template(close),
            "turtle":    turtle_signals(close),
            "trend":     trend_following(close),
            "kelly":     kelly_sizing(close),
            "factors":   factor_profile(symbol, info, close),
            "druck":     druckenmiller_check(close, regime),
            "error":     None,
        }
    except Exception as e:
        return {"error": str(e)}
