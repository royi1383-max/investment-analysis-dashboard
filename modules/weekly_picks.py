"""
Weekly Recommendations Engine — automatic, no user input.

Scans the broad-market stock universe (WEEKLY_UNIVERSE unioned with the
live S&P 500 constituent list — see _full_stock_universe) against five
pillars:
  1. Fundamental quality
  2. Technical + momentum
  3. Analyst consensus (Yahoo Finance primary)
  4. Options flow (call/put bias)
  5. Breakout setup

Entry thresholds are calibrated to the current market regime
(Risk-On / Neutral / Risk-Off) from market_context.get_regime().

Three qualification paths feed one final ranked list (see FINAL_CAP):
  SWING       — passes the strict entry-condition gate (_passes_entry)
  QUALITY_DIP — good business, price knocked down for reasons that don't
                reflect the business itself (Opportunity Lens' "QUALITY ON
                SALE" quadrant — see _check_quality_dip)
  ETF_THEME   — theme/sector ETFs scored on trend strength alone, no
                fundamentals gate (see _scan_etfs)

Claude produces a full "Buy Thesis" for each qualifying STOCK:
  why now · when to enter · target · stop · macro relevance · key risk
ETFs get a rule-based thesis instead (see _etf_thesis) — "is this theme
trending" isn't a company-specific buy case an LLM call adds much to.
"""
import json
import hashlib
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime
import datetime as _dt
from pathlib import Path

from config import ANTHROPIC_API_KEY, FINNHUB_API_KEY, WEEKLY_UNIVERSE
from utils.cache import get_ticker_info, get_price_history
import modules.sector_strength as sector_strength
import modules.opportunity as opportunity

# ── Disk path for pick history (alongside the wp cache file in app root) ──────
_WP_HISTORY_PATH = Path(__file__).parent.parent / ".wp_history.json"

from utils.claude_client import get_client as _get_client

# Finnhub circuit breaker — module-level, reset at each scan start
_FH_BREAKER = {"failures": 0}
from modules import fundamental, technical, momentum as mom_module, scoring
from modules.finnhub_data  import fetch_all as finnhub_fetch
from modules.options_flow  import analyze as options_analyze
from modules.market_context import get_regime


# ── Broad-market universe ──────────────────────────────────────────────────────
# WEEKLY_UNIVERSE alone is a fixed ~223-ticker hand-curated list — a closed
# circle that can't surface anything not already typed into config.py. This
# unions it with the live S&P 500 constituent list (scraped from Wikipedia —
# free, no API key, self-updating as the index changes) so the scan actually
# covers the broad market, not just names someone remembered to add.

@st.cache_data(ttl=86400, show_spinner=False)
def _sp500_constituents() -> list[str]:
    """S&P 500 tickers. Returns [] on any failure (network, page structure
    change) so a scan degrades to the curated WEEKLY_UNIVERSE alone rather
    than crashing — this is a broadening layer, not a hard dependency."""
    try:
        import urllib.request
        from io import StringIO
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        df = pd.read_html(StringIO(html))[0]
        # yfinance wants BRK-B, not BRK.B
        return [str(s).strip().replace(".", "-") for s in df["Symbol"].tolist()]
    except Exception:
        return []


def _full_stock_universe() -> list[str]:
    """WEEKLY_UNIVERSE first (preserves the existing anchor group unchanged)
    unioned with the live S&P 500 list, deduped."""
    seen = list(dict.fromkeys(WEEKLY_UNIVERSE))
    for sym in _sp500_constituents():
        if sym not in seen:
            seen.append(sym)
    return seen


# ── Weekly universe rotation ──────────────────────────────────────────────────

def _current_week_num() -> int:
    """ISO week number of today (1–53)."""
    return _dt.date.today().isocalendar()[1]


def _get_weekly_sample(universe: list[str], n_anchor: int = 30, n_rotating: int = 30) -> list[str]:
    """
    Returns n_anchor + n_rotating stocks deterministic for the current calendar week.
    The anchor group (first n_anchor) is always included.
    The rotating group changes each week via a seeded RNG.
    """
    anchor  = universe[:n_anchor]
    rest    = universe[n_anchor:]
    if not rest:
        return anchor

    week_key = _dt.date.today().strftime("%Y-W%W") + "v1"
    seed     = int(hashlib.md5(week_key.encode()).hexdigest(), 16) % (2 ** 32)
    rng      = np.random.default_rng(seed)
    n_take   = min(n_rotating, len(rest))
    rotating = rng.choice(rest, size=n_take, replace=False).tolist()
    return anchor + rotating


# ── Pick history (recency penalty) ───────────────────────────────────────────

def _load_pick_history() -> dict[str, int]:
    """Returns {symbol: iso_week_number} of last appearance."""
    from utils.persist import load_json
    data = load_json(_WP_HISTORY_PATH, default={})
    try:
        return {k: int(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_pick_history(history: dict[str, int]) -> None:
    from utils.persist import save_json
    save_json(_WP_HISTORY_PATH, history)


def _recency_penalty(symbol: str, history: dict[str, int], current_week: int) -> float:
    """
    Returns a score penalty for picks that appeared in the last 4 weeks.
    Penalty fades: week-1 → -1.4, week-2 → -1.05, week-3 → -0.7, week-4 → -0.35
    """
    last_week = history.get(symbol, 0)
    if last_week == 0:
        return 0.0
    # Handle year-rollover: if current_week < last_week, assume next year
    delta = current_week - last_week
    if delta < 0:
        delta += 53
    if 1 <= delta <= 4:
        return (5 - delta) * 0.35
    return 0.0


# ── Sector diversity cap ──────────────────────────────────────────────────────

def _apply_sector_cap(qualified: list[dict], max_per_sector: int = 2) -> list[dict]:
    """Keep at most max_per_sector picks per GICS sector (already sorted by score)."""
    sector_count: dict[str, int] = {}
    result = []
    for r in qualified:
        s = (r.get("sector") or "Other").strip()
        if sector_count.get(s, 0) < max_per_sector:
            result.append(r)
            sector_count[s] = sector_count.get(s, 0) + 1
    return result


# ── Analyst data — Yahoo Finance primary, Finnhub supplement ─────────────────

_REC_KEY_LABEL = {
    "strong_buy":   ("Strong Buy",   "#16c784"),
    "buy":          ("Buy",          "#a3e635"),
    "hold":         ("Hold",         "#f0b90b"),
    "underperform": ("Underperform", "#f97316"),
    "sell":         ("Sell",         "#ea3a44"),
}


def _yahoo_bull_pct(rec_mean: float | None) -> float:
    if rec_mean is None:
        return 50.0
    return round(max(5.0, min(95.0, 95.0 - (rec_mean - 1.0) * 22.5)), 1)


@st.cache_data(ttl=1800, show_spinner=False)
def _analyst_data(symbol: str) -> dict:
    info        = get_ticker_info(symbol)
    rec_key     = (info.get("recommendationKey") or "").lower().replace(" ", "_")
    rec_mean    = info.get("recommendationMean")
    n_analysts  = info.get("numberOfAnalystOpinions") or 0
    pt_mean     = info.get("targetMeanPrice")
    pt_high     = info.get("targetHighPrice")
    pt_low      = info.get("targetLowPrice")

    label, color = _REC_KEY_LABEL.get(rec_key, ("N/A", "#8a9bc2"))
    bull_pct     = _yahoo_bull_pct(rec_mean)

    result = {
        "bull_pct":        bull_pct,
        "consensus":       label,
        "consensus_color": color,
        "total_analysts":  n_analysts,
        "pt_mean":         pt_mean,
        "pt_high":         pt_high,
        "pt_low":          pt_low,
        "pt_analysts":     n_analysts,
        "rec_mean":        rec_mean,
        "source":          "Yahoo Finance",
    }

    # Circuit breaker: after 2 consecutive Finnhub failures (likely rate-limited),
    # skip Finnhub for the rest of the scan — Yahoo stays the primary source anyway.
    if FINNHUB_API_KEY and _FH_BREAKER["failures"] < 2:
        try:
            fh  = finnhub_fetch(symbol)
            rec = fh.get("recommendations", {})
            pt  = fh.get("price_target", {})
            if "rec_error" in fh or "error" in fh:
                _FH_BREAKER["failures"] += 1
            else:
                _FH_BREAKER["failures"] = 0
            fh_total = rec.get("total", 0)
            if fh_total > n_analysts and fh_total > 0:
                result.update({
                    "bull_pct":        rec.get("bull_pct", bull_pct),
                    "consensus":       rec.get("consensus", label),
                    "consensus_color": rec.get("consensus_color", color),
                    "total_analysts":  fh_total,
                    "source":          "Finnhub",
                })
            if not pt_mean and pt.get("mean"):
                result["pt_mean"]     = pt["mean"]
                result["pt_analysts"] = pt.get("analysts", 0)
        except Exception:
            _FH_BREAKER["failures"] += 1

    return result


def _analyst_score(analyst: dict, price: float) -> float:
    bull  = analyst.get("bull_pct", 50) / 100
    score = 5.0 + (bull - 0.5) * 8
    if analyst.get("pt_mean") and price and price > 0:
        upside = analyst["pt_mean"] / price - 1
        score += min(2.0, max(-2.0, upside * 5))
    return round(max(1.0, min(10.0, score)), 2)


# ── Model scores ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _score_model(symbol: str) -> dict:
    try:
        f  = fundamental.analyze(symbol)
        t  = technical.analyze(symbol)
        mo = mom_module.analyze(symbol)
        s  = scoring.compute(f["score"], t["score"], mo["score"], 5, 5, 5)
        return {
            "composite":   s["final"],
            "fundamental": f["score"],
            "technical":   t["score"],
            "momentum":    mo["score"],
            "label":       s["label"],
            "color":       s["color"],
            "vol_ratio":   t.get("vol_ratio", 1.0),
        }
    except Exception:
        return {}


# ── Price / momentum metrics ──────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _momentum_data(symbol: str) -> dict:
    try:
        info = get_ticker_info(symbol)
        ph   = get_price_history(symbol, period="1y")
        c    = ph["Close"].squeeze() if not ph.empty else pd.Series([])
        vol  = ph["Volume"].squeeze() if not ph.empty else pd.Series([])

        from utils.indicators import rsi_last, trailing_return
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        ma50  = float(c.rolling(50).mean().iloc[-1])  if len(c) >= 50  else None
        ma200 = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else None
        r1w   = trailing_return(c, 5)
        r1m   = trailing_return(c, 21)
        r3m   = trailing_return(c, 63)

        rvol = None
        if len(vol) >= 20:
            avg5  = float(vol.iloc[-5:].mean())
            avg20 = float(vol.iloc[-20:].mean())
            rvol  = avg5 / avg20 if avg20 > 0 else 1.0

        rsi = rsi_last(c)

        return {
            "price":        price,
            "name":         info.get("shortName", symbol),
            "sector":       info.get("sector", ""),
            "market_cap":   info.get("marketCap"),
            "forward_pe":   info.get("forwardPE"),
            "revenue_growth": info.get("revenueGrowth"),
            "gross_margin":   info.get("grossMargins"),
            "short_float":    info.get("shortPercentOfFloat"),
            "ma50": ma50, "ma200": ma200,
            "above_ma200": (price > ma200) if ma200 and price else None,
            "above_ma50":  (price > ma50)  if ma50  and price else None,
            "pct_vs_ma200": ((price / ma200 - 1) * 100) if ma200 and price else None,
            "r1w": r1w, "r1m": r1m, "r3m": r3m, "rsi": rsi, "rvol": rvol,
        }
    except Exception:
        return {}


# ── Breakout setup ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _breakout_data(symbol: str) -> dict:
    try:
        ph    = get_price_history(symbol, period="1y")
        if ph.empty or len(ph) < 30:
            return {"score": 5, "signals": [], "setup": "No data"}

        close = ph["Close"].squeeze()
        high  = ph["High"].squeeze()
        vol   = ph["Volume"].squeeze()
        price = float(close.iloc[-1])

        high52 = float(high.rolling(252).max().iloc[-1]) if len(high) >= 252 else float(high.max())
        pct_from_high = (price / high52 - 1) if high52 > 0 else -1.0

        bb_std  = close.rolling(20).std()
        bb_mean = close.rolling(20).mean()
        with np.errstate(divide="ignore", invalid="ignore"):
            bandwidth = (bb_std.iloc[-1] / bb_mean.iloc[-1] * 100) if bb_mean.iloc[-1] else None
            avg_bw_60 = (bb_std / bb_mean * 100).rolling(60).mean().iloc[-1] if len(close) >= 80 else None
        squeeze = bool(bandwidth and avg_bw_60 and bandwidth < avg_bw_60 * 0.75)

        range10   = float(close.iloc[-10:].max() - close.iloc[-10:].min())
        range_pct = (range10 / price * 100) if price > 0 else 100
        tight_range = range_pct < 5.0

        avg5  = float(vol.iloc[-5:].mean())  if len(vol) >= 5  else None
        avg20 = float(vol.iloc[-20:].mean()) if len(vol) >= 20 else None
        vol_surge = bool(avg5 and avg20 and avg5 > avg20 * 1.5
                         and float(close.iloc[-1]) > float(close.iloc[-5]))

        score = 5.0
        signals = []
        tags    = []

        if pct_from_high > -0.03:
            score += 2.5; signals.append("At 52W high — breakout territory"); tags.append("NEW HIGH")
        elif pct_from_high > -0.08:
            score += 1.5; signals.append(f"Within {abs(pct_from_high)*100:.1f}% of 52W high"); tags.append("NEAR HIGH")
        elif pct_from_high > -0.15:
            score += 0.5; signals.append(f"{abs(pct_from_high)*100:.1f}% below 52W high")

        if squeeze:
            score += 1.5; signals.append("BB squeeze — volatility compression"); tags.append("BB SQUEEZE")
        if tight_range:
            score += 1.0; signals.append(f"Tight range ({range_pct:.1f}%) — coiling"); tags.append("COILING")
        if vol_surge:
            score += 1.0; signals.append("Volume surge — breakout confirmed"); tags.append("VOL BREAKOUT")
        if pct_from_high < -0.35:
            score -= 1.5

        return {
            "score":         round(max(1.0, min(10.0, score)), 2),
            "pct_from_high": pct_from_high,
            "squeeze":       squeeze,
            "tight_range":   tight_range,
            "vol_surge":     vol_surge,
            "range_pct":     range_pct,
            "signals":       signals,
            "setup":         " · ".join(tags) if tags else "No clear setup",
        }
    except Exception:
        return {"score": 5, "signals": [], "setup": "Error"}


# ── ETF theme scan ──────────────────────────────────────────────────────────────
# ETFs have no fundamentals to score — qualifying them on the stock filter
# (_passes_entry, which checks fundamental/analyst-consensus/options) makes
# no sense. They qualify on trend/relative strength + breakout setup alone,
# reusing sector_strength.py's existing ETF strength scorer (same one behind
# the Analyze page's Sector Context cards) so "what's a strong theme right
# now" comes from one scoring method, not two.

@st.cache_data(ttl=1800, show_spinner=False)
def _score_etf(symbol: str) -> dict:
    try:
        strength = sector_strength.etf_strength(symbol)
        if not strength:
            return {}
        breakout = _breakout_data(symbol)
        info = get_ticker_info(symbol)
        return {
            "symbol":          symbol,
            "name":            info.get("longName") or info.get("shortName") or symbol,
            "price":           strength.get("price"),
            "strength_score":  strength.get("score", 5),
            "grade":           strength.get("grade", ""),
            "r1m":             strength.get("r1m"),
            "r3m":             strength.get("r3m"),
            "rs1m":            strength.get("rs1m"),
            "above_50":        strength.get("above_50"),
            "above_200":       strength.get("above_200"),
            "breakout_score":  breakout.get("score", 5),
            "breakout_setup":  breakout.get("setup", ""),
        }
    except Exception:
        return {}


def _scan_etfs(etf_universe: list[str], min_score: float = 6.5) -> list[dict]:
    qualified = []
    for sym in etf_universe:
        d = _score_etf(sym)
        if not d:
            continue
        composite = round(d["strength_score"] * 0.7 + d["breakout_score"] * 0.3, 2)
        if composite >= min_score:
            d["weekly_score"] = composite
            d["category"]     = "ETF_THEME"
            qualified.append(d)
    qualified.sort(key=lambda x: x["weekly_score"], reverse=True)
    return qualified


def _etf_thesis(etf: dict) -> dict:
    """Rule-based, not Claude — an ETF thesis is 'is the theme trending',
    not a company-specific buy case, so it doesn't need an LLM call."""
    r1m, r3m, rs1m = etf.get("r1m") or 0, etf.get("r3m") or 0, etf.get("rs1m") or 0
    return {
        "action":       "BUY" if etf["weekly_score"] >= 7.5 else "WATCH",
        "conviction":   4 if etf["weekly_score"] >= 7.5 else 3,
        "quality_flag": "THEME ETF",
        "headline":     f"{etf.get('grade','Strong')} theme momentum — {r1m:+.1f}% 1M, {r3m:+.1f}% 3M",
        "why_buy": [
            f"Relative strength vs SPY: {rs1m:+.1f}% (1M)",
            f"{'Above' if etf.get('above_200') else 'Below'} its 200-day moving average",
            f"Breakout setup: {etf.get('breakout_setup') or 'no clear setup'}",
        ],
        "macro_relevance":     "Sector/theme-level flow — check the Sector Rotation page for the broader picture.",
        "investor_psychology": "Trend-following: the thesis is that money is already rotating into this theme.",
        "when_buy":   "Current price — this is a momentum/trend play, not a dip entry.",
        "target_zone": "No single target — hold while relative strength vs SPY stays positive.",
        "stop_loss":  "A close back below the 50-day moving average invalidates the trend.",
        "key_risk":   "Theme rotation — sector momentum can reverse faster than a single stock's fundamentals would.",
        "catalyst_this_week": "Broad sector/theme flow rather than a single company event.",
    }


# ── Quality-dip carve-out ────────────────────────────────────────────────────────
# The strict swing filter (_passes_entry) requires technical/momentum
# strength — which by definition excludes "good business, temporarily
# beaten-down stock," even though that's a real, distinct opportunity (buy
# quality at a price the business's own fundamentals don't justify). Reuses
# Opportunity Lens' quality-vs-condition read instead of re-deriving it.

def _check_quality_dip(symbol: str) -> dict | None:
    try:
        opp = opportunity.analyze(symbol)
        if opp.get("error"):
            return None
        if opp.get("quadrant") == "QUALITY ON SALE":
            return opp
    except Exception:
        pass
    return None


# ── Composite weekly score ─────────────────────────────────────────────────────

def _composite(model: dict, analyst_s: float, mom: dict,
               options: dict, breakout: dict) -> float:
    comp  = model.get("composite", 5) or 5
    opt_s = options.get("score", 5)   or 5
    brk_s = breakout.get("score", 5)  or 5

    r3m       = mom.get("r3m") or 0
    mom_bonus = min(2.0, max(-2.0, r3m * 6))

    rvol = mom.get("rvol") or 1.0
    vol_bonus = 1.0 if rvol > 1.5 else 0.5 if rvol > 1.2 else -0.5 if rvol < 0.7 else 0.0

    ma200_bonus = 0.5 if mom.get("above_ma200") else -0.5 if mom.get("above_ma200") is False else 0.0

    # Weekly acceleration bonus — rewards stocks moving right now
    r1w        = mom.get("r1w") or 0
    accel_bonus = min(0.8, max(-0.3, r1w * 12))

    score = (
        comp       * 0.30 +
        analyst_s  * 0.20 +
        opt_s      * 0.15 +
        brk_s      * 0.15 +
        5          * 0.20
        + mom_bonus + vol_bonus + ma200_bonus + accel_bonus
    )
    return round(max(1, min(10, score)), 2)


# ── Entry condition checks ────────────────────────────────────────────────────

def _passes_entry(r: dict, thresholds: dict) -> bool:
    """
    A stock must pass at least 4 of 6 entry conditions to qualify.
    Thresholds come from the current market regime.
    """
    passes = 0

    if (r.get("fundamental") or 0) >= thresholds["fundamental"]:
        passes += 1
    if (r.get("technical") or 0) >= thresholds["technical"]:
        passes += 1
    if (r.get("bull_pct") or 0) >= thresholds["bull_pct"]:
        passes += 1
    if r.get("above_ma200") is True:
        passes += 1
    if (r.get("r3m") or -99) >= thresholds["r3m_min"]:
        passes += 1
    cp = r.get("cp_ratio")
    if cp is None or cp >= 0.7:    # neutral/bullish options or no data
        passes += 1

    return passes >= 4


# ── Claude Buy Thesis ─────────────────────────────────────────────────────────

def claude_buy_thesis(stocks: list[dict], regime: dict) -> dict:
    """
    ONE Claude call for all qualifying stocks.
    Produces a structured Buy Thesis per stock with macro/geo/sentiment context.
    """
    if not ANTHROPIC_API_KEY or not stocks:
        return {}

    mkt = regime.get("signals", {})
    regime_name = regime.get("regime", "NEUTRAL")

    lines = []
    for s in stocks:
        pt_up = ((s.get("pt_mean") or 0) / (s.get("price") or 1) - 1) * 100 \
                if s.get("pt_mean") and s.get("price") else 0
        lines.append(
            f"- {s['symbol']} ({s.get('name','')}) [{s.get('sector','')}]"
            f" | Score: {s.get('weekly_score','?')}"
            f" | F:{s.get('fundamental','?')} T:{s.get('technical','?')} M:{s.get('momentum_s','?')}"
            f" | Analyst: {s.get('bull_pct','?')}% bullish ({s.get('consensus','?')})"
            f"   PT upside: {pt_up:+.1f}%"
            f" | Options C/P: {s.get('cp_ratio','N/A')} (score {s.get('options_score','?')})"
            f" | Breakout: {s.get('breakout_setup','—')} (score {s.get('breakout_score','?')})"
            f" | RVOL: {s.get('rvol','?')}"
            f" | 3M: {(s.get('r3m') or 0)*100:+.1f}%  RSI: {s.get('rsi','?')}"
            f" | Above MA200: {'yes' if s.get('above_ma200') else 'no'}"
            f" | Rev growth: {(s.get('revenue_growth') or 0)*100:+.1f}%"
            f" | Gross margin: {(s.get('gross_margin') or 0)*100:.0f}%"
            f" | Short float: {(s.get('short_float') or 0)*100:.1f}%"
        )

    prompt = f"""You are a senior portfolio manager and macro strategist producing this week's actionable buy recommendations.

CURRENT MARKET CONTEXT:
- Regime: {regime_name}
- VIX: {mkt.get('vix') or 'N/A'} — {"elevated fear" if (mkt.get('vix') or 20)>22 else "calm"}
- S&P 500: {"above" if mkt.get('spy_above_200') else "below"} MA200, 1M return: {(mkt.get('spy_r1m') or 0)*100:+.1f}%
- 10Y Yield: {mkt.get('tnx') or 'N/A'}% {"(rising — headwind for growth)" if mkt.get('tnx_rising') else "(stable)"}
- Nasdaq (QQQ) 1M: {(mkt.get('qqq_r1m') or 0)*100:+.1f}%
- Today: {datetime.now().strftime('%B %d, %Y')}

QUALIFYING STOCKS (pre-screened, passed all entry conditions):
{chr(10).join(lines)}

For EACH stock, produce a concise, opinionated Buy Thesis. Be SPECIFIC — cite exact metrics from the data above.
Reference current macro/geopolitical relevance (AI spending cycle, rate trajectory, sector rotation, China exposure, defense spending, etc.)
Factor in investor psychology: is this a "fear dip" setup? A momentum continuation? A re-rating story?
IMPORTANT: Always respond in English regardless of any context language.

Respond ONLY with valid JSON (no markdown fences):
{{
  "theses": [
    {{
      "symbol": "<ticker>",
      "action": "<STRONG BUY | BUY>",
      "conviction": <1-5>,
      "quality_flag": "<QUALITY GROWTH | MOMENTUM PLAY | SPECULATIVE>",
      "headline": "<one punchy sentence: the core thesis>",
      "why_buy": [
        "<specific reason 1 — cite a metric>",
        "<specific reason 2 — macro/sector angle>",
        "<specific reason 3 — technical/options setup>"
      ],
      "macro_relevance": "<how current macro/geo environment specifically benefits this stock this week>",
      "investor_psychology": "<current sentiment: fear dip, FOMO momentum, accumulation, rotation — and why that benefits entry>",
      "when_buy": "<exact entry condition: break above $X, dip to MA50 at $Y, buy now at market, etc.>",
      "target_zone": "<price target or % upside — be specific>",
      "stop_loss": "<specific stop level or condition>",
      "key_risk": "<the single risk that invalidates this thesis>",
      "catalyst_this_week": "<specific near-term catalyst: earnings, macro event, technical level, sector news>"
    }}
  ]
}}"""

    try:
        from utils.claude_client import extract_json, salvage_json_objects
        msg = _get_client().messages.create(
            model="claude-sonnet-5",
            max_tokens=16000,  # 22 stocks × large nested JSON — 8000 proved too small
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}],
        )
        raw = extract_json(msg.content[0].text)
        try:
            return {t["symbol"]: t for t in json.loads(raw).get("theses", [])}
        except json.JSONDecodeError:
            # Output hit max_tokens mid-JSON — salvage every COMPLETE thesis
            # and lose only the one that was cut off.
            salvaged = salvage_json_objects(raw, "theses")
            if salvaged:
                out = {t["symbol"]: t for t in salvaged if "symbol" in t}
                out["_warning"] = (f"Response was truncated — recovered "
                                   f"{len(out)} theses; the last one was lost.")
                return out
            raise
    except Exception as e:
        # Surface the failure — UI shows it instead of silently dropping all theses
        return {"_error": str(e)}


# ── Main: run automatic recommendations ───────────────────────────────────────

FINAL_CAP = 15   # max total picks shown — stocks + ETFs combined
MAX_ETFS  = 5    # ETFs never crowd out more than a third of the final list


def run_recommendations(progress_cb=None) -> dict:
    """
    Scans a weekly-rotated subset of the broad-market universe (WEEKLY_UNIVERSE
    unioned with the live S&P 500 list — see _full_stock_universe), filters by
    market regime, applies recency penalty and sector cap. Alongside the
    strict swing-entry filter, also carves out "quality on sale" stocks (good
    business, beaten-down price — see _check_quality_dip) that the swing
    filter would otherwise reject outright, and separately scans a pool of
    theme/sector ETFs for trend strength. All three feed into ONE ranked,
    capped list (see FINAL_CAP/MAX_ETFS) rather than three separate ones.
    Returns:
      {
        "regime": <regime dict>,
        "recommendations": [<qualified dicts, each tagged "category">],
        "scanned": <int>,
        "filtered_out": <int>,
        "week_num": <int>,
        "universe_size": <int>,   # size of the full deduped stock universe
      }
    Stock rows include Claude Buy Thesis if API key is set; ETF rows get a
    rule-based thesis (an LLM call doesn't fit "is this theme trending").
    """
    regime      = get_regime()
    thresholds  = regime["thresholds"]
    current_week = _current_week_num()
    pick_history = _load_pick_history()
    _FH_BREAKER["failures"] = 0   # fresh scan — give Finnhub another chance

    full_universe = _full_stock_universe()
    scan_universe = _get_weekly_sample(full_universe, n_anchor=30, n_rotating=50)
    total         = len(scan_universe)
    all_results   = []

    for i, sym in enumerate(scan_universe):
        if progress_cb:
            progress_cb((i + 0.5) / total, f"Scanning {sym}…")

        model    = _score_model(sym)
        mom      = _momentum_data(sym)
        analyst  = _analyst_data(sym)
        options  = options_analyze(sym)
        breakout = _breakout_data(sym)

        analyst_s = _analyst_score(analyst, mom.get("price", 0))
        weekly_s  = _composite(model, analyst_s, mom, options, breakout)

        row = {
            # Identity
            "symbol":     sym,
            "name":       mom.get("name", sym),
            "sector":     mom.get("sector", ""),
            "price":      mom.get("price"),
            "market_cap": mom.get("market_cap"),

            # Scores
            "weekly_score":  weekly_s,
            "model_score":   model.get("composite"),
            "model_label":   model.get("label", "N/A"),
            "model_color":   model.get("color", "#8a9bc2"),
            "fundamental":   model.get("fundamental"),
            "technical":     model.get("technical"),
            "momentum_s":    model.get("momentum"),
            "analyst_score": round(analyst_s, 1),
            "options_score": options.get("score", 5),
            "breakout_score": breakout.get("score", 5),

            # Analyst
            "bull_pct":        analyst.get("bull_pct", 0),
            "consensus":       analyst.get("consensus", "N/A"),
            "consensus_color": analyst.get("consensus_color", "#8a9bc2"),
            "total_analysts":  analyst.get("total_analysts", 0),
            "pt_mean":         analyst.get("pt_mean"),
            "pt_high":         analyst.get("pt_high"),
            "pt_low":          analyst.get("pt_low"),
            "analyst_source":  analyst.get("source", "Yahoo Finance"),
            "rec_mean":        analyst.get("rec_mean"),

            # Momentum / price
            "r1w": mom.get("r1w"), "r1m": mom.get("r1m"), "r3m": mom.get("r3m"),
            "rsi": mom.get("rsi"), "rvol": mom.get("rvol"),
            "above_ma200": mom.get("above_ma200"),
            "above_ma50":  mom.get("above_ma50"),
            "pct_vs_ma200": mom.get("pct_vs_ma200"),
            "revenue_growth": mom.get("revenue_growth"),
            "gross_margin":   mom.get("gross_margin"),
            "forward_pe":     mom.get("forward_pe"),
            "short_float":    mom.get("short_float"),

            # Options
            "cp_ratio":        options.get("cp_ratio"),
            "options_signal":  options.get("signal", ""),
            "options_has_data": options.get("has_data", False),

            # Breakout
            "breakout_setup":   breakout.get("setup", ""),
            "breakout_signals": breakout.get("signals", []),
            "pct_from_high":    breakout.get("pct_from_high"),
            "bb_squeeze":       breakout.get("squeeze", False),
            "vol_surge":        breakout.get("vol_surge", False),
        }
        all_results.append(row)

    # ── Apply recency penalty before filtering ───────────────────────────────
    for r in all_results:
        penalty = _recency_penalty(r["symbol"], pick_history, current_week)
        r["recency_penalty"] = penalty
        r["weekly_score"]    = round(max(1.0, r["weekly_score"] - penalty), 2)

    # ── Filter: swing entries pass the strict condition gate ──────────────────
    swing_qualified = [r for r in all_results if _passes_entry(r, thresholds)]
    for r in swing_qualified:
        r["category"] = "SWING"
    swing_syms = {r["symbol"] for r in swing_qualified}

    # ── Quality-dip carve-out — good business, price out of favor, would
    # otherwise be rejected outright by the swing filter above ────────────────
    if progress_cb:
        progress_cb(0.75, "Checking for quality stocks on sale…")
    dip_qualified = []
    dip_candidates = [r for r in all_results
                      if r["symbol"] not in swing_syms and (r.get("fundamental") or 0) >= 6.5]
    for r in dip_candidates:
        opp = _check_quality_dip(r["symbol"])
        if opp:
            r = dict(r)
            r["category"]              = "QUALITY_DIP"
            r["opportunity_quadrant"]  = opp.get("quadrant")
            r["opportunity_guidance"]  = opp.get("guidance")
            r["quality_score"]         = opp.get("quality")
            r["condition_score"]       = opp.get("condition")
            dip_qualified.append(r)
    dip_qualified.sort(key=lambda x: x["weekly_score"], reverse=True)

    stock_pool = swing_qualified + dip_qualified
    stock_pool.sort(key=lambda x: x["weekly_score"], reverse=True)
    stock_pool = _apply_sector_cap(stock_pool, max_per_sector=2)

    # ── ETF theme scan — separate pool, separate scoring method ───────────────
    if progress_cb:
        progress_cb(0.85, "Scanning theme ETFs…")
    etf_qualified = _scan_etfs(sector_strength.theme_etf_universe())

    # ── Combine into ONE ranked, capped list — ETFs never take more than
    # MAX_ETFS slots, but backfill with more ETFs if stocks come up short ────
    n_etf = min(MAX_ETFS, len(etf_qualified))
    n_stock_slots = FINAL_CAP - n_etf
    stock_final = stock_pool[:n_stock_slots]
    if len(stock_final) < n_stock_slots:
        n_etf = min(len(etf_qualified), n_etf + (n_stock_slots - len(stock_final)))
    qualified = stock_final + etf_qualified[:n_etf]
    qualified.sort(key=lambda x: x["weekly_score"], reverse=True)

    # ── Claude Buy Thesis — stocks only (an LLM "buy case" doesn't fit an
    # ETF's "is the theme trending" question; those get a rule-based one) ─────
    stock_rows = [r for r in qualified if r.get("category") != "ETF_THEME"]
    etf_rows   = [r for r in qualified if r.get("category") == "ETF_THEME"]
    if progress_cb:
        progress_cb(0.92, f"Claude generating buy theses for {len(stock_rows)} stocks…")

    thesis_error = None
    thesis_warning = None
    if ANTHROPIC_API_KEY and stock_rows:
        theses = claude_buy_thesis(stock_rows, regime)
        thesis_error = theses.get("_error")
        thesis_warning = theses.get("_warning")
        for r in stock_rows:
            r["thesis"] = theses.get(r["symbol"], {})
    else:
        for r in stock_rows:
            r["thesis"] = {}
    for r in etf_rows:
        r["thesis"] = _etf_thesis(r)

    # ── Persist pick history for next week's recency penalty (stocks only —
    # ETFs aren't subject to the recency penalty, they're a different asset
    # class and "the theme is still hot" isn't staleness) ─────────────────────
    new_history = dict(pick_history)
    for r in stock_rows:
        new_history[r["symbol"]] = current_week
    # Prune entries older than 6 weeks to keep the file small
    new_history = {sym: wk for sym, wk in new_history.items()
                   if abs(current_week - wk) <= 6 or (current_week < 6 and 53 - wk + current_week <= 6)}
    _save_pick_history(new_history)

    # Top 5 near-misses — stocks that were scanned but didn't qualify for the
    # strict swing filter, sorted by weekly_score so the UI can show "who
    # almost made it" (quality-dip/ETF paths don't affect this — it's
    # specifically about the swing entry conditions shown alongside it).
    not_qualified = [r for r in all_results if r["symbol"] not in swing_syms]
    not_qualified.sort(key=lambda x: x.get("weekly_score", 0), reverse=True)
    near_misses = [{
        "symbol":      r["symbol"],
        "name":        r.get("name", r["symbol"]),
        "weekly_score": r.get("weekly_score"),
        "fundamental": r.get("fundamental"),
        "technical":   r.get("technical"),
        "bull_pct":    r.get("bull_pct"),
        "above_ma200": r.get("above_ma200"),
        "r3m":         r.get("r3m"),
        "cp_ratio":    r.get("cp_ratio"),
        "options_has_data": r.get("options_has_data", False),
    } for r in not_qualified[:5]]

    return {
        "regime":          regime,
        "recommendations": qualified,
        "scanned":         total,
        "filtered_out":    total - len(swing_qualified),
        "n_swing":         len(swing_qualified),
        "n_dip":           len(dip_qualified),
        "n_etf":           len(etf_qualified),
        "near_misses":     near_misses,
        "thresholds":      thresholds,
        "week_num":        current_week,
        "universe_size":   len(full_universe),
        "pick_history":    new_history,
        "thesis_error":    thesis_error,
        "thesis_warning":  thesis_warning,
    }
