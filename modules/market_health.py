"""
Market Health Dashboard — macro & sentiment indicators.
Data: yfinance (VIX, yields, indices, commodities) + FRED API (rates, CPI, unemployment).
"""
import json
import yfinance as yf
import requests
import streamlit as st
from config import FRED_API_KEY, ANTHROPIC_API_KEY
from utils.claude_client import get_client as _get_client
from utils.cache import parallel_map

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

INDICATORS = {
    # ── Fear & Sentiment ──────────────────────────────────────────────────────
    "vix": {
        "label": "VIX — Fear Index",
        "source": "yf", "ticker": "^VIX",
        "category": "Fear & Sentiment",
        "desc": "The CBOE Volatility Index measures expected 30-day market volatility derived from S&P 500 options. Known as the 'fear gauge'.",
        "thresholds": [
            (0,  15,  "green",  "Calm — low fear, complacency risk"),
            (15, 20,  "green",  "Normal — healthy market environment"),
            (20, 28,  "yellow", "Elevated — investors nervous, caution warranted"),
            (28, 40,  "red",    "Fear — significant stress, potential buying opportunity"),
            (40, 999, "red",    "Extreme Fear — panic, historically good entry zone"),
        ],
        "invest_signal": "VIX spikes (>30) historically precede strong 12-month forward returns. Buy fear, sell greed.",
        "format": "number_1dp",
    },
    "sp500_vs_ma200": {
        "label": "S&P 500 vs MA200",
        "source": "yf", "ticker": "^GSPC",
        "category": "Market Trend",
        "desc": "Whether the S&P 500 is trading above or below its 200-day moving average. The single most reliable long-term trend indicator.",
        "thresholds": [
            (5,   999, "green",  "Bull trend — above MA200 by >5%"),
            (0,   5,   "yellow", "Near MA200 — critical support zone"),
            (-5,  0,   "yellow", "Just below MA200 — caution, trend weakening"),
            (-999,-5,  "red",    "Bear trend — below MA200, avoid new longs"),
        ],
        "invest_signal": "Historically, S&P 500 above MA200 = 15% avg annual return. Below MA200 = flat/negative.",
        "format": "pct_vs_ma",
    },
    "yield_curve": {
        "label": "Yield Curve (10Y–2Y)",
        "source": "fred", "series": "T10Y2Y",
        "category": "Macro Environment",
        "desc": "Spread between 10-year and 2-year Treasury yields. Inverted curve (negative) has preceded every US recession since 1955.",
        "thresholds": [
            (0.5, 999,  "green",  "Normal — healthy economic outlook"),
            (0,   0.5,  "yellow", "Flat — slowing growth, watch carefully"),
            (-0.5, 0,   "yellow", "Inverted — recession warning within 12-18 months"),
            (-999, -0.5,"red",    "Deeply inverted — elevated recession risk"),
        ],
        "invest_signal": "Curve re-steepening after inversion = recession starting. First 6 months of re-steepen = worst for stocks.",
        "format": "pct_raw",
    },
    "yield_10y": {
        "label": "10-Year Treasury Yield",
        "source": "fred", "series": "DGS10",
        "category": "Macro Environment",
        "desc": "The benchmark long-term rate — the discount rate used to value future cash flows, so it drives equity multiples directly (especially high-multiple growth names) and sets the 'risk-free' bar every other asset is priced against.",
        "thresholds": [
            (0,   3.5, "green",  "Low — supportive of high equity multiples"),
            (3.5, 4.5, "yellow", "Moderate — normal historical range"),
            (4.5, 5.0, "yellow", "Elevated — headwind for long-duration/growth multiples"),
            (5.0, 999, "red",    "High — significant multiple-compression pressure, competes hard with equities for capital"),
        ],
        "invest_signal": "Rising 10Y = money rotates from long-duration growth/tech into value, financials, and short-duration cash-like instruments. Falling 10Y reverses that flow.",
        "format": "pct_raw",
    },
    "fed_rate": {
        "label": "Fed Funds Rate",
        "source": "fred", "series": "FEDFUNDS",
        "category": "Macro Environment",
        "desc": "The Federal Reserve's benchmark interest rate. Higher rates = headwind for growth stocks and multiples. Rate cuts = tailwind.",
        "thresholds": [
            (0,   2,   "green",  "Accommodative — cheap money, growth-friendly"),
            (2,   3.5, "yellow", "Neutral — moderate, watch direction"),
            (3.5, 5,   "yellow", "Restrictive — headwind for high-multiple stocks"),
            (5,   999, "red",    "Very restrictive — significant multiple compression risk"),
        ],
        "invest_signal": "Direction matters more than level. First rate cut = historically +15% for equities over next 12 months.",
        "format": "pct_raw",
    },
    "cpi": {
        "label": "CPI Inflation (YoY)",
        "source": "fred", "series": "CPIAUCSL", "yoy": True,
        "category": "Macro Environment",
        "desc": "Consumer Price Index year-over-year change. High inflation forces the Fed to keep rates high, compressing stock multiples.",
        "thresholds": [
            (0,   2.5, "green",  "On target — Fed can be accommodative"),
            (2.5, 3.5, "yellow", "Slightly elevated — Fed stays cautious"),
            (3.5, 5,   "yellow", "Above target — rate cut unlikely"),
            (5,   999, "red",    "High inflation — expect continued rate pressure"),
        ],
        "invest_signal": "Inflation falling toward 2% = green light for Fed cuts = multiple expansion for growth stocks.",
        "format": "pct_yoy",
    },
    "core_cpi": {
        "label": "Core CPI (YoY, ex Food/Energy)",
        "source": "fred", "series": "CPILFESL", "yoy": True,
        "category": "Macro Environment",
        "desc": "CPI excluding volatile food and energy prices — the Fed's real inflation-trend gauge, since headline CPI can swing on gas prices alone. What the Fed actually watches when deciding on rates.",
        "thresholds": [
            (0,   2.5, "green",  "On target — supports a Fed pivot toward cuts"),
            (2.5, 3.2, "yellow", "Sticky — Fed stays cautious even if headline CPI looks better"),
            (3.2, 4.5, "yellow", "Elevated core — underlying inflation not resolved"),
            (4.5, 999, "red",    "High core inflation — Fed pressured to stay restrictive regardless of headline"),
        ],
        "invest_signal": "When core CPI diverges from headline CPI (e.g. headline falling on cheap gas, core still sticky), core is the one that actually moves the Fed.",
        "format": "pct_yoy",
    },
    "unemployment": {
        "label": "Unemployment Rate",
        "source": "fred", "series": "UNRATE",
        "category": "Macro Environment",
        "desc": "US unemployment rate. Low unemployment = strong economy but also = sticky inflation. Rising unemployment = recession risk but = Fed cuts.",
        "thresholds": [
            (0,   4,   "green",  "Full employment — strong consumer spending"),
            (4,   5,   "yellow", "Softening labor market — watch trend"),
            (5,   6.5, "yellow", "Rising — economic slowdown in progress"),
            (6.5, 999, "red",    "Recession conditions — Fed should be cutting"),
        ],
        "invest_signal": "Rising unemployment + falling inflation = Fed pivot. Historically bullish for equities 6-12 months out.",
        "format": "pct_raw",
    },
    "dxy": {
        "label": "US Dollar Index (DXY)",
        "source": "yf", "ticker": "DX-Y.NYB",
        "category": "Fear & Sentiment",
        "desc": "Strength of USD vs basket of major currencies. Strong dollar = headwind for multinational earnings, commodities, and emerging markets.",
        "thresholds": [
            (0,   95,  "green",  "Weak dollar — tailwind for global stocks and commodities"),
            (95,  100, "yellow", "Neutral dollar"),
            (100, 105, "yellow", "Strong dollar — headwind for multinationals"),
            (105, 999, "red",    "Very strong dollar — significant EPS headwind for US exporters"),
        ],
        "invest_signal": "Dollar weakness historically correlates with strong international and emerging market returns.",
        "format": "number_1dp",
    },
    "hy_spread": {
        "label": "High-Yield Credit Spread",
        "source": "fred", "series": "BAMLH0A0HYM2",
        "category": "Fear & Sentiment",
        "desc": "Extra yield investors demand to hold junk bonds vs Treasuries. Widens when credit stress rises — a leading indicator of equity stress.",
        "thresholds": [
            (0,   3.5, "green",  "Tight spreads — risk appetite healthy, credit benign"),
            (3.5, 5,   "yellow", "Widening — investors cautious on credit quality"),
            (5,   7,   "yellow", "Elevated — credit stress building"),
            (7,   999, "red",    "Wide spreads — financial stress, watch for equity selloff"),
        ],
        "invest_signal": "Spread widening often leads equity selloffs by 2-6 weeks. Tightening = all-clear for risk assets.",
        "format": "pct_raw",
    },
    "gold": {
        "label": "Gold vs Trend (MA200)",
        "source": "yf", "ticker": "GC=F",
        "category": "Fear & Sentiment",
        "desc": "Gold price relative to its own 200-day average. A sharp rally above trend = safe-haven demand spike. Relative measure stays valid as prices drift over the years.",
        "thresholds": [
            (-999, -5,  "yellow", "Below trend — weak safe-haven demand"),
            (-5,   5,   "green",  "In trend — no unusual fear signal"),
            (5,    12,  "yellow", "Above trend — safe-haven demand building"),
            (12,   999, "red",    "Sharp spike above trend — significant risk-off sentiment"),
        ],
        "invest_signal": "Gold spiking above its MA200 with falling yields + weak dollar = risk-off environment. Monitor vs equity direction.",
        "format": "pct_vs_ma",
    },
    "sp500_trend": {
        "label": "S&P 500 — 3M Momentum",
        "source": "yf", "ticker": "^GSPC",
        "category": "Market Trend",
        "desc": "S&P 500 3-month price return. Trend-following signal — rising markets tend to continue rising in the short term.",
        "thresholds": [
            (5,   999,  "green",  "Strong uptrend — momentum positive"),
            (0,   5,    "yellow", "Mild uptrend — cautiously positive"),
            (-5,  0,    "yellow", "Mild downtrend — caution"),
            (-999,-5,   "red",    "Downtrend — avoid aggressive longs"),
        ],
        "invest_signal": "Positive 3M momentum in S&P = increased probability of continued gains over next 3 months.",
        "format": "pct_raw",
    },
}

# ── Scoring weights for composite ─────────────────────────────────────────────
WEIGHTS = {
    "vix":            0.18,
    "sp500_vs_ma200": 0.15,
    "yield_curve":    0.12,
    "fed_rate":       0.12,
    "cpi":            0.12,
    "hy_spread":      0.12,
    "sp500_trend":    0.10,
    "unemployment":   0.05,
    "dxy":            0.04,
}


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_all() -> dict:
    def _one(item):
        key, cfg = item
        try:
            if cfg["source"] == "yf":
                return key, _fetch_yf(cfg)
            if cfg["source"] == "fred":
                return key, _fetch_fred(cfg)
        except Exception as e:
            return key, {"value": None, "error": str(e)}
        return key, None

    results = {}
    for out in parallel_map(_one, INDICATORS.items()):
        if isinstance(out, Exception) or out[1] is None:
            continue
        results[out[0]] = out[1]
    return results


def _fetch_yf(cfg: dict) -> dict:
    t = yf.Ticker(cfg["ticker"])
    hist = t.history(period="1y", interval="1d")
    if hist.empty:
        return {"value": None}

    close  = hist["Close"].dropna()
    latest = float(close.iloc[-1])

    extra = {}
    if cfg.get("ticker") in ("^GSPC", "^IXIC"):
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        r3m   = float(close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) >= 64 else None
        extra["ma200"] = ma200
        extra["r3m"]   = r3m
        if cfg["label"].startswith("S&P 500 vs"):
            if ma200:
                extra["display_value"] = (latest / ma200 - 1) * 100
        if cfg["label"].startswith("S&P 500 —"):
            extra["display_value"] = r3m

    # Gold is scored relative to its own MA200 (price-drift-proof)
    if cfg.get("ticker") == "GC=F":
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        if ma200:
            extra["ma200"] = ma200
            extra["display_value"] = (latest / ma200 - 1) * 100

    return {"value": latest, **extra}


def _fetch_yield_curve_yf() -> dict:
    """Approximate 10Y-2Y spread using yfinance ^TNX (10Y) and ^FVX (5Y).
    The 10Y-5Y spread is directionally equivalent to 10Y-2Y for inversion signals."""
    try:
        t10 = yf.Ticker("^TNX").history(period="5d", interval="1d")
        t5  = yf.Ticker("^FVX").history(period="5d", interval="1d")
        if t10.empty or t5.empty:
            return {"value": None, "error": "yfinance yield data unavailable"}
        tnx = float(t10["Close"].dropna().iloc[-1]) / 10   # convert index to %
        fvx = float(t5["Close"].dropna().iloc[-1])  / 10
        spread = round(tnx - fvx, 3)
        return {"value": spread, "approx": True,
                "note": "≈ 10Y–5Y spread (FRED key missing)"}
    except Exception as e:
        return {"value": None, "error": f"yfinance fallback failed: {e}"}


def _fetch_yield_10y_yf() -> dict:
    """10Y yield via yfinance ^TNX when FRED key is missing — same source
    already used for the yield-curve approximation, just not divided
    against a second maturity."""
    try:
        t10 = yf.Ticker("^TNX").history(period="5d", interval="1d")
        if t10.empty:
            return {"value": None, "error": "yfinance yield data unavailable"}
        tnx = float(t10["Close"].dropna().iloc[-1]) / 10
        return {"value": round(tnx, 3), "approx": True,
                "note": "≈ yfinance ^TNX (FRED key missing)"}
    except Exception as e:
        return {"value": None, "error": f"yfinance fallback failed: {e}"}


def _fetch_fred(cfg: dict) -> dict:
    # yfinance fallbacks when FRED key is missing
    if not FRED_API_KEY and cfg["series"] == "T10Y2Y":
        return _fetch_yield_curve_yf()
    if not FRED_API_KEY and cfg["series"] == "DGS10":
        return _fetch_yield_10y_yf()

    if not FRED_API_KEY:
        return {"value": None, "error": "Add FRED_API_KEY to .env for this indicator (free at fred.stlouisfed.org)"}

    params = {
        "series_id":    cfg["series"],
        "api_key":      FRED_API_KEY,
        "file_type":    "json",
        "limit":        5,
        "sort_order":   "desc",
        "observation_end": "9999-12-31",
    }
    r = requests.get(FRED_BASE, params=params, timeout=8)
    r.raise_for_status()
    obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
    if not obs:
        return {"value": None}

    latest_val = float(obs[0]["value"])
    extra = {}

    # YoY series (CPI, Core CPI, ...) — flagged per-indicator via "yoy": True
    # rather than hardcoding series IDs, so adding another YoY series later
    # is a config entry, not a code change.
    if cfg.get("yoy"):
        params2 = {**params, "limit": 15}
        r2 = requests.get(FRED_BASE, params=params2, timeout=8)
        obs2 = [o for o in r2.json().get("observations", []) if o["value"] != "."]
        if len(obs2) >= 13:
            val_now  = float(obs2[0]["value"])
            val_year = float(obs2[12]["value"])
            extra["display_value"] = (val_now / val_year - 1) * 100

    return {"value": latest_val, **extra}


def _get_display_value(key: str, data: dict) -> float | None:
    if data.get("display_value") is not None:
        return data["display_value"]
    return data.get("value")


def is_approx(key: str, data: dict) -> bool:
    """True when the value is a yfinance approximation, not the real FRED figure."""
    return bool(data.get("approx"))


def _classify(key: str, value: float | None) -> dict:
    if value is None:
        return {"color": "gray", "label": "No data", "score": 50}
    cfg = INDICATORS[key]
    for lo, hi, color, label in cfg["thresholds"]:
        if lo <= value < hi:
            score = {"green": 85, "yellow": 55, "red": 25}[color]
            return {"color": color, "label": label, "score": score}
    return {"color": "gray", "label": "Out of range", "score": 50}


def compute_composite(data: dict) -> dict:
    total, weight_used = 0.0, 0.0
    signals = {}
    for key, w in WEIGHTS.items():
        d = data.get(key, {})
        val = _get_display_value(key, d)
        cl  = _classify(key, val)
        signals[key] = {**cl, "value": val, "display": _fmt(key, val)}
        if val is not None:
            total       += cl["score"] * w
            weight_used += w

    composite = (total / weight_used) if weight_used > 0 else 50

    if composite >= 70:
        overall_label = "Healthy — Risk-On"
        overall_color = "#16c784"
        recommendation = "Market conditions favor equity exposure. Consider adding to growth positions."
    elif composite >= 55:
        overall_label = "Cautiously Positive"
        overall_color = "#a3e635"
        recommendation = "Mixed signals. Favor quality companies with strong fundamentals. Stay selective."
    elif composite >= 42:
        overall_label = "Neutral — Wait & See"
        overall_color = "#f0b90b"
        recommendation = "Uncertain environment. Hold current positions, avoid large new commitments."
    elif composite >= 28:
        overall_label = "Caution — Risk-Off"
        overall_color = "#f97316"
        recommendation = "Multiple warning signs. Reduce exposure, raise cash, tighten stop losses."
    else:
        overall_label = "Danger — Defensive Mode"
        overall_color = "#ea3a44"
        recommendation = "High stress environment. Capital preservation first. Historical buying opportunity may be forming."

    return {
        "score": round(composite, 1),
        "label": overall_label,
        "color": overall_color,
        "recommendation": recommendation,
        "signals": signals,
    }


def _narrative_snapshot(data: dict, composite: dict) -> str:
    """Canonical JSON snapshot of the current readings — passed to
    macro_narrative() as a single hashable string so st.cache_data keys on
    the actual DATA (regenerate when readings change) rather than on
    nothing (which would cache-and-never-refresh) or on unstable dict
    identity (which would defeat caching entirely)."""
    rows = []
    for key, sig in composite["signals"].items():
        ind = INDICATORS[key]
        rows.append({
            "label": ind["label"], "category": ind["category"],
            "value": sig.get("display", "N/A"), "read": sig.get("label", ""),
            "color": sig.get("color", "gray"),
        })
    return json.dumps({
        "composite_score": composite["score"], "composite_label": composite["label"],
        "indicators": rows,
    }, sort_keys=True)


@st.cache_data(ttl=1800, show_spinner=False)
def macro_narrative(snapshot_json: str) -> dict:
    """
    Dynamic 'what does this combination actually mean' read — the static
    per-indicator invest_signal strings above are always true in isolation,
    but don't say where money is rotating TO given how these specific
    readings combine RIGHT NOW (e.g. rising yields + strong dollar + sticky
    core CPI reads very differently from rising yields + weak dollar +
    falling core CPI, even though both have 'rising yields'). Same
    Claude-narrates-the-numbers pattern as modules/macro_geo.py, generalized
    from one stock to the whole market.
    """
    if not ANTHROPIC_API_KEY:
        return {
            "error": "Add ANTHROPIC_API_KEY to enable the dynamic macro narrative — "
                     "the indicator cards above still work without it."
        }

    snapshot = json.loads(snapshot_json)
    rows_txt = "\n".join(
        f"- {r['label']} ({r['category']}): {r['value']} — {r['read']} [{r['color']}]"
        for r in snapshot["indicators"]
    )

    prompt = f"""You are a senior macro strategist explaining, in plain terms, what TODAY's specific combination of indicator readings means for where money is flowing across asset classes and equity sectors — not a generic explainer of what each indicator means in isolation.

CURRENT READINGS:
{rows_txt}

Composite market health: {snapshot['composite_score']}/100 — {snapshot['composite_label']}

Reason about how these readings interact (e.g. rate direction + dollar direction + inflation trend together, not each alone). Be specific about equity sectors/styles (growth vs value, cyclicals vs defensives, duration-sensitive vs cash-generative, US vs international, commodities/gold) and WHY, given the actual combination above — not boilerplate that would apply to any macro backdrop.
IMPORTANT: Always respond in English regardless of any context language.

Respond ONLY with valid JSON (no markdown fences):
{{
  "headline": "<one sentence: the core money-flow story right now>",
  "narrative": "<3-4 sentences connecting the specific readings above into one coherent story>",
  "money_flowing_into": ["<asset class or style 1>", "<asset class or style 2>"],
  "money_flowing_out_of": ["<asset class or style 1>", "<asset class or style 2>"],
  "sectors_favored": ["<sector 1>", "<sector 2>"],
  "sectors_at_risk": ["<sector 1>", "<sector 2>"],
  "watch_for": "<the one thing that would change this read if it shifted>"
}}"""

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-5",
            max_tokens=1200,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        parsed["error"] = None
        return parsed
    except Exception as e:
        return {"error": f"Macro narrative unavailable: {e}"}


def _fmt(key: str, val: float | None) -> str:
    if val is None:
        return "N/A"
    fmt = INDICATORS[key]["format"]
    if fmt == "number_1dp":  return f"{val:.1f}"
    if fmt == "pct_raw":     return f"{val:.2f}%"
    if fmt == "pct_yoy":     return f"{val:.1f}%"
    if fmt == "pct_vs_ma":   return f"{val:+.1f}% vs MA200"
    if fmt == "price":       return f"${val:,.0f}"
    return f"{val:.2f}"
