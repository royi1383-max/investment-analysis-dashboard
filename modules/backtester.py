"""
Strategy Backtester — vectorized backtesting for 6 common trading strategies.
Uses yfinance daily data; no external libraries required (numpy/pandas only).
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

STRATEGIES: dict[str, dict] = {
    "SMA Crossover":       {"fast": 20,  "slow": 50},
    "EMA Crossover":       {"fast": 12,  "slow": 26},
    "RSI Reversal":        {"period": 14, "oversold": 30, "overbought": 70},
    "MACD":                {"fast": 12,  "slow": 26, "signal": 9},
    "Bollinger Bands":     {"period": 20, "std_dev": 2.0},
    "Momentum":            {"period": 20},
    "Technical Consensus": {},
}

# Small parameter grids searched on the TRAIN window only, for walk-forward
# out-of-sample validation (run_backtest_walkforward). Never search on test data.
_PARAM_GRID: dict[str, list[dict]] = {
    "SMA Crossover":       [{"fast": 10, "slow": 30}, {"fast": 20, "slow": 50}, {"fast": 30, "slow": 100}],
    "EMA Crossover":       [{"fast": 8,  "slow": 21}, {"fast": 12, "slow": 26}, {"fast": 19, "slow": 39}],
    "RSI Reversal":        [{"period": 14, "oversold": 30, "overbought": 70},
                            {"period": 14, "oversold": 25, "overbought": 75},
                            {"period": 21, "oversold": 30, "overbought": 70}],
    "MACD":                [{"fast": 12, "slow": 26, "signal": 9}, {"fast": 8, "slow": 17, "signal": 9}],
    "Bollinger Bands":     [{"period": 20, "std_dev": 2.0}, {"period": 20, "std_dev": 2.5}, {"period": 10, "std_dev": 1.5}],
    "Momentum":            [{"period": 10}, {"period": 20}, {"period": 60}],
    "Technical Consensus": [{}],
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
    from utils.indicators import rsi as _rsi_fn
    rsi = _rsi_fn(close, period)
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
    from utils.indicators import macd as _macd_fn
    macd_line, sig_line, _ = _macd_fn(close, fast, slow, signal_period, adjust=False)
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


def _technical_consensus_signals(close: pd.Series) -> pd.Series:
    """Equal-weighted majority vote across Turtle breakout, MA/12-1
    trend-following, a Minervini-style trend template, and 20d momentum —
    the same 'every method counts once' philosophy as
    fund_models.combined_verdict(), but computed causally bar-by-bar (every
    rolling window only ever looks at past + current data) so it can be
    walk-forward tested without look-ahead bias."""
    n = len(close)
    signal = pd.Series(0, index=close.index)
    if n < 260:
        return signal

    # Turtle: long while price stays inside the 20d-high/10d-low channel of PRIOR bars.
    prev_hi20 = close.shift(1).rolling(20).max()
    prev_lo10 = close.shift(1).rolling(10).min()
    turtle_on = pd.Series(False, index=close.index)
    in_pos = False
    for i in range(n):
        hi, lo = prev_hi20.iloc[i], prev_lo10.iloc[i]
        if pd.isna(hi) or pd.isna(lo):
            continue
        if not in_pos and close.iloc[i] > hi:
            in_pos = True
        elif in_pos and close.iloc[i] < lo:
            in_pos = False
        turtle_on.iloc[i] = in_pos

    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()
    mom_12_1 = close.shift(21) / close.shift(252) - 1   # 12-1 momentum, causal
    trend_bull = (close > ma200) & (ma50 > ma200) & (mom_12_1 > 0)
    trend_bear = (close < ma200) & (ma50 < ma200) & (mom_12_1 < 0)

    hi52 = close.rolling(252).max()
    lo52 = close.rolling(252).min()
    minervini_bull = ((close > ma150) & (close > ma200) & (ma150 > ma200) &
                      (close > ma50) & (close >= lo52 * 1.30) & (close >= hi52 * 0.75))

    mom20 = close / close.shift(20) - 1
    mom_bull = mom20 > 0
    mom_bear = mom20 < 0

    n_bull = turtle_on.astype(int) + trend_bull.astype(int) + minervini_bull.astype(int) + mom_bull.astype(int)
    n_bear = trend_bear.astype(int) + mom_bear.astype(int)
    signal[n_bull >= 3] = 1
    signal[(n_bull < 3) & (n_bear >= 2)] = -1
    return signal


def _signal_for(strategy: str, close: pd.Series, p: dict) -> pd.Series:
    """Dispatch to the right signal generator. Shared by run_backtest and
    run_backtest_walkforward so both use identical signal logic."""
    if strategy == "SMA Crossover":
        return _sma_signals(close, int(p["fast"]), int(p["slow"]))
    if strategy == "EMA Crossover":
        return _ema_signals(close, int(p["fast"]), int(p["slow"]))
    if strategy == "RSI Reversal":
        return _rsi_signals(close, int(p["period"]), float(p["oversold"]), float(p["overbought"]))
    if strategy == "MACD":
        return _macd_signals(close, int(p["fast"]), int(p["slow"]), int(p["signal"]))
    if strategy == "Bollinger Bands":
        return _bb_signals(close, int(p["period"]), float(p["std_dev"]))
    if strategy == "Momentum":
        return _momentum_signals(close, int(p["period"]))
    if strategy == "Technical Consensus":
        return _technical_consensus_signals(close)
    raise ValueError(f"Unknown strategy: {strategy}")


# ── Metrics ──────────────────────────────────────────────────────────────────

# Below this, a "vol" is floating-point noise from std() of a (near-)constant
# series (e.g. all-zero returns when a strategy never triggers a signal) —
# not real variance. Guards against Sharpe/Sortino exploding to absurd
# values like 1e17 on a flat/no-trade period.
_MIN_MEANINGFUL_STD = 1e-10


def _sharpe(daily_ret: pd.Series, risk_free: float = 0.05) -> float:
    excess = daily_ret - risk_free / 252
    std = excess.std()
    return float(excess.mean() / std * np.sqrt(252)) if std > _MIN_MEANINGFUL_STD else 0.0


def _sortino(daily_ret: pd.Series, risk_free: float = 0.05) -> float:
    downside_std = daily_ret[daily_ret < 0].std() * np.sqrt(252)
    ann_ret = daily_ret.mean() * 252 - risk_free
    return float(ann_ret / downside_std) if downside_std > _MIN_MEANINGFUL_STD else 0.0


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
        raw_signal = _signal_for(strategy, close, p)
    except Exception as e:
        return error_result(f"Signal generation failed: {e}")

    returns       = close.pct_change(fill_method=None).fillna(0)
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


# ── Walk-forward validation ───────────────────────────────────────────────────

def _segment_metrics(close: pd.Series, raw_signal: pd.Series, seg_index: pd.Index, capital: float) -> dict:
    seg_ret = close.pct_change(fill_method=None).fillna(0).reindex(seg_index)
    seg_sig = raw_signal.shift(1).fillna(0).reindex(seg_index).fillna(0)
    strat_ret = seg_sig * seg_ret
    equity = (1 + strat_ret).cumprod() * capital
    bm     = (1 + seg_ret).cumprod() * capital
    active = strat_ret[strat_ret != 0]
    return {
        "total_return":     float(equity.iloc[-1] / capital - 1) if len(equity) else 0.0,
        "benchmark_return": float(bm.iloc[-1] / capital - 1) if len(bm) else 0.0,
        "sharpe":           _sharpe(strat_ret),
        "sortino":          _sortino(strat_ret),
        "max_drawdown":     _max_drawdown(equity),
        "win_rate":         float((active > 0).sum() / len(active)) if len(active) else 0.0,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def run_backtest_walkforward(
    symbol: str,
    strategy: str,
    period: str = "3y",
    capital: float = 10_000,
    params: dict | None = None,
    train_frac: float = 0.7,
) -> dict:
    """
    Walk-forward validation: pick the best parameter set on the TRAIN window
    only (by in-sample Sharpe), then evaluate that SAME frozen parameter set
    on the TEST window it never saw. Reports both, plus a robustness verdict.

    This is the honest way to check whether a technical strategy (or the
    'Technical Consensus' composite) has real out-of-sample edge, vs. just
    fitting noise — the discipline RN SB's own backtest-methodology notes
    ('Ten Performance Criteria', walk-forward/out-of-sample testing) insist on.

    NOTE: this only works for strategies built purely from PRICE history.
    Fundamental-based checklists (Buffett, Piotroski, Graham, ...) cannot be
    walk-forward tested this way — yfinance only exposes CURRENT fundamentals,
    not point-in-time historical snapshots, so any attempt would have
    look-ahead bias baked in. Use score_validation.py's live forward-tracking
    for those instead.
    """
    try:
        tk   = yf.Ticker(symbol.upper())
        hist = tk.history(period=period, interval="1d")
        if hist.empty or len(hist) < 120:
            return {"error": f"Not enough data for {symbol} ({period}). Try a longer period."}
        close = hist["Close"].squeeze().dropna()
    except Exception as e:
        return {"error": f"Failed to fetch data for {symbol}: {e}"}

    split_i = int(len(close) * train_frac)
    if split_i < 60 or (len(close) - split_i) < 30:
        return {"error": "Not enough data to split into meaningful train/test windows."}
    train_idx, test_idx = close.index[:split_i], close.index[split_i:]

    candidates = list(_PARAM_GRID.get(strategy, [params or {}]))
    if params and params not in candidates:
        candidates = [params] + candidates

    best = None
    for cand in candidates:
        p = {**(STRATEGIES.get(strategy, {})), **cand}
        try:
            raw_signal = _signal_for(strategy, close, p)
        except Exception:
            continue
        train_metrics = _segment_metrics(close, raw_signal, train_idx, capital)
        if best is None or train_metrics["sharpe"] > best["train"]["sharpe"]:
            best = {"params": cand, "train": train_metrics, "signal": raw_signal}

    if best is None:
        return {"error": "No valid parameter set produced a usable signal."}

    test_metrics = _segment_metrics(close, best["signal"], test_idx, capital)
    degradation  = best["train"]["sharpe"] - test_metrics["sharpe"]

    if test_metrics["sharpe"] <= 0:
        verdict = "OVERFIT WARNING — out-of-sample Sharpe is zero or negative; the in-sample edge did not survive."
    elif test_metrics["sharpe"] >= best["train"]["sharpe"] * 0.5:
        verdict = "ROBUST — out-of-sample Sharpe holds up reasonably close to in-sample; the edge looks real."
    else:
        verdict = "DEGRADED — out-of-sample Sharpe is well below in-sample; treat the strategy with caution."

    return {
        "symbol":             symbol.upper(),
        "strategy":           strategy,
        "chosen_params":      best["params"],
        "train_period":       (str(train_idx[0].date()), str(train_idx[-1].date())),
        "test_period":        (str(test_idx[0].date()), str(test_idx[-1].date())),
        "in_sample":          best["train"],
        "out_of_sample":      test_metrics,
        "sharpe_degradation": round(degradation, 2),
        "verdict":            verdict,
        "error":              None,
    }
