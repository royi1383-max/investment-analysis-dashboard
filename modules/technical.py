"""
Technical analysis module.
Uses pandas-ta for indicators. Returns score 1-10 + chart data.
"""
import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

from utils.cache import get_price_history


def _safe(val):
    if val is None: return None
    try:
        v = float(val)
        return None if np.isnan(v) else v
    except Exception:
        return None


def analyze(symbol: str) -> dict:
    df = get_price_history(symbol, period="1y")
    if df.empty or len(df) < 30:
        return {"score": 5, "scores": {}, "df": pd.DataFrame(), "signals": []}

    close = df["Close"].squeeze()
    high  = df["High"].squeeze()
    low   = df["Low"].squeeze()
    vol   = df["Volume"].squeeze()

    scores  = {}
    signals = []

    # ── Moving Averages ──────────────────────────────────────────────────────
    ma50  = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    price = float(close.iloc[-1])

    above_ma50  = price > float(ma50.iloc[-1])  if not pd.isna(ma50.iloc[-1])  else None
    above_ma200 = price > float(ma200.iloc[-1]) if not pd.isna(ma200.iloc[-1]) else None

    if above_ma50 and above_ma200:
        scores["Trend (MA)"] = 9
        signals.append(("✅", "Price above MA50 & MA200 — strong uptrend"))
    elif above_ma50:
        scores["Trend (MA)"] = 6
        signals.append(("🟡", "Price above MA50 but below MA200"))
    elif above_ma200:
        scores["Trend (MA)"] = 5
        signals.append(("🟡", "Price above MA200 but below MA50"))
    else:
        scores["Trend (MA)"] = 2
        signals.append(("❌", "Price below MA50 & MA200 — downtrend"))

    # Golden / Death Cross
    if not pd.isna(ma50.iloc[-1]) and not pd.isna(ma200.iloc[-1]):
        if above_ma50 is not None and len(ma50.dropna()) > 1:
            prev_ma50  = float(ma50.dropna().iloc[-2])
            prev_ma200 = float(ma200.dropna().iloc[-2]) if len(ma200.dropna()) > 1 else float(ma200.iloc[-1])
            cur_ma50   = float(ma50.iloc[-1])
            cur_ma200  = float(ma200.iloc[-1])
            if prev_ma50 < prev_ma200 and cur_ma50 > cur_ma200:
                signals.append(("🌟", "Golden Cross — MA50 crossed above MA200"))
            elif prev_ma50 > prev_ma200 and cur_ma50 < cur_ma200:
                signals.append(("💀", "Death Cross — MA50 crossed below MA200"))

    # ── RSI ──────────────────────────────────────────────────────────────────
    if HAS_TA:
        rsi_series = ta.rsi(close, length=14)
        rsi = _safe(rsi_series.iloc[-1]) if rsi_series is not None else None
    else:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi_series = 100 - (100 / (1 + rs))
        rsi = _safe(rsi_series.iloc[-1])

    if rsi is not None:
        if 40 <= rsi <= 60:
            scores["RSI"] = 7
        elif 30 <= rsi < 40:
            scores["RSI"] = 8
            signals.append(("📈", f"RSI={rsi:.1f} — approaching oversold, potential bounce"))
        elif rsi < 30:
            scores["RSI"] = 9
            signals.append(("🔥", f"RSI={rsi:.1f} — oversold"))
        elif 60 < rsi <= 70:
            scores["RSI"] = 6
        else:
            scores["RSI"] = 3
            signals.append(("⚠️", f"RSI={rsi:.1f} — overbought"))
    else:
        scores["RSI"] = 5

    # ── MACD ─────────────────────────────────────────────────────────────────
    if HAS_TA:
        macd_df = ta.macd(close)
        if macd_df is not None and not macd_df.empty:
            macd_col  = [c for c in macd_df.columns if "MACD_" in c and "MACDs" not in c and "MACDh" not in c]
            sig_col   = [c for c in macd_df.columns if "MACDs_" in c]
            hist_col  = [c for c in macd_df.columns if "MACDh_" in c]
            macd_val  = _safe(macd_df[macd_col[0]].iloc[-1])  if macd_col  else None
            macd_sig  = _safe(macd_df[sig_col[0]].iloc[-1])   if sig_col   else None
            macd_hist = _safe(macd_df[hist_col[0]].iloc[-1])  if hist_col  else None
        else:
            macd_val = macd_sig = macd_hist = None
    else:
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd_line = ema12 - ema26
        macd_sig_line = macd_line.ewm(span=9).mean()
        macd_val  = _safe(macd_line.iloc[-1])
        macd_sig  = _safe(macd_sig_line.iloc[-1])
        macd_hist = (macd_val - macd_sig) if macd_val and macd_sig else None
        macd_df   = pd.DataFrame({"MACD": macd_line, "Signal": macd_sig_line})

    if macd_val is not None and macd_sig is not None:
        if macd_val > macd_sig and (macd_hist or 0) > 0:
            scores["MACD"] = 8
            signals.append(("✅", "MACD above signal — bullish momentum"))
        elif macd_val < macd_sig:
            scores["MACD"] = 3
            signals.append(("❌", "MACD below signal — bearish momentum"))
        else:
            scores["MACD"] = 5
    else:
        scores["MACD"] = 5

    # ── Volume ────────────────────────────────────────────────────────────────
    vol_avg20 = vol.rolling(20).mean()
    cur_vol   = float(vol.iloc[-1])
    avg_vol   = float(vol_avg20.iloc[-1]) if not pd.isna(vol_avg20.iloc[-1]) else cur_vol
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 1.0

    if vol_ratio > 1.5:
        scores["Volume"] = 8
        signals.append(("📊", f"Volume {vol_ratio:.1f}x above average — strong conviction"))
    elif vol_ratio > 1.0:
        scores["Volume"] = 6
    elif vol_ratio > 0.7:
        scores["Volume"] = 5
    else:
        scores["Volume"] = 3

    # ── 52-Week position ──────────────────────────────────────────────────────
    high52 = float(high.rolling(252).max().iloc[-1]) if len(high) >= 252 else float(high.max())
    low52  = float(low.rolling(252).min().iloc[-1])  if len(low)  >= 252 else float(low.min())
    pct_from_high = (price - high52) / high52 if high52 > 0 else 0
    pct_from_low  = (price - low52)  / (high52 - low52) if (high52 - low52) > 0 else 0.5

    if pct_from_high > -0.05:
        scores["52W Position"] = 9
        signals.append(("🏆", "Near 52-week high — strong trend"))
    elif pct_from_high > -0.15:
        scores["52W Position"] = 7
    elif pct_from_high > -0.30:
        scores["52W Position"] = 5
    else:
        scores["52W Position"] = 3
        signals.append(("📉", f"Price {abs(pct_from_high)*100:.0f}% below 52W high"))

    # ── Weighted score ────────────────────────────────────────────────────────
    weights = {
        "Trend (MA)":    0.30,
        "RSI":           0.20,
        "MACD":          0.25,
        "Volume":        0.10,
        "52W Position":  0.15,
    }
    total = sum(scores.get(k, 5) * w for k, w in weights.items())

    # Add indicators to df for charting
    df = df.copy()
    df["MA50"]  = close.rolling(50).mean()
    df["MA200"] = close.rolling(200).mean()
    df["RSI"]   = rsi_series

    return {
        "score":   round(total, 2),
        "scores":  scores,
        "signals": signals,
        "df":      df,
        "rsi":     rsi,
        "macd_val": macd_val,
        "macd_sig": macd_sig,
        "high52":   high52,
        "low52":    low52,
        "price":    price,
        "vol_ratio": vol_ratio,
    }
