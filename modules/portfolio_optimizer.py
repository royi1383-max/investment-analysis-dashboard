"""
Portfolio Optimizer — Efficient Frontier (Markowitz mean-variance) and PCA
factor decomposition, per RN SB's Python for Finance notes (portfolio
optimization via scipy.optimize sweeps + PCA on the return matrix).
Long-only, fully-invested (weights sum to 1, no shorting/leverage) — matches
a retail brokerage account, not a hedge fund book.
"""
import numpy as np
import pandas as pd
import streamlit as st
from scipy.optimize import minimize

from utils.cache import get_price_history


@st.cache_data(ttl=1800, show_spinner=False)
def _returns_matrix(symbols: tuple, period: str = "2y") -> pd.DataFrame:
    frames = {}
    for sym in symbols:
        try:
            ph = get_price_history(sym, period=period)
            if ph.empty:
                continue
            frames[sym] = ph["Close"].squeeze().pct_change(fill_method=None).dropna()
        except Exception:
            continue
    if len(frames) < 2:
        return pd.DataFrame()
    return pd.DataFrame(frames).dropna()


# Epsilon guard, not bare truthiness — vol can land on floating-point noise
# (e.g. 1e-14) for a near-zero-variance portfolio, which is still "truthy".
_MIN_MEANINGFUL_VOL = 1e-9


def _portfolio_stats(w: np.ndarray, mean_ret: np.ndarray, cov: np.ndarray) -> tuple[float, float]:
    ann_ret = float(w @ mean_ret) * 252
    ann_vol = float(np.sqrt(w @ cov @ w)) * np.sqrt(252)
    return ann_ret, ann_vol


def efficient_frontier(symbols: tuple, period: str = "2y", n_random: int = 2000,
                       risk_free: float = 0.045) -> dict:
    """
    Long-only mean-variance frontier: a random-weight cloud (for the scatter)
    plus the exact max-Sharpe (tangency) and min-volatility portfolios via
    SLSQP-constrained optimization.
    """
    rets = _returns_matrix(symbols)
    if rets.empty or rets.shape[1] < 2:
        return {"error": "Need at least 2 symbols with overlapping price history."}

    syms = list(rets.columns)
    n = len(syms)
    mean_ret = rets.mean().values
    cov = rets.cov().values

    rng = np.random.default_rng(42)
    raw = rng.random((n_random, n))
    weights = raw / raw.sum(axis=1, keepdims=True)
    cloud = []
    for w in weights:
        ar, av = _portfolio_stats(w, mean_ret, cov)
        sharpe = (ar - risk_free) / av if av > _MIN_MEANINGFUL_VOL else 0.0
        cloud.append({"return": ar, "vol": av, "sharpe": sharpe})
    cloud_df = pd.DataFrame(cloud)

    bounds = tuple((0.0, 1.0) for _ in range(n))
    constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1},)
    x0 = np.repeat(1 / n, n)

    def neg_sharpe(w):
        ar, av = _portfolio_stats(w, mean_ret, cov)
        return -(ar - risk_free) / av if av > _MIN_MEANINGFUL_VOL else 1e6

    def vol_only(w):
        return _portfolio_stats(w, mean_ret, cov)[1]

    max_sharpe_res = minimize(neg_sharpe, x0, method="SLSQP", bounds=bounds, constraints=constraints)
    min_vol_res    = minimize(vol_only,   x0, method="SLSQP", bounds=bounds, constraints=constraints)

    def _pack(res):
        if not res.success:
            return None
        w = res.x
        ar, av = _portfolio_stats(w, mean_ret, cov)
        sharpe = (ar - risk_free) / av if av > _MIN_MEANINGFUL_VOL else 0.0
        return {"weights": dict(zip(syms, [round(float(x) * 100, 1) for x in w])),
                "return_pct": round(ar * 100, 2), "vol_pct": round(av * 100, 2),
                "sharpe": round(sharpe, 2)}

    return {
        "symbols":    syms,
        "cloud":      cloud_df,
        "max_sharpe": _pack(max_sharpe_res),
        "min_vol":    _pack(min_vol_res),
        "error":      None,
    }


def pca_factors(symbols: tuple, period: str = "2y", n_components: int = 3) -> dict:
    """
    PCA on the standardized return matrix via SVD (no sklearn dependency).
    PC1 is almost always a 'market factor' — how much of the universe's
    variance is just moving together vs. idiosyncratic/diversifying.
    Loading SIGN is arbitrary (SVD sign ambiguity); only magnitude matters.
    """
    rets = _returns_matrix(symbols)
    if rets.empty or rets.shape[1] < 3:
        return {"error": "Need at least 3 symbols with overlapping price history."}

    syms = list(rets.columns)
    n_components = min(n_components, len(syms))
    X = rets.values
    X = (X - X.mean(axis=0)) / X.std(axis=0)

    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    explained = (S ** 2) / np.sum(S ** 2)

    loadings = pd.DataFrame(Vt[:n_components].T, index=syms,
                            columns=[f"PC{i+1}" for i in range(n_components)])
    explained_pct = [round(float(explained[i]) * 100, 1) for i in range(n_components)]

    pc1_exposure = loadings["PC1"].abs().sort_values(ascending=False)

    return {
        "symbols":             syms,
        "loadings":            loadings,
        "explained_pct":       explained_pct,
        "market_factor_pct":   explained_pct[0],
        "top_pc1_exposure":    pc1_exposure.head(5).to_dict(),
        "bottom_pc1_exposure": pc1_exposure.tail(3).to_dict(),
        "error":               None,
    }
