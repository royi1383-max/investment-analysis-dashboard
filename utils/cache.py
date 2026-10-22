import sys
from concurrent.futures import ThreadPoolExecutor
import streamlit as st
import yfinance as yf
import pandas as pd


def parallel_map(fn, items, max_workers: int = 8) -> list:
    """Run fn(item) for every item on a thread pool; results keep input order.

    Network-bound fetches (yfinance, FRED) spend their time waiting, so running them
    side by side cuts page load time. An item whose fn raises yields the exception
    object instead of aborting the whole batch.
    """
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
    ctx = get_script_run_ctx()

    def _run(item):
        if ctx is not None:
            add_script_run_ctx(None, ctx)  # let cached functions work inside the worker thread
        try:
            return fn(item)
        except Exception as e:  # noqa: BLE001 - reported to the caller, not swallowed
            return e

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(_run, list(items)))


@st.cache_data(ttl=3600, show_spinner=False)
def search_tickers(query: str, limit: int = 8) -> list[dict]:
    """Find tickers by company name or partial symbol (Yahoo Finance search, no API key)."""
    try:
        quotes = yf.Search(query, max_results=limit).quotes
    except Exception as e:
        print(f"[cache] search_tickers({query}) failed: {e}", file=sys.stderr)
        return []
    return [
        {"symbol": q["symbol"], "name": q.get("shortname") or q.get("longname") or ""}
        for q in quotes if q.get("symbol")
    ]


@st.cache_data(ttl=900, show_spinner=False)
def get_ticker_info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception as e:
        print(f"[cache] get_ticker_info({symbol}) failed: {e}", file=sys.stderr)
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def get_price_history(symbol: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if "Close" in df.columns:
            df = df[df["Close"].notna()]
        return df
    except Exception as e:
        print(f"[cache] get_price_history({symbol}, {period}) failed: {e}", file=sys.stderr)
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def get_institutional_holders(symbol: str) -> pd.DataFrame:
    try:
        df = yf.Ticker(symbol).institutional_holders
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception as e:
        print(f"[cache] get_institutional_holders({symbol}) failed: {e}", file=sys.stderr)
        return pd.DataFrame()


@st.cache_data(ttl=1800, show_spinner=False)
def get_insider_transactions(symbol: str) -> pd.DataFrame:
    try:
        df = yf.Ticker(symbol).insider_transactions
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception as e:
        print(f"[cache] get_insider_transactions({symbol}) failed: {e}", file=sys.stderr)
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_financials(symbol: str):
    t = yf.Ticker(symbol)
    try:
        income = t.income_stmt
        balance = t.balance_sheet
        cashflow = t.cashflow
        return income, balance, cashflow
    except Exception as e:
        print(f"[cache] get_financials({symbol}) failed: {e}", file=sys.stderr)
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
