"""Streamlit UI for the 💰 New Money allocator (logic lives in new_money.py)."""
from __future__ import annotations

import html as _html
import io

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import WEEKLY_UNIVERSE
from modules import new_money as nm

_BUCKET_COLORS = {"core": "#4da3ff", "sectors": "#a3e635", "qos": "#16c784", "reserve": "#8a94a6"}


def _md(s: str) -> str:
    """Escape '$' so st.markdown doesn't render "$81 … ($100)" as LaTeX."""
    return s.replace("$", "\\$")


def _fx_usdils() -> float | None:
    try:
        from utils.cache import get_price_history
        df = get_price_history("ILS=X", period="5d")
        if df is not None and not df.empty:
            return float(df["Close"].squeeze().iloc[-1])
    except Exception:
        pass
    return None


def _holdings_from_upload(file, fx: float) -> list[dict]:
    from modules import portfolio as mod_portfolio
    df_raw, fmt = mod_portfolio.load_portfolio(file)
    if df_raw is None or df_raw.empty:
        return []
    out = []
    if fmt == "broker":
        df = mod_portfolio.enrich_portfolio_broker(df_raw)
        for _, r in df.iterrows():
            v_nis = r.get("Value (NIS)") or 0
            out.append({"ticker": r.get("Ticker") or "", "name": r.get("Name", ""),
                        "value": float(v_nis) / fx if fx else 0.0, "sector": r.get("Sector"),
                        "kind": "Israeli" if r.get("Type") == "Israeli" else "US"})
    else:
        df = mod_portfolio.enrich_portfolio(df_raw)
        for _, r in df.iterrows():
            out.append({"ticker": r["Ticker"], "name": r.get("Name", ""),
                        "value": float(r["Market Value"]), "sector": r.get("Sector"), "kind": "US"})
    return out


def _holdings_from_text(txt: str) -> list[dict]:
    """Lines of `TICKER, value_usd` → holdings (sector looked up live)."""
    from utils.cache import get_ticker_info
    out = []
    for line in (txt or "").splitlines():
        parts = [p.strip() for p in line.replace("\t", ",").split(",") if p.strip()]
        if len(parts) < 2:
            continue
        try:
            val = float(parts[1].replace("$", "").replace("_", ""))
        except ValueError:
            continue
        t = parts[0].upper()
        try:
            sector = (get_ticker_info(t) or {}).get("sector")
        except Exception:
            sector = None
        out.append({"ticker": t, "name": t, "value": val, "sector": sector, "kind": "US"})
    return out


def render() -> None:
    st.title("💰 New Money Allocator")
    with st.expander("ⓘ About this page — what, how it's computed, how to use"):
        st.markdown("""**What:** you have a new deposit — this page splits it into concrete buys.
**How:** three signals the app already computes, combined:
1. **🏥 Market Health** composite → how much goes in **now** vs. a **staged reserve**, and the mix between buckets.
2. **🔄 Sector Rotation** → the strongest sector ETFs (score ≥ 6, above MA200, momentum not fading).
3. **🎯 Opportunity Lens** → **Quality on Sale** stocks. Only names with ≥ 3/5 reversal signals get money (starter size); the rest go to a watchlist.

Every line is checked against your **current portfolio**: a broad sector already above the cap gets nothing new, and no single stock goes above the position cap. Rebalancing with new money instead of selling means **no realized capital-gains tax** (25% in Israel).
**Use:** read it as a plan, not an order. Re-run when the reserve tranche dates arrive.""")

    # ── Inputs ────────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        amount_in = st.number_input("Amount to invest", min_value=0.0, value=20_000.0,
                                    step=1_000.0, format="%.0f", key="nm_amount")
    with c2:
        cur = st.radio("Currency", ["₪ ILS", "$ USD"], horizontal=True, key="nm_cur")
    with c3:
        fx_live = st.session_state.get("nm_fx_live")
        if fx_live is None:
            fx_live = _fx_usdils()
            st.session_state["nm_fx_live"] = fx_live
        fx = st.number_input("USD/ILS", min_value=1.0, value=float(fx_live or 3.6), step=0.01,
                             format="%.3f", key="nm_fx",
                             help="Live from Yahoo (ILS=X) when available; editable.")
    amount_usd = amount_in / fx if cur.startswith("₪") else amount_in

    st.markdown('<div class="panel-head">CURRENT PORTFOLIO</div>', unsafe_allow_html=True)
    src = st.radio("Where are your current holdings?",
                   ["Upload file (same formats as 💼 Portfolio)", "Type them", "No portfolio yet"],
                   horizontal=True, key="nm_src", label_visibility="collapsed")
    if src.startswith("Upload"):
        up = st.file_uploader("Broker export or CSV (Ticker, Shares, Avg Price)",
                              type=["csv", "xlsx"], key="nm_upload")
        if up is not None and st.session_state.get("nm_upload_name") != up.name:
            with st.spinner("Reading portfolio and live prices…"):
                st.session_state["nm_holdings"] = _holdings_from_upload(up, fx)
                st.session_state["nm_upload_name"] = up.name
    elif src.startswith("Type"):
        txt = st.text_area("One per line: TICKER, value in USD", "VT, 30000\nNVDA, 8000\nMSFT, 5000",
                           key="nm_txt", height=110)
        if st.button("Use these holdings", key="nm_txt_btn"):
            with st.spinner("Looking up sectors…"):
                st.session_state["nm_holdings"] = _holdings_from_text(txt)
    else:
        st.session_state["nm_holdings"] = []
    holdings = st.session_state.get("nm_holdings", [])
    if holdings:
        tot = sum(h["value"] for h in holdings)
        st.caption(f"{len(holdings)} positions · ${tot:,.0f} (≈ ₪{tot*fx:,.0f})")

    # ── Settings ──────────────────────────────────────────────────────────────
    d = nm.DEFAULT_SETTINGS
    with st.expander("⚙️ Rules & assumptions (editable)", expanded=False):
        s1, s2, s3 = st.columns(3)
        core_ticker = s1.text_input("Core index vehicle", d["core_ticker"], key="nm_core",
                                    help="VT = global all-cap (US-domiciled). For an Israeli investor, "
                                         "Irish UCITS alternatives (VWRA / SSAC on LSE) avoid US estate "
                                         "tax exposure and cut dividend withholding to 15% inside the fund.")
        reserve_vehicle = s1.text_input("Reserve parked in", d["reserve_vehicle"], key="nm_res",
                                        help="0-3M T-bills. Shekel alternative: a money-market fund (קרן כספית).")
        sector_cap = s2.slider("Max % in one broad sector", 10, 60, int(d["sector_cap_pct"]), key="nm_scap")
        pos_cap = s2.slider("Max % in one stock", 2, 20, int(d["position_cap_pct"]), key="nm_pcap")
        top_sectors = s3.slider("Sector ETFs to buy", 1, 5, d["top_sectors"], key="nm_topsec")
        max_qos = s3.slider("Max Quality-on-Sale names", 0, 8, d["max_qos_names"], key="nm_maxq")
        categories = st.multiselect(
            "Sector Rotation groups to choose from",
            ["Broad Sectors", "AI & Compute", "Tech Themes", "Healthcare", "Finance & Crypto",
             "Energy & Power", "Industry & Defense", "Consumer & Housing", "Geographies",
             "Styles & Factors", "Commodities"],
            default=d["categories"], key="nm_cats",
            help="Theme ETFs count against their broad sector's cap (e.g. SMH counts as Technology).")
        f1, f2 = st.columns(2)
        commission = f1.number_input("Commission per trade ($)", 0.0, 50.0, 0.0, 0.5, key="nm_comm")
        max_fee = f2.number_input("Max fee as % of trade", 0.05, 5.0, 0.5, 0.05, key="nm_fee",
                                  help="Lines smaller than commission ÷ this % are folded into the core.")
        override = st.checkbox("Override the regime's deploy-now % and mix", key="nm_ovr")
        dep_ovr, mix_ovr = None, None
        if override:
            o1, o2, o3, o4 = st.columns(4)
            dep_ovr = o1.slider("Deploy now %", 0, 100, 50, key="nm_dep") / 100
            mix_ovr = {"core": o2.slider("Core", 0, 100, 45, key="nm_mc"),
                       "sectors": o3.slider("Sectors", 0, 100, 25, key="nm_ms"),
                       "qos": o4.slider("QoS", 0, 100, 30, key="nm_mq")}
            if sum(mix_ovr.values()) == 0:
                mix_ovr = None
        uni_extra = st.text_input("Extra tickers to check for Quality on Sale (comma-separated)",
                                  "", key="nm_extra")
        max_analyze = st.slider("Stocks to run through Opportunity Lens", 10, 60, 30, key="nm_maxan",
                                help="After a fast drawdown filter (≥15% off the 1y high) on the "
                                     f"{len(WEEKLY_UNIVERSE)}-ticker curated universe. Your stock "
                                     "holdings are always included.")
        st.markdown("**Regime table (v1 assumption):**")
        st.dataframe(pd.DataFrame([{
            "Market Health ≥": lo, "Regime": lbl, "Deploy now": f"{dep*100:.0f}%",
            "Core": f"{m['core']*100:.0f}%", "Sectors": f"{m['sectors']*100:.0f}%",
            "Quality on Sale": f"{m['qos']*100:.0f}%"} for lo, lbl, dep, m, _ in nm.REGIME_TABLE]),
            hide_index=True, width="stretch")

    settings = {"core_ticker": core_ticker.strip().upper() or d["core_ticker"],
                "reserve_vehicle": reserve_vehicle.strip().upper() or d["reserve_vehicle"],
                "sector_cap_pct": float(sector_cap), "position_cap_pct": float(pos_cap),
                "top_sectors": top_sectors, "max_qos_names": max_qos, "categories": categories,
                "commission_usd": commission, "max_fee_pct": max_fee,
                "deploy_now_pct": dep_ovr, "mix": mix_ovr}

    # ── Data (heavy, on button) ───────────────────────────────────────────────
    if st.button("🧮 Build my allocation", type="primary", key="nm_go"):
        from modules import market_health as mod_mh, sector_strength as mod_ss
        status = st.status("Collecting signals…", expanded=True)
        status.write("🏥 Market Health…")
        mh_data = mod_mh.fetch_all()
        comp = mod_mh.compute_composite(mh_data)
        status.write(f"→ {comp['score']:.0f}/100 · {comp['label']}")
        status.write("🔄 Sector Rotation…")
        rot = mod_ss.get_sector_rotation()
        status.write(f"→ {len(rot)} sector/theme ETFs ranked")
        status.write("🎯 Scanning for Quality on Sale…")
        held_stocks = [h["ticker"] for h in holdings
                       if h.get("ticker") and h.get("kind") != "Israeli"
                       and h["ticker"] not in {r["etf"] for r in rot}]
        extra = [t.strip().upper() for t in uni_extra.split(",") if t.strip()]
        qos = nm.scan_quality_on_sale(WEEKLY_UNIVERSE + extra, always_include=held_stocks + extra,
                                      max_analyze=max_analyze, progress_cb=status.write)
        n_qos = sum(1 for q in qos if q["quadrant"] == "QUALITY ON SALE")
        status.write(f"→ {n_qos} Quality-on-Sale names found")
        status.update(label="Signals ready", state="complete", expanded=False)
        st.session_state["nm_signals"] = {"health": comp, "rotation": rot, "qos": qos}

    sig = st.session_state.get("nm_signals")
    if not sig:
        st.info("Set the amount and your holdings, then press **Build my allocation**. "
                "The scan takes ~1 minute the first time (cached afterwards).")
        return

    plan = nm.allocate(amount_usd, sig["health"]["score"], sig["rotation"], sig["qos"],
                       holdings, settings)
    _render_plan(plan, sig, fx)


def _render_plan(plan: dict, sig: dict, fx: float) -> None:
    reg = plan["regime"]
    color = sig["health"].get("color", "#f0b90b")
    st.markdown(
        f'<div style="border-left:4px solid {color};padding:10px 14px;background:#1c2333;color:#e8edf8;'
        f'border-radius:6px;margin:8px 0">'
        f'<b>Market regime: {_html.escape(reg["label"])} ({reg["score"]:.0f}/100)</b><br>'
        f'<span style="color:#b8c2d6">{_html.escape(reg["note"])}</span></div>',
        unsafe_allow_html=True)

    amt = plan["amount"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Deposit", f"${amt:,.0f}", f"₪{amt*fx:,.0f}", delta_color="off")
    k2.metric("Invest now", f"${plan['deployed_now']:,.0f}",
              f"{plan['deployed_now']/amt*100:.0f}%" if amt else None, delta_color="off")
    k3.metric("Staged reserve", f"${amt - plan['deployed_now']:,.0f}")
    k4.metric("Min trade", f"${plan['min_trade']:,.0f}")

    # ── Allocation table + donut ──────────────────────────────────────────────
    st.markdown('<div class="panel-head">RECOMMENDED SPLIT</div>', unsafe_allow_html=True)
    rows = [{"Bucket": ln["bucket_label"], "Ticker": ln["ticker"], "Name": ln["name"],
             "Amount ($)": ln["amount"], "Amount (₪)": ln["amount"] * fx,
             "% of deposit": ln["pct"], "Why": ln["why"]} for ln in plan["lines"]]
    df = pd.DataFrame(rows)
    t_col, p_col = st.columns([3, 1])
    with t_col:
        if df.empty:
            st.warning("Nothing to allocate — enter an amount.")
        else:
            st.dataframe(df.style.format({"Amount ($)": "${:,.0f}", "Amount (₪)": "₪{:,.0f}",
                                          "% of deposit": "{:.1f}%"}),
                         hide_index=True, width="stretch",
                         column_config={"Why": st.column_config.TextColumn(width="large")})
    with p_col:
        if not df.empty:
            agg: dict[str, float] = {}
            for ln in plan["lines"]:
                agg[ln["bucket"]] = agg.get(ln["bucket"], 0) + ln["amount"]
            fig = go.Figure(go.Pie(labels=[nm.BUCKET_LABELS[k] for k in agg], values=list(agg.values()),
                                   hole=0.55, marker_colors=[_BUCKET_COLORS[k] for k in agg],
                                   textinfo="percent", sort=False))
            fig.update_layout(paper_bgcolor="#131722", font_color="#e8edf8", height=260,
                              margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig, width="stretch")

    if not df.empty:
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        st.download_button("📥 Download plan (CSV)", buf.getvalue().encode("utf-8-sig"),
                           "new_money_plan.csv", "text/csv", key="nm_dl")

    # ── Tranches ──────────────────────────────────────────────────────────────
    if plan["tranches"]:
        st.markdown('<div class="panel-head">RESERVE — WHEN THE REST GOES IN</div>', unsafe_allow_html=True)
        for i, t in enumerate(plan["tranches"], 1):
            st.markdown(_md(f"**Tranche {i} — ${t['amount']:,.0f} (₪{t['amount']*fx:,.0f})** · "
                            f"{t['when']}. → {t['into']}."))

    # ── Watchlist / skipped ───────────────────────────────────────────────────
    w_col, s_col = st.columns(2)
    with w_col:
        st.markdown('<div class="panel-head">👁 QUALITY ON SALE — NOT READY YET</div>', unsafe_allow_html=True)
        if plan["watchlist"]:
            st.dataframe(pd.DataFrame([{
                "Ticker": w["ticker"], "Name": w.get("name", ""), "Quality": w.get("quality"),
                "Reversal": f"{w.get('readiness', 0)}/5",
                "From high": f"{w['drawdown']:+.0f}%" if w.get("drawdown") is not None else "—",
            } for w in plan["watchlist"]]), hide_index=True, width="stretch")
            st.caption("Good businesses still falling. No money until ≥3/5 reversal signals — "
                       "that's what the reserve tranches are waiting for.")
        else:
            st.caption("None found in this scan.")
    with s_col:
        st.markdown('<div class="panel-head">⛔ SKIPPED BECAUSE OF YOUR PORTFOLIO / COSTS</div>',
                    unsafe_allow_html=True)
        if plan["skipped"]:
            for s in plan["skipped"]:
                st.markdown(_md(f"- **{_html.escape(s['ticker'])}** {_html.escape(s.get('name') or '')} — "
                                f"{_html.escape(s['reason'])}"))
        else:
            st.caption("Nothing was blocked by caps or minimum trade size.")

    # ── Exposure before/after ─────────────────────────────────────────────────
    if plan["portfolio_total"] > 0:
        st.markdown('<div class="panel-head">EXPOSURE — BEFORE vs AFTER THIS DEPOSIT</div>',
                    unsafe_allow_html=True)
        ex = plan["exposure"]
        fig = go.Figure()
        fig.add_bar(name="Before", y=[e["label"] for e in ex], x=[e["before_pct"] for e in ex],
                    orientation="h", marker_color="#4a5568")
        fig.add_bar(name="After", y=[e["label"] for e in ex], x=[e["after_pct"] for e in ex],
                    orientation="h", marker_color="#4da3ff")
        cap = plan["settings"]["sector_cap_pct"]
        fig.add_vline(x=cap, line_dash="dash", line_color="#ea3a44",
                      annotation_text=f"sector cap {cap:.0f}%", annotation_font_color="#ea3a44")
        fig.update_layout(barmode="group", paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                          font_color="#e8edf8", height=max(260, 34 * len(ex) + 80),
                          margin=dict(t=20, b=20, l=10, r=10), yaxis=dict(autorange="reversed"),
                          xaxis_title="% of total portfolio", legend=dict(orientation="h"))
        st.plotly_chart(fig, width="stretch")

    # ── Israeli-investor notes ────────────────────────────────────────────────
    with st.expander("🇮🇱 Tax & cost notes for an Israeli investor (not modeled yet)"):
        st.markdown("""- **Capital gains 25%** on real (inflation-adjusted) gains when you sell — which is why this page rebalances with *new* money instead of selling winners.
- **US dividends:** 25% withheld at source with a W-8BEN (treaty rate); Israeli tax tops up to 25%. Irish-domiciled UCITS ETFs pay 15% inside the fund instead.
- **US estate tax:** non-residents are exposed above ~$60k of US-situs assets (US stocks and US-domiciled ETFs). UCITS ETFs avoid this.
- **Currency:** buying in USD adds USD/ILS exposure. The ₪ amounts above use today's rate.
- **Fees:** set your broker's commission in *Rules & assumptions* so small lines get folded into the core.

*Next step: model these properly — after-tax comparison of US vs. UCITS vehicles and a loss-offset helper.*""")
