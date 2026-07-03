"""
Institutional & Insider activity module.
"""
import pandas as pd
import numpy as np
import yfinance as yf
from utils.cache import get_institutional_holders, get_insider_transactions, get_ticker_info


def analyze(symbol: str) -> dict:
    inst_df    = get_institutional_holders(symbol)
    insider_df = get_insider_transactions(symbol)
    info       = get_ticker_info(symbol)

    scores  = {}
    signals = []

    # ── Institutional holdings ───────────────────────────────────────────────
    inst_pct = None
    if not inst_df.empty:
        # yfinance returns columns like: Holder, Shares, Date Reported, % Out, Value
        if "% Out" in inst_df.columns:
            try:
                inst_pct = float(str(inst_df["% Out"].iloc[0]).replace("%","")) / 100
            except Exception:
                inst_pct = None

    heldPctInst = info.get("heldPercentInstitutions")
    if heldPctInst and inst_pct is None:
        inst_pct = heldPctInst

    if inst_pct is not None:
        if inst_pct > 0.80:   scores["Institutional %"] = 8
        elif inst_pct > 0.60: scores["Institutional %"] = 7
        elif inst_pct > 0.40: scores["Institutional %"] = 6
        elif inst_pct > 0.20: scores["Institutional %"] = 5
        else:                  scores["Institutional %"] = 4
    else:
        scores["Institutional %"] = 5

    # ── Short interest ────────────────────────────────────────────────────────
    short_pct = info.get("shortPercentOfFloat")
    if short_pct is not None:
        if short_pct < 0.03:   scores["Short Interest"] = 9
        elif short_pct < 0.07: scores["Short Interest"] = 7
        elif short_pct < 0.15: scores["Short Interest"] = 5
        elif short_pct < 0.25: scores["Short Interest"] = 3
        else:
            scores["Short Interest"] = 1
            signals.append(("⚠️", f"High short interest: {short_pct*100:.1f}% of float"))
    else:
        scores["Short Interest"] = 5

    # ── Insider transactions ──────────────────────────────────────────────────
    insider_score = 5
    buy_value = sell_value = 0

    if not insider_df.empty:
        cols = insider_df.columns.str.lower()
        insider_df.columns = cols

        buy_mask  = insider_df.apply(lambda r: any(
            k in str(v).lower() for k in ["buy","purchase","acqui"] for v in r
        ), axis=1)
        sell_mask = insider_df.apply(lambda r: any(
            k in str(v).lower() for k in ["sell","sale","disposed"] for v in r
        ), axis=1)

        val_col = next((c for c in cols if "value" in c), None)
        if val_col:
            try:
                buy_value  = insider_df.loc[buy_mask,  val_col].apply(lambda x: abs(pd.to_numeric(x, errors="coerce"))).sum()
                sell_value = insider_df.loc[sell_mask, val_col].apply(lambda x: abs(pd.to_numeric(x, errors="coerce"))).sum()
            except Exception:
                pass

        ratio = buy_value / (buy_value + sell_value + 1)
        if ratio > 0.7:
            insider_score = 9
            signals.append(("🟢", "Strong insider buying signal"))
        elif ratio > 0.5:
            insider_score = 7
        elif ratio > 0.3:
            insider_score = 5
        elif ratio > 0.1:
            insider_score = 3
        else:
            insider_score = 2
            signals.append(("🔴", "Heavy insider selling detected"))

    scores["Insider Activity"] = insider_score

    # ── Weighted score ────────────────────────────────────────────────────────
    weights = {
        "Institutional %":  0.35,
        "Short Interest":   0.35,
        "Insider Activity": 0.30,
    }
    total = sum(scores.get(k, 5) * w for k, w in weights.items())

    return {
        "score":         round(total, 2),
        "scores":        scores,
        "signals":       signals,
        "inst_df":       inst_df,
        "insider_df":    insider_df,
        "inst_pct":      inst_pct,
        "short_pct":     short_pct,
        "buy_value":     buy_value,
        "sell_value":    sell_value,
    }
