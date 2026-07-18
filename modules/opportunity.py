"""
Opportunity Lens — separates BUSINESS QUALITY from CURRENT CONDITION.

The composite score measures what's happening NOW — so a great business in a
temporary, sentiment-driven drawdown scores low, exactly when it might be the
best buy. This module splits the read into two independent axes:

  QUALITY  (slow-moving, momentum-free): margins vs sector, ROE, FCF,
           balance sheet, Piotroski F-Score — is the BUSINESS intact?
  CONDITION (fast-moving): trend, momentum, RSI — is the STOCK acting well?

Quadrant verdicts:
  Quality↑ Condition↑  →  LEADER            (own it)
  Quality↑ Condition↓  →  QUALITY ON SALE   (the opportunity case — gate entry
                                             on reversal signals, not hope)
  Quality↓ Condition↑  →  MOMENTUM ONLY     (rent, don't own)
  Quality↓ Condition↓  →  FALLING KNIFE     (cheap for a reason)

Reversal Readiness (0-5, deterministic — is the turn actually starting?):
  1. Higher low        — last swing low above the prior swing low
  2. RSI divergence    — price made a lower low, RSI made a higher low
  3. Base forming      — 20d volatility contracting vs 60d (range tightening)
  4. MA20 reclaim      — price back above a rising MA20
  5. Selling exhausted — down-day volume drying up vs prior month
"""
import numpy as np
import pandas as pd
import streamlit as st

from utils.cache import get_ticker_info, get_price_history
from utils.indicators import rsi, rsi_last, trailing_return


# ─── Quality axis (momentum-free) ─────────────────────────────────────────────

def _quality_score(symbol: str, info: dict) -> tuple[float, list]:
    """0-10 from fundamentals only. Returns (score, [(label, pts, max, detail)])."""
    from modules.metric_context import _SECTOR_NORMS
    parts = []

    sector = info.get("sector") or ""
    gm = info.get("grossMargins")
    lo, hi = _SECTOR_NORMS.get(sector, {}).get("gm", (25, 55))
    if gm is not None:
        gm_pts = 2.0 if gm * 100 > hi else 1.2 if gm * 100 >= lo else 0.0
        parts.append(("Margins vs sector", gm_pts, 2.0, f"{gm*100:.0f}% (band {lo}-{hi}%)"))
    roe = info.get("returnOnEquity")
    if roe is not None:
        roe_pts = 2.0 if roe >= 0.20 else 1.5 if roe >= 0.12 else 0.8 if roe >= 0.08 else 0.0
        parts.append(("Return on equity", roe_pts, 2.0, f"{roe*100:.0f}%"))
    fcf, mc = info.get("freeCashflow"), info.get("marketCap")
    if fcf is not None and mc:
        fy = fcf / mc * 100
        fy_pts = 2.0 if fy >= 4 else 1.2 if fy > 1 else 0.6 if fy > 0 else 0.0
        parts.append(("FCF generation", fy_pts, 2.0, f"{fy:.1f}% yield"))
    d2e_raw = info.get("debtToEquity")
    if d2e_raw is not None:
        d2e = d2e_raw / 100 if d2e_raw > 10 else d2e_raw
        cap = _SECTOR_NORMS.get(sector, {}).get("d2e", 1.2)
        de_pts = 1.5 if d2e <= cap * 0.5 else 1.0 if d2e <= cap else 0.0
        parts.append(("Balance sheet", de_pts, 1.5, f"D/E {d2e:.2f} (cap {cap:.1f})"))
    try:
        from modules.fund_models import piotroski_fscore
        pio = piotroski_fscore(symbol)
        if pio.get("score") is not None:
            p_pts = 2.5 if pio["score"] >= 8 else 1.8 if pio["score"] >= 6 else 1.0 if pio["score"] >= 5 else 0.0
            parts.append(("Piotroski trajectory", p_pts, 2.5, f"F-Score {pio['score']}/9"))
    except Exception:
        pass

    if not parts:
        return 5.0, []
    total = sum(p for _, p, _, _ in parts)
    mx    = sum(m for _, _, m, _ in parts)
    return round(total / mx * 10, 1), parts


# ─── Condition axis (price action only) ───────────────────────────────────────

def _condition_score(close: pd.Series) -> tuple[float, str]:
    """0-10 from trend + momentum. Returns (score, one-line detail)."""
    if close is None or len(close) < 70:
        return 5.0, "Insufficient history"
    price = float(close.iloc[-1])
    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
    r1m = trailing_return(close, 21) or 0
    r3m = trailing_return(close, 63) or 0

    s = 5.0
    s += 1.5 if price > ma50 else -1.5
    if ma200 is not None:
        s += 1.5 if price > ma200 else -1.5
    s += float(np.clip(r1m * 12, -1.5, 1.5))
    s += float(np.clip(r3m * 6,  -1.5, 1.5))
    s = round(max(0, min(10, s)), 1)
    detail = (f"{'above' if price > ma50 else 'below'} MA50"
              + (f", {'above' if price > ma200 else 'below'} MA200" if ma200 else "")
              + f", 1M {r1m*100:+.0f}%, 3M {r3m*100:+.0f}%")
    return s, detail


# ─── Reversal readiness detectors ─────────────────────────────────────────────

def _reversal_signals(df: pd.DataFrame) -> list[tuple[str, bool, str]]:
    """5 deterministic bottom-formation signals on OHLCV daily data."""
    out = []
    try:
        close = df["Close"].squeeze().dropna()
        low   = df["Low"].squeeze().dropna()
        vol   = df["Volume"].squeeze().fillna(0)
        if len(close) < 90:
            return [("Insufficient history", False, "need ~4 months of data")]

        # 1. Higher low — the most recent 15d swing low sits above the prior one
        w = 15
        seg3 = float(low.iloc[-w:].min())
        seg2 = float(low.iloc[-2*w:-w].min())
        seg1 = float(low.iloc[-3*w:-2*w].min())
        higher_low = seg3 > seg2
        out.append(("Higher low forming", higher_low,
                    f"swing lows: {seg1:.2f} → {seg2:.2f} → {seg3:.2f}"))

        # 2. RSI positive divergence — price lower low, RSI higher low
        r = rsi(close).dropna()
        div = False
        if len(r) >= 2*w:
            p_now, p_prev = float(close.iloc[-w:].min()), float(close.iloc[-2*w:-w].min())
            r_now, r_prev = float(r.iloc[-w:].min()), float(r.iloc[-2*w:-w].min())
            div = p_now < p_prev and r_now > r_prev + 2
        out.append(("RSI positive divergence", div,
                    "price lower low but RSI refusing to confirm" if div else
                    "no divergence — momentum confirms the price weakness"))

        # 3. Base forming — 20d realized vol vs prior 60d
        ret = close.pct_change(fill_method=None).dropna()
        v20 = float(ret.iloc[-20:].std())
        v60 = float(ret.iloc[-80:-20].std())
        base = v60 > 0 and v20 < v60 * 0.75
        out.append(("Volatility contracting (base)", base,
                    f"20d vol at {v20/v60*100:.0f}% of prior level" if v60 > 0 else "n/a"))

        # 4. MA20 reclaim with MA20 turning up
        ma20 = close.rolling(20).mean()
        reclaim = (float(close.iloc[-1]) > float(ma20.iloc[-1]) and
                   float(ma20.iloc[-1]) > float(ma20.iloc[-5]))
        out.append(("Price reclaimed rising MA20", reclaim,
                    "first trend structure repair" if reclaim else "still under the short trend"))

        # 5. Selling exhaustion — down-day volume drying up
        down_days = ret < 0
        dv_recent = float(np.nan_to_num(vol.iloc[-10:][down_days.iloc[-10:]].mean()))
        dv_prior  = float(np.nan_to_num(vol.iloc[-40:-10][down_days.iloc[-40:-10]].mean()))
        dry = dv_prior > 0 and dv_recent < dv_prior * 0.7
        out.append(("Selling pressure drying up", dry,
                    f"down-day volume at {dv_recent/dv_prior*100:.0f}% of prior month" if dv_prior > 0 else "n/a"))
    except Exception as e:
        out.append(("Signal computation failed", False, str(e)))
    return out


# ─── Main ─────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def analyze(symbol: str) -> dict:
    """Full opportunity read. Returns quadrant verdict + guidance."""
    try:
        info = get_ticker_info(symbol)
        df   = get_price_history(symbol, period="1y")
        if df.empty:
            return {"error": "No price data"}
        close = df["Close"].squeeze()

        quality, q_parts = _quality_score(symbol, info)
        condition, c_detail = _condition_score(close)

        hi52 = info.get("fiftyTwoWeekHigh")
        price = info.get("currentPrice") or info.get("regularMarketPrice") or float(close.iloc[-1])
        dd = (price / hi52 - 1) * 100 if hi52 else None

        signals = _reversal_signals(df)
        readiness = sum(1 for _, ok, _ in signals if ok)

        hq, lq = quality >= 6.5, quality < 4.5
        hc, lc = condition >= 6, condition <= 4

        if hq and hc:
            quadrant, color = "LEADER", "#16c784"
            guidance = ("Quality business acting well — this is what you hold. The risk is "
                        "overpaying, not the business; check valuation, not the chart.")
        elif hq and lc:
            quadrant, color = "QUALITY ON SALE", "#4da3ff"
            if readiness >= 3:
                guidance = (f"The business is intact but the stock is out of favor — AND "
                            f"{readiness}/5 reversal signals are firing. This is the zone where "
                            f"a starter position (⅓–½ size) with a stop under the recent low "
                            f"makes sense. Add on trend confirmation (MA50 reclaim).")
            else:
                guidance = (f"The business is intact but the stock is still falling — only "
                            f"{readiness}/5 reversal signals. DON'T catch it yet: put it on the "
                            f"watchlist and wait for at least 3 signals (higher low + base + "
                            f"MA20 reclaim is the classic sequence). Opportunity ≠ timing.")
        elif lq and lc:
            quadrant, color = "FALLING KNIFE", "#ea3a44"
            guidance = ("Weak business AND weak stock — the market is right about this one. "
                        "Cheapness is the bait, deteriorating fundamentals are the hook. "
                        "Needs a fundamental turnaround story, not just a bounce.")
        elif lq and hc:
            quadrant, color = "MOMENTUM WITHOUT QUALITY", "#f97316"
            guidance = ("The stock acts great but the business doesn't back it — this works "
                        "until it doesn't, violently. Trade it with stops if at all; never "
                        "average down on it.")
        else:
            quadrant, color = "MIXED / TRANSITIONAL", "#f0b90b"
            guidance = ("Neither axis is decisive — the honest read is 'no edge'. Let it "
                        "develop; the best trades come from clearer quadrants.")

        return {
            "quality": quality, "quality_parts": q_parts,
            "condition": condition, "condition_detail": c_detail,
            "drawdown": round(dd, 1) if dd is not None else None,
            "signals": signals, "readiness": readiness,
            "quadrant": quadrant, "color": color, "guidance": guidance,
            "error": None,
        }
    except Exception as e:
        return {"error": str(e)}
