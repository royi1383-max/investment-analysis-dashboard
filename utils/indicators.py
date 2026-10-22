"""
Shared technical indicators — single source of truth.

Replaces 5 separate RSI implementations and 2 MACD implementations that
previously lived in: technical.py, ai_screener.py, weekly_picks.py,
alerts.py, backtester.py.

All functions accept a pandas Series of closing prices.
"""
import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder-smoothed-free simple RSI (rolling mean), matching the
    implementation previously used across the project.
    Zero-loss windows (14 straight up days) correctly yield RSI=100
    instead of NaN."""
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    out   = 100 - 100 / (1 + rs)
    # All-gains window → mathematically RSI = 100 (was NaN)
    out[(loss == 0) & (gain > 0)] = 100.0
    return out


def rsi_last(close: pd.Series, period: int = 14) -> float | None:
    """Latest RSI value, or None if not computable."""
    try:
        if len(close) < period + 1:
            return None
        val = float(rsi(close, period).iloc[-1])
        return None if np.isnan(val) else round(val, 1)
    except Exception:
        return None


def macd(close: pd.Series, fast: int = 12, slow: int = 26,
         signal: int = 9, adjust: bool = False) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Returns (macd_line, signal_line, histogram)."""
    ema_fast  = close.ewm(span=fast, adjust=adjust).mean()
    ema_slow  = close.ewm(span=slow, adjust=adjust).mean()
    macd_line = ema_fast - ema_slow
    sig_line  = macd_line.ewm(span=signal, adjust=adjust).mean()
    return macd_line, sig_line, macd_line - sig_line


def trailing_return(close: pd.Series, days: int) -> float | None:
    """Return over the trailing window using the project-wide convention
    `close[-1] / close[-days] - 1` (21=1M, 63=3M, 126=6M).
    None when insufficient history."""
    try:
        if len(close) < days + 1:
            return None
        return float(close.iloc[-1] / close.iloc[-days] - 1)
    except Exception:
        return None


def find_swing_points(series: pd.Series, order: int = 5) -> tuple[list[int], list[int]]:
    """
    Swing highs/lows: a bar whose value is the strict max/min among the
    `order` bars on EITHER side of it. Positional (iloc) indices, not
    labels — deliberately simple/deterministic (no smoothing, no ML) so a
    support/resistance level or trendline built from these is fully
    explainable from the price series alone.
    Returns (high_idx, low_idx).
    """
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    highs, lows = [], []
    for i in range(order, n - order):
        window = vals[i - order:i + order + 1]
        if vals[i] == window.max() and np.sum(window == vals[i]) == 1:
            highs.append(i)
        if vals[i] == window.min() and np.sum(window == vals[i]) == 1:
            lows.append(i)
    return highs, lows


def support_resistance_levels(df: pd.DataFrame, order: int = 5,
                              cluster_pct: float = 0.02, max_levels: int = 3) -> dict:
    """
    Horizontal support/resistance from clustered swing-point prices —
    a level that's been touched by 2+ swing highs/lows within
    `cluster_pct` of each other is a real level, not a one-off wiggle.
    Returns {"resistance": [prices above current, nearest first],
             "support": [prices below current, nearest first]}.
    """
    if df.empty or len(df) < order * 2 + 2:
        return {"resistance": [], "support": []}

    high_idx, low_idx = find_swing_points(df["Close"].squeeze(), order=order)
    current = float(df["Close"].squeeze().iloc[-1])

    def _cluster(idx_list, col):
        prices = sorted(float(df[col].squeeze().iloc[i]) for i in idx_list)
        clusters: list[list[float]] = []
        for p in prices:
            if clusters and abs(p - clusters[-1][-1]) / clusters[-1][-1] <= cluster_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        # Only clusters with 2+ touches count as a real level.
        return [sum(c) / len(c) for c in clusters if len(c) >= 2]

    levels = _cluster(high_idx, "High") + _cluster(low_idx, "Low")
    resistance = sorted([lv for lv in levels if lv > current])[:max_levels]
    support    = sorted([lv for lv in levels if lv < current], reverse=True)[:max_levels]
    return {"resistance": resistance, "support": support}


def trendlines(df: pd.DataFrame, order: int = 5, lookback_pivots: int = 4) -> dict:
    """
    Support/resistance TRENDLINES (as opposed to horizontal levels): a
    least-squares line through the most recent swing lows (rising line
    under an uptrend) and another through the most recent swing highs
    (falling line over a downtrend) — the two lines classically drawn by
    hand to frame a trend channel. Needs 2+ pivots of each type; returns
    None for a side that doesn't have enough.
    Returns {"support": {"x": [ts0, ts1], "y": [p0, p1]} | None,
             "resistance": {...} | None}.
    """
    if df.empty or len(df) < order * 2 + 2:
        return {"support": None, "resistance": None}

    close = df["Close"].squeeze()
    high_idx, low_idx = find_swing_points(close, order=order)
    n = len(df)

    def _fit(idx_list, col):
        recent = idx_list[-lookback_pivots:]
        if len(recent) < 2:
            return None
        xs = np.array(recent, dtype=float)
        ys = np.array([float(df[col].squeeze().iloc[i]) for i in recent])
        slope, intercept = np.polyfit(xs, ys, 1)
        x0, x1 = recent[0], n - 1
        y0, y1 = slope * x0 + intercept, slope * x1 + intercept
        return {"x": [df.index[x0], df.index[x1]], "y": [float(y0), float(y1)]}

    return {
        "support":    _fit(low_idx, "Low"),
        "resistance": _fit(high_idx, "High"),
    }
