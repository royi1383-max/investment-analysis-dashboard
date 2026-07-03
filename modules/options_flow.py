"""
Options flow analysis — call/put volume ratio, open interest bias,
near-the-money call activity. Scores bullish options sentiment 1-10.
"""
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=1800, show_spinner=False)
def analyze(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        exps = ticker.options
        if not exps:
            return _empty()

        # Current price
        try:
            price = ticker.fast_info.last_price
        except Exception:
            price = None

        total_call_vol = 0
        total_put_vol  = 0
        total_call_oi  = 0
        total_put_oi   = 0
        atm_call_vol   = 0   # within 5-10% OTM — most bullish signal

        # Look at nearest 3 expirations (near-term flow is most actionable)
        for exp in exps[:3]:
            try:
                chain = ticker.option_chain(exp)
                calls = chain.calls
                puts  = chain.puts

                if not calls.empty:
                    call_v = calls["volume"].fillna(0)
                    call_oi = calls["openInterest"].fillna(0)
                    total_call_vol += float(call_v.sum())
                    total_call_oi  += float(call_oi.sum())

                    if price and price > 0:
                        # ATM/slightly OTM calls = real directional bets
                        mask = (calls["strike"] >= price * 0.97) & (calls["strike"] <= price * 1.08)
                        atm_call_vol += float(call_v[mask].sum())

                if not puts.empty:
                    total_put_vol += float(puts["volume"].fillna(0).sum())
                    total_put_oi  += float(puts["openInterest"].fillna(0).sum())
            except Exception:
                continue

        if total_call_vol + total_put_vol == 0:
            return _empty()

        cp_vol_ratio = total_call_vol / total_put_vol if total_put_vol > 0 else 2.0
        cp_oi_ratio  = total_call_oi  / total_put_oi  if total_put_oi  > 0 else 2.0
        atm_call_pct = atm_call_vol / total_call_vol  if total_call_vol > 0 else 0

        # Score — baseline market has ~0.6-0.9 C/P ratio (hedging bias toward puts)
        if cp_vol_ratio >= 2.5:
            score  = 10
            signal = "Extreme call dominance — highly unusual bullish flow"
        elif cp_vol_ratio >= 1.8:
            score  = 9
            signal = "Very strong call buying — institutional bullish bets"
        elif cp_vol_ratio >= 1.3:
            score  = 8
            signal = "Elevated call/put ratio — bullish options bias"
        elif cp_vol_ratio >= 1.0:
            score  = 7
            signal = "More calls than puts — moderately bullish flow"
        elif cp_vol_ratio >= 0.7:
            score  = 5
            signal = "Balanced options activity — neutral flow"
        elif cp_vol_ratio >= 0.5:
            score  = 4
            signal = "More puts than calls — cautious sentiment"
        else:
            score  = 2
            signal = "Heavy put buying — bearish options flow"

        # Bonus: concentrated near-the-money call bets
        if atm_call_pct > 0.5 and score >= 7:
            score = min(10, score + 0.5)
            signal += " · ATM calls dominate (targeted bets)"

        # OI confirms trend
        if cp_oi_ratio > cp_vol_ratio:
            signal += " · OI confirms bullish bias"

        return {
            "score":        round(score, 1),
            "call_vol":     int(total_call_vol),
            "put_vol":      int(total_put_vol),
            "cp_ratio":     round(cp_vol_ratio, 2),
            "cp_oi_ratio":  round(cp_oi_ratio, 2),
            "atm_call_pct": round(atm_call_pct * 100, 1),
            "total_vol":    int(total_call_vol + total_put_vol),
            "signal":       signal,
            "has_data":     True,
        }

    except Exception:
        return _empty()


def _empty() -> dict:
    return {
        "score":        5,
        "call_vol":     0,
        "put_vol":      0,
        "cp_ratio":     None,
        "cp_oi_ratio":  None,
        "atm_call_pct": None,
        "total_vol":    0,
        "signal":       "Options data unavailable",
        "has_data":     False,
    }
