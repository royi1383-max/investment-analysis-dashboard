"""
Fundamental analysis module — Growth-first scoring.
Returns a score 1-10 per metric and an overall Fundamental Score.
"""
import pandas as pd
import numpy as np
from utils.cache import get_ticker_info, get_financials


def _safe(val, default=None):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return val


def _score_peg(peg):
    if peg is None: return 5
    if peg < 0:     return 4
    if peg < 1:     return 10
    if peg < 1.5:   return 8
    if peg < 2:     return 6
    if peg < 3:     return 4
    return 2


def _score_ps(ps):
    if ps is None: return 5
    if ps < 5:     return 9
    if ps < 10:    return 7
    if ps < 20:    return 5
    if ps < 40:    return 3
    return 2


def _score_gross_margin(gm):
    if gm is None: return 5
    if gm > 0.70:  return 10
    if gm > 0.55:  return 8
    if gm > 0.40:  return 6
    if gm > 0.25:  return 4
    return 2


def _score_revenue_growth(g):
    if g is None: return 5
    if g > 0.50:  return 10
    if g > 0.30:  return 8
    if g > 0.15:  return 6
    if g > 0.05:  return 4
    if g > 0:     return 3
    return 1


def _score_rule40(r40):
    if r40 is None: return 5
    if r40 > 60:   return 10
    if r40 > 40:   return 8
    if r40 > 20:   return 5
    if r40 > 0:    return 3
    return 1


def _score_fcf_yield(fy):
    if fy is None: return 5
    if fy > 0.05:  return 10
    if fy > 0.02:  return 7
    if fy > 0:     return 5
    return 2


def _score_debt_equity(de):
    if de is None: return 6
    if de < 0.3:   return 10
    if de < 0.7:   return 7
    if de < 1.5:   return 5
    if de < 3:     return 3
    return 1


def analyze(symbol: str) -> dict:
    info = get_ticker_info(symbol)
    income, balance, cashflow = get_financials(symbol)

    # ── Raw metrics from yfinance info ──────────────────────────────────────
    market_cap    = _safe(info.get("marketCap"))
    revenue_ttm   = _safe(info.get("totalRevenue"))
    gross_profit  = _safe(info.get("grossProfits"))
    net_income    = _safe(info.get("netIncomeToCommon"))
    free_cash_flow = _safe(info.get("freeCashflow"))
    total_debt    = _safe(info.get("totalDebt"), 0)
    total_equity  = _safe(info.get("totalStockholderEquity"))
    eps_fwd       = _safe(info.get("forwardEps"))
    pe_fwd        = _safe(info.get("forwardPE"))
    peg           = _safe(info.get("pegRatio"))
    revenue_growth = _safe(info.get("revenueGrowth"))    # YoY
    earnings_growth = _safe(info.get("earningsGrowth"))
    rd_expense    = _safe(info.get("researchAndDevelopment"))

    # ── Computed ratios ──────────────────────────────────────────────────────
    ps_ratio      = (market_cap / revenue_ttm) if market_cap and revenue_ttm and revenue_ttm > 0 else None
    gross_margin  = (gross_profit / revenue_ttm) if gross_profit and revenue_ttm and revenue_ttm > 0 else None
    fcf_yield     = (free_cash_flow / market_cap) if free_cash_flow and market_cap and market_cap > 0 else None
    de_raw = _safe(info.get("debtToEquity"))
    if de_raw is not None:
        debt_equity = de_raw / 100
    elif total_debt and total_equity and abs(total_equity) > 1e6:
        debt_equity = total_debt / total_equity
    else:
        debt_equity = None
    fcf_margin    = (free_cash_flow / revenue_ttm) if free_cash_flow and revenue_ttm and revenue_ttm > 0 else None
    rd_pct        = (rd_expense / revenue_ttm) if rd_expense and revenue_ttm and revenue_ttm > 0 else None

    # Rule of 40
    rule40 = None
    if revenue_growth is not None and fcf_margin is not None:
        rule40 = (revenue_growth * 100) + (fcf_margin * 100)

    # ── Scores ───────────────────────────────────────────────────────────────
    scores = {
        "PEG Ratio":        _score_peg(peg),
        "P/S Ratio":        _score_ps(ps_ratio),
        "Gross Margin":     _score_gross_margin(gross_margin),
        "Revenue Growth":   _score_revenue_growth(revenue_growth),
        "Rule of 40":       _score_rule40(rule40),
        "FCF Yield":        _score_fcf_yield(fcf_yield),
        "Debt/Equity":      _score_debt_equity(debt_equity),
    }

    weights = {
        "Revenue Growth": 0.25,
        "Rule of 40":     0.20,
        "Gross Margin":   0.20,
        "PEG Ratio":      0.15,
        "FCF Yield":      0.10,
        "P/S Ratio":      0.05,
        "Debt/Equity":    0.05,
    }
    total_score = sum(scores[k] * weights[k] for k in scores)

    # Track which scored metrics were unavailable (defaulted to 5 / 6)
    _scored_inputs = {
        "PEG Ratio":      peg,
        "P/S Ratio":      ps_ratio,
        "Gross Margin":   gross_margin,
        "Revenue Growth": revenue_growth,
        "Rule of 40":     rule40,
        "FCF Yield":      fcf_yield,
        "Debt/Equity":    debt_equity,
    }
    missing_metrics = [k for k, v in _scored_inputs.items() if v is None]

    is_pre_profit   = (net_income is not None and net_income < 0)
    has_earnings    = pe_fwd is not None or peg is not None

    return {
        "score": round(total_score, 2),
        "scores": scores,
        "metrics": {
            "Market Cap":      market_cap,
            "P/S Ratio":       ps_ratio,
            "Forward P/E":     pe_fwd,
            "PEG Ratio":       peg,
            "Gross Margin":    gross_margin,
            "Revenue Growth":  revenue_growth,
            "Earnings Growth": earnings_growth,
            "FCF Yield":       fcf_yield,
            "FCF Margin":      fcf_margin,
            "Debt/Equity":     debt_equity,
            "R&D % Revenue":   rd_pct,
            "Rule of 40":      rule40,
        },
        # Data quality metadata
        "missing_metrics": missing_metrics,
        "is_pre_profit":   is_pre_profit,
        "has_earnings":    has_earnings,
    }
