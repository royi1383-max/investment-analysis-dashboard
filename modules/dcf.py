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

from utils.cache import get_ticker_info, get_financials, get_price_history

# Sectors where the cash-flow statement is dominated by loan-book / trading-
# securities / policy-reserve movements rather than operating economics —
# a standard FCF DCF is the wrong lens here (e.g. JPM shows base FCF of
# -$147B purely from balance-sheet financing flows, not cash burn).
# Use a Dividend Discount Model instead (see get_ddm_inputs / run_ddm).
FINANCIAL_SECTORS = {"Financial Services", "Financials"}


@st.cache_data(ttl=3600, show_spinner=False)
def get_dcf_inputs(symbol: str) -> dict:
    """Fetch base FCF, net debt, shares outstanding, and a suggested growth rate."""
    out = {"error": None}
    try:
        _, _, cf = get_financials(symbol)
        info = get_ticker_info(symbol)
        out["sector"] = info.get("sector", "")
        out["is_financial"] = out["sector"] in FINANCIAL_SECTORS

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

        revenue_ttm = float(info.get("totalRevenue") or 0) or None
        current_fcf_margin = (base_fcf / revenue_ttm) if revenue_ttm else None

        out.update({
            "base_fcf":     base_fcf,
            "fcf_history":  fcf_history,
            "net_debt":     total_debt - total_cash,
            "shares_out":   shares_out,
            "price":        price,
            "suggested_g":  round(suggested_g, 3),
            "name":         info.get("shortName", symbol),
            "beta":         info.get("beta"),
            "revenue_ttm":  revenue_ttm,
            "revenue_growth": info.get("revenueGrowth"),
            "current_fcf_margin": current_fcf_margin,
            "dividend_rate": info.get("dividendRate"),
            "payout_ratio":  info.get("payoutRatio"),
            "roe":           info.get("returnOnEquity"),
        })
        return out
    except Exception as e:
        return {"error": f"DCF data fetch failed: {e}"}


def get_risk_free_rate() -> float:
    """Current 10Y Treasury yield (^TNX) as a decimal. Falls back to 4.5% if unavailable."""
    try:
        tnx = get_price_history("^TNX", period="5d")
        return float(tnx["Close"].squeeze().iloc[-1]) / 100
    except Exception:
        return 0.045


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
    df.index.name = "FCF Growth ↓"
    df.columns.name = "Discount Rate / WACC →"
    return df


# ─── Dividend Discount Model — for financials (banks/insurers) ────────────────
# Their cash-flow statement mixes loan-book/trading/reserve movements into
# "Free Cash Flow," so a standard FCF DCF isn't meaningful. Value the dividend
# stream instead, with a Gordon-growth model off the sustainable growth rate
# (ROE × retention ratio) — the textbook approach for bank/insurer valuation.

def run_ddm(dps: float, growth: float, cost_of_equity: float) -> dict:
    """Constant-growth Dividend Discount Model. Rates as decimals."""
    if cost_of_equity <= growth:
        return {"error": "Cost of equity must exceed the dividend growth rate."}
    if not dps or dps <= 0:
        return {"error": "No dividend to discount."}
    next_dps = dps * (1 + growth)
    intrinsic_ps = next_dps / (cost_of_equity - growth)
    return {
        "next_dps":       next_dps,
        "intrinsic_ps":   intrinsic_ps,
        "cost_of_equity": cost_of_equity,
        "growth":         growth,
        "error":          None,
    }


# ─── Revenue-bridge DCF — for genuinely pre-profit growth companies ───────────
# Standard FCF-DCF explodes (or is undefined) when base FCF is negative. This
# projects revenue forward and ramps the FCF margin linearly from today's
# (possibly negative) margin to an assumed mature-state margin, so the model
# answers "what is this worth once it reaches a normal margin" instead of
# refusing to answer.

def run_revenue_dcf(revenue_ttm: float, revenue_growth: float, current_margin: float,
                     target_margin: float, terminal_growth: float, discount: float,
                     net_debt: float, shares_out: float, years: int = 5) -> dict:
    """Revenue → ramped FCF margin → terminal value. Rates as decimals."""
    if discount <= terminal_growth:
        return {"error": "Discount rate must exceed terminal growth."}

    proj, pv_sum = [], 0.0
    for y in range(1, years + 1):
        rev_y    = revenue_ttm * (1 + revenue_growth) ** y
        margin_y = current_margin + (target_margin - current_margin) * (y / years)
        fcf_y    = rev_y * margin_y
        pv       = fcf_y / (1 + discount) ** y
        proj.append({"year": y, "revenue": rev_y, "margin": margin_y, "fcf": fcf_y, "pv": pv})
        pv_sum  += pv

    terminal_fcf   = proj[-1]["fcf"] * (1 + terminal_growth)
    terminal_val   = terminal_fcf / (discount - terminal_growth)
    terminal_pv    = terminal_val / (1 + discount) ** years
    enterprise_val = pv_sum + terminal_pv
    equity_val     = enterprise_val - net_debt
    intrinsic_ps   = equity_val / shares_out if shares_out > 0 else 0

    return {
        "fcf_projection":   proj,
        "pv_fcf_sum":       pv_sum,
        "terminal_value":   terminal_val,
        "terminal_pv":      terminal_pv,
        "terminal_weight":  terminal_pv / enterprise_val * 100 if enterprise_val > 0 else 0,
        "enterprise_value": enterprise_val,
        "equity_value":     equity_val,
        "intrinsic_ps":     intrinsic_ps,
        "error":            None,
    }
