"""
Metric Context — educational, context-aware metric ranges.

"Is a P/E of 35 high?" — depends on the stock. This module asks Claude Haiku
to assess ~10 key metrics FOR THIS SPECIFIC STOCK: what a healthy range looks
like given its sector, size, growth profile, margin structure and the current
macro regime — so the user learns to read numbers in context, not absolutes.
Also provides DETERMINISTIC in-context interpreters (no AI, instant):
  rsi_in_context(close)  — trend-regime-adjusted RSI bands + integrated verdict
                           (RSI 74 in a strong uptrend ≠ RSI 74 in a downtrend)
"""
import json
import pandas as pd
import streamlit as st

from utils.claude_client import get_client, extract_json, ENGLISH_ENFORCEMENT


# ─── Deterministic: RSI in trend context ──────────────────────────────────────

def rsi_in_context(close: pd.Series) -> dict:
    """
    Judge the CURRENT RSI against the stock's own trend regime — the healthy
    band shifts with trend. Integrates: trend regime (MA50/MA200), extension
    above MA50, and 1M return, into one verdict.

    Returns {rsi, regime, normal_band, verdict, verdict_color, detail, tooltip}
    or {"error": ...}.
    """
    try:
        from utils.indicators import rsi_last, trailing_return
        if close is None or len(close) < 60:
            return {"error": "Insufficient history"}
        rsi = rsi_last(close)
        if rsi is None:
            return {"error": "RSI not computable"}

        price = float(close.iloc[-1])
        ma50  = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        ma200_prev = float(close.rolling(200).mean().iloc[-21]) if len(close) >= 221 else None
        ext50 = (price / ma50 - 1) * 100 if ma50 else 0.0
        r1m   = (trailing_return(close, 21) or 0) * 100

        # ── Trend regime → the band that counts as "normal" here ─────────────
        if ma200 and ma50 and price > ma50 > ma200 and (ma200_prev is None or ma200 > ma200_prev):
            regime, band_lo, band_hi = "Strong uptrend", 45, 75
        elif ma200 and price > ma200:
            regime, band_lo, band_hi = "Uptrend / consolidation", 38, 68
        elif ma200 and price < ma200 and ma50 and ma50 < ma200:
            regime, band_lo, band_hi = "Downtrend", 25, 55
        else:
            regime, band_lo, band_hi = "Sideways / unclear", 35, 65

        # ── Integrated verdict (RSI × trend × extension) ─────────────────────
        stretched_ext = ext50 > 15
        if rsi > band_hi + 10:
            verdict, color = "VERY STRETCHED", "#ea3a44"
            detail = (f"RSI {rsi:.0f} is far above even the {band_lo}-{band_hi} band that a "
                      f"{regime.lower()} justifies. Combined with {ext50:+.0f}% extension above "
                      f"MA50, risk/reward for NEW buying is poor — wait for a reset, don't chase.")
        elif rsi > band_hi:
            if regime == "Strong uptrend" and not stretched_ext:
                verdict, color = "HOT BUT HEALTHY", "#f0b90b"
                detail = (f"RSI {rsi:.0f} is above the normal {band_lo}-{band_hi} band, but in a "
                          f"strong uptrend with only {ext50:+.0f}% extension above MA50 this often "
                          f"reflects genuine momentum, not a top. Holders stay; new buyers size "
                          f"small or wait for the {band_lo}s.")
            else:
                verdict, color = "STRETCHED", "#f97316"
                bear_note = ("In a downtrend, high RSI usually marks a bear-market rally, not a breakout."
                             if regime == "Downtrend" else
                             "Extension + high RSI = elevated pullback odds.")
                detail = (f"RSI {rsi:.0f} exceeds the {band_lo}-{band_hi} band appropriate for a "
                          f"{regime.lower()}, and price is {ext50:+.0f}% above MA50. {bear_note}")
        elif rsi < band_lo - 10:
            verdict, color = "WASHED OUT", "#4da3ff"
            zone_note = ("In an uptrend this is historically a strong buy zone."
                         if "uptrend" in regime.lower() else
                         "In a downtrend, oversold can stay oversold — wait for a base, not just a low RSI.")
            detail = (f"RSI {rsi:.0f} is far below the {band_lo}-{band_hi} band — capitulation "
                      f"territory. {zone_note}")
        elif rsi < band_lo:
            if "uptrend" in regime.lower():
                verdict, color = "PULLBACK ZONE", "#16c784"
                detail = (f"RSI {rsi:.0f} sits below the normal {band_lo}-{band_hi} band — a "
                          f"pullback within an intact uptrend. The classic add zone IF the trend "
                          f"thesis still holds.")
            else:
                verdict, color = "WEAK", "#f97316"
                detail = (f"RSI {rsi:.0f} below the {band_lo}-{band_hi} band — weak momentum "
                          f"consistent with the broken trend.")
        else:
            verdict, color = "NORMAL FOR THIS TREND", "#16c784"
            detail = (f"RSI {rsi:.0f} is inside the {band_lo}-{band_hi} band that fits a "
                      f"{regime.lower()} — momentum neither stretched nor broken. "
                      f"1M return {r1m:+.1f}%, extension vs MA50 {ext50:+.0f}%.")

        tooltip = (f"RSI {rsi:.0f} · {regime}. Normal band HERE: {band_lo}-{band_hi} "
                   f"(not the textbook 30-70 — the band shifts with trend). "
                   f"{verdict}: {detail}")

        return {"rsi": rsi, "regime": regime, "normal_band": (band_lo, band_hi),
                "ext50": round(ext50, 1), "r1m": round(r1m, 1),
                "verdict": verdict, "verdict_color": color,
                "detail": detail, "tooltip": tooltip}
    except Exception as e:
        return {"error": str(e)}


# ─── Deterministic interpreters for ALL key metrics ───────────────────────────
# Shared shape: {value_s, band_s, verdict, color, detail}
# Context always comes first: sector norms, growth profile, size, market regime.

_C = {"good": "#16c784", "ok": "#a3e635", "warn": "#f0b90b",
      "hot": "#f97316", "bad": "#ea3a44", "info": "#4da3ff", "na": "#556070"}

# Sector norms: (gross margin typical band %, debt/equity typical cap)
_SECTOR_NORMS = {
    "Technology":             {"gm": (55, 85), "d2e": 0.8},
    "Communication Services": {"gm": (45, 70), "d2e": 1.0},
    "Healthcare":             {"gm": (50, 80), "d2e": 0.9},
    "Financial Services":     {"gm": (30, 60), "d2e": 2.5},   # leverage is the business
    "Consumer Cyclical":      {"gm": (25, 45), "d2e": 1.2},
    "Consumer Defensive":     {"gm": (20, 40), "d2e": 1.2},
    "Industrials":            {"gm": (20, 40), "d2e": 1.2},
    "Energy":                 {"gm": (15, 40), "d2e": 0.9},
    "Basic Materials":        {"gm": (15, 35), "d2e": 0.9},
    "Utilities":              {"gm": (30, 60), "d2e": 2.0},   # regulated, debt-funded
    "Real Estate":            {"gm": (40, 70), "d2e": 2.0},
}


def _mk(value_s, band_s, verdict, color_key, detail):
    return {"value_s": value_s, "band_s": band_s, "verdict": verdict,
            "color": _C[color_key], "detail": detail}


def pe_in_context(fwd_pe, rev_growth) -> dict | None:
    """P/E judged against the company's own growth (PEG logic)."""
    if not fwd_pe or fwd_pe <= 0:
        return None
    g = (rev_growth or 0) * 100
    if g > 5:
        fair_lo, fair_hi = max(8, g * 0.8), g * 2.0   # PEG ~0.8-2.0 on growth
        band_s = f"{fair_lo:.0f}-{fair_hi:.0f}x for {g:.0f}% growth"
        if fwd_pe < fair_lo:
            return _mk(f"{fwd_pe:.1f}x", band_s, "CHEAP FOR ITS GROWTH", "good",
                       f"Forward P/E {fwd_pe:.0f} vs {g:.0f}% revenue growth = PEG "
                       f"{fwd_pe/g:.1f}. The market is pricing this growth at a discount — "
                       f"verify growth durability before celebrating.")
        if fwd_pe <= fair_hi:
            return _mk(f"{fwd_pe:.1f}x", band_s, "FAIR FOR ITS GROWTH", "ok",
                       f"P/E {fwd_pe:.0f} on {g:.0f}% growth = PEG {fwd_pe/g:.1f} — "
                       f"inside the 0.8-2.0 zone where growth roughly justifies the multiple.")
        return _mk(f"{fwd_pe:.1f}x", band_s, "PRICED FOR PERFECTION", "hot",
                   f"P/E {fwd_pe:.0f} needs MORE than the current {g:.0f}% growth to work "
                   f"(PEG {fwd_pe/g:.1f}). Any growth miss gets punished twice — "
                   f"by estimates AND by the multiple.")
    band_s = "10-18x for low/no growth"
    if fwd_pe <= 18:
        return _mk(f"{fwd_pe:.1f}x", band_s, "REASONABLE", "ok",
                   f"Low growth ({g:.0f}%) supports only a market-or-below multiple; "
                   f"{fwd_pe:.0f}x is inside that zone.")
    return _mk(f"{fwd_pe:.1f}x", band_s, "EXPENSIVE FOR NO GROWTH", "bad",
               f"{fwd_pe:.0f}x with only {g:.0f}% growth — the multiple assumes a "
               f"re-acceleration that isn't in the numbers yet.")


def ps_in_context(ps, rev_growth, gross_margin) -> dict | None:
    """P/S judged against growth × gross margin (a 90%-margin business 'deserves' more)."""
    if not ps or ps <= 0:
        return None
    g  = (rev_growth or 0) * 100
    gm = (gross_margin or 0.4)
    justified = max(1.0, (g / 10) * (gm / 0.5) * 2.5)   # heuristic anchor
    band_s = f"~{justified*0.6:.0f}-{justified*1.4:.0f}x for this growth+margin mix"
    if ps < justified * 0.6:
        return _mk(f"{ps:.1f}x", band_s, "CHEAP FOR THE MODEL", "good",
                   f"P/S {ps:.1f} vs ~{justified:.0f}x justified by {g:.0f}% growth at "
                   f"{gm*100:.0f}% gross margin — either a bargain or the market doubts "
                   f"the growth. Find out which.")
    if ps <= justified * 1.4:
        return _mk(f"{ps:.1f}x", band_s, "IN LINE", "ok",
                   f"P/S {ps:.1f} matches what {g:.0f}% growth at {gm*100:.0f}% gross "
                   f"margin typically commands.")
    return _mk(f"{ps:.1f}x", band_s, "RICH", "hot",
               f"P/S {ps:.1f} is well above the ~{justified:.0f}x this growth/margin mix "
               f"usually earns — the stock needs beat-and-raise quarters to hold the multiple.")


def margin_in_context(gross_margin, sector) -> dict | None:
    if gross_margin is None:
        return None
    gm = gross_margin * 100
    lo, hi = _SECTOR_NORMS.get(sector or "", {}).get("gm", (25, 55))
    band_s = f"{lo}-{hi}% typical for {sector or 'this sector'}"
    if gm > hi:
        return _mk(f"{gm:.0f}%", band_s, "ELITE PRICING POWER", "good",
                   f"Gross margin {gm:.0f}% exceeds the {lo}-{hi}% {sector} norm — "
                   f"a moat signal, as long as it's stable or rising.")
    if gm >= lo:
        return _mk(f"{gm:.0f}%", band_s, "SECTOR NORMAL", "ok",
                   f"Gross margin {gm:.0f}% is standard for {sector} ({lo}-{hi}%). "
                   f"Watch the TREND more than the level.")
    return _mk(f"{gm:.0f}%", band_s, "BELOW SECTOR", "warn",
               f"Gross margin {gm:.0f}% under the {lo}-{hi}% {sector} norm — "
               f"weak pricing power or a cost problem vs peers.")


def debt_in_context(d2e_raw, sector) -> dict | None:
    """yfinance debtToEquity comes as % — normalize to ratio."""
    if d2e_raw is None:
        return None
    d2e = d2e_raw / 100 if d2e_raw > 10 else d2e_raw
    cap = _SECTOR_NORMS.get(sector or "", {}).get("d2e", 1.2)
    band_s = f"<{cap:.1f} typical cap for {sector or 'this sector'}"
    if sector in ("Financial Services", "Utilities", "Real Estate"):
        note = f"{sector} runs structurally high leverage — compare within the sector only."
    else:
        note = ""
    if d2e <= cap * 0.5:
        return _mk(f"{d2e:.2f}", band_s, "FORTRESS", "good",
                   f"Debt/Equity {d2e:.2f} — big balance-sheet headroom; downturns become "
                   f"buying opportunities, not survival tests. {note}")
    if d2e <= cap:
        return _mk(f"{d2e:.2f}", band_s, "MANAGEABLE", "ok",
                   f"Debt/Equity {d2e:.2f} within the {sector or 'sector'} norm (<{cap:.1f}). {note}")
    return _mk(f"{d2e:.2f}", band_s, "LEVERED", "warn",
               f"Debt/Equity {d2e:.2f} above the {cap:.1f} sector norm — fine while rates "
               f"fall and cash flows hold; painful if either reverses. {note}")


def growth_in_context(rev_growth, size_class) -> dict | None:
    if rev_growth is None:
        return None
    g = rev_growth * 100
    bands = {"mega-cap": (8, 20), "large-cap": (10, 25),
             "mid-cap": (15, 35), "small-cap": (20, 50)}
    lo, hi = bands.get(size_class, (10, 25))
    band_s = f"{lo}-{hi}% strong for a {size_class or 'company'}"
    if g > hi:
        return _mk(f"{g:+.0f}%", band_s, "HYPERGROWTH FOR ITS SIZE", "good",
                   f"{g:.0f}% revenue growth at {size_class} scale is exceptional — "
                   f"the law of large numbers says enjoy it but model deceleration.")
    if g >= lo:
        return _mk(f"{g:+.0f}%", band_s, "HEALTHY FOR ITS SIZE", "ok",
                   f"{g:.0f}% growth is solid for a {size_class} — "
                   f"{'at this scale even ' + str(int(lo)) + '% moves the needle' if size_class=='mega-cap' else 'in line with quality peers'}.")
    if g >= 0:
        return _mk(f"{g:+.0f}%", band_s, "SLOW FOR ITS SIZE", "warn",
                   f"{g:.0f}% growth below the {lo}-{hi}% bar for a {size_class} — "
                   f"the multiple must be cheap to compensate.")
    return _mk(f"{g:+.0f}%", band_s, "SHRINKING", "bad",
               f"Revenue declining {g:.0f}% — only interesting as a turnaround bet "
               f"with a specific catalyst.")


def beta_in_context(beta, regime) -> dict | None:
    if beta is None:
        return None
    r = (regime or {}).get("regime", "NEUTRAL")
    band_s = f"regime is {r}"
    if beta >= 1.5:
        if r == "RISK-ON":
            return _mk(f"{beta:.2f}", band_s, "HIGH BETA — TAILWIND NOW", "good",
                       f"Beta {beta:.1f} amplifies the current RISK-ON tape in your favor — "
                       f"but this same number becomes the fastest bleeder when the regime flips.")
        return _mk(f"{beta:.2f}", band_s, "HIGH BETA — HEADWIND NOW", "warn",
                   f"Beta {beta:.1f} in a {r} regime = amplified downside. High-beta longs "
                   f"fight the regime here; size smaller or hedge.")
    if beta >= 0.8:
        return _mk(f"{beta:.2f}", band_s, "MARKET-LIKE", "ok",
                   f"Beta {beta:.1f} — moves roughly with the index; regime matters less "
                   f"for this position than stock-specific execution.")
    return _mk(f"{beta:.2f}", band_s, "DEFENSIVE", "info",
               f"Beta {beta:.1f} — cushions drawdowns, lags melt-ups. "
               f"{'Dead weight in a RISK-ON tape.' if r == 'RISK-ON' else 'Exactly what a ' + r + ' regime rewards.'}")


def short_in_context(short_pct, r1m) -> dict | None:
    if short_pct is None:
        return None
    s = short_pct * 100
    mom = (r1m or 0) * 100
    band_s = "<5% normal · >15% battleground"
    if s > 15 and mom > 8:
        return _mk(f"{s:.1f}%", band_s, "SQUEEZE FUEL", "info",
                   f"Short interest {s:.0f}% WITH +{mom:.0f}% 1M momentum — rising price "
                   f"forces shorts to cover, adding fuel. Volatile both ways; not a "
                   f"fundamental thesis by itself.")
    if s > 15:
        return _mk(f"{s:.1f}%", band_s, "HEAVILY SHORTED", "warn",
                   f"{s:.0f}% of float bet against this stock — sophisticated players see "
                   f"something broken. Check the bear case BEFORE buying the dip.")
    if s > 5:
        return _mk(f"{s:.1f}%", band_s, "ELEVATED SKEPTICISM", "warn",
                   f"Short interest {s:.0f}% — above-normal doubt, worth reading the "
                   f"bear thesis, not yet a battleground.")
    return _mk(f"{s:.1f}%", band_s, "NO CROWDED BEAR BET", "ok",
               f"Short interest {s:.0f}% — the market has no organized bear case here.")


def ext200_in_context(close) -> dict | None:
    """Extension vs MA200, normalized by the stock's own volatility — a calm
    stock 15% above MA200 is stretched; a wild one isn't."""
    try:
        if close is None or len(close) < 210:
            return None
        price = float(close.iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        ext = (price / ma200 - 1) * 100
        vol_ann = float(close.pct_change(fill_method=None).iloc[-126:].std() * (252 ** 0.5)) * 100
        stretch = ext / (vol_ann / 4) if vol_ann > 0 else 0   # ext in units of quarter-vol
        band_s = f"±{vol_ann/4:.0f}% is one 'normal step' for this stock's {vol_ann:.0f}% vol"
        if stretch > 2:
            return _mk(f"{ext:+.0f}%", band_s, "FAR ABOVE TREND", "hot",
                       f"{ext:+.0f}% above MA200 = {stretch:.1f} normal steps for a stock with "
                       f"{vol_ann:.0f}% annual vol — mean-reversion risk is real; adding here "
                       f"is momentum-chasing, not investing.")
        if stretch > 0.5:
            return _mk(f"{ext:+.0f}%", band_s, "HEALTHY UPTREND DISTANCE", "ok",
                       f"{ext:+.0f}% above MA200 is proportionate to this stock's "
                       f"{vol_ann:.0f}% volatility — trending, not parabolic.")
        if stretch > -0.5:
            return _mk(f"{ext:+.0f}%", band_s, "AT TREND", "info",
                       f"Price sits near its MA200 — the long-term trend line is being "
                       f"tested; direction of the break matters more than the level.")
        return _mk(f"{ext:+.0f}%", band_s, "BELOW TREND", "warn",
                   f"{abs(ext):.0f}% below MA200 — the long-term trend is broken; "
                   f"cheapness alone is not a catalyst.")
    except Exception:
        return None


def fcf_yield_in_context(info: dict, tnx: float | None) -> dict | None:
    """FCF yield vs the 10-year Treasury — is the equity paying you more cash
    than the risk-free alternative?"""
    fcf = info.get("freeCashflow")
    mc  = info.get("marketCap")
    if not fcf or not mc or mc <= 0:
        return None
    fy = fcf / mc * 100
    rf = tnx if tnx is not None else 4.2
    band_s = f"10Y Treasury pays {rf:.1f}%"
    if fy <= 0:
        return _mk(f"{fy:.1f}%", band_s, "BURNS CASH", "bad",
                   f"Negative FCF yield — you're paying for future promises while the "
                   f"risk-free rate pays {rf:.1f}%. The growth story must be exceptional "
                   f"to justify this.")
    if fy >= rf:
        return _mk(f"{fy:.1f}%", band_s, "BEATS THE BOND", "good",
                   f"FCF yield {fy:.1f}% ≥ the {rf:.1f}% 10Y — the business already pays "
                   f"more cash than the risk-free alternative, and unlike a bond that "
                   f"coupon can GROW. The quality-value sweet spot.")
    if fy >= rf * 0.5:
        return _mk(f"{fy:.1f}%", band_s, "PARTIAL CASH SUPPORT", "ok",
                   f"FCF yield {fy:.1f}% vs {rf:.1f}% risk-free — you're paying some "
                   f"growth premium; the gap must be closed by FCF growth.")
    return _mk(f"{fy:.1f}%", band_s, "GROWTH-PREMIUM PRICING", "warn",
               f"FCF yield {fy:.1f}% is under half the {rf:.1f}% 10Y — nearly all the "
               f"value sits in FUTURE cash flows. Rate rises hit exactly this kind of "
               f"stock hardest.")


@st.cache_data(ttl=43200, show_spinner=False)
def ps_vs_history(symbol: str, current_ps: float | None) -> dict | None:
    """Current P/S vs the stock's OWN 5-year range (percentile).
    'Expensive vs itself' matters as much as 'expensive vs peers'."""
    if not current_ps or current_ps <= 0:
        return None
    try:
        from modules.historical import fetch_metric
        hist = fetch_metric(symbol, "ps_ratio", years=5)
        hist = hist.dropna() if hist is not None else None
        if hist is None or len(hist) < 8:
            return None
        pctile = float((hist < current_ps).mean()) * 100
        lo, hi, med = float(hist.min()), float(hist.max()), float(hist.median())
        band_s = f"own 5y range {lo:.1f}-{hi:.1f}x (median {med:.1f}x)"
        if pctile >= 85:
            return _mk(f"{current_ps:.1f}x", band_s, "NEAR 5Y HIGHS", "hot",
                       f"P/S {current_ps:.1f} sits at the {pctile:.0f}th percentile of its own "
                       f"5-year history (median {med:.1f}x). The market has re-rated the story — "
                       f"you're paying a multiple the stock itself rarely sustained. "
                       f"Growth must accelerate, or the multiple mean-reverts.")
        if pctile >= 60:
            return _mk(f"{current_ps:.1f}x", band_s, "ABOVE OWN TYPICAL", "warn",
                       f"P/S {current_ps:.1f} is above its own 5y median ({med:.1f}x, "
                       f"{pctile:.0f}th percentile) — some multiple expansion already banked.")
        if pctile >= 30:
            return _mk(f"{current_ps:.1f}x", band_s, "OWN TYPICAL RANGE", "ok",
                       f"P/S {current_ps:.1f} near its own 5y median ({med:.1f}x) — the market "
                       f"prices the story consistently with its own history.")
        return _mk(f"{current_ps:.1f}x", band_s, "CHEAP VS OWN HISTORY", "good",
                   f"P/S {current_ps:.1f} at the {pctile:.0f}th percentile of its own 5y range "
                   f"(median {med:.1f}x) — de-rated vs its own past. Ask WHY before buying: "
                   f"slower growth, or just sentiment?")
    except Exception:
        return None


def interpret_all(symbol: str, info: dict, close, regime: dict) -> dict:
    """All deterministic in-context reads for one stock. Keys map to display labels."""
    mc = info.get("marketCap")
    size = ("mega-cap" if mc and mc > 200e9 else "large-cap" if mc and mc > 10e9
            else "mid-cap" if mc and mc > 2e9 else "small-cap" if mc else None)
    ps = None
    rev = info.get("totalRevenue")
    if mc and rev and rev > 0:
        ps = mc / rev
    from utils.indicators import trailing_return
    r1m = trailing_return(close, 21) if close is not None and len(close) > 22 else None

    out = {}
    tnx = (regime or {}).get("signals", {}).get("tnx")
    pairs = [
        ("Forward P/E",   pe_in_context(info.get("forwardPE"), info.get("revenueGrowth"))),
        ("Price/Sales",   ps_in_context(ps, info.get("revenueGrowth"), info.get("grossMargins"))),
        ("P/S vs History", ps_vs_history(symbol, ps)),
        ("FCF Yield",     fcf_yield_in_context(info, tnx)),
        ("Revenue Growth", growth_in_context(info.get("revenueGrowth"), size)),
        ("Gross Margin",  margin_in_context(info.get("grossMargins"), info.get("sector"))),
        ("Debt/Equity",   debt_in_context(info.get("debtToEquity"), info.get("sector"))),
        ("Beta",          beta_in_context(info.get("beta"), regime)),
        ("Short Interest", short_in_context(info.get("shortPercentOfFloat"), r1m)),
        ("vs MA200",      ext200_in_context(close)),
    ]
    for label, res in pairs:
        if res is not None:
            out[label] = res
    return out


@st.cache_data(ttl=21600, show_spinner=False)
def contextual_ranges(symbol: str, profile_json: str, regime_str: str) -> list[dict]:
    """
    Returns [{metric, value, healthy_range, assessment: LOW|FAIR|HIGH|N/A,
              explanation}] — empty list on failure.
    Cached 6h per (symbol, profile snapshot).
    """
    client = get_client()
    if client is None:
        return []
    try:
        prompt = f"""You are a patient investing teacher. A student is looking at {symbol} and needs to
understand whether each metric is low/fair/high FOR THIS SPECIFIC KIND OF STOCK — not vs.
the whole market. Anchor every range to the company's sector, market-cap size, growth
profile and the current macro regime.

STOCK PROFILE:
{profile_json}

MACRO CONTEXT: {regime_str}

For each metric present in the profile (skip ones with null values), give:
- healthy_range: the range that would be NORMAL for a company with this profile (e.g. "25-45x is normal for a 30%-growth mega-cap software name")
- assessment: where the actual value sits — LOW / FAIR / HIGH
- explanation: ONE sentence teaching WHY that range applies to this stock specifically.

Cover these metrics when available: forward_pe, ps_ratio, peg, gross_margin, revenue_growth,
profit_margin, debt_to_equity, beta, short_percent, rsi.

{ENGLISH_ENFORCEMENT}
Respond ONLY with a JSON array:
[{{"metric": "<display name>", "value": "<actual formatted value>",
   "healthy_range": "<range for THIS stock>", "assessment": "LOW|FAIR|HIGH",
   "explanation": "<one teaching sentence>"}}]"""
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1800,
            messages=[{"role": "user", "content": prompt}],
        )
        out = json.loads(extract_json(msg.content[0].text))
        return out if isinstance(out, list) else []
    except Exception:
        return []


def build_profile(symbol: str, info: dict, rsi: float | None = None) -> dict:
    """Compact stock profile for the prompt."""
    mc = info.get("marketCap")
    size = ("mega-cap" if mc and mc > 200e9 else
            "large-cap" if mc and mc > 10e9 else
            "mid-cap" if mc and mc > 2e9 else
            "small-cap" if mc else "unknown size")
    ps = None
    rev = info.get("totalRevenue")
    if mc and rev and rev > 0:
        ps = round(mc / rev, 1)
    return {
        "name":            info.get("shortName", symbol),
        "sector":          info.get("sector"),
        "industry":        info.get("industry"),
        "size_class":      size,
        "market_cap_b":    round(mc / 1e9, 1) if mc else None,
        "forward_pe":      info.get("forwardPE"),
        "ps_ratio":        ps,
        "peg":             info.get("trailingPegRatio"),
        "gross_margin":    info.get("grossMargins"),
        "revenue_growth":  info.get("revenueGrowth"),
        "profit_margin":   info.get("profitMargins"),
        "debt_to_equity":  info.get("debtToEquity"),
        "beta":            info.get("beta"),
        "short_percent":   info.get("shortPercentOfFloat"),
        "rsi":             rsi,
    }
