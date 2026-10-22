"""
Sector Strength — computes a 3-level sector hierarchy for any stock:
  Level 1: Broad sector (Technology, Health Care, …)         → XLK, XLV, …
  Level 2: Sub-sector (Semiconductors, Biotech, Fintech, …)  → SOXX, XBI, FINX, …
  Level 3: Niche label(s) derived from industry string AND business summary
           → "Memory Chips", "AI Accelerators", "Optical Connectivity", …
           (a list, not a single label — multi-thematic/niche companies get
           more than one tag instead of being force-fit into one)

For each level, computes:
  - 1M / 3M return
  - Above MA50 / MA200
  - Relative Strength vs SPY (1M)
  - Strength score 1-10

All results are cached for 30 minutes.
"""
import re
from pathlib import Path

import streamlit as st
from utils.cache import get_ticker_info, get_price_history
from utils.persist import load_json, save_json

_ROTATION_SNAPSHOT_PATH = Path(__file__).parent.parent / ".sector_rotation_snapshot.json"


def _word_match(keyword: str, text: str) -> bool:
    """Leading-word-boundary match — plain substring risks false hits like
    "gas" inside "Vegas". No trailing boundary so plurals still match
    ("semiconductor" vs. yfinance's "Semiconductors", "bank" vs. "Banks")."""
    return re.search(r'\b' + re.escape(keyword.lower()), text) is not None


# ── Level-1: broad sector → ETF ───────────────────────────────────────────────
SECTOR_ETF: dict[str, tuple[str, str]] = {
    # Keys are yfinance's actual .info["sector"] strings — NOT GICS names.
    # yfinance uses its own taxonomy (verified live): "Financial Services"
    # not "Financials", "Healthcare" not "Health Care", "Consumer Cyclical"
    # not "Consumer Discretionary", "Consumer Defensive" not "Consumer
    # Staples", "Basic Materials" not "Materials". Mismatches here silently
    # blanked the Level-1 sector card for ~half the market (banks, healthcare,
    # consumer, materials) while tech names (where the names happen to align)
    # worked fine — which is why this went unnoticed.
    "Technology":             ("Technology",          "XLK"),
    "Communication Services": ("Communication",       "XLC"),
    "Consumer Cyclical":      ("Consumer Discret.",   "XLY"),
    "Consumer Defensive":     ("Consumer Staples",    "XLP"),
    "Healthcare":             ("Health Care",         "XLV"),
    "Financial Services":     ("Financials",          "XLF"),
    "Energy":                 ("Energy",              "XLE"),
    "Industrials":            ("Industrials",         "XLI"),
    "Basic Materials":        ("Materials",           "XLB"),
    "Real Estate":            ("Real Estate",         "XLRE"),
    "Utilities":              ("Utilities",           "XLU"),
}

# ── Level-2: industry keyword → (sub-sector label, ETF) ──────────────────────
# Entries are checked IN ORDER — first match wins.
# keyword is matched case-insensitively against yfinance 'industry' string.
INDUSTRY_MAP: list[tuple[str, str, str]] = [
    # Technology sub-sectors
    ("memory",              "Memory Chips",          "MU"),
    ("gpu",                 "AI / GPU Chips",         "NVDA"),
    ("semiconductor",       "Semiconductors",         "SOXX"),
    ("electronic component","Semiconductors",         "SOXX"),
    ("software-application","Application Software",   "IGV"),
    ("software-infra",      "Infrastructure SW",      "IGV"),
    ("software",            "Software / SaaS",        "IGV"),
    ("cloud",               "Cloud Computing",        "WCLD"),
    ("internet content",    "Internet / Social",      "SOCL"),
    ("internet",            "Internet",               "PNQI"),
    ("computer hardware",   "Computer Hardware",      "XLK"),
    ("data storage",        "Data Storage",           "SOXX"),
    ("electronic gaming",   "Gaming / Esports",       "HERO"),
    ("scientific instruments","Test & Measurement",   "XLK"),
    ("it services",         "IT Services",            "XLK"),
    ("information tech",    "IT Services",            "XLK"),
    ("consulting",          "IT Consulting",          "XLK"),
    # Communication & Media
    ("social media",        "Social Media",           "SOCL"),
    ("interactive media",   "Social Media",           "SOCL"),
    ("entertainment",       "Streaming & Media",      "PBS"),
    ("telecom",             "Telecom",                "IYZ"),
    ("broadcasting",        "Broadcasting / Media",   "PBS"),
    ("publishing",          "Digital Publishing",     "PBS"),
    # Consumer
    ("internet retail",     "E-Commerce",             "ONLN"),
    ("specialty retail",    "Retail",                 "XLY"),
    ("auto manufacturer",   "Auto / EV",              "DRIV"),
    ("restaurant",          "Restaurants",            "BITE"),
    ("travel",              "Travel & Tourism",       "JETS"),
    ("hotel",               "Travel & Tourism",       "JETS"),
    ("airline",             "Airlines",               "JETS"),
    ("luxury",              "Consumer Luxury",        "XLY"),
    # Health Care
    ("biotechnology",       "Biotechnology",          "XBI"),
    ("drug manufacturer",   "Pharma",                 "XPH"),
    ("medical device",      "Medical Devices",        "IHI"),
    ("diagnostics",         "Diagnostics & Research", "IHI"),
    ("health information",  "Health IT",              "XLV"),
    ("genomics",            "Genomics",               "ARKG"),
    ("clinical stage",      "Clinical-Stage Biotech", "XBI"),
    # Financials
    ("asset management",    "Asset Management",       "XLF"),
    ("insurance",           "Insurance",              "KIE"),
    ("bank",                "Banking",                "KRE"),
    ("capital market",      "Capital Markets",        "IAI"),
    ("financial data",      "Fintech",                "FINX"),
    ("payment",             "Digital Payments",       "IPAY"),
    ("mortgage",            "Mortgage / REIT Finance","REM"),
    # Energy
    ("renewable",           "Clean Energy",           "ICLN"),
    ("solar",               "Solar Energy",           "TAN"),
    ("uranium",             "Nuclear / Uranium",      "URA"),
    ("nuclear",             "Nuclear Energy",         "URA"),
    ("oil",                 "Oil & Gas",              "XOP"),
    ("gas",                 "Oil & Gas",              "XOP"),
    ("lng",                 "LNG / Natural Gas",      "FCG"),
    # Industrials
    ("aerospace",           "Aerospace & Defense",    "ITA"),
    ("defense",             "Aerospace & Defense",    "ITA"),
    ("infrastructure",      "Infrastructure",         "PAVE"),
    ("construction",        "Construction",           "PAVE"),
    ("electrical equipment","Electrical Equipment",   "XLI"),
    ("automation",          "Robotics & Automation",  "BOTZ"),
    ("robotics",            "Robotics & Automation",  "BOTZ"),
    # Materials & Commodities
    ("gold",                "Gold / Precious Metals", "GDX"),
    ("silver",              "Silver / Precious Metals","GDX"),
    ("lithium",             "Lithium & Battery Tech", "LIT"),
    ("mining",              "Mining / Metals",        "XME"),
    ("steel",               "Steel / Metals",         "XME"),
    ("copper",              "Copper / Base Metals",   "XME"),
    # Real Estate
    ("reit",                "REITs",                  "VNQ"),
    ("data center",         "Data Center REITs",      "SRVR"),
]

# ── Level-3: niche label from industry ────────────────────────────────────────
NICHE_MAP: list[tuple[str, str]] = [
    ("high bandwidth memory",  "HBM / High-Bandwidth Memory"),
    ("dram",                   "DRAM Memory"),
    ("nand",                   "NAND Flash Storage"),
    ("memory",                 "Memory Chips"),
    ("gpu",                    "GPU / AI Accelerators"),
    ("ai chip",                "AI Chips"),
    ("foundry",                "Chip Foundry (TSMC-type)"),
    ("fabless",                "Fabless Chip Design"),
    ("wafer",                  "Chip Equipment / EDA"),
    ("networking",             "Networking Silicon"),
    ("cybersecurity",          "Cybersecurity / SASE"),
    ("fintech",                "Fintech / Digital Payments"),
    ("autonomous",             "Autonomous Vehicles / AV"),
    ("generative ai",          "Generative AI Infrastructure"),
    ("cloud",                  "Cloud / SaaS"),
    ("genomics",               "Genomics / Precision Medicine"),
    ("space",                  "Space Technology"),
    ("quantum",                "Quantum Computing"),
    ("glp",                    "GLP-1 / Obesity Drugs"),
    ("weight loss",            "GLP-1 / Obesity Drugs"),
    ("electric vehicle",       "Electric Vehicles / EV"),
    ("battery",                "Battery / Energy Storage"),
    ("uranium",                "Uranium / Nuclear"),
    ("esport",                 "Esports / Gaming"),
    ("crypto",                 "Crypto Infrastructure"),
    ("blockchain",             "Blockchain / Web3"),
    ("defi",                   "DeFi / Digital Assets"),
    ("defense contractor",     "Prime Defense Contractor"),
    ("satellite",              "Satellite / Space Comms"),
    ("drone",                  "Drones / UAV"),
]

# ── Level-3b: business-description themes ────────────────────────────────────
# yfinance's 'industry' field is ONE short controlled-vocabulary string (e.g.
# CRDO -> just "Semiconductors"), which is exactly why multi-thematic/niche
# companies get force-fit into a single generic label — a chip company that's
# really an optical/Ethernet connectivity play has nowhere to show that in
# 'industry'. 'longBusinessSummary' is free text but far richer, so it's
# scanned separately (ALL matches kept, not first-match-wins) to surface the
# themes 'industry' alone can't. Deliberately multi-word/specific phrases to
# avoid false hits on generic words.
SUMMARY_THEME_MAP: list[tuple[str, str]] = [
    ("optical transceiver",      "Optical Connectivity"),
    ("ethernet",                 "Networking / Ethernet Silicon"),
    ("serdes",                   "SerDes / High-Speed I/O"),
    ("retimer",                  "Signal Integrity (Retimers/DSPs)"),
    ("active electrical cable",  "High-Speed Interconnect (AEC)"),
    ("pcie",                     "PCIe Connectivity"),
    ("data center interconnect", "Data Center Interconnect"),
    ("hyperscale",               "Hyperscale / AI Data Center"),
    ("artificial intelligence",  "AI Infrastructure"),
    ("machine learning",         "AI / Machine Learning"),
    ("autonomous driving",       "Autonomous Driving"),
    ("gene editing",             "Gene Editing"),
    ("obesity",                  "GLP-1 / Obesity Drugs"),
]


def theme_etf_universe() -> list[str]:
    """Distinct ETF tickers used as sub-sector/theme proxies across
    INDUSTRY_MAP — reused by Weekly Picks as its ETF scan candidate pool
    (so 'what's a strong theme right now' draws from the same ETF set
    already curated for sector-context lookups, not a separate list)."""
    seen: list[str] = []
    for _, _, etf in INDUSTRY_MAP:
        if etf not in seen:
            seen.append(etf)
    return seen


# ── ETF strength helper ────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _etf_strength(ticker: str) -> dict:
    """Returns strength metrics for an ETF/stock used as sector proxy."""
    try:
        df  = get_price_history(ticker, period="1y")
        spy = get_price_history("SPY",    period="1y")
        if df.empty:
            return {}

        c   = df["Close"].squeeze()
        cs  = spy["Close"].squeeze()

        price  = float(c.iloc[-1])
        ma50   = float(c.rolling(50).mean().iloc[-1])  if len(c) >= 50  else price
        ma200  = float(c.rolling(200).mean().iloc[-1]) if len(c) >= 200 else price
        r1w    = float(c.iloc[-1] / c.iloc[-6]  - 1)  if len(c) >= 7   else 0.0
        r1m    = float(c.iloc[-1] / c.iloc[-21] - 1)  if len(c) >= 22  else 0.0
        r3m    = float(c.iloc[-1] / c.iloc[-63] - 1)  if len(c) >= 64  else 0.0
        spy1w  = float(cs.iloc[-1] / cs.iloc[-6]  - 1) if len(cs) >= 7  else 0.0
        spy1m  = float(cs.iloc[-1] / cs.iloc[-21] - 1) if len(cs) >= 22 else 0.0
        rs1w   = r1w - spy1w
        rs1m   = r1m - spy1m

        above_50  = price > ma50
        above_200 = price > ma200

        # Score 1-10
        s = 5.0
        if above_200: s += 1.5
        if above_50:  s += 1.0
        s += min(2.0, max(-2.0, r1m * 10))
        s += min(1.0, max(-1.0, rs1m * 8))
        score = round(max(1.0, min(10.0, s)), 1)

        if score >= 7.5:   grade, gc = "Very Strong 🔥", "#16c784"
        elif score >= 6.0: grade, gc = "Strong ✅",      "#a3e635"
        elif score >= 4.5: grade, gc = "Neutral ⚠",     "#f0b90b"
        else:              grade, gc = "Weak ❌",         "#ea3a44"

        return {
            "ticker":    ticker,
            "price":     price,
            "r1w":       round(r1w * 100, 1),
            "r1m":       round(r1m * 100, 1),
            "r3m":       round(r3m * 100, 1),
            "rs1w":      round(rs1w * 100, 1),
            "rs1m":      round(rs1m * 100, 1),
            "above_50":  above_50,
            "above_200": above_200,
            "score":     score,
            "grade":     grade,
            "grade_color": gc,
        }
    except Exception:
        return {}


# Public name — _etf_strength predates this being called from outside the
# module (Weekly Picks' ETF scan path); alias rather than rename so nothing
# already importing the private name breaks.
etf_strength = _etf_strength


# ── Public API ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def get_sector_context(symbol: str) -> dict:
    """
    Returns 3-level sector context for a stock symbol.
    {
      "level1": {"label": ..., "etf": ..., "strength": {...}},
      "level2": {"label": ..., "etf": ..., "strength": {...}} | None,
      "level3": [{"label": ...}, ...] | None,   # list — can be 1-4 tags
    }
    """
    info     = get_ticker_info(symbol)
    sector   = info.get("sector", "")
    industry = (info.get("industry") or "").lower()
    summary  = (info.get("longBusinessSummary") or "").lower()

    result = {}

    # Level 1 — broad sector
    if sector in SECTOR_ETF:
        lbl, etf = SECTOR_ETF[sector]
        result["level1"] = {
            "label":    lbl,
            "etf":      etf,
            "strength": _etf_strength(etf),
        }
    elif sector:
        result["level1"] = {"label": sector, "etf": None, "strength": {}}

    # Level 2 — sub-sector (first match). Word-boundary match against
    # yfinance's controlled 'industry' string only — no company name here,
    # that field is free text and produces false matches (see level 3 note).
    level1_etf = result.get("level1", {}).get("etf")
    for keyword, sub_lbl, sub_etf in INDUSTRY_MAP:
        if _word_match(keyword, industry):
            # No point showing a "sub-sector" card that's just the broad
            # sector's own ETF again — same numbers, no new information.
            # Some industries genuinely don't have a good dedicated proxy;
            # skip rather than fake one.
            if sub_etf == level1_etf:
                break
            strength = _etf_strength(sub_etf)
            result["level2"] = {
                "label":    sub_lbl,
                "etf":      sub_etf,
                "strength": strength,
            }
            break

    # Level 3 — niche labels (no ETF, just descriptive). Matched against the
    # controlled 'industry' string AND, separately, the free-text business
    # summary — collecting EVERY match (not first-match-wins) instead of
    # collapsing a multi-thematic company (e.g. a "semiconductor" company
    # that's really an optical/Ethernet connectivity play) into one label.
    # Still never matched against the company's free-text NAME — that used
    # to fire on incidental substrings ("space"/"battery"/"gas" appearing in
    # an unrelated company name) and forced a niche label onto stocks it
    # didn't fit. Most stocks legitimately won't have a niche tag — fine,
    # level 3 is optional. Capped so a very wordy summary can't turn into a
    # wall of tags.
    niches: list[str] = []
    for keyword, niche_lbl in NICHE_MAP:
        if _word_match(keyword, industry) and niche_lbl not in niches:
            niches.append(niche_lbl)
    for keyword, niche_lbl in SUMMARY_THEME_MAP:
        if _word_match(keyword, summary) and niche_lbl not in niches:
            niches.append(niche_lbl)
    if niches:
        result["level3"] = [{"label": n} for n in niches[:4]]

    return result


# ── Sector Rotation ───────────────────────────────────────────────────────────

# (label, etf, category) — category powers the grouped bar-chart view.
ROTATION_CATEGORIES = [
    "Broad Sectors", "AI & Compute", "Tech Themes", "Healthcare",
    "Finance & Crypto", "Energy & Power", "Industry & Defense",
    "Consumer & Housing", "Commodities", "Rates & Credit",
    "Geographies", "Styles & Factors",
]

_ROTATION_SECTORS: list[tuple[str, str, str]] = [
    # ── Broad SPDR Sectors ────────────────────────────────────────────────────
    ("Technology",             "XLK",  "Broad Sectors"),
    ("Communication",          "XLC",  "Broad Sectors"),
    ("Consumer Discret.",      "XLY",  "Broad Sectors"),
    ("Consumer Staples",       "XLP",  "Broad Sectors"),
    ("Health Care",            "XLV",  "Broad Sectors"),
    ("Financials",             "XLF",  "Broad Sectors"),
    ("Energy",                 "XLE",  "Broad Sectors"),
    ("Industrials",            "XLI",  "Broad Sectors"),
    ("Materials",              "XLB",  "Broad Sectors"),
    ("Real Estate",            "XLRE", "Broad Sectors"),
    ("Utilities",              "XLU",  "Broad Sectors"),
    # ── AI & Compute (the AI supply chain, layer by layer) ────────────────────
    ("Semiconductors",         "SOXX", "AI & Compute"),
    ("Semis Broad/Liquid",     "SMH",  "AI & Compute"),
    ("Semis Equal-Weight (Memory)", "XSD", "AI & Compute"),
    ("AI & Big Data",          "AIQ",  "AI & Compute"),
    ("AI Broad Index",         "XAIX", "AI & Compute"),
    ("Data Center REITs",      "SRVR", "AI & Compute"),
    ("Grid & Electrification", "GRID", "AI & Compute"),
    ("Cloud Computing",        "WCLD", "AI & Compute"),
    ("Robotics & AI",          "BOTZ", "AI & Compute"),
    ("Quantum Computing",      "QTUM", "AI & Compute"),
    # ── Tech Themes ───────────────────────────────────────────────────────────
    ("Software / SaaS",        "IGV",  "Tech Themes"),
    ("Cybersecurity",          "CIBR", "Tech Themes"),
    ("Internet / Social",      "PNQI", "Tech Themes"),
    ("Gaming & Esports",       "HERO", "Tech Themes"),
    ("Space",                  "ARKX", "Tech Themes"),
    ("Innovation (ARK)",       "ARKK", "Tech Themes"),
    # ── Healthcare ────────────────────────────────────────────────────────────
    ("Biotech",                "XBI",  "Healthcare"),
    ("MedTech Devices",        "IHI",  "Healthcare"),
    ("Genomics",               "ARKG", "Healthcare"),
    ("Pharma (GLP-1 names)",   "XPH",  "Healthcare"),
    ("Obesity / GLP-1",        "OZEM", "Healthcare"),
    # ── Finance & Crypto ──────────────────────────────────────────────────────
    ("Fintech",                "FINX", "Finance & Crypto"),
    ("Digital Payments",       "IPAY", "Finance & Crypto"),
    ("Regional Banks",         "KRE",  "Finance & Crypto"),
    ("Bitcoin",                "IBIT", "Finance & Crypto"),
    ("Blockchain Stocks",      "BLOK", "Finance & Crypto"),
    # ── Energy & Power (the AI-power trade included) ──────────────────────────
    ("Clean Energy",           "ICLN", "Energy & Power"),
    ("Solar Energy",           "TAN",  "Energy & Power"),
    ("Nuclear / Uranium",      "URA",  "Energy & Power"),
    ("Nuclear Renaissance (AI Power)", "NUKZ", "Energy & Power"),
    ("Natural Gas Producers",  "FCG",  "Energy & Power"),
    ("Oil Services",           "OIH",  "Energy & Power"),
    # ── Industry & Defense ────────────────────────────────────────────────────
    ("Aerospace & Defense",    "ITA",  "Industry & Defense"),
    ("Infrastructure",         "PAVE", "Industry & Defense"),
    ("Lithium & EV Battery",   "LIT",  "Industry & Defense"),
    ("Transportation",         "IYT",  "Industry & Defense"),
    ("EU Defense (NATO trade)","EUAD", "Industry & Defense"),
    ("Global Shipping",        "BOAT", "Industry & Defense"),
    # ── Consumer & Housing ────────────────────────────────────────────────────
    ("E-Commerce",             "ONLN", "Consumer & Housing"),
    ("Airlines & Travel",      "JETS", "Consumer & Housing"),
    ("Homebuilders",           "ITB",  "Consumer & Housing"),
    ("Retail",                 "XRT",  "Consumer & Housing"),
    # ── Commodities ───────────────────────────────────────────────────────────
    ("Gold Miners",            "GDX",  "Commodities"),
    ("Silver Miners",          "SIL",  "Commodities"),
    ("Copper Miners",          "COPX", "Commodities"),
    ("Rare Earths",            "REMX", "Commodities"),
    ("Agriculture",            "MOO",  "Commodities"),
    ("Water",                  "PHO",  "Commodities"),
    # ── Rates & Credit (regime reads) ─────────────────────────────────────────
    ("Long Treasuries (20y+)", "TLT",  "Rates & Credit"),
    ("High-Yield Credit",      "HYG",  "Rates & Credit"),
    # ── Geographies ───────────────────────────────────────────────────────────
    ("China Tech",             "KWEB", "Geographies"),
    ("India",                  "INDA", "Geographies"),
    ("Japan",                  "EWJ",  "Geographies"),
    ("Taiwan",                 "EWT",  "Geographies"),
    ("South Korea",            "EWY",  "Geographies"),
    ("Vietnam",                "VNM",  "Geographies"),
    ("Europe",                 "VGK",  "Geographies"),
    ("Brazil",                 "EWZ",  "Geographies"),
    ("Mexico",                 "EWW",  "Geographies"),
    ("Argentina",              "ARGT", "Geographies"),
    ("Latin America",          "ILF",  "Geographies"),
    ("Saudi Arabia",           "KSA",  "Geographies"),
    ("Israel",                 "EIS",  "Geographies"),
    ("Emerging Markets",       "EEM",  "Geographies"),
    ("Germany",                "EWG",  "Geographies"),
    ("United Kingdom",         "EWU",  "Geographies"),
    ("Poland",                 "EPOL", "Geographies"),
    ("Indonesia",              "EIDO", "Geographies"),
    ("Turkey",                 "TUR",  "Geographies"),
    ("Australia",              "EWA",  "Geographies"),
    ("Canada",                 "EWC",  "Geographies"),
    # ── Styles ────────────────────────────────────────────────────────────────
    ("Small Cap Growth",       "IWO",  "Styles & Factors"),
    ("Dividend Growth",        "VIG",  "Styles & Factors"),
    ("Magnificent 7",          "MAGS", "Styles & Factors"),
    ("S&P Equal Weight (Breadth)", "RSP", "Styles & Factors"),
    ("Momentum Factor",        "MTUM", "Styles & Factors"),
    ("Quality Factor",         "QUAL", "Styles & Factors"),
    ("Low Volatility",         "USMV", "Styles & Factors"),
    ("Value Factor",           "VTV",  "Styles & Factors"),
]


def _load_rotation_snapshot() -> dict:
    """{etf: {"rs1m": ..., "date": "YYYY-MM-DD"}} from the last time this ran
    on a *different calendar day* — used to show what moved since the user
    last actually looked, instead of waiting for a full month of RS drift."""
    return load_json(_ROTATION_SNAPSHOT_PATH, default={})


def _save_rotation_snapshot(rot: list[dict]) -> None:
    """Only overwrites the stored snapshot once a new day starts, so the
    'since last check' delta stays meaningful across same-day reruns
    instead of comparing a reading against itself seconds later."""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    prev = _load_rotation_snapshot()
    if prev.get("_date") == today:
        return
    snap = {"_date": today}
    for r in rot:
        snap[r["etf"]] = {"rs1m": r["rs1m"]}
    save_json(_ROTATION_SNAPSHOT_PATH, snap)


@st.cache_data(ttl=1800, show_spinner=False)
def get_sector_rotation() -> list[dict]:
    """
    Returns strength metrics for all rotation sectors, sorted by 1M RS vs SPY
    (best performers first).

    Each dict:
      label, etf, price, r1w, r1m, r3m, rs1w, rs1m, rs3m,
      above_50, above_200, score, grade, grade_color,
      momentum_dir   ("↑" accelerating / "→" stable / "↓" decelerating, 1M vs 3M — slow/confirmed)
      early_signal   ("up" / "down" / None) — 1-week RS breaking away from the 1M trend,
                      the earliest read this data can give before it shows up in momentum_dir
      rs1m_prev_day  previous stored snapshot's RS 1M (None if no prior-day snapshot)
      rs1m_delta     rs1m - rs1m_prev_day (None if no prior-day snapshot)
    """
    prev_snap = _load_rotation_snapshot()
    # Pre-compute SPY 3M return once (reused for every sector)
    try:
        from utils.cache import get_price_history as _gph
        _spy = _gph("SPY", period="1y")
        _sc  = _spy["Close"].squeeze()
        _spy_r3m = float(_sc.iloc[-1] / _sc.iloc[-63] - 1) * 100 if len(_sc) >= 64 else 0.0
    except Exception:
        _sc, _spy_r3m = None, 0.0

    results = []
    for label, etf, category in _ROTATION_SECTORS:
        s = _etf_strength(etf)
        if not s:
            continue

        rs1w = s.get("rs1w", 0)
        rs1m = s.get("rs1m", 0)

        # 3M RS vs SPY
        try:
            from utils.cache import get_price_history as _gph
            etf_ph = _gph(etf, period="1y")
            if not etf_ph.empty:
                ec = etf_ph["Close"].squeeze()
                rs3m_etf = float(ec.iloc[-1] / ec.iloc[-63] - 1) * 100 if len(ec) >= 64 else 0
                rs3m = rs3m_etf - _spy_r3m
            else:
                rs3m = 0.0
        except Exception:
            rs3m = 0.0

        # Momentum direction: 1M RS improving vs 3M RS baseline — a slow,
        # already-confirmed read (needs a full month of drift to move).
        if rs1m > rs3m + 2:
            mom_dir = "↑"
        elif rs1m < rs3m - 2:
            mom_dir = "↓"
        else:
            mom_dir = "→"

        # Early-turn signal: the latest WEEK's RS breaking away from the 1M
        # trend — catches a rotation starting days before it's big enough
        # to move the 1M-vs-3M momentum_dir above. Purely a leading heads-up,
        # not a confirmed call.
        early = None
        if rs1w > rs1m + 4:
            early = "up"
        elif rs1w < rs1m - 4:
            early = "down"

        prev = prev_snap.get(etf)
        rs1m_prev_day = prev.get("rs1m") if prev else None
        rs1m_delta = round(rs1m - rs1m_prev_day, 1) if rs1m_prev_day is not None else None

        results.append({
            "label":         label,
            "etf":           etf,
            "category":      category,
            "price":         s.get("price"),
            "r1w":           s.get("r1w", 0),
            "r1m":           s.get("r1m", 0),
            "r3m":           s.get("r3m", 0),
            "rs1w":          round(rs1w, 1),
            "rs1m":          round(rs1m, 1),
            "rs3m":          round(rs3m, 1),
            "above_50":      s.get("above_50", False),
            "above_200":     s.get("above_200", False),
            "score":         s.get("score", 5.0),
            "grade":         s.get("grade", "Neutral ⚠"),
            "grade_color":   s.get("grade_color", "#f0b90b"),
            "momentum_dir":  mom_dir,
            "early_signal":  early,
            "rs1m_prev_day": rs1m_prev_day,
            "rs1m_delta":    rs1m_delta,
        })

    sorted_results = sorted(results, key=lambda x: x["rs1m"], reverse=True)
    _save_rotation_snapshot(sorted_results)
    return sorted_results
