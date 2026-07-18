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
            "buffett":   buffett_check(info),
            "munger":    munger_filter(symbol, info),
            "lynch":     lynch_check(info),
            "graham":    graham_check(info),
            "greenblatt": magic_formula(info),
            "canslim":   canslim_check(info, close, regime),
            "bogle":     bogle_test(close),
            "error":     None,
        }
    except Exception as e:
        return {"error": str(e)}


# ═══ Guru Checklists — value-investing legends, mechanically applied ══════════

def buffett_check(info: dict) -> dict:
    """Buffett: a WONDERFUL business (moat evidenced by ROE + margins + low debt)
    at a FAIR price (owner-earnings yield vs bonds)."""
    checks = []
    roe = info.get("returnOnEquity")
    gm  = info.get("grossMargins")
    pm  = info.get("profitMargins")
    d2e_raw = info.get("debtToEquity")
    d2e = (d2e_raw / 100 if d2e_raw and d2e_raw > 10 else d2e_raw)
    fcf, mc = info.get("freeCashflow"), info.get("marketCap")
    oe_yield = (fcf / mc * 100) if fcf and mc else None

    checks.append(("ROE >= 15% (compounding machine)",
                   roe is not None and roe >= 0.15,
                   f"{roe*100:.0f}%" if roe is not None else "N/A"))
    checks.append(("Gross margin >= 40% (pricing power / moat)",
                   gm is not None and gm >= 0.40,
                   f"{gm*100:.0f}%" if gm is not None else "N/A"))
    checks.append(("Net margin >= 10% (real profitability)",
                   pm is not None and pm >= 0.10,
                   f"{pm*100:.0f}%" if pm is not None else "N/A"))
    checks.append(("Debt/Equity <= 0.8 (no leverage crutch)",
                   d2e is not None and d2e <= 0.8,
                   f"{d2e:.2f}" if d2e is not None else "N/A"))
    checks.append(("Owner-earnings yield >= 4% (fair price)",
                   oe_yield is not None and oe_yield >= 4,
                   f"{oe_yield:.1f}%" if oe_yield is not None else "N/A"))

    passed = sum(1 for _, ok, _ in checks if ok)
    quality_passed = sum(1 for (_, ok, _) in checks[:4] if ok)
    if passed == 5:
        verdict = "WONDERFUL AT A FAIR PRICE — the full Buffett setup"
    elif quality_passed >= 3 and (oe_yield or 0) < 4:
        verdict = "WONDERFUL BUT PRICEY — quality is here, the price isn't. Patience."
    elif quality_passed >= 3:
        verdict = "QUALITY BUSINESS — most moat markers present"
    else:
        verdict = "NOT A BUFFETT BUSINESS — moat evidence missing"
    return {"checks": checks, "passed": passed, "total": 5, "verdict": verdict}


def munger_filter(symbol: str, info: dict) -> dict:
    """Munger inversion: don't be smart — avoid being stupid.
    Lists reasons NOT to own it; zero flags = passes the stupidity filter."""
    flags = []
    d2e_raw = info.get("debtToEquity")
    d2e = (d2e_raw / 100 if d2e_raw and d2e_raw > 10 else d2e_raw)
    if d2e is not None and d2e > 1.5:
        flags.append(f"Heavy leverage (D/E {d2e:.1f}) — 'all I want to know is where I will die'")
    roe = info.get("returnOnEquity")
    if roe is not None and roe < 0.08:
        flags.append(f"Low ROE ({roe*100:.0f}%) — mediocre business economics")
    fcf = info.get("freeCashflow")
    if fcf is not None and fcf < 0:
        flags.append("Burns cash — hope is not a strategy")
    try:
        from modules.earnings_quality import analyze as eq_analyze
        eq = eq_analyze(symbol)
        for name, status, detail in eq.get("checks", []):
            if status == "flag":
                flags.append(f"Accounting: {name} — {detail}")
    except Exception:
        pass
    short = info.get("shortPercentOfFloat")
    if short is not None and short > 0.15:
        flags.append(f"{short*100:.0f}% of float shorted — smart people are betting against it")

    verdict = ("PASSES THE STUPIDITY FILTER — no obvious way to lose"
               if not flags else
               f"{len(flags)} REASON{'S' if len(flags) > 1 else ''} TO STAY AWAY — invert, always invert")
    return {"flags": flags, "verdict": verdict}


def lynch_check(info: dict) -> dict:
    """Peter Lynch: classify the company (six categories), then pay a PEG that
    makes sense for its type. 'Know what you own and why.'"""
    growth = info.get("earningsGrowth") or info.get("revenueGrowth")
    g = (growth or 0) * 100
    mc = info.get("marketCap") or 0
    sector = info.get("sector") or ""
    peg = info.get("trailingPegRatio")
    if peg is None:
        fpe = info.get("forwardPE")
        peg = (fpe / g) if fpe and g > 3 else None

    if g < 0:
        cat, cat_note = "Turnaround", "Only interesting with a specific recovery catalyst — check debt survival first."
    elif g > 20:
        cat, cat_note = "Fast Grower", "Lynch's favorite — 20-25%+ growers bought at a sane PEG made his career."
    elif g >= 10:
        cat, cat_note = ("Stalwart" if mc > 50e9 else "Fast-ish Grower"), \
                        "Steady compounder — buy on dips, expect 30-50% moves, not ten-baggers."
    elif sector in ("Energy", "Basic Materials", "Industrials") and g < 10:
        cat, cat_note = "Cyclical", "Timing IS the thesis — buy when P/E looks HIGH (trough earnings), sell when it looks cheap."
    else:
        cat, cat_note = "Slow Grower", "Dividend story at best — Lynch mostly avoided these."

    if peg is not None and peg > 0:
        if peg < 1:
            peg_verdict = f"PEG {peg:.2f} — BARGAIN for the growth (Lynch buy zone)"
        elif peg <= 1.5:
            peg_verdict = f"PEG {peg:.2f} — fair price for the growth"
        elif peg <= 2:
            peg_verdict = f"PEG {peg:.2f} — paying up; needs flawless execution"
        else:
            peg_verdict = f"PEG {peg:.2f} — expensive vs growth; Lynch walks away"
    else:
        peg_verdict = "PEG not computable (no earnings or no growth)"

    return {"category": cat, "cat_note": cat_note, "growth_pct": round(g, 1),
            "peg": round(peg, 2) if peg else None, "peg_verdict": peg_verdict}


def graham_check(info: dict) -> dict:
    """Ben Graham: intrinsic value floor via the Graham Number
    sqrt(22.5 x EPS x BVPS) and a margin of safety below it."""
    import math as _m
    eps  = info.get("trailingEps")
    bvps = info.get("bookValue")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    cr = info.get("currentRatio")
    out = {"graham_number": None, "margin": None, "verdict": "", "current_ratio": cr}
    if not eps or not bvps or eps <= 0 or bvps <= 0 or not price:
        out["verdict"] = ("Not Graham territory — negative earnings or book value. "
                          "Graham only priced PROFITABLE, asset-backed businesses.")
        return out
    gn = _m.sqrt(22.5 * eps * bvps)
    margin = (gn / price - 1) * 100
    out["graham_number"] = round(gn, 2)
    out["margin"] = round(margin, 1)
    if margin >= 30:
        out["verdict"] = f"DEEP VALUE — {margin:.0f}% margin of safety below the Graham Number"
    elif margin >= 0:
        out["verdict"] = f"Near fair value — {margin:.0f}% margin of safety (Graham wanted 30%+)"
    else:
        out["verdict"] = (f"Price is {abs(margin):.0f}% ABOVE the Graham Number — "
                          f"growth stocks almost always are; this test suits mature businesses")
    return out


def magic_formula(info: dict) -> dict:
    """Greenblatt: rank by earnings yield (EBIT/EV) + return on capital
    (ROA proxy). Good business + cheap price, mechanically."""
    mc   = info.get("marketCap")
    debt = info.get("totalDebt") or 0
    cash = info.get("totalCash") or 0
    ebitda = info.get("ebitda")
    roa  = info.get("returnOnAssets")
    if not mc or not ebitda:
        return {"verdict": "Data unavailable (needs EBITDA + market cap)", "ey": None, "roc": None}
    ev = mc + debt - cash
    if ev <= 0:
        return {"verdict": "Negative enterprise value — check the data", "ey": None, "roc": None}
    ey  = ebitda / ev * 100
    roc = (roa or 0) * 100
    good_ey, good_roc = ey >= 8, roc >= 12
    if good_ey and good_roc:
        verdict = "MAGIC FORMULA CANDIDATE — good business at a cheap price"
    elif good_roc:
        verdict = "GOOD BUSINESS, NOT CHEAP — quality present, yield too low to rank"
    elif good_ey:
        verdict = "CHEAP BUT MEDIOCRE — yield without quality is often a value trap"
    else:
        verdict = "Ranks low on both Greenblatt factors"
    return {"ey": round(ey, 1), "roc": round(roc, 1), "verdict": verdict}


def canslim_check(info: dict, close, regime: dict) -> dict:
    """O'Neil CANSLIM — 7 letters, mechanically checked."""
    from utils.indicators import trailing_return
    checks = []
    qg = info.get("earningsQuarterlyGrowth")
    checks.append(("C — Current quarterly EPS growth >= 25%",
                   qg is not None and qg >= 0.25,
                   f"{qg*100:+.0f}%" if qg is not None else "N/A"))
    ag = info.get("earningsGrowth")
    checks.append(("A — Annual earnings growth >= 25%",
                   ag is not None and ag >= 0.25,
                   f"{ag*100:+.0f}%" if ag is not None else "N/A"))
    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    hi52 = info.get("fiftyTwoWeekHigh")
    near_high = bool(price and hi52 and price >= hi52 * 0.85)
    checks.append(("N — New-high territory (>= 85% of 52w high)",
                   near_high,
                   f"{price/hi52*100:.0f}% of high" if price and hi52 else "N/A"))
    flt = info.get("floatShares")
    checks.append(("S — Supply: float < 1B shares",
                   flt is not None and flt < 1e9,
                   f"{flt/1e6:,.0f}M float" if flt else "N/A"))
    r6m = trailing_return(close, 126) if close is not None and len(close) > 127 else None
    spy_r6m = None
    try:
        spy = get_price_history("SPY", period="1y")
        spy_r6m = trailing_return(spy["Close"].squeeze(), 126)
    except Exception:
        pass
    leader = r6m is not None and spy_r6m is not None and r6m > spy_r6m
    checks.append(("L — Leader: beats SPY over 6M",
                   leader,
                   f"{(r6m or 0)*100:+.0f}% vs SPY {(spy_r6m or 0)*100:+.0f}%"))
    inst = info.get("heldPercentInstitutions")
    checks.append(("I — Institutional sponsorship 20-90%",
                   inst is not None and 0.20 <= inst <= 0.90,
                   f"{inst*100:.0f}%" if inst is not None else "N/A"))
    regime_ok = (regime or {}).get("regime") in ("RISK-ON", "NEUTRAL")
    checks.append(("M — Market direction supportive",
                   regime_ok, (regime or {}).get("regime", "N/A")))

    passed = sum(1 for _, ok, _ in checks if ok)
    if passed >= 6:
        verdict = "CANSLIM SETUP — the full O'Neil breakout profile"
    elif passed >= 4:
        verdict = "PARTIAL — watch the failing letters; N and M matter most for timing"
    else:
        verdict = "NOT A CANSLIM STOCK right now"
    return {"checks": checks, "passed": passed, "total": 7, "verdict": verdict}


def bogle_test(close) -> dict:
    """Bogle's brutal question: did owning THIS even beat just indexing?"""
    from utils.indicators import trailing_return
    try:
        spy = get_price_history("SPY", period="2y")["Close"].squeeze()
        out = {}
        for label, days in (("1Y", 252), ("6M", 126)):
            s = trailing_return(close, days) if close is not None and len(close) > days else None
            b = trailing_return(spy, days) if len(spy) > days else None
            if s is not None and b is not None:
                out[label] = {"stock": round(s * 100, 1), "spy": round(b * 100, 1),
                              "beat": s > b}
        if not out:
            return {"verdict": "Insufficient history", "rows": {}}
        beats = sum(1 for v in out.values() if v["beat"])
        if beats == len(out):
            verdict = "Beat the index on every window — active pick justified (so far)"
        elif beats == 0:
            verdict = "Indexing won every window — Bogle wins again; is the thesis worth the effort?"
        else:
            verdict = "Mixed vs the index — the burden of proof is on the stock picker"
        return {"rows": out, "verdict": verdict}
    except Exception as e:
        return {"verdict": f"Unavailable: {e}", "rows": {}}
