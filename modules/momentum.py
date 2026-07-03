"""
Momentum & Relative Strength module.
Compares ticker vs SPY over multiple timeframes.
"""
import pandas as pd
import numpy as np
from utils.cache import get_price_history


def _return(df: pd.DataFrame, days: int) -> float | None:
    close = df["Close"].squeeze()
    if len(close) < days + 1:
        return None
    return float(close.iloc[-1] / close.iloc[-days] - 1)


def _score_return(ret):
    if ret is None: return 5
    if ret > 0.50:  return 10
    if ret > 0.25:  return 9
    if ret > 0.10:  return 7
    if ret > 0.02:  return 6
    if ret > -0.05: return 5
    if ret > -0.15: return 3
    return 1


def _score_rs(ticker_ret, bench_ret):
    if ticker_ret is None or bench_ret is None: return 5
    outperf = ticker_ret - bench_ret
    if outperf > 0.20:  return 10
    if outperf > 0.10:  return 8
    if outperf > 0.02:  return 6
    if outperf > -0.02: return 5
    if outperf > -0.10: return 3
    return 1


def analyze(symbol: str) -> dict:
    df_tick = get_price_history(symbol, period="2y")
    df_spy  = get_price_history("SPY", period="2y")

    periods = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    returns = {}
    spy_ret = {}
    scores  = {}

    for label, days in periods.items():
        r = _return(df_tick, days)
        s = _return(df_spy, days)
        returns[label] = r
        spy_ret[label] = s
        rs_score = _score_rs(r, s)
        abs_score = _score_return(r)
        scores[f"Abs {label}"] = abs_score
        scores[f"RS vs SPY {label}"] = rs_score

    # Overall momentum score: weight recent periods more
    period_weights = {"1M": 0.15, "3M": 0.25, "6M": 0.30, "1Y": 0.30}
    momentum_score = sum(
        (scores.get(f"RS vs SPY {k}", 5) * 0.6 + scores.get(f"Abs {k}", 5) * 0.4) * w
        for k, w in period_weights.items()
    )

    # Sector momentum: compare to QQQ
    df_qqq = get_price_history("QQQ", period="2y")
    qqq_ret_3m = _return(df_qqq, 63)
    rs_vs_qqq_3m = (returns["3M"] - qqq_ret_3m) if returns["3M"] and qqq_ret_3m else None

    return {
        "score":        round(momentum_score, 2),
        "scores":       scores,
        "returns":      returns,
        "spy_returns":  spy_ret,
        "rs_vs_qqq_3m": rs_vs_qqq_3m,
        "df":           df_tick,
    }
