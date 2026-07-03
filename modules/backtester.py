"""
Strategy Backtester — vectorized backtesting for 6 common trading strategies.
Uses yfinance daily data; no external libraries required (numpy/pandas only).
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import date

STRATEGIES: dict[str, dict] = {
    "SMA Crossover":   {"fast": 20,  "slow": 50},
    "EMA Crossover":   {"fast": 12,  "slow": 26},
    "RSI Reversal":    {"period": 14, "oversold": 30, "overbought": 70},
    "MACD":            {"fast": 12,  "slow": 26, "signal": 9},
    "Bollinger Bands": {"period": 20, "std_dev": 2.0},
    "Momentum":        {"period": 20},
}


# ── Signal generators ────────────────────────────────────────────────────────

def _sma_signals(close: pd.Series, fast: int, slow: int) -> pd.Series:
    ma_fast = close.rolling(fast).mean()
    ma_slow = close.rolling(slow).mean()
    signal = pd.Series(0, index=close.index)
    signal[ma_fast > ma_slow] = 1
    signal[ma_fast < ma_slow] = -1
    return signal


def _ema_signals(close: pd.Series, fast: int, slow: int) -> pd.Series:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    signal = pd.Series(0, index=close.index)
    signal[ema_fast > ema_slow] = 1
    signal[ema_fast < ema_slow] = -1
    return signal


def _rsi_signals(close: pd.Series, period: int, oversold: float, overbought: float) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    signal = pd.Series(0, index=close.index)
    # Enter long when RSI crosses above oversold; exit when crosses above overbought
    in_position = False
    for i in range(len(rsi)):
        v = rsi.iloc[i]
        if pd.isna(v):
            signal.iloc[i] = 0
            continue
        if not in_position and v < oversold:
            in_position = True
        elif in_position and v > overbought:
            in_position = False
        signal.iloc[i] = 1 if in_position else 0
    return signal


def _macd_signals(close: pd.Series, fast: int, slow: int, signal_period: int) -> pd.Series:
    ema_fast   = close.ewm(span=fast,   adjust=False).mean()
    ema_slow   = close.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    sig_line   = macd_line.ewm(span=signal_period, adjust=False).mean()
    signal = pd.Series(0, index=close.index)
    signal[macd_line > sig_line] = 1
    signal[macd_line < sig_line] = -1
    return signal


def _bb_signals(close: pd.Series, period: int, std_dev: float) -> pd.Series:
    mid  = close.rolling(period).mean()
    std  = close.rolling(period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    signal = pd.Series(0, index=close.index)
    in_position = False
    for i in range(len(close)):
        p = close.iloc[i]
        lo = lower.iloc[i] if not pd.isna(lower.iloc[i]) else np.nan
        up = upper.iloc[i] if not pd.isna(upper.iloc[i]) else np.nan
        if pd.isna(lo):
            signal.iloc[i] = 0
            continue
        if not in_position and p < lo:
            in_position = True
        elif in_position and p > up:
            in_position = False
        signal.iloc[i] = 1 if in_position else 0
    return signal


def _momentum_signals(close: pd.Series, period: int) -> pd.Series:
    mom = close / close.shift(period) - 1
    signal = pd.Series(0, index=close.index)
    signal[mom > 0] = 1
    signal[mom < 0] = -1
    return signal


# ── Metrics ──────────────────────────────────────────────────────────────────

def _sharpe(daily_ret: pd.Series, risk_free: float = 0.05) -> float:
    excess = daily_ret - risk_free / 252
    std = excess.std()
    return float(excess.mean() / std * np.sqrt(252)) if std > 0 else 0.0


def _sortino(daily_ret: pd.Series, risk_free: float = 0.05) -> float:
    downside_std = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    ann_ret = daily_ret.mean() * 252 - risk_free
    return float(ann_ret / downside_std) if downside_std > 0 else 0.0


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd   = (equity - peak) / peak
    return float(dd.min())


def _cagr(equity: pd.Series) -> float:
    if len(equity) < 2:
        return 0.0
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def _extract_trades(close: pd.Series, signal: pd.Series, capital: float) -> list[dict]:
    trades = []
    position = 0
    entry_price = 0.0
    cumulative = capital
    for i in range(1, len(signal)):
        prev_sig = signal.iloc[i - 1]
        curr_sig = signal.iloc[i]
        price    = close.iloc[i]
        if prev_sig <= 0 and curr_sig > 0 and position == 0:
            position    = 1
            entry_price = price
            trades.append({
                "date":   close.index[i].date() if hasattr(close.index[i], "date") else close.index[i],
                "action": "BUY",
                "price":  round(price, 2),
                "pnl":    None,
                "cum_return": None,
            })
        elif prev_sig > 0 and curr_sig <= 0 and position == 1:
            position = 0
            pnl      = (price - entry_price) / entry_price
            cumulative *= (1 + pnl)
            trades.append({
                "date":       close.index[i].date() if hasattr(close.index[i], "date") else close.index[i],
                "action":     "SELL",
                "price":      round(price, 2),
                "pnl":        round(pnl * 100, 2),
                "cum_return": round((cumulative / capital - 1) * 100, 2),
            })
    return trades


# ── Main backtest function ────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def run_backtest(
    symbol: str,
    strategy: str,
    period: str = "2y",
    capital: float = 10_000,
    params: dict | None = None,
) -> dict:
    """
    Run a vectorized backtest for the given strategy.

    Returns dict with equity_curve, benchmark_curve, trades, and performance metrics.
    On failure, returns {"error": "<message>"}.
    """
    error_result = lambda msg: {"error": msg}

    try:
        tk   = yf.Ticker(symbol.upper())
        hist = tk.history(period=period, interval="1d")
        if hist.empty or len(hist) < 60:
            return error_result(f"Not enough data for {symbol} ({period}). Try a shorter period.")
        close = hist["Close"].squeeze().dropna()
    except Exception as e:
        return error_result(f"Failed to fetch data for {symbol}: {e}")

    p = {**(STRATEGIES.get(strategy, {})), **(params or {})}

    try:
        if strategy == "SMA Crossover":
            raw_signal = _sma_signals(close, int(p["fast"]), int(p["slow"]))
        elif strategy == "EMA Crossover":
            raw_signal = _ema_signals(close, int(p["fast"]), int(p["slow"]))
        elif strategy == "RSI Reversal":
            raw_signal = _rsi_signals(close, int(p["period"]), float(p["oversold"]), float(p["overbought"]))
        elif strategy == "MACD":
            raw_signal = _macd_signals(close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
        elif strategy == "Bollinger Bands":
            raw_signal = _bb_signals(close, int(p["period"]), float(p["std_dev"]))
        elif strategy == "Momentum":
            raw_signal = _momentum_signals(close, int(p["period"]))
        else:
            return error_result(f"Unknown strategy: {strategy}")
    except Exception as e:
        return error_result(f"Signal generation failed: {e}")

    returns       = close.pct_change().fillna(0)
    strat_returns = raw_signal.shift(1).fillna(0) * returns
    equity_curve  = (1 + strat_returns).cumprod() * capital
    bm_curve      = (1 + returns).cumprod() * capital

    total_return     = float(equity_curve.iloc[-1] / capital - 1)
    benchmark_return = float(bm_curve.iloc[-1] / capital - 1)
    volatility       = float(strat_returns.std() * np.sqrt(252))

    daily_in_market  = strat_returns[raw_signal.shift(1).fillna(0) != 0]
    win_trades       = (strat_returns > 0).sum()
    loss_trades      = (strat_returns < 0).sum()
    total_trade_days = win_trades + loss_trades
    win_rate         = float(win_trades / total_trade_days) if total_trade_days > 0 else 0.0

    gross_profit = strat_returns[strat_returns > 0].sum()
    gross_loss   = abs(strat_returns[strat_returns < 0].sum())
    profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    trades = _extract_trades(close, raw_signal, capital)

    return {
        "equity_curve":      equity_curve,
        "benchmark_curve":   bm_curve,
        "trades":            trades,
        "total_return":      total_return,
        "benchmark_return":  benchmark_return,
        "cagr":              _cagr(equity_curve),
        "sharpe":            _sharpe(strat_returns),
        "sortino":           _sortino(strat_returns),
        "max_drawdown":      _max_drawdown(equity_curve),
        "win_rate":          win_rate,
        "total_trades":      len([t for t in trades if t["action"] == "SELL"]),
        "profit_factor":     profit_factor,
        "volatility":        volatility,
        "error":             None,
    }
