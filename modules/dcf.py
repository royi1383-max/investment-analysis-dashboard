"""
DCF Valuation — implements the "dcf-valuation" skill natively.

5-year two-stage DCF from yfinance cash-flow data:
  base FCF → 5y projection at growth rate g → terminal value (Gordon,
  terminal growth gt) → discount at WACC → enterprise value → equity value
  (minus net debt) → intrinsic value per share vs market price.

Also returns a sensitivity matrix (growth × discount rate).
All assumptions user-adjustable in the UI; sensible defaults derived
from the stock's own history.
"""
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from utils.cache import get_ticker_info


@st.cache_data(ttl=3600, show_spinner=False)
def get_dcf_inputs(symbol: str) -> dict:
    """Fetch base FCF, net debt, shares outstanding, and a suggested growth rate."""
    out = {"error": None}
    try:
        tk = yf.Ticker(symbol)
        cf = tk.cashflow
        info = get_ticker_info(symbol)

        # ── Base FCF ─────────────────────────────────────────────────────────
        fcf_series = None
        if cf is not None and not cf.empty:
            if "Free Cash Flow" in cf.index:
                fcf_series = cf.loc["Free Cash Flow"].dropna()
            elif "Operating Cash Flow" in cf.index and "Capital Expenditure" in cf.index:
                fcf_series = (cf.loc["Operating Cash Flow"] +
                              cf.loc["Capital Expenditure"]).dropna()  # capex is negative

        if fcf_series is None or fcf_series.empty:
            fcf_ttm = info.get("freeCashflow")
            if not fcf_ttm:
                return {"error": "No free-cash-flow data available for this stock."}
            base_fcf = float(fcf_ttm)
            fcf_history = []
        else:
            vals = [float(v) for v in fcf_series.values][:4]
            base_fcf = vals[0]
            fcf_history = list(reversed(vals))   # oldest → newest

        if base_fcf <= 0:
            out["negative_fcf"] = True

        # ── Historical FCF growth (suggested g) ──────────────────────────────
        suggested_g = 0.10
        if len(fcf_history) >= 2 and fcf_history[0] > 0 and fcf_history[-1] > 0:
            years = len(fcf_history) - 1
            cagr = (fcf_history[-1] / fcf_history[0]) ** (1 / years) - 1
            suggested_g = max(0.02, min(0.30, cagr))   # clamp to sane band

        # ── Net debt + shares ────────────────────────────────────────────────
        total_debt = float(info.get("totalDebt") or 0)
        total_cash = float(info.get("totalCash") or 0)
        shares_out = float(info.get("sharesOutstanding") or 0)
        if shares_out <= 0:
            return {"error": "Shares outstanding unavailable."}

        price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)

        out.update({
            "base_fcf":     base_fcf,
            "fcf_history":  fcf_history,
            "net_debt":     total_debt - total_cash,
            "shares_out":   shares_out,
            "price":        price,
            "suggested_g":  round(suggested_g, 3),
            "name":         info.get("shortName", symbol),
            "beta":         info.get("beta"),
        })
        return out
    except Exception as e:
        return {"error": f"DCF data fetch failed: {e}"}


def run_dcf(base_fcf: float, growth: float, terminal_growth: float,
            discount: float, net_debt: float, shares_out: float,
            years: int = 5) -> dict:
    """Two-stage DCF. Rates as decimals (0.10 = 10%)."""
    if discount <= terminal_growth:
        return {"error": "Discount rate must exceed terminal growth."}

    fcf_proj, pv_sum = [], 0.0
    fcf = base_fcf
    for y in range(1, years + 1):
        fcf = fcf * (1 + growth)
        pv  = fcf / (1 + discount) ** y
        fcf_proj.append({"year": y, "fcf": fcf, "pv": pv})
        pv_sum += pv

    terminal_val    = fcf * (1 + terminal_growth) / (discount - terminal_growth)
    terminal_pv     = terminal_val / (1 + discount) ** years
    enterprise_val  = pv_sum + terminal_pv
    equity_val      = enterprise_val - net_debt
    intrinsic_ps    = equity_val / shares_out if shares_out > 0 else 0

    return {
        "fcf_projection":  fcf_proj,
        "pv_fcf_sum":      pv_sum,
        "terminal_value":  terminal_val,
        "terminal_pv":     terminal_pv,
        "terminal_weight": terminal_pv / enterprise_val * 100 if enterprise_val > 0 else 0,
        "enterprise_value": enterprise_val,
        "equity_value":    equity_val,
        "intrinsic_ps":    intrinsic_ps,
        "error":           None,
    }


def sensitivity_matrix(base_fcf: float, terminal_growth: float, net_debt: float,
                       shares_out: float, growth_center: float,
                       discount_center: float) -> pd.DataFrame:
    """Intrinsic value per share across growth × discount grid (±2pp steps)."""
    growths   = [growth_center + d for d in (-0.04, -0.02, 0, 0.02, 0.04)]
    discounts = [discount_center + d for d in (-0.02, -0.01, 0, 0.01, 0.02)]
    rows = {}
    for g in growths:
        row = {}
        for r in discounts:
            res = run_dcf(base_fcf, g, terminal_growth, r, net_debt, shares_out)
            row[f"{r*100:.0f}%"] = res["intrinsic_ps"] if not res.get("error") else np.nan
        rows[f"{g*100:+.0f}%"] = row
    df = pd.DataFrame(rows).T
    df.index.name = "FCF Growth"
    return df
