"""
Institutional & Insider activity module.
"""
import pandas as pd
import streamlit as st
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
    sell_value_routine = sell_value_discretionary = 0
    routine_sell_pct = None

    if not insider_df.empty:
        cols = insider_df.columns.str.lower()
        insider_df.columns = cols

        # "Transaction" is frequently blank in current yfinance data; "Text" carries
        # the description ("Sale at price ...", "Purchase at price ..."). Restrict
        # keyword matching to these describing columns — scanning the whole row
        # (Insider name, URL, Position) risks false keyword hits.
        desc_cols = [c for c in ("transaction", "text") if c in cols]
        scan_cols = desc_cols if desc_cols else list(cols)

        buy_mask  = insider_df[scan_cols].apply(lambda r: any(
            k in str(v).lower() for k in ["buy","purchase","acqui"] for v in r
        ), axis=1)
        sell_mask = insider_df[scan_cols].apply(lambda r: any(
            k in str(v).lower() for k in ["sell","sale","disposed"] for v in r
        ), axis=1)

        val_col = next((c for c in cols if "value" in c), None)
        if val_col:
            try:
                buy_value  = insider_df.loc[buy_mask,  val_col].apply(lambda x: abs(pd.to_numeric(x, errors="coerce"))).sum()
                sell_value = insider_df.loc[sell_mask, val_col].apply(lambda x: abs(pd.to_numeric(x, errors="coerce"))).sum()
            except Exception:
                pass

        # yfinance's insider data has no SEC Form 4 transaction code and no
        # 10b5-1 checkbox — every RSU-vesting "tax sale" and every deliberate
        # open-market dump both just say "Sale at price X per share." That's
        # a real data-source limitation, not something we can query around.
        # The one signal that DOES survive: a pre-scheduled 10b5-1 plan (or
        # recurring RSU vesting) sells the *same share count* over and over
        # on a cadence, while a one-off discretionary sale doesn't. So: any
        # insider whose sells repeat an identical share count 3+ times gets
        # those specific transactions tagged "routine" — verified live on
        # CRDO, where one exec's sells were 30x @ 55,000 sh and 18x @ 27,500
        # sh, an unmistakable scheduled-plan signature, vs. other insiders
        # with zero repeats (genuinely one-off, i.e. actually discretionary).
        _routine_split_computed = False
        if val_col and "insider" in cols and "shares" in cols and sell_mask.any():
            _routine_split_computed = True
            sells = insider_df.loc[sell_mask, ["insider", "shares", val_col]].copy()
            sells["shares_n"] = pd.to_numeric(sells["shares"], errors="coerce")
            sells["value_n"]  = sells[val_col].apply(lambda x: abs(pd.to_numeric(x, errors="coerce")))
            routine_mask = pd.Series(False, index=sells.index)
            for _insider, grp in sells.groupby("insider"):
                rep_counts = grp["shares_n"].value_counts()
                routine_share_counts = set(rep_counts[rep_counts >= 3].index)
                if routine_share_counts:
                    routine_mask.loc[grp.index] = grp["shares_n"].isin(routine_share_counts)
            sell_value_routine       = sells.loc[routine_mask, "value_n"].sum()
            sell_value_discretionary = sells.loc[~routine_mask, "value_n"].sum()
            if sell_value:
                routine_sell_pct = round(sell_value_routine / sell_value * 100, 0)

        # NOTE: open-market insider *purchases* are structurally rare at large-caps
        # (most activity is RSU-vesting "Sale" transactions, grants, gifts) — a
        # low buy/sell ratio is the norm, not a red flag. Thresholds are calibrated
        # so "no notable buying" reads as neutral rather than automatically bearish.
        # The ratio is driven by DISCRETIONARY selling only — a pile of routine
        # scheduled-plan liquidation (see above) isn't the same signal as one
        # exec deciding, today, to sell a lot of stock, so it shouldn't drag
        # the score down the same way.
        sell_for_ratio = sell_value_discretionary if _routine_split_computed else sell_value
        ratio = buy_value / (buy_value + sell_for_ratio + 1)
        if ratio > 0.6:
            insider_score = 9
            signals.append(("🟢", "Strong insider buying signal"))
        elif ratio > 0.35:
            insider_score = 7
            signals.append(("🟢", "Notable insider buying"))
        elif ratio > 0.15:
            insider_score = 6
        elif ratio > 0.05:
            insider_score = 5
        elif sell_for_ratio > 0:
            insider_score = 4
        else:
            insider_score = 5

        # Only flag as a bearish signal when DISCRETIONARY selling is both
        # lopsided AND sizable in dollar terms (routine scheduled-plan
        # liquidation, however large, shouldn't read as alarm).
        if ratio < 0.05 and sell_for_ratio > 5_000_000:
            insider_score = 3
            signals.append(("🔴", "Heavy discretionary insider selling detected"))

        if routine_sell_pct is not None and routine_sell_pct >= 50:
            signals.append(("ℹ️", f"~{routine_sell_pct:.0f}% of insider selling matches a "
                                  "repeating-share-count pattern (likely RSU vesting / 10b5-1 "
                                  "scheduled plans) — not a discretionary signal"))

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
        "sell_value_routine":       sell_value_routine,
        "sell_value_discretionary": sell_value_discretionary,
        "routine_sell_pct":         routine_sell_pct,
    }


_PERIOD_LABELS = {"0q": "This Quarter", "+1q": "Next Quarter",
                  "0y": "This Year",    "+1y": "Next Year"}


@st.cache_data(ttl=21600, show_spinner=False)
def get_eps_revenue_estimates(symbol: str) -> dict:
    """
    Forward EPS/revenue analyst consensus, straight from Yahoo Finance via
    yfinance (Ticker.earnings_estimate / .revenue_estimate / .eps_trend) —
    free, no API key, and covers small-caps that Finnhub/FMP's free tiers
    don't: both of those gate their price-target AND estimates endpoints
    to paid plans (verified live — 402/403 on this app's free keys, even
    for a mega-cap like AAPL), so they can never fill this gap regardless
    of company size. Yahoo's own consensus tables, by contrast, come back
    populated even for a 2-analyst micro-cap.

    Returns {eps: DataFrame|None, revenue: DataFrame|None,
             eps_revision_pct: float|None, error: str|None}.
    eps_revision_pct = the current-year+next-year forward EPS estimate's
    average % change over the last 90 days (rising estimates ahead of
    price is a classic quiet-accumulation tell; falling estimates are the
    opposite) — same read `modules/opportunity.py::_eps_revisions()`
    already uses elsewhere, recomputed here so this module doesn't have to
    import from opportunity.py for one number.
    """
    try:
        t = yf.Ticker(symbol)
        eps_est = t.earnings_estimate
        rev_est = t.revenue_estimate
        eps_trend = t.eps_trend
    except Exception as e:
        return {"eps": None, "revenue": None, "eps_revision_pct": None, "error": str(e)}

    def _relabel(df):
        if df is None or df.empty:
            return None
        out = df.rename(index=_PERIOD_LABELS)
        return out[out.index.isin(_PERIOD_LABELS.values())]

    eps_revision_pct = None
    if eps_trend is not None and not eps_trend.empty:
        revs = []
        for row in ("0y", "+1y"):
            if row in eps_trend.index:
                cur, old = eps_trend.loc[row, "current"], eps_trend.loc[row, "90daysAgo"]
                if pd.notna(cur) and pd.notna(old) and old != 0:
                    revs.append((float(cur) / float(old) - 1) * 100)
        if revs:
            eps_revision_pct = round(sum(revs) / len(revs), 1)

    return {
        "eps":              _relabel(eps_est),
        "revenue":          _relabel(rev_est),
        "eps_revision_pct": eps_revision_pct,
        "error":            None,
    }
