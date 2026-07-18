"""
Earnings Quality — forensic red flags (Chanos / short-seller lens).

Checks from yfinance financial statements:
  • Share dilution — share count trend over 3-4 years
  • Stock-based compensation as % of revenue
  • Accruals gap — net income vs operating cash flow (earnings backed by cash?)
  • Receivables growing faster than revenue (channel stuffing signal)
  • Cash conversion — FCF / net income
  • Debt trend — total debt trajectory

Each check returns (status, detail): "good" / "warn" / "flag" / "na".
"""
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


def _trend(series_vals: list[float]) -> float | None:
    """CAGR-style trend over the available annual values (oldest→newest)."""
    vals = [v for v in series_vals if v is not None and not pd.isna(v)]
    if len(vals) < 2 or vals[0] == 0:
        return None
    years = len(vals) - 1
    try:
        if vals[0] < 0 or vals[-1] < 0:
            return None
        return (vals[-1] / vals[0]) ** (1 / years) - 1
    except Exception:
        return None


def _row(df: pd.DataFrame, names: list[str]) -> list[float] | None:
    """First matching row, values oldest→newest."""
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            vals = df.loc[n].dropna()
            if not vals.empty:
                return list(reversed([float(v) for v in vals.values]))
    return None


@st.cache_data(ttl=86400, show_spinner=False)
def analyze(symbol: str) -> dict:
    """Run all quality checks. Returns {checks: [(name, status, detail)], score}."""
    checks = []
    try:
        tk  = yf.Ticker(symbol)
        inc = tk.income_stmt
        bal = tk.balance_sheet
        cfs = tk.cashflow
    except Exception as e:
        return {"error": f"Financials unavailable: {e}", "checks": [], "score": None}

    # ── 1. Share dilution ─────────────────────────────────────────────────────
    shares = _row(bal, ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"])
    if shares and len(shares) >= 2:
        tr = _trend(shares)
        if tr is not None:
            pct = tr * 100
            if pct > 4:
                checks.append(("Share Dilution", "flag",
                               f"Share count growing {pct:+.1f}%/yr — shareholders diluted meaningfully"))
            elif pct > 1.5:
                checks.append(("Share Dilution", "warn",
                               f"Share count growing {pct:+.1f}%/yr — mild dilution"))
            elif pct < -1:
                checks.append(("Share Dilution", "good",
                               f"Share count shrinking {pct:+.1f}%/yr — buybacks returning capital"))
            else:
                checks.append(("Share Dilution", "good", f"Share count stable ({pct:+.1f}%/yr)"))
        else:
            checks.append(("Share Dilution", "na", "Trend not computable"))
    else:
        checks.append(("Share Dilution", "na", "Share count history unavailable"))

    # ── 2. SBC / Revenue ──────────────────────────────────────────────────────
    sbc = _row(cfs, ["Stock Based Compensation"])
    rev = _row(inc, ["Total Revenue", "Operating Revenue"])
    if sbc and rev and rev[-1] > 0:
        sbc_pct = abs(sbc[-1]) / rev[-1] * 100
        if sbc_pct > 15:
            checks.append(("SBC / Revenue", "flag",
                           f"Stock comp = {sbc_pct:.1f}% of revenue — heavy hidden dilution cost"))
        elif sbc_pct > 8:
            checks.append(("SBC / Revenue", "warn",
                           f"Stock comp = {sbc_pct:.1f}% of revenue — notable for a mature company"))
        else:
            checks.append(("SBC / Revenue", "good", f"Stock comp = {sbc_pct:.1f}% of revenue"))
    else:
        checks.append(("SBC / Revenue", "na", "SBC data unavailable"))

    # ── 3. Accruals gap: NI vs OCF ────────────────────────────────────────────
    ni  = _row(inc, ["Net Income", "Net Income Common Stockholders"])
    ocf = _row(cfs, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    if ni and ocf and ni[-1] and ni[-1] > 0:
        ratio = ocf[-1] / ni[-1]
        if ratio < 0.6:
            checks.append(("Cash Backing (OCF/NI)", "flag",
                           f"Operating cash flow is only {ratio:.2f}× net income — "
                           f"earnings not backed by cash (accrual-heavy)"))
        elif ratio < 0.9:
            checks.append(("Cash Backing (OCF/NI)", "warn",
                           f"OCF = {ratio:.2f}× net income — watch accruals"))
        else:
            checks.append(("Cash Backing (OCF/NI)", "good",
                           f"OCF = {ratio:.2f}× net income — earnings are cash-backed"))
    else:
        checks.append(("Cash Backing (OCF/NI)", "na", "NI/OCF data unavailable or loss-making"))

    # ── 4. Receivables vs revenue growth ──────────────────────────────────────
    recv = _row(bal, ["Accounts Receivable", "Receivables", "Net Receivables"])
    if recv and rev and len(recv) >= 2 and len(rev) >= 2 and recv[-2] > 0 and rev[-2] > 0:
        recv_g = recv[-1] / recv[-2] - 1
        rev_g  = rev[-1] / rev[-2] - 1
        gap = (recv_g - rev_g) * 100
        if gap > 15:
            checks.append(("Receivables vs Revenue", "flag",
                           f"Receivables grew {recv_g*100:+.0f}% vs revenue {rev_g*100:+.0f}% — "
                           f"possible aggressive revenue recognition"))
        elif gap > 7:
            checks.append(("Receivables vs Revenue", "warn",
                           f"Receivables outpacing revenue by {gap:.0f}pp"))
        else:
            checks.append(("Receivables vs Revenue", "good",
                           f"Receivables in line with revenue growth ({gap:+.0f}pp gap)"))
    else:
        checks.append(("Receivables vs Revenue", "na", "Receivables data unavailable"))

    # ── 5. Cash conversion: FCF / NI ──────────────────────────────────────────
    fcf = _row(cfs, ["Free Cash Flow"])
    if fcf is None and ocf:
        capex = _row(cfs, ["Capital Expenditure"])
        if capex and len(capex) == len(ocf):
            fcf = [o + c for o, c in zip(ocf, capex)]
    if fcf and ni and ni[-1] and ni[-1] > 0:
        conv = fcf[-1] / ni[-1]
        if conv < 0.5:
            checks.append(("FCF Conversion", "flag",
                           f"FCF = {conv:.2f}× net income — heavy capex/working-capital drag on real cash"))
        elif conv < 0.8:
            checks.append(("FCF Conversion", "warn", f"FCF = {conv:.2f}× net income"))
        else:
            checks.append(("FCF Conversion", "good",
                           f"FCF = {conv:.2f}× net income — profits convert to cash"))
    else:
        checks.append(("FCF Conversion", "na", "FCF data unavailable or loss-making"))

    # ── 6. Debt trend ─────────────────────────────────────────────────────────
    debt = _row(bal, ["Total Debt", "Long Term Debt"])
    if debt and len(debt) >= 2 and debt[0] > 0:
        tr = _trend(debt)
        if tr is not None:
            pct = tr * 100
            if pct > 25:
                checks.append(("Debt Trend", "flag", f"Total debt growing {pct:+.0f}%/yr"))
            elif pct > 10:
                checks.append(("Debt Trend", "warn", f"Total debt growing {pct:+.0f}%/yr"))
            else:
                checks.append(("Debt Trend", "good", f"Debt trend {pct:+.0f}%/yr — contained"))
        else:
            checks.append(("Debt Trend", "na", "Trend not computable"))
    else:
        checks.append(("Debt Trend", "na", "Debt history unavailable"))

    # ── Score ─────────────────────────────────────────────────────────────────
    weights = {"good": 1.0, "warn": 0.5, "flag": 0.0}
    scored = [(n, s, d) for n, s, d in checks if s in weights]
    score = round(sum(weights[s] for _, s, _ in scored) / len(scored) * 10, 1) if scored else None

    return {"checks": checks, "score": score, "error": None}
