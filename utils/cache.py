import sys
import streamlit as st
import yfinance as yf
import pandas as pd


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
