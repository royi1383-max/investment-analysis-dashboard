"""
Options Pricing — Black-Scholes-Merton, Binomial (CRR), Monte Carlo, and an
implied-volatility solver, checked against REAL market option-chain data via
yfinance rather than synthetic inputs. Methodology per Hilpisch's Python for
Finance (RN SB: 30.resources/Data & Business Intelligence/Python for Finance
- Quantitative Analytics).

Scope: vanilla European/American options via BSM/Binomial/Monte Carlo, plus
Newton/Brent implied vol. Stochastic-vol (Heston) and jump-diffusion (Merton)
models are out of scope for this pass — see Alpha Lab > Sources & Principles.
"""
import numpy as np
import streamlit as st
import yfinance as yf
from scipy.stats import norm
from scipy.optimize import brentq

from utils.cache import get_price_history

RISK_FREE_RATE = 0.045   # short-term T-bill proxy; adjustable in the UI


# ─── Option chain (real market data) ──────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def get_expiries(symbol: str) -> list[str]:
    try:
        return list(yf.Ticker(symbol.upper()).options)
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def get_chain(symbol: str, expiry: str) -> dict:
    """Returns {"calls": DataFrame|None, "puts": DataFrame|None, "error": None|str}."""
    try:
        chain = yf.Ticker(symbol.upper()).option_chain(expiry)
        return {"calls": chain.calls, "puts": chain.puts, "error": None}
    except Exception as e:
        return {"calls": None, "puts": None, "error": str(e)}


@st.cache_data(ttl=1800, show_spinner=False)
def historical_vol(symbol: str, window_days: int = 60) -> float | None:
    """Annualized realized volatility from daily log returns."""
    try:
        ph = get_price_history(symbol, period="6mo")
        if ph.empty:
            return None
        close = ph["Close"].squeeze()
        log_ret = np.log(close / close.shift(1)).dropna()
        window_days = min(window_days, len(log_ret))
        if window_days < 10:
            return None
        return float(log_ret.iloc[-window_days:].std() * np.sqrt(252))
    except Exception:
        return None


# ─── Black-Scholes-Merton ──────────────────────────────────────────────────────

def bsm_price(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> float:
    """European option price. T in years, sigma annualized."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, (S - K) if kind == "call" else (K - S))
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if kind == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def bsm_greeks(S: float, K: float, T: float, r: float, sigma: float, kind: str = "call") -> dict:
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {"delta": None, "gamma": None, "vega": None, "theta": None, "rho": None}
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    pdf_d1 = norm.pdf(d1)
    gamma = pdf_d1 / (S * sigma * np.sqrt(T))
    vega = S * pdf_d1 * np.sqrt(T) / 100   # per 1 vol point (1%)
    if kind == "call":
        delta = float(norm.cdf(d1))
        theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T))
                 - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365
        rho = K * T * np.exp(-r * T) * norm.cdf(d2) / 100
    else:
        delta = float(norm.cdf(d1) - 1)
        theta = (-(S * pdf_d1 * sigma) / (2 * np.sqrt(T))
                 + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365
        rho = -K * T * np.exp(-r * T) * norm.cdf(-d2) / 100
    return {"delta": round(delta, 4), "gamma": round(float(gamma), 5),
            "vega": round(float(vega), 4), "theta": round(float(theta), 4),
            "rho": round(float(rho), 4)}


def implied_vol(market_price: float, S: float, K: float, T: float, r: float,
                kind: str = "call") -> float | None:
    """Solve for sigma via Brent's method (bracketed, no derivative needed)."""
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return None
    intrinsic = max(0.0, (S - K) if kind == "call" else (K - S))
    if market_price < intrinsic:
        return None   # quoted price violates no-arbitrage bound — can't solve

    def f(sigma):
        return bsm_price(S, K, T, r, sigma, kind) - market_price

    try:
        return float(brentq(f, 1e-4, 5.0, xtol=1e-6, maxiter=200))
    except Exception:
        return None


# ─── Binomial (Cox-Ross-Rubinstein) ────────────────────────────────────────────

def binomial_price(S: float, K: float, T: float, r: float, sigma: float,
                   steps: int = 200, kind: str = "call", american: bool = False) -> float:
    if T <= 0 or sigma <= 0 or steps < 1:
        return max(0.0, (S - K) if kind == "call" else (K - S))
    dt = T / steps
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp(r * dt) - d) / (u - d)
    disc = np.exp(-r * dt)

    j = np.arange(steps + 1)
    prices = S * (u ** (steps - j)) * (d ** j)
    values = np.maximum(prices - K, 0.0) if kind == "call" else np.maximum(K - prices, 0.0)

    for step in range(steps - 1, -1, -1):
        values = disc * (p * values[:-1] + (1 - p) * values[1:])
        if american:
            j = np.arange(step + 1)
            prices = S * (u ** (step - j)) * (d ** j)
            exercise = np.maximum(prices - K, 0.0) if kind == "call" else np.maximum(K - prices, 0.0)
            values = np.maximum(values, exercise)
    return float(values[0])


# ─── Monte Carlo (antithetic variates) ─────────────────────────────────────────

def monte_carlo_price(S: float, K: float, T: float, r: float, sigma: float,
                      kind: str = "call", n_paths: int = 50_000, seed: int = 42) -> dict:
    """European option price via GBM simulation. Antithetic variates (mirrored
    +/-z shocks) roughly halve the standard error for the same path count."""
    if T <= 0 or sigma <= 0:
        payoff = max(0.0, (S - K) if kind == "call" else (K - S))
        return {"price": payoff, "std_error": 0.0}
    rng = np.random.default_rng(seed)
    half = n_paths // 2
    z = rng.standard_normal(half)
    z = np.concatenate([z, -z])
    ST = S * np.exp((r - 0.5 * sigma ** 2) * T + sigma * np.sqrt(T) * z)
    payoff = np.maximum(ST - K, 0.0) if kind == "call" else np.maximum(K - ST, 0.0)
    disc_payoff = np.exp(-r * T) * payoff
    price = float(disc_payoff.mean())
    std_error = float(disc_payoff.std(ddof=1) / np.sqrt(len(disc_payoff)))
    return {"price": round(price, 4), "std_error": round(std_error, 4)}
