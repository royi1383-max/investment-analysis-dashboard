"""
SEC EDGAR 13F Smart Money Tracker.
Fetches institutional holdings from 13F-HR filings for ~11 famous hedge funds.
No API key required — SEC EDGAR is free (rate limit: 10 req/s).
Data is ~45 days delayed (SEC filing deadline).
"""
import re
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
import streamlit as st

_HEADERS = {"User-Agent": "InvestmentDashboard royi1383@gmail.com"}
_NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"

FAMOUS_FUNDS: dict[str, dict] = {
    "Druckenmiller":     {"cik": "0001536411", "style": "Macro"},
    "Bill Ackman":       {"cik": "0001336528", "style": "Activist"},
    "David Tepper":      {"cik": "0001656456", "style": "Event-Driven"},
    "Seth Klarman":      {"cik": "0001061768", "style": "Deep Value"},
    "Tiger Global":      {"cik": "0001167483", "style": "Growth"},
    "Bridgewater":       {"cik": "0001350694", "style": "Macro"},
    "Viking Global":     {"cik": "0001103804", "style": "Long/Short"},
    "Coatue Mgmt":       {"cik": "0001135730", "style": "Tech Growth"},
    "Renaissance Tech":  {"cik": "0001037389", "style": "Quant"},
    "Cathie Wood (ARK)": {"cik": "0001697748", "style": "Disruptive Tech"},
    "Michael Burry":     {"cik": "0001649339", "style": "Contrarian"},
}


def _fetch(url: str) -> bytes:
    # SEC rate limit is 10 req/s — pace every request
    time.sleep(0.15)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


def _get_13f_filings(cik: str) -> list[dict]:
    """Return list of 13F-HR filings for a CIK [{accession, date}], newest first."""
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = json.loads(_fetch(url))
    filings = data.get("filings", {}).get("recent", {})
    forms      = filings.get("form", [])
    dates      = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    result = [
        {"accession": accessions[i], "date": dates[i]}
        for i, f in enumerate(forms) if f == "13F-HR"
    ]
    return result[:6]


def _find_infotable_url(cik_raw: str, accession: str) -> str | None:
    """Find the InfoTable XML file URL from a filing's directory listing."""
    acc_nodash = accession.replace("-", "")
    dir_url = f"https://www.sec.gov/Archives/edgar/data/{cik_raw}/{acc_nodash}/"
    try:
        html = _fetch(dir_url).decode("utf-8")
    except Exception:
        return None
    # All XML files in the directory
    xml_files = re.findall(r'href="(/Archives/edgar/data/[^"]+\.xml)"', html)
    for f in xml_files:
        if "primary_doc" not in f.lower():
            return "https://www.sec.gov" + f
    # Fallback: first XML
    if xml_files:
        return "https://www.sec.gov" + xml_files[0]
    return None


def _parse_holdings(xml_bytes: bytes) -> list[dict]:
    """Parse 13F InfoTable XML into holdings list."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    ns = {"n": _NS}
    rows = []
    for info in root.findall("n:infoTable", ns):
        def g(tag: str) -> str:
            el = info.find(f"n:{tag}", ns)
            return (el.text or "").strip() if el is not None else ""

        try:
            shares_el = info.find("n:shrsOrPrnAmt/n:sshPrnamt", ns)
            shares = int((shares_el.text or "0").replace(",", "")) if shares_el is not None else 0
            value_raw = g("value").replace(",", "")
            value_k = int(value_raw) if value_raw.isdigit() else 0
        except (ValueError, AttributeError):
            shares, value_k = 0, 0

        rows.append({
            "name":    g("nameOfIssuer"),
            "cusip":   g("cusip"),
            "value_k": value_k,
            "shares":  shares,
        })

    # Some filers report values in dollars instead of thousands (non-standard).
    # Detection: if any single holding exceeds $50B (50M in thousands), values are in dollars.
    if rows:
        max_val = max((r["value_k"] for r in rows), default=0)
        if max_val > 50_000_000:
            for r in rows:
                r["value_k"] = r["value_k"] // 1000

    return rows


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_fund_pair(cik: str) -> tuple[list[dict], list[dict], str, str]:
    """
    Fetch latest + previous 13F holdings for a fund.
    Returns (latest_holdings, prev_holdings, latest_date, prev_date).
    Cached 24h per CIK.
    """
    try:
        cik_raw = str(int(cik))
        filings = _get_13f_filings(cik)
        if not filings:
            return [], [], "", ""

        def _load(filing: dict) -> list[dict]:
            # pacing handled inside _fetch()
            xml_url = _find_infotable_url(cik_raw, filing["accession"])
            if not xml_url:
                return []
            return _parse_holdings(_fetch(xml_url))

        latest = _load(filings[0])
        prev   = _load(filings[1]) if len(filings) > 1 else []
        return (
            latest, prev,
            filings[0]["date"],
            filings[1]["date"] if len(filings) > 1 else "",
        )
    except Exception:
        return [], [], "", ""


_LEGAL_WORDS = {
    "inc", "corp", "corporation", "incorporated", "ltd", "limited",
    "co", "llc", "plc", "group", "holdings", "technologies", "technology",
    "systems", "solutions", "services", "international", "global",
    "enterprises", "company", "companies", "the", "and",
}

def _name_keywords(long_name: str) -> list[str]:
    """Extract distinctive words from a company name for fuzzy matching."""
    words = re.findall(r'[a-z0-9]+', long_name.lower())
    meaningful = [w for w in words if w not in _LEGAL_WORDS and len(w) >= 4]
    return meaningful[:2]


def _matches_stock(issuer_name: str, keywords: list[str]) -> bool:
    issuer = issuer_name.lower()
    return any(kw in issuer for kw in keywords)


def _fmt_shares(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _fmt_value(value_k: int) -> str:
    val_m = value_k / 1_000
    if val_m >= 1_000:
        return f"${val_m / 1_000:.1f}B"
    return f"${val_m:.0f}M"


def _change_info(curr_shares: int, prev_shares: int) -> tuple[str, str]:
    """Returns (label_text, hex_color)."""
    if prev_shares == 0:
        return "🆕 NEW", "#16c784"
    pct = (curr_shares - prev_shares) / prev_shares
    if pct >= 0.10:
        return f"➕ +{pct * 100:.0f}%", "#16c784"
    if pct <= -0.10:
        return f"✂️ -{abs(pct) * 100:.0f}%", "#ea3a44"
    return "— HOLD", "#556070"


def get_smart_money_for_stock(symbol: str, stock_name: str) -> list[dict]:
    """
    Cross-reference all FAMOUS_FUNDS holdings for a given stock.
    Returns list of dicts sorted by position size (largest first).
    Each dict: {fund, style, shares_fmt, value_fmt, change_label, change_color, filing_date}
    """
    keywords = _name_keywords(stock_name)
    if not keywords:
        return []

    results = []
    for fund_name, meta in FAMOUS_FUNDS.items():
        try:
            latest, prev, date_l, _ = _fetch_fund_pair(meta["cik"])
            if not latest:
                continue

            curr_h = next((h for h in latest if _matches_stock(h["name"], keywords)), None)
            if curr_h is None:
                continue

            prev_h = next((h for h in prev if _matches_stock(h["name"], keywords)), None)
            prev_shares = prev_h["shares"] if prev_h else 0

            label, color = _change_info(curr_h["shares"], prev_shares)

            results.append({
                "fund":         fund_name,
                "style":        meta["style"],
                "shares":       curr_h["shares"],
                "shares_fmt":   _fmt_shares(curr_h["shares"]),
                "value_fmt":    _fmt_value(curr_h["value_k"]),
                "change_label": label,
                "change_color": color,
                "filing_date":  date_l,
            })
        except Exception:
            continue

    results.sort(key=lambda x: -x["shares"])
    return results
