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
