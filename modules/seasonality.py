"""
Seasonality Analysis — monthly/quarterly historical return patterns.
Uses yfinance monthly history; cached 24h.
"""
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import date

MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


@st.cache_data(ttl=86400, show_spinner=False)
def get_seasonality(symbol: str, years: int = 10) -> dict:
    """
    Returns monthly and quarterly seasonality stats for a stock.
    {
      "monthly": {1: {"avg_return": 0.023, "win_rate": 0.70, "median": 0.02, "count": 10}, ...12},
      "quarterly": {1: {...}, 2: {...}, 3: {...}, 4: {...}},
      "best_month": 10, "worst_month": 9,
      "current_month": 6, "current_month_avg": 0.018,
      "years_analyzed": 10,
      "heatmap": {2015: {1: 0.03, 2: -0.01, ...}, ...}
    }
    Returns empty dict on failure.
    """
    try:
        tk = yf.Ticker(symbol)
        hist = tk.history(period=f"{years}y", interval="1mo")
        if hist.empty or len(hist) < 12:
            return {}

        close = hist["Close"].squeeze()
        monthly_ret = close.pct_change(fill_method=None).dropna()

        monthly: dict = {}
        for m in range(1, 13):
            mask = monthly_ret.index.month == m
            rets = monthly_ret[mask].dropna()
            if len(rets) == 0:
                continue
            monthly[m] = {
                "avg_return": float(rets.mean()),
                "win_rate":   float((rets > 0).sum() / len(rets)),
                "median":     float(rets.median()),
                "count":      int(len(rets)),
            }

        # Quarterly stats — group months into Q1-Q4
        quarterly: dict = {}
        for q in range(1, 5):
            q_months = [q * 3 - 2, q * 3 - 1, q * 3]
            mask = monthly_ret.index.month.isin(q_months)
            rets = monthly_ret[mask].dropna()
            if len(rets) == 0:
                continue
            quarterly[q] = {
                "avg_return": float(rets.mean()),
                "win_rate":   float((rets > 0).sum() / len(rets)),
                "count":      int(len(rets)),
            }

        # Heatmap: year × month
        heatmap: dict = {}
        for yr, grp in monthly_ret.groupby(monthly_ret.index.year):
            heatmap[int(yr)] = {}
            for m in range(1, 13):
                sel = grp[grp.index.month == m]
                if len(sel) > 0:
                    heatmap[int(yr)][m] = round(float(sel.iloc[0]), 4)

        if not monthly:
            return {}

        best_month  = max(monthly.keys(), key=lambda m: monthly[m]["avg_return"])
        worst_month = min(monthly.keys(), key=lambda m: monthly[m]["avg_return"])
        cur_month   = date.today().month

        return {
            "monthly":           monthly,
            "quarterly":         quarterly,
            "best_month":        best_month,
            "worst_month":       worst_month,
            "current_month":     cur_month,
            "current_month_avg": monthly.get(cur_month, {}).get("avg_return", 0),
            "years_analyzed":    len(set(monthly_ret.index.year)),
            "heatmap":           heatmap,
        }
    except Exception:
        return {}
