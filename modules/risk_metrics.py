"""
Portfolio Risk Metrics — correlation, beta, max drawdown, VaR.
All computed from 1-year daily price history via yfinance (no external API).
"""
import numpy as np
import pandas as pd
import streamlit as st
from utils.cache import get_price_history


@st.cache_data(ttl=1800, show_spinner=False)
def _daily_returns(symbol: str) -> pd.Series:
    try:
        ph = get_price_history(symbol, period="1y")
        if ph.empty:
            return pd.Series(dtype=float)
        c = ph["Close"].squeeze()
        return c.pct_change(fill_method=None).dropna()
    except Exception:
        return pd.Series(dtype=float)


def compute_risk(symbols: list[str], weights: list[float]) -> dict:
    """
    symbols  — list of US tickers
    weights  — portfolio weights (same length, will be normalised to sum=1)

    Returns:
      correlation_matrix  pd.DataFrame
      portfolio_beta      float   vs SPY
      max_drawdown_pct    float   (negative, e.g. -22.4)
      var_95_1d           float   (negative %, worst-case 1-day at 95% conf)
      var_95_1w           float   (negative %, 1-week scaled)
      annual_vol_pct      float   annualised portfolio volatility
      sharpe_approx       float   annualised Sharpe (0% risk-free)
      concentration_hhi   float   0-1 Herfindahl index
      risk_flags          list[str]
    """
    if not symbols or not weights:
        return {}

    symbols = [s.upper() for s in symbols]
    w = np.array(weights[: len(symbols)], dtype=float)
    w = w / w.sum()

    # ── Fetch returns ─────────────────────────────────────────────────────────
    raw = {s: _daily_returns(s) for s in symbols}
    spy_raw = _daily_returns("SPY")

    valid = {s: r for s, r in raw.items() if not r.empty}
    if len(valid) < 2:
        return {"error": "Need at least 2 symbols with price history"}

    # Align to common dates
    df = pd.DataFrame(valid).dropna()
    spy = spy_raw.reindex(df.index).dropna()
    df  = df.loc[spy.index]
    if len(df) < 30:
        return {"error": "Insufficient overlapping price history"}

    vsyms = [s for s in symbols if s in df.columns]
    vw    = np.array([w[i] for i, s in enumerate(symbols) if s in df.columns])
    vw    = vw / vw.sum()
    df    = df[vsyms]

    # ── Correlation matrix ────────────────────────────────────────────────────
    corr = df.corr().round(2)

    # ── Portfolio daily returns ───────────────────────────────────────────────
    port_rets = (df.values @ vw)  # 1-D array

    # ── Beta vs SPY ───────────────────────────────────────────────────────────
    cov_mat = np.cov(port_rets, spy.values)
    beta    = cov_mat[0, 1] / cov_mat[1, 1] if cov_mat[1, 1] != 0 else 1.0

    # ── Max Drawdown ─────────────────────────────────────────────────────────
    cum     = (1 + pd.Series(port_rets)).cumprod()
    roll_mx = cum.cummax()
    dd      = (cum - roll_mx) / roll_mx
    max_dd  = float(dd.min()) * 100

    # ── VaR 95% (historical simulation) ─────────────────────────────────────
    var_1d = float(np.percentile(port_rets, 5)) * 100   # 5th pctile daily
    var_1w = var_1d * np.sqrt(5)

    # ── Annualised vol & Sharpe ──────────────────────────────────────────────
    ann_vol = float(port_rets.std()) * np.sqrt(252) * 100
    ann_ret = float(port_rets.mean()) * 252 * 100
    sharpe  = ann_ret / ann_vol if ann_vol else 0.0

    # ── Concentration (HHI) ──────────────────────────────────────────────────
    hhi = float(np.sum(vw ** 2))

    # ── Risk flags ────────────────────────────────────────────────────────────
    flags = []

    if hhi > 0.25:
        top_i = int(np.argmax(vw))
        flags.append(
            f"High concentration — {vsyms[top_i]} is "
            f"{vw[top_i]*100:.0f}% of portfolio (HHI {hhi:.2f})"
        )

    for i, s1 in enumerate(vsyms):
        for j, s2 in enumerate(vsyms):
            if j <= i:
                continue
            c_val = float(corr.loc[s1, s2])
            if c_val > 0.85:
                flags.append(
                    f"{s1} ↔ {s2} correlation {c_val:.2f} — "
                    "nearly identical risk, little diversification benefit"
                )

    if beta > 1.4:
        flags.append(
            f"Portfolio beta {beta:.2f} — "
            "amplifies market swings by {:.0f}% vs SPY".format(beta * 100 - 100)
        )
    elif beta < 0.5:
        flags.append(f"Portfolio beta {beta:.2f} — very low market sensitivity")

    if max_dd < -35:
        flags.append(
            f"Max drawdown {max_dd:.1f}% (past year) — "
            "significant tail risk, consider position sizing"
        )

    return {
        "symbols":            vsyms,
        "weights":            vw.tolist(),
        "correlation_matrix": corr,
        "portfolio_beta":     round(beta, 2),
        "max_drawdown_pct":   round(max_dd, 1),
        "var_95_1d":          round(var_1d, 2),
        "var_95_1w":          round(var_1w, 2),
        "annual_vol_pct":     round(ann_vol, 1),
        "sharpe_approx":      round(sharpe, 2),
        "concentration_hhi":  round(hhi, 3),
        "risk_flags":         flags,
    }
