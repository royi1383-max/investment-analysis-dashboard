"""
Portfolio management module.
Supports two CSV formats:
  1. Standard: Ticker, Shares, Avg Price
  2. Israeli broker export (auto-detected)
"""
import io
import pandas as pd
import numpy as np
import streamlit as st
from utils.cache import get_ticker_info, get_price_history
from modules import scoring, fundamental, technical, momentum as mom_module

REQUIRED_COLS = {"Ticker", "Shares", "Avg Price"}

# ── Israeli broker column positions (0-indexed after skipping header rows) ────
# col 0  : type (0=Israeli security, 2=US stock)
# col 1  : security number (Israeli security ID)
# col 2  : name
# col 3  : current price (NIS per 100 units for IL, USD per share for US)
# col 4  : portfolio value (NIS)
# col 7  : P&L % from purchase (NIS basis)
# col 8  : P&L absolute (NIS)
# col 9  : quantity / shares
# col 10 : last transaction date
# col 11 : currency (NIS / USD)
# col 12 : total current value in local currency
# col 13 : symbol (US ticker or Israeli fund code)
# col 14 : avg purchase price (same units as col 3)
# col 15 : P&L % in local currency

_ENCODINGS = ["utf-8-sig", "cp1255", "windows-1255", "latin-1", "utf-8"]


def _clean_name(s: str) -> str:
    if not isinstance(s, str):
        return str(s)
    return s.lstrip("â‏").strip().strip('"').strip("'")


def _to_float(v) -> float | None:
    try:
        if pd.isna(v):
            return None
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None


def _detect_broker_format(file) -> tuple[pd.DataFrame | None, str]:
    """Try to parse as Israeli broker CSV. Returns (df, encoding) or (None, '')."""
    content = file.read()
    file.seek(0)

    for enc in _ENCODINGS:
        try:
            text   = content.decode(enc)
            lines  = [l for l in text.split("\n") if l.strip()]
            # Find first line where col[0] is "0" or "2" (data row)
            start  = None
            for i, line in enumerate(lines):
                first = line.split(",")[0].strip().strip('"')
                if first in ("0", "2"):
                    start = i
                    break
            if start is None:
                continue
            raw = "\n".join(lines[start:])
            df  = pd.read_csv(io.StringIO(raw), header=None, on_bad_lines="skip")
            if df.shape[1] >= 14 and df.iloc[0, 0] in (0, 2):
                return df, enc
        except Exception:
            continue
    return None, ""


def _parse_broker(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        try:
            sec_type = int(r.iloc[0])
            if sec_type not in (0, 2):
                continue

            security_num = str(r.iloc[1]).strip()
            name         = _clean_name(r.iloc[2])
            cur_price    = _to_float(r.iloc[3])
            value_nis    = _to_float(r.iloc[4])
            pnl_pct_nis  = _to_float(r.iloc[7])
            pnl_abs_nis  = _to_float(r.iloc[8])
            qty          = _to_float(r.iloc[9])
            currency     = _clean_name(r.iloc[11]) if len(r) > 11 else ""
            symbol       = _clean_name(r.iloc[13]) if len(r) > 13 else ""
            avg_price    = _to_float(r.iloc[14]) if len(r) > 14 else None
            pnl_pct_loc  = _to_float(r.iloc[15]) if len(r) > 15 else None

            if qty is None or qty == 0:
                continue

            is_us      = sec_type == 2
            is_israeli = sec_type == 0

            # For Israeli securities: price is per 100 units
            if is_israeli and cur_price and qty:
                actual_cur_price = cur_price / 100
                actual_avg_price = avg_price / 100 if avg_price else None
            else:
                actual_cur_price = cur_price
                actual_avg_price = avg_price

            cost_basis = (actual_avg_price * qty) if actual_avg_price and qty else None
            if cost_basis is None and value_nis and pnl_pct_nis is not None:
                cost_basis = value_nis / (1 + pnl_pct_nis / 100)

            # Determine ticker for yfinance lookup
            ticker = symbol if is_us and symbol and not symbol.startswith("FTM") else None

            rows.append({
                "Security Number": security_num,
                "Name":            name,
                "Ticker":          ticker or "",
                "Symbol":          symbol,
                "Type":            "US Stock" if is_us else "Israeli",
                "Currency":        "USD" if is_us else "NIS",
                "Shares":          qty,
                "Avg Price":       actual_avg_price,
                "Current Price":   actual_cur_price,
                "Value (NIS)":     value_nis,
                "Cost Basis (NIS)": cost_basis,
                "P&L (%)":         pnl_pct_loc if is_us else pnl_pct_nis,
                "P&L (NIS)":       pnl_abs_nis,
            })
        except Exception:
            continue

    return pd.DataFrame(rows)


def load_portfolio(file) -> tuple[pd.DataFrame | None, str]:
    """
    Returns (dataframe, format_type) where format_type is 'standard' or 'broker'.
    """
    try:
        # Try broker format first
        broker_df, enc = _detect_broker_format(file)
        if broker_df is not None:
            parsed = _parse_broker(broker_df)
            if not parsed.empty:
                return parsed, "broker"

        # Fall back to standard format
        file.seek(0)
        if file.name.endswith(".csv"):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)
        df.columns = df.columns.str.strip()
        missing = REQUIRED_COLS - set(df.columns)
        if missing:
            st.error(f"Missing columns: {missing}. Required: Ticker, Shares, Avg Price")
            return None, ""
        df["Ticker"]    = df["Ticker"].str.upper().str.strip()
        df["Shares"]    = pd.to_numeric(df["Shares"],    errors="coerce")
        df["Avg Price"] = pd.to_numeric(df["Avg Price"], errors="coerce")
        return df.dropna(subset=["Ticker", "Shares", "Avg Price"]), "standard"

    except Exception as e:
        st.error(f"Error loading portfolio: {e}")
        return None, ""


def enrich_portfolio_broker(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich broker-format portfolio with live prices for US stocks."""
    rows = []
    for _, row in df.iterrows():
        r = row.to_dict()
        ticker = r.get("Ticker", "")

        if ticker:
            try:
                info      = get_ticker_info(ticker)
                price_df  = get_price_history(ticker, period="5d")
                live_px   = float(price_df["Close"].squeeze().iloc[-1]) if not price_df.empty else r.get("Current Price")
                r["Current Price"] = live_px
                r["Sector"]  = info.get("sector", "US Stock")
                r["Name"]    = info.get("shortName", r["Name"])
            except Exception:
                r["Sector"] = "US Stock"
        else:
            r["Sector"] = "Israeli Fund / Certificate"

        rows.append(r)
    return pd.DataFrame(rows)


def enrich_portfolio(df: pd.DataFrame, run_scores: bool = False) -> pd.DataFrame:
    """Standard format enrichment (original logic)."""
    rows = []
    for _, row in df.iterrows():
        sym   = row["Ticker"]
        info  = get_ticker_info(sym)
        pdf   = get_price_history(sym, period="5d")
        price_stale = pdf.empty
        cur_p = float(pdf["Close"].squeeze().iloc[-1]) if not pdf.empty else row["Avg Price"]

        cost  = row["Shares"] * row["Avg Price"]
        val   = row["Shares"] * cur_p
        pnl   = val - cost
        pnl_p = pnl / cost if cost > 0 else 0

        enriched = {
            "Ticker": sym, "Name": info.get("shortName", sym),
            "Shares": row["Shares"], "Avg Price": row["Avg Price"],
            "Current Price": cur_p, "Market Value": val,
            "P&L ($)": pnl, "P&L (%)": pnl_p,
            "Sector": info.get("sector", "ETF/Other"),
            "Price Stale": price_stale,
        }
        if run_scores:
            try:
                f  = fundamental.analyze(sym)
                t  = technical.analyze(sym)
                mo = mom_module.analyze(sym)
                s  = scoring.compute(f["score"], t["score"], mo["score"], 5, 5, 5)
                enriched["Score"]  = s["final"]
                enriched["Rating"] = s["label"]
            except Exception:
                enriched["Score"]  = None
                enriched["Rating"] = "N/A"
        rows.append(enriched)
    return pd.DataFrame(rows)


def portfolio_summary_broker(df: pd.DataFrame) -> dict:
    total_nis = df["Value (NIS)"].sum()
    total_cost_nis = df["Cost Basis (NIS)"].dropna().sum()
    total_pnl_nis  = df["P&L (NIS)"].dropna().sum()

    df = df.copy()
    df["Weight"] = df["Value (NIS)"] / total_nis if total_nis else 0

    sector_exp = (
        df.groupby("Sector")["Value (NIS)"].sum() / total_nis * 100
    ).sort_values(ascending=False)

    return {
        "total_value_nis":  total_nis,
        "total_cost_nis":   total_cost_nis,
        "total_pnl_nis":    total_pnl_nis,
        "total_pnl_pct":    total_pnl_nis / total_cost_nis if total_cost_nis else 0,
        "sector_exposure":  sector_exp,
        "n_positions":      len(df),
        "us_positions":     len(df[df["Type"] == "US Stock"]),
        "il_positions":     len(df[df["Type"] == "Israeli"]),
    }


def portfolio_summary(df: pd.DataFrame) -> dict:
    total_cost  = df["Market Value"].sum() - df["P&L ($)"].sum()
    total_value = df["Market Value"].sum()
    total_pnl   = df["P&L ($)"].sum()
    pnl_pct     = total_pnl / total_cost if total_cost else 0
    df = df.copy()
    df["Weight"] = df["Market Value"] / total_value if total_value else 0
    sector_exp = (
        (df.groupby("Sector")["Market Value"].sum() / total_value * 100)
        if total_value else df.groupby("Sector")["Market Value"].sum() * 0
    ).sort_values(ascending=False)
    return {
        "total_cost": total_cost, "total_value": total_value,
        "total_pnl": total_pnl,   "total_pnl_pct": pnl_pct,
        "sector_exposure": sector_exp, "n_positions": len(df),
    }
