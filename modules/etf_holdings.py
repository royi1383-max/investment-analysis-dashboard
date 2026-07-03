"""
ETF Holdings module — fetches top holdings for any ETF ticker via yfinance.
Returns a list of dicts with weight, ticker, name, and sector.
Cached for 24 hours (holdings change infrequently).
"""
import streamlit as st
import yfinance as yf
import pandas as pd


@st.cache_data(ttl=86400, show_spinner=False)
def get_holdings(etf_symbol: str, _v: int = 2) -> list[dict]:  # _v bumps cache key
    """
    Returns top holdings for an ETF.
    Each dict: {ticker, name, weight_pct, sector}
    Returns empty list if not an ETF or data unavailable.
    """
    try:
        tk = yf.Ticker(etf_symbol.upper())
        holdings = tk.funds_data.top_holdings
        if holdings is None or (isinstance(holdings, pd.DataFrame) and holdings.empty):
            return []
        rows = []
        for i, (idx, row) in enumerate(holdings.iterrows()):
            if i >= 20:
                break
            ticker = str(idx).strip() if idx else ""
            name   = str(row.get("Name", row.get("name", ticker))).strip()
            # Holding Percent is a decimal (0.13 = 13%)
            weight = row.get("Holding Percent", row.get("% Assets", row.get("weight", 0)))
            try:
                weight = float(weight)
                if weight < 1.0:
                    weight = weight * 100
            except Exception:
                weight = 0.0
            rows.append({
                "ticker":     ticker,
                "name":       name,
                "weight_pct": round(weight, 2),
                "sector":     str(row.get("Sector", row.get("sector", ""))).strip(),
            })
        return rows
    except Exception:
        pass
    return []


def is_etf(symbol: str) -> bool:
    """Quick check whether a ticker is an ETF."""
    try:
        info = yf.Ticker(symbol.upper()).info
        q_type = info.get("quoteType", "").upper()
        return q_type in ("ETF", "MUTUALFUND")
    except Exception:
        return False


def render_etf_holdings(etf_symbol: str, max_rows: int = 10) -> None:
    """
    Render a compact ETF holdings table inside a Streamlit container.
    Only renders if the symbol is an ETF with available holdings data.
    """
    holdings = get_holdings(etf_symbol)
    if not holdings:
        return

    top = holdings[:max_rows]
    total_shown = sum(h["weight_pct"] for h in top)

    rows_html = ""
    for h in top:
        bar_w = min(int(h["weight_pct"] / max(top[0]["weight_pct"], 1) * 100), 100)
        rows_html += (
            f'<tr>'
            f'<td style="padding:4px 8px;font-family:\'IBM Plex Mono\',monospace;'
            f'font-weight:700;color:#60a5fa;white-space:nowrap">{h["ticker"]}</td>'
            f'<td style="padding:4px 8px;color:#b0bec5;font-size:12px">{h["name"][:28]}</td>'
            f'<td style="padding:4px 8px">'
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="background:#16c784;height:6px;border-radius:3px;width:{bar_w}%;min-width:4px"></div>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:12px;'
            f'color:#16c784;white-space:nowrap">{h["weight_pct"]:.2f}%</span>'
            f'</div>'
            f'</td>'
            f'<td style="padding:4px 8px;color:#8a9bc2;font-size:11px">{h["sector"][:20]}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="background:#161b27;border:1px solid #2a3348;border-radius:8px;'
        f'padding:12px 16px;margin-top:8px">'
        f'<div style="font-size:10px;font-family:\'IBM Plex Mono\',monospace;color:#16c784;'
        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">'
        f'TOP {len(top)} HOLDINGS · {etf_symbol.upper()} · {total_shown:.1f}% of fund</div>'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 8px;'
        f'font-family:\'IBM Plex Mono\',monospace">TICKER</th>'
        f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 8px;'
        f'font-family:\'IBM Plex Mono\',monospace">NAME</th>'
        f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 8px;'
        f'font-family:\'IBM Plex Mono\',monospace">WEIGHT</th>'
        f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 8px;'
        f'font-family:\'IBM Plex Mono\',monospace">SECTOR</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>',
        unsafe_allow_html=True,
    )
