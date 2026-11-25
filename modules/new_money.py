"""
New Money Allocator — "I have X to invest today. Where does it go?"

Combines three signals the app already computes into one concrete split:

  1. MARKET HEALTH composite (0-100)  → how much to deploy NOW vs. keep as a
     staged reserve, and the mix between the three buckets below.
  2. SECTOR ROTATION                  → which sector ETFs are strong right now
                                         (trend + relative strength vs SPY).
  3. OPPORTUNITY LENS                  → which individual stocks are
                                         "QUALITY ON SALE" (good business, beaten-down
                                         stock). Only names with ≥3/5 reversal signals
                                         get money; the rest are a watchlist.

…and checks every line against the CURRENT portfolio, so new money fills
under-weight areas instead of piling onto what you already own (rebalancing
with new cash instead of selling — no realized capital-gains tax).

Everything below `allocate()` is pure (no network) so it is unit-testable; the
network-bound scanner lives in `scan_quality_on_sale()`.

ASSUMPTIONS (v1 — surfaced in the UI, all overridable):
  • Regime table (deploy-now % and bucket mix per Market Health band) is a
    judgement call, not a backtested optimum. See REGIME_TABLE.
  • In weak markets the mix tilts TOWARD Quality-on-Sale (buy fear) but the
    deploy-now % drops — i.e. buy cheap, but in tranches.
  • Money a bucket cannot use (no strong sector, no ready QoS name, cap hit)
    goes to: sectors → core, QoS → reserve (wait for reversal), tiny lines
    below the minimum trade → core.
  • Portfolio exposure is keyed by broad sector (SPDR ETF ticker). Broad index
    ETFs and unknown funds count as "Broad / Other" and are never capped.
"""
from __future__ import annotations

import math

# ─── Regime table ─────────────────────────────────────────────────────────────
# (min_score, label, deploy_now_pct, mix{core, sectors, qos}, note)
REGIME_TABLE = [
    (70, "Healthy — Risk-On", 0.70, {"core": 0.40, "sectors": 0.40, "qos": 0.20},
     "Trend is your friend: ride strong sectors. Few real bargains in a healthy "
     "market, so Quality-on-Sale gets a smaller slice. Keep 30% to buy dips."),
    (55, "Cautiously Positive", 0.60, {"core": 0.45, "sectors": 0.30, "qos": 0.25},
     "Mixed signals: lean on the core, stay selective in sectors."),
    (42, "Neutral — Wait & See", 0.50, {"core": 0.50, "sectors": 0.20, "qos": 0.30},
     "No clear edge: half now, half in tranches. Prefer quality over momentum."),
    (28, "Caution — Risk-Off", 0.40, {"core": 0.45, "sectors": 0.10, "qos": 0.45},
     "Prices are getting cheaper — tilt to Quality-on-Sale, but only names whose "
     "reversal has started. Most of the deposit waits in tranches."),
    (0, "Danger — Defensive Mode", 0.35, {"core": 0.40, "sectors": 0.00, "qos": 0.60},
     "Fear is high and so is opportunity. Deploy a third now into the core and "
     "ready bargains; stage the rest — bottoms take time to form."),
]

BUCKET_LABELS = {
    "core":    "🧱 Core (broad index)",
    "sectors": "🔄 Strong sectors",
    "qos":     "🎯 Quality on Sale",
    "reserve": "⏳ Staged reserve",
}

# yfinance .info["sector"] → broad-sector key (SPDR ETF). Mirrors
# sector_strength.SECTOR_ETF but kept local so this module stays import-light.
YF_SECTOR_TO_KEY = {
    "Technology": "XLK", "Communication Services": "XLC",
    "Consumer Cyclical": "XLY", "Consumer Defensive": "XLP",
    "Healthcare": "XLV", "Financial Services": "XLF", "Energy": "XLE",
    "Industrials": "XLI", "Basic Materials": "XLB", "Real Estate": "XLRE",
    "Utilities": "XLU",
}
KEY_LABELS = {
    "XLK": "Technology", "XLC": "Communication", "XLY": "Consumer Discret.",
    "XLP": "Consumer Staples", "XLV": "Health Care", "XLF": "Financials",
    "XLE": "Energy", "XLI": "Industrials", "XLB": "Materials",
    "XLRE": "Real Estate", "XLU": "Utilities",
    "ISRAEL": "Israel (local securities)", "OTHER": "Broad / Other",
}
# Rotation categories whose ETFs are really a slice of one broad sector — so a
# semis/AI ETF counts against the Technology cap, not as a free new bucket.
CATEGORY_TO_KEY = {
    "AI & Compute": "XLK", "Tech Themes": "XLK", "Healthcare": "XLV",
    "Finance & Crypto": "XLF", "Energy & Power": "XLE",
    "Industry & Defense": "XLI",
}

DEFAULT_SETTINGS = {
    "core_ticker":       "VT",     # global all-cap; UCITS alt: VWRA.L / SSAC.L
    "reserve_vehicle":   "SGOV",   # 0-3M T-bills; IL alt: קרן כספית
    "sector_cap_pct":    30.0,     # max % of total portfolio in one broad sector
    "position_cap_pct":  8.0,      # max % of total portfolio in one stock
    "top_sectors":       3,
    "max_qos_names":     5,
    "min_readiness":     3,        # Opportunity Lens: ≥3/5 = starter zone
    "commission_usd":    0.0,      # per trade
    "max_fee_pct":       0.5,      # trade must be big enough that fee ≤ this
    "min_trade_floor":   100.0,    # never suggest a trade smaller than this
    "categories":        ["Broad Sectors"],
    "deploy_now_pct":    None,     # None = from regime table
    "mix":               None,     # None = from regime table
}


# ─── Regime ───────────────────────────────────────────────────────────────────

def regime_plan(score: float | None) -> dict:
    """Map a Market Health composite (0-100) to a deployment plan."""
    if score is None or (isinstance(score, float) and math.isnan(score)):
        score = 50.0
    for lo, label, deploy, mix, note in REGIME_TABLE:
        if score >= lo:
            return {"score": float(score), "label": label, "deploy_now_pct": deploy,
                    "mix": dict(mix), "note": note}
    lo, label, deploy, mix, note = REGIME_TABLE[-1]
    return {"score": float(score), "label": label, "deploy_now_pct": deploy,
            "mix": dict(mix), "note": note}


# ─── Exposure ─────────────────────────────────────────────────────────────────

def _rotation_key_map(rotation: list[dict]) -> dict[str, str]:
    """ETF ticker → exposure key, from the rotation list's categories."""
    m = {}
    for r in rotation or []:
        etf, cat = r.get("etf"), r.get("category")
        if not etf:
            continue
        if cat == "Broad Sectors":
            m[etf] = etf
        elif cat in CATEGORY_TO_KEY:
            m[etf] = CATEGORY_TO_KEY[cat]
    return m


def exposure_key(ticker: str | None, sector: str | None, kind: str | None = None,
                 etf_map: dict[str, str] | None = None) -> str:
    """Which exposure bucket a holding / candidate belongs to."""
    if kind == "Israeli":
        return "ISRAEL"
    t = (ticker or "").upper()
    if etf_map and t in etf_map:
        return etf_map[t]
    if t in KEY_LABELS:
        return t
    if sector in YF_SECTOR_TO_KEY:
        return YF_SECTOR_TO_KEY[sector]
    return "OTHER"


def holdings_exposure(holdings: list[dict], etf_map: dict[str, str] | None = None) -> dict:
    """holdings: [{ticker, value, sector?, kind?}] in ONE currency (USD).
    Returns {"total": float, "by_key": {key: value}, "by_ticker": {ticker: value}}."""
    by_key: dict[str, float] = {}
    by_ticker: dict[str, float] = {}
    total = 0.0
    for h in holdings or []:
        v = float(h.get("value") or 0)
        if v <= 0:
            continue
        k = h.get("key") or exposure_key(h.get("ticker"), h.get("sector"), h.get("kind"), etf_map)
        by_key[k] = by_key.get(k, 0.0) + v
        t = (h.get("ticker") or "").upper()
        if t:
            by_ticker[t] = by_ticker.get(t, 0.0) + v
        total += v
    return {"total": total, "by_key": by_key, "by_ticker": by_ticker}


# ─── Bucket rankers ───────────────────────────────────────────────────────────

def is_strong_sector(r: dict) -> bool:
    """Trend-confirmed and not losing steam."""
    return (r.get("score", 0) >= 6.0 and bool(r.get("above_200"))
            and r.get("momentum_dir") != "↓")


def sector_rank_score(r: dict) -> float:
    s = r.get("rs1m", 0) + 0.5 * r.get("rs3m", 0) + r.get("score", 5)
    if r.get("early_signal") == "up":
        s += 2
    elif r.get("early_signal") == "down":
        s -= 2
    if r.get("momentum_dir") == "↑":
        s += 1
    return s


def rank_sectors(rotation: list[dict], categories: list[str]) -> list[dict]:
    cands = [r for r in rotation or [] if r.get("category") in categories and is_strong_sector(r)]
    return sorted(cands, key=sector_rank_score, reverse=True)


def qos_rank_score(c: dict) -> float:
    return float(c.get("quality", 0)) * (1 + float(c.get("readiness", 0))) \
        + 0.5 * float(c.get("n_support", 0)) - 0.5 * float(c.get("n_negative", 0)) \
        + (1.0 if c.get("sector_strong") else 0.0)


# ─── Allocation ───────────────────────────────────────────────────────────────

def min_trade_size(settings: dict) -> float:
    fee = float(settings.get("commission_usd") or 0)
    max_fee = float(settings.get("max_fee_pct") or 0.5) / 100
    by_fee = fee / max_fee if max_fee > 0 and fee > 0 else 0.0
    return max(float(settings.get("min_trade_floor") or 0), by_fee)


def _split(amount: float, weights: list[float]) -> list[float]:
    tot = sum(weights)
    if amount <= 0 or tot <= 0:
        return [0.0] * len(weights)
    return [amount * w / tot for w in weights]


def allocate(amount: float, health_score: float | None, rotation: list[dict],
             qos_candidates: list[dict], holdings: list[dict],
             settings: dict | None = None) -> dict:
    """Build the recommended split. All money values in USD.

    rotation:        output of sector_strength.get_sector_rotation()
    qos_candidates:  [{ticker, name, sector, quality, readiness, quadrant,
                       drawdown, n_support, n_negative, guidance}]
    holdings:        [{ticker, value, sector, kind}]
    """
    cfg = {**DEFAULT_SETTINGS, **(settings or {})}
    amount = max(0.0, float(amount or 0))
    regime = regime_plan(health_score)
    deploy_pct = cfg["deploy_now_pct"] if cfg["deploy_now_pct"] is not None else regime["deploy_now_pct"]
    mix = dict(cfg["mix"] or regime["mix"])
    mtot = sum(mix.values()) or 1.0
    mix = {k: v / mtot for k, v in mix.items()}

    etf_map = _rotation_key_map(rotation)
    exp = holdings_exposure(holdings, etf_map)
    total_after = exp["total"] + amount
    sector_cap = cfg["sector_cap_pct"] / 100 * total_after
    pos_cap = cfg["position_cap_pct"] / 100 * total_after
    min_trade = min_trade_size(cfg)

    deploy = amount * deploy_pct
    reserve = amount - deploy
    budget = {k: deploy * mix.get(k, 0) for k in ("core", "sectors", "qos")}

    planned_by_key: dict[str, float] = {}
    lines: list[dict] = []
    skipped: list[dict] = []
    to_core = 0.0
    to_reserve = 0.0

    def headroom(key: str) -> float:
        if key in ("OTHER",):
            return float("inf")
        return max(0.0, sector_cap - exp["by_key"].get(key, 0.0) - planned_by_key.get(key, 0.0))

    # ── Sectors ──────────────────────────────────────────────────────────────
    ranked = rank_sectors(rotation, cfg["categories"])
    chosen = []
    for r in ranked:
        key = etf_map.get(r["etf"], "OTHER")
        if headroom(key) <= 0:
            skipped.append({"ticker": r["etf"], "name": r["label"],
                            "reason": f"{KEY_LABELS.get(key, key)} already ≥ {cfg['sector_cap_pct']:.0f}% of portfolio"})
            continue
        if any(etf_map.get(c["etf"]) == key for c in chosen) and key != "OTHER":
            continue  # one ETF per broad sector — diversify, don't double up
        chosen.append(r)
        if len(chosen) >= cfg["top_sectors"]:
            break
    if budget["sectors"] > 0 and not chosen:
        to_core += budget["sectors"]
    else:
        weights = [max(0.5, r.get("score", 5) - 5) for r in chosen]
        for r, amt in zip(chosen, _split(budget["sectors"], weights)):
            key = etf_map.get(r["etf"], "OTHER")
            amt_ok = min(amt, headroom(key))
            to_core += amt - amt_ok
            if amt_ok <= 0:
                continue
            planned_by_key[key] = planned_by_key.get(key, 0.0) + amt_ok
            why = (f"{r['label']}: grade {r.get('grade','')}, RS vs SPY 1M {r.get('rs1m',0):+.1f}% / "
                   f"3M {r.get('rs3m',0):+.1f}%, above MA200, momentum {r.get('momentum_dir','')}")
            if r.get("early_signal") == "up":
                why += " · 🆕 early up-signal this week"
            lines.append({"bucket": "sectors", "ticker": r["etf"], "name": r["label"],
                          "amount": amt_ok, "key": key, "why": why})

    # ── Quality on Sale ──────────────────────────────────────────────────────
    strong_keys = {etf_map.get(r["etf"]) for r in rank_sectors(rotation, list(set(
        [r.get("category") for r in rotation or []])))}
    ready, watch = [], []
    for c in qos_candidates or []:
        if c.get("quadrant") != "QUALITY ON SALE":
            continue
        c = dict(c)
        c["key"] = exposure_key(c.get("ticker"), c.get("sector"), None, etf_map)
        c["sector_strong"] = c["key"] in strong_keys
        (ready if c.get("readiness", 0) >= cfg["min_readiness"] else watch).append(c)
    ready.sort(key=qos_rank_score, reverse=True)
    watch.sort(key=qos_rank_score, reverse=True)

    picked = []
    for c in ready:
        if headroom(c["key"]) <= 0:
            skipped.append({"ticker": c["ticker"], "name": c.get("name", ""),
                            "reason": f"{KEY_LABELS.get(c['key'], c['key'])} already at sector cap"})
            continue
        if pos_cap - exp["by_ticker"].get(c["ticker"].upper(), 0.0) <= 0:
            skipped.append({"ticker": c["ticker"], "name": c.get("name", ""),
                            "reason": f"position already ≥ {cfg['position_cap_pct']:.0f}% of portfolio"})
            continue
        picked.append(c)
        if len(picked) >= cfg["max_qos_names"]:
            break

    if budget["qos"] > 0 and not picked:
        to_reserve += budget["qos"]
    else:
        weights = [qos_rank_score(c) for c in picked]
        for c, amt in zip(picked, _split(budget["qos"], weights)):
            # Starter position: at most HALF of the max position (Opportunity
            # Lens: "starter ⅓–½ size, add on MA50 reclaim").
            per_name_cap = max(0.0, min(pos_cap * 0.5, pos_cap - exp["by_ticker"].get(c["ticker"].upper(), 0.0)))
            amt_ok = min(amt, per_name_cap, headroom(c["key"]))
            to_reserve += amt - amt_ok
            if amt_ok <= 0:
                continue
            planned_by_key[c["key"]] = planned_by_key.get(c["key"], 0.0) + amt_ok
            dd = c.get("drawdown")
            why = (f"Quality {c.get('quality',0):.1f}/10, {c.get('readiness',0)}/5 reversal signals"
                   + (f", {dd:+.0f}% from 52w high" if dd is not None else "")
                   + (" · sector is strong" if c.get("sector_strong") else "")
                   + (" · already held — averaging down" if exp["by_ticker"].get(c["ticker"].upper()) else "")
                   + ". Starter size; add on MA50 reclaim.")
            lines.append({"bucket": "qos", "ticker": c["ticker"], "name": c.get("name", ""),
                          "amount": amt_ok, "key": c["key"], "why": why})

    # ── Minimum-trade filter (commission efficiency) ─────────────────────────
    kept = []
    for ln in lines:
        if ln["amount"] < min_trade:
            to_core += ln["amount"]
            planned_by_key[ln["key"]] = planned_by_key.get(ln["key"], 0.0) - ln["amount"]
            skipped.append({"ticker": ln["ticker"], "name": ln["name"],
                            "reason": f"${ln['amount']:,.0f} is below the minimum trade (${min_trade:,.0f})"})
        else:
            kept.append(ln)
    lines = kept

    core_amt = budget["core"] + to_core
    if 0 < core_amt < min_trade:
        to_reserve += core_amt
        core_amt = 0.0
    if core_amt > 0:
        lines.insert(0, {"bucket": "core", "ticker": cfg["core_ticker"], "name": "Broad global index",
                         "amount": core_amt, "key": "OTHER",
                         "why": "Diversified base — the part of the deposit that doesn't need a view."
                                + (f" Includes ${to_core:,.0f} that the sector/QoS buckets couldn't use."
                                   if to_core > 0.5 else "")})

    reserve_total = reserve + to_reserve
    tranches = []
    if reserve_total > 0.5:
        t1, t2 = reserve_total / 2, reserve_total - reserve_total / 2
        tranches = [
            {"amount": t1, "when": "In 2–4 weeks, or earlier if the S&P 500 falls 5% from today",
             "into": "Same split as today (re-run this page with the tranche amount)"},
            {"amount": t2, "when": "In 6–8 weeks, or earlier on a 10% drop / a watchlist name reaching "
                                   f"{cfg['min_readiness']}/5 reversal signals",
             "into": "Prefer Quality-on-Sale names that became ready"},
        ]
        lines.append({"bucket": "reserve", "ticker": cfg["reserve_vehicle"], "name": "Parked (T-bills / money market)",
                      "amount": reserve_total, "key": "CASH",
                      "why": f"Staged entry ({(1-deploy_pct)*100:.0f}% by regime"
                             + (f" + ${to_reserve:,.0f} with no ready QoS name / under min trade" if to_reserve > 0.5 else "")
                             + "). Earns interest while it waits."})

    for ln in lines:
        ln["pct"] = ln["amount"] / amount * 100 if amount else 0.0
        ln["bucket_label"] = BUCKET_LABELS[ln["bucket"]]

    # ── Exposure before/after ────────────────────────────────────────────────
    after = dict(exp["by_key"])
    for ln in lines:
        k = ln["key"]
        after[k] = after.get(k, 0.0) + ln["amount"]
    keys = sorted(set(exp["by_key"]) | set(after), key=lambda k: -after.get(k, 0))
    exposure_rows = [{
        "key": k, "label": "Cash / reserve" if k == "CASH" else KEY_LABELS.get(k, k),
        "before_pct": exp["by_key"].get(k, 0.0) / exp["total"] * 100 if exp["total"] else 0.0,
        "after_pct": after.get(k, 0.0) / total_after * 100 if total_after else 0.0,
    } for k in keys]

    return {
        "amount": amount, "regime": regime, "deploy_now_pct": deploy_pct, "mix": mix,
        "lines": lines, "tranches": tranches, "skipped": skipped,
        "watchlist": watch[:10], "exposure": exposure_rows,
        "portfolio_total": exp["total"], "min_trade": min_trade, "settings": cfg,
        "deployed_now": sum(ln["amount"] for ln in lines if ln["bucket"] != "reserve"),
    }


# ─── Network-bound scanner ────────────────────────────────────────────────────

def scan_quality_on_sale(tickers: list[str], always_include: list[str] | None = None,
                         max_analyze: int = 30, min_drawdown: float = 15.0,
                         progress_cb=None) -> list[dict]:
    """Two-stage scan: cheap price-only drawdown filter, then the full
    Opportunity Lens on the survivors (plus `always_include`, e.g. current
    holdings, which are always analyzed so averaging-down shows up)."""
    from utils.cache import get_price_history, get_ticker_info, parallel_map
    from modules import opportunity

    always = [t.upper() for t in (always_include or []) if t]
    uni = list(dict.fromkeys([t.upper() for t in tickers if t] + always))

    def _dd(sym):
        df = get_price_history(sym, period="1y")
        if df is None or df.empty:
            return None
        c = df["Close"].squeeze()
        return float(c.iloc[-1] / c.max() - 1) * 100

    dds = parallel_map(_dd, uni)
    dd_map = {s: d for s, d in zip(uni, dds) if isinstance(d, float)}
    pool = [s for s, d in dd_map.items() if -70 <= d <= -min_drawdown and s not in always]
    pool.sort(key=lambda s: dd_map[s])                       # deepest first
    to_analyze = list(dict.fromkeys(always + pool[:max_analyze]))
    if progress_cb:
        progress_cb(f"{len(dd_map)} prices checked · {len(pool)} down ≥{min_drawdown:.0f}% · "
                    f"running Opportunity Lens on {len(to_analyze)}")

    def _one(sym):
        info = get_ticker_info(sym) or {}
        if info.get("quoteType") not in (None, "EQUITY"):
            return None
        o = opportunity.analyze(sym)
        if o.get("error"):
            return None
        return {"ticker": sym, "name": info.get("shortName", sym), "sector": info.get("sector"),
                "quality": o["quality"], "condition": o["condition"], "readiness": o["readiness"],
                "quadrant": o["quadrant"], "drawdown": o["drawdown"],
                "n_support": o.get("n_support", 0), "n_negative": o.get("n_negative", 0),
                "guidance": o["guidance"]}

    out = parallel_map(_one, to_analyze)
    return [r for r in out if isinstance(r, dict)]
