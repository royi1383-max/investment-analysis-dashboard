"""
FMP (Financial Modeling Prep) integration — free-tier endpoints (250 req/day).

Available on free tier (probed live against /stable/*):
  • grades          — full analyst rating-action history per symbol
                      (upgrade / downgrade / maintain / initiate). Reliable,
                      per-symbol, the main feature here.
  • senate-latest    — market-wide US Senate trading disclosures. Free tier
                      hard-caps this at page=0, limit<=25 — a single snapshot
                      of the 25 most recent disclosures across ALL symbols/
                      senators, no pagination (page>0 or limit>25 -> 402).
                      Useful as a raw "what did Congress just do" feed;
                      too small a sample for reliable per-symbol lookup or
                      cluster detection — treat both as best-effort bonuses.

Per-symbol senate-trades / house-trades / insider-trading endpoints are
premium (402 on free tier) — not called.
"""
import json
import datetime
import urllib.request
import streamlit as st

from config import FMP_API_KEY

_BASE = "https://financialmodelingprep.com/stable"


def _get(path: str, params: str) -> list | dict | None:
    try:
        url = f"{_BASE}/{path}?{params}&apikey={FMP_API_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "InvestmentDashboard"})
        return json.loads(urllib.request.urlopen(req, timeout=15).read())
    except Exception:
        return None


# ─── Congress (Senate) trading feed ───────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)
def senate_latest() -> list[dict]:
    """Latest 25 Senate trading disclosures, market-wide (newest first).
    Free tier hard-caps this endpoint at page=0, limit<=25 (no pagination
    allowed — page>0 or limit>25 both 402). Returns [] on failure / no key."""
    if not FMP_API_KEY:
        return []
    d = _get("senate-latest", "page=0&limit=25")
    rows = d if isinstance(d, list) else []
    out = []
    for r in rows:
        out.append({
            "symbol":     (r.get("symbol") or "").upper(),
            "name":       f"{r.get('firstName','')} {r.get('lastName','')}".strip(),
            "district":   r.get("district", ""),
            "type":       r.get("type", ""),          # Purchase / Sale / Exchange
            "amount":     r.get("amount", ""),
            "tx_date":    r.get("transactionDate", ""),
            "disc_date":  r.get("disclosureDate", ""),
            "asset":      r.get("assetDescription", ""),
            "link":       r.get("link", ""),
        })
    return out


def senate_for_symbol(symbol: str, feed: list[dict] | None = None) -> list[dict]:
    """Filter the market-wide feed for one symbol."""
    feed = feed if feed is not None else senate_latest()
    return [r for r in feed if r["symbol"] == symbol.upper()]


def senate_cluster_summary(feed: list[dict] | None = None) -> list[dict]:
    """Symbols traded by more than one senator within the available feed —
    the cluster signal. NOTE: free tier only exposes the 25 most recent
    market-wide disclosures, so this fires rarely; treat as a bonus, not
    a reliable scanner. Returns [{symbol, buys, sells, senators, latest}]."""
    feed = feed if feed is not None else senate_latest()
    agg: dict[str, dict] = {}
    for r in feed:
        if not r["symbol"]:
            continue
        a = agg.setdefault(r["symbol"], {"symbol": r["symbol"], "buys": 0,
                                         "sells": 0, "senators": set(), "latest": ""})
        if "purchase" in r["type"].lower():
            a["buys"] += 1
        elif "sale" in r["type"].lower():
            a["sells"] += 1
        a["senators"].add(r["name"])
        a["latest"] = max(a["latest"], r["tx_date"])
    out = []
    for a in agg.values():
        n_sen = len(a["senators"])
        a["senators"] = n_sen
        if n_sen >= 2:
            out.append(a)
    out.sort(key=lambda x: (-x["senators"], -(x["buys"] + x["sells"])))
    return out


# ─── Analyst rating actions ───────────────────────────────────────────────────

@st.cache_data(ttl=21600, show_spinner=False)
def analyst_grades(symbol: str) -> dict:
    """Rating-action history: recent actions + 90-day up/down momentum.
    Returns {recent: [...], up_90d, down_90d, init_90d, verdict, color}."""
    if not FMP_API_KEY:
        return {"error": "No FMP_API_KEY configured."}
    d = _get("grades", f"symbol={symbol.upper()}")
    if not isinstance(d, list) or not d:
        return {"error": "No grades data."}

    cutoff = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    up = down = init = 0
    for r in d:
        if (r.get("date") or "") < cutoff:
            continue
        act = (r.get("action") or "").lower()
        if act == "upgrade":
            up += 1
        elif act == "downgrade":
            down += 1
        elif act in ("initiate", "initiated coverage"):
            init += 1

    net = up - down
    if net >= 3:
        verdict, color = f"REVISION MOMENTUM UP — {up} upgrades vs {down} downgrades in 90d", "#16c784"
    elif net <= -3:
        verdict, color = f"REVISION MOMENTUM DOWN — {down} downgrades vs {up} upgrades in 90d", "#ea3a44"
    elif up + down == 0:
        verdict, color = "No rating changes in 90d — analysts standing pat", "#8a9bc2"
    else:
        verdict, color = f"Mixed: {up} up / {down} down in 90d", "#f0b90b"

    recent = [{
        "date":    r.get("date", ""),
        "firm":    r.get("gradingCompany", ""),
        "action":  (r.get("action") or "").lower(),
        "from":    r.get("previousGrade", ""),
        "to":      r.get("newGrade", ""),
    } for r in d[:15]]

    return {"recent": recent, "up_90d": up, "down_90d": down, "init_90d": init,
            "verdict": verdict, "color": color, "error": None}
