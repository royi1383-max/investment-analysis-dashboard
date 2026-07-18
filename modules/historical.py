"""
Historical fundamentals comparison module.
Fetches multi-year quarterly data for up to 4 tickers.
"""
import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st

METRICS_CATALOG = {
    "price_norm": {
        "label": "Stock Price (Normalized to 100)",
        "hebrew": "Price Performance",
        "desc": "Each stock normalized so the start date = 100. Lets you compare relative performance between companies of different sizes.",
        "signal_good": "Above 100 = gain since start. Above SPY = market outperformance.",
        "signal_bad": "Below 100 = loss. Below SPY = underperformance.",
        "why": "Most intuitive comparison. '$100 invested then — how much is it worth today?'",
        "format": "index",
    },
    "revenue": {
        "label": "Revenue — Quarterly ($B)",
        "hebrew": "Revenue",
        "desc": "Total quarterly revenue. The foundation of all analysis — companies without revenue growth struggle to justify high valuations.",
        "signal_good": "Consistent quarter-over-quarter growth = healthy, expanding business.",
        "signal_bad": "Deceleration for 2+ consecutive quarters = warning signal.",
        "why": "Revenue is the lifeblood of a company. All growth and profitability flows from it.",
        "format": "billions",
    },
    "revenue_growth": {
        "label": "Revenue Growth YoY (%)",
        "hebrew": "Revenue Growth",
        "desc": "Year-over-year revenue growth rate vs the same quarter last year. Comparable across companies of any size.",
        "signal_good": ">30% = hypergrowth. 15–30% = strong. 10–15% = healthy.",
        "signal_bad": "0–10% = maturing. Negative = shrinking business.",
        "why": "Wall Street prices the future, not the past. Accelerating growth = multiple expansion.",
        "format": "pct",
    },
    "gross_margin": {
        "label": "Gross Margin (%)",
        "hebrew": "Gross Margin",
        "desc": "Percentage of revenue remaining after cost of goods/services. A measure of business quality and pricing power.",
        "signal_good": ">70% = excellent (SaaS/software). 40–70% = good.",
        "signal_bad": "<25% = low pricing power, commoditized business.",
        "why": "High gross margins = hard-to-replicate product. That is the moat.",
        "format": "pct",
    },
    "net_margin": {
        "label": "Net Margin (%)",
        "hebrew": "Net Margin",
        "desc": "Percentage of revenue that becomes net profit after all expenses, depreciation, and taxes.",
        "signal_good": ">20% = excellent. 10–20% = good.",
        "signal_bad": "Negative = company is losing money.",
        "why": "The 'real' profit. If negative, the key question is the path to profitability.",
        "format": "pct",
    },
    "fcf_margin": {
        "label": "FCF Margin (%)",
        "hebrew": "FCF Margin",
        "desc": "Percentage of revenue that becomes actual free cash flow. Often more reliable than accounting profit since cash is harder to manipulate.",
        "signal_good": ">20% = excellent. Positive = financial health.",
        "signal_bad": "Negative = burning cash — check runway.",
        "why": "Buffett: 'Earnings are opinion, cash is fact.'",
        "format": "pct",
    },
    "eps": {
        "label": "EPS — Earnings Per Share ($)",
        "hebrew": "EPS",
        "desc": "Net income divided by average share count. What each shareholder 'earns' per share they own.",
        "signal_good": "Consistent growth = compounding profitability. Positive surprises = price catalyst.",
        "signal_bad": "Negative EPS = loss. Declining = dilution or margin erosion.",
        "why": "P/E is derived from EPS. Growing EPS = P/E compresses = stock becomes 'cheaper' automatically.",
        "format": "dollar",
    },
    "ps_ratio": {
        "label": "P/S Ratio — Price to Sales",
        "hebrew": "P/S Ratio",
        "desc": "Stock price divided by revenue per share (TTM). How much investors pay for each dollar of revenue.",
        "signal_good": "<5 = cheap. 5–15 = reasonable for a growth company.",
        "signal_bad": ">30 = very expensive — requires very fast growth to justify.",
        "why": "Useful when there is no profit yet. Shows if valuation is detaching from fundamentals.",
        "format": "ratio",
    },
    "debt_equity": {
        "label": "Debt/Equity — Leverage Ratio",
        "hebrew": "Debt / Equity",
        "desc": "Total financial debt divided by shareholders' equity. Measures financial leverage and risk. Cheap debt at low rates, dangerous at high rates.",
        "signal_good": "<0.5 = conservative. 0.5–1 = normal.",
        "signal_bad": ">2 = highly leveraged — check interest coverage.",
        "why": "In a high-rate environment, high-debt companies face margin compression and refinancing risk.",
        "format": "ratio",
    },
    "net_income": {
        "label": "Net Income — Quarterly ($)",
        "hebrew": "Net Income",
        "desc": "Quarterly net profit after all expenses, depreciation, and taxes. The 'bottom line' of the income statement.",
        "signal_good": "Consistently positive and growing = compounding profitability.",
        "signal_bad": "Negative = company is losing money. Declining = margin erosion.",
        "why": "Net income drives EPS, which drives P/E multiples — the core of equity valuation.",
        "format": "billions",
    },
    "earnings_growth": {
        "label": "Earnings Growth YoY — Net Income (%)",
        "hebrew": "Earnings Growth YoY",
        "desc": "Year-over-year growth rate of net income. Shows whether profitability is accelerating or decelerating.",
        "signal_good": ">20% = strong. 10–20% = healthy. Consistent beats = catalyst.",
        "signal_bad": "Negative = earnings decline. Worse than estimates = selloff risk.",
        "why": "Earnings acceleration is one of the strongest predictors of stock outperformance.",
        "format": "pct",
    },
}


def _cutoff(df: pd.DataFrame, years: int) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = df.index.max() - pd.DateOffset(years=years)
    return df[df.index >= cutoff]


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_metric(symbol: str, metric_key: str, years: int = 5) -> pd.Series:
    meta = METRICS_CATALOG.get(metric_key)
    if not meta:
        return pd.Series(dtype=float)
    try:
        t = yf.Ticker(symbol)
        return _compute(t, meta, years)
    except Exception:
        return pd.Series(dtype=float)


def _compute(t, meta: dict, years: int) -> pd.Series:
    fmt = meta["format"]
    key = meta["label"]

    # ── Price ────────────────────────────────────────────────────────────────
    if fmt == "index":
        hist = t.history(period=f"{years}y", interval="1mo")
        if hist.empty:
            return pd.Series(dtype=float)
        s = hist["Close"].resample("QE").last().dropna()
        return (s / s.iloc[0] * 100).rename(key)

    # ── Income statement metrics ──────────────────────────────────────────────
    inc = t.quarterly_income_stmt
    if inc is None or inc.empty:
        return pd.Series(dtype=float)
    inc = _cutoff(inc.T.sort_index(), years)

    def _col(df, *names):
        for n in names:
            if n in df.columns:
                return df[n].dropna()
        return None

    if meta["label"].startswith("Revenue —"):
        rev = _col(inc, "Total Revenue")
        return (rev / 1e9).rename(key) if rev is not None else pd.Series(dtype=float)

    if meta["label"].startswith("Net Income"):
        ni = _col(inc, "Net Income")
        return (ni / 1e9).rename(key) if ni is not None else pd.Series(dtype=float)

    if meta["label"].startswith("Earnings Growth"):
        ni = _col(inc, "Net Income")
        if ni is None:
            return pd.Series(dtype=float)
        return (_yoy(ni) * 100).rename(key)

    if meta["label"].startswith("Revenue Growth") or ("Revenue" in meta["label"] and "Growth" in meta["label"]):
        rev = _col(inc, "Total Revenue")
        if rev is None:
            return pd.Series(dtype=float)
        return (_yoy(rev) * 100).rename(key)

    if "Gross Margin" in meta["label"]:
        rev = _col(inc, "Total Revenue")
        gp  = _col(inc, "Gross Profit")
        if rev is None or gp is None:
            return pd.Series(dtype=float)
        return (gp / rev * 100).replace([np.inf, -np.inf], np.nan).dropna().rename(key)

    if "Net Margin" in meta["label"]:
        rev = _col(inc, "Total Revenue")
        ni  = _col(inc, "Net Income")
        if rev is None or ni is None:
            return pd.Series(dtype=float)
        return (ni / rev * 100).replace([np.inf, -np.inf], np.nan).dropna().rename(key)

    if "EPS" in meta["label"]:
        eps = _col(inc, "Basic EPS", "Diluted EPS")
        return eps.rename(key) if eps is not None else pd.Series(dtype=float)

    # ── Cash flow ────────────────────────────────────────────────────────────
    if "FCF" in meta["label"]:
        cf  = t.quarterly_cashflow
        if cf is None or cf.empty:
            return pd.Series(dtype=float)
        cf  = _cutoff(cf.T.sort_index(), years)
        rev = _col(inc, "Total Revenue")
        fcf = _col(cf, "Free Cash Flow")
        if rev is None or fcf is None:
            return pd.Series(dtype=float)
        combined = pd.concat([rev, fcf], axis=1).dropna()
        combined.columns = ["rev", "fcf"]
        return (combined["fcf"] / combined["rev"] * 100).replace([np.inf, -np.inf], np.nan).dropna().rename(key)

    # ── Balance sheet ─────────────────────────────────────────────────────────
    if "Debt" in meta["label"]:
        bal = t.quarterly_balance_sheet
        if bal is None or bal.empty:
            return pd.Series(dtype=float)
        bal = _cutoff(bal.T.sort_index(), years)
        debt = _col(bal, "Total Debt", "Long Term Debt")
        eq   = _col(bal, "Stockholders Equity", "Common Stock Equity")
        if debt is None or eq is None:
            return pd.Series(dtype=float)
        return (debt / eq).replace([np.inf, -np.inf], np.nan).dropna().rename(key)

    # ── P/S Ratio ─────────────────────────────────────────────────────────────
    if "P/S" in meta["label"]:
        info   = t.info
        shares = info.get("sharesOutstanding", 0)
        hist   = t.history(period=f"{years}y", interval="1mo")
        if not shares or hist.empty:
            return pd.Series(dtype=float)
        rev = _col(inc, "Total Revenue")
        if rev is None:
            return pd.Series(dtype=float)
        rev_ttm = rev.rolling(4, min_periods=1).sum()
        rps = rev_ttm / shares
        price_q = hist["Close"].resample("QE").last()
        df = pd.concat([price_q, rps], axis=1).dropna()
        df.columns = ["price", "rps"]
        return (df["price"] / df["rps"]).replace([np.inf, -np.inf], np.nan).dropna().rename(key)

    return pd.Series(dtype=float)


def _yoy(s: pd.Series) -> pd.Series:
    return s.pct_change(periods=4, fill_method=None)
