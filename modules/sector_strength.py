"""
Sector Strength — computes a 3-level sector hierarchy for any stock:
  Level 1: Broad sector (Technology, Health Care, …)         → XLK, XLV, …
  Level 2: Sub-sector (Semiconductors, Biotech, Fintech, …)  → SOXX, XBI, FINX, …
  Level 3: Niche label derived from industry string          → "Memory Chips", "AI Accelerators", …

For each level, computes:
  - 1M / 3M return
  - Above MA50 / MA200
  - Relative Strength vs SPY (1M)
  - Strength score 1-10

All results are cached for 30 minutes.
"""
import numpy as np
import streamlit as st
from utils.cache import get_ticker_info, get_price_history


# ── Level-1: broad sector → ETF ───────────────────────────────────────────────
SECTOR_ETF: dict[str, tuple[str, str]] = {
    "Technology":             ("Technology",          "XLK"),
    "Communication Services": ("Communication",       "XLC"),
    "Consumer Discretionary": ("Consumer Discret.",   "XLY"),
    "Consumer Staples":       ("Consumer Staples",    "XLP"),
    "Health Care":            ("Health Care",         "XLV"),
    "Financials":             ("Financials",          "XLF"),
    "Energy":                 ("Energy",              "XLE"),
    "Industrials":            ("Industrials",         "XLI"),
    "Materials":              ("Materials",           "XLB"),
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
    ("entertainment",       "Streaming & Media",      "XLC"),
    ("telecom",             "Telecom",                "IYZ"),
    ("broadcasting",        "Broadcasting / Media",   "XLC"),
    ("publishing",          "Digital Publishing",     "XLC"),
    # Consumer
    ("internet retail",     "E-Commerce",             "ONLN"),
    ("specialty retail",    "Retail",                 "XLY"),
    ("auto manufacturer",   "Auto / EV",              "DRIV"),
    ("restaurant",          "Restaurants",            "XLY"),
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
    ("capital market",      "Capital Markets",        "XLF"),
    ("financial data",      "Fintech",                "FINX"),
    ("payment",             "Digital Payments",       "IPAY"),
    ("mortgage",            "Mortgage / REIT Finance","XLRE"),
    # Energy
    ("renewable",           "Clean Energy",           "ICLN"),
    ("solar",               "Solar Energy",           "TAN"),
    ("uranium",             "Nuclear / Uranium",      "URA"),
    ("nuclear",             "Nuclear Energy",         "URA"),
    ("oil",                 "Oil & Gas",              "XLE"),
    ("gas",                 "Oil & Gas",              "XLE"),
    ("lng",                 "LNG / Natural Gas",      "XLE"),
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
    ("reit",                "REITs",                  "XLRE"),
    ("data center",         "Data Center REITs",      "XLRE"),
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
        r1m    = float(c.iloc[-1] / c.iloc[-21] - 1)  if len(c) >= 22  else 0.0
        r3m    = float(c.iloc[-1] / c.iloc[-63] - 1)  if len(c) >= 64  else 0.0
        spy1m  = float(cs.iloc[-1] / cs.iloc[-21] - 1) if len(cs) >= 22 else 0.0
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
            "r1m":       round(r1m * 100, 1),
            "r3m":       round(r3m * 100, 1),
            "rs1m":      round(rs1m * 100, 1),
            "above_50":  above_50,
            "above_200": above_200,
            "score":     score,
            "grade":     grade,
            "grade_color": gc,
        }
    except Exception:
        return {}


# ── Public API ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def get_sector_context(symbol: str) -> dict:
    """
    Returns 3-level sector context for a stock symbol.
    {
      "level1": {"label": ..., "etf": ..., "strength": {...}},
      "level2": {"label": ..., "etf": ..., "strength": {...}} | None,
      "level3": {"label": ...} | None,
    }
    """
    info     = get_ticker_info(symbol)
    sector   = info.get("sector", "")
    industry = (info.get("industry") or "").lower()

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

    # Level 2 — sub-sector (first match)
    for keyword, sub_lbl, sub_etf in INDUSTRY_MAP:
        if keyword.lower() in industry:
            strength = _etf_strength(sub_etf)
            result["level2"] = {
                "label":    sub_lbl,
                "etf":      sub_etf,
                "strength": strength,
            }
            break

    # Level 3 — niche label (no ETF, just descriptive)
    long_name = (info.get("longName") or info.get("shortName") or "").lower()
    search_str = industry + " " + long_name
    for keyword, niche_lbl in NICHE_MAP:
        if keyword.lower() in search_str:
            result["level3"] = {"label": niche_lbl}
            break

    return result


# ── Sector Rotation ───────────────────────────────────────────────────────────

# All 11 SPDR broad sectors + thematic sub-sectors for rotation view
_ROTATION_SECTORS: list[tuple[str, str]] = [
    # ── Broad SPDR Sectors ────────────────────────────────────────────────────
    ("Technology",             "XLK"),
    ("Communication",          "XLC"),
    ("Consumer Discret.",      "XLY"),
    ("Consumer Staples",       "XLP"),
    ("Health Care",            "XLV"),
    ("Financials",             "XLF"),
    ("Energy",                 "XLE"),
    ("Industrials",            "XLI"),
    ("Materials",              "XLB"),
    ("Real Estate",            "XLRE"),
    ("Utilities",              "XLU"),
    # ── AI & Tech Themes ──────────────────────────────────────────────────────
    ("Semiconductors",         "SOXX"),
    ("Software / SaaS",        "IGV"),
    ("Cloud Computing",        "WCLD"),
    ("Cybersecurity",          "CIBR"),
    ("Robotics & AI",          "BOTZ"),
    ("Internet / Social",      "PNQI"),
    ("Gaming & Esports",       "HERO"),
    # ── Healthcare Themes ─────────────────────────────────────────────────────
    ("Biotech",                "XBI"),
    ("MedTech Devices",        "IHI"),
    ("Genomics",               "ARKG"),
    ("Pharma",                 "XPH"),
    # ── Finance & Payments ────────────────────────────────────────────────────
    ("Fintech",                "FINX"),
    ("Digital Payments",       "IPAY"),
    ("Regional Banks",         "KRE"),
    ("Bitcoin / Crypto",       "IBIT"),
    # ── Energy Transition ─────────────────────────────────────────────────────
    ("Clean Energy",           "ICLN"),
    ("Solar Energy",           "TAN"),
    ("Nuclear / Uranium",      "URA"),
    # ── Industrials & Defense ─────────────────────────────────────────────────
    ("Aerospace & Defense",    "ITA"),
    ("Infrastructure",         "PAVE"),
    ("Lithium & EV Battery",   "LIT"),
    # ── Consumer & Macro ──────────────────────────────────────────────────────
    ("E-Commerce",             "ONLN"),
    ("Airlines & Travel",      "JETS"),
    # ── Frontier Tech ─────────────────────────────────────────────────────────
    ("Space",                  "ARKX"),
    ("Quantum Computing",      "QTUM"),
    ("Innovation (ARK)",       "ARKK"),
    # ── Housing, Transport & Consumer ────────────────────────────────────────
    ("Homebuilders",           "ITB"),
    ("Retail",                 "XRT"),
    ("Transportation",         "IYT"),
    # ── Commodities & Resources ───────────────────────────────────────────────
    ("Oil Services",           "OIH"),
    ("Copper Miners",          "COPX"),
    ("Agriculture",            "MOO"),
    ("Water",                  "PHO"),
    # ── Global & Commodities ──────────────────────────────────────────────────
    ("Gold Miners",            "GDX"),
    ("China Tech",             "KWEB"),
    ("India",                  "INDA"),
    ("Japan",                  "EWJ"),
    ("Europe",                 "VGK"),
    ("Emerging Markets",       "EEM"),
    ("Israel",                 "EIS"),
    # ── Styles ────────────────────────────────────────────────────────────────
    ("Small Cap Growth",       "IWO"),
    ("Dividend Growth",        "VIG"),
]


@st.cache_data(ttl=1800, show_spinner=False)
def get_sector_rotation() -> list[dict]:
    """
    Returns strength metrics for all rotation sectors, sorted by 1M RS vs SPY
    (best performers first).

    Each dict:
      label, etf, price, r1w, r1m, r3m, rs1m, rs3m,
      above_50, above_200, score, grade, grade_color,
      momentum_dir  ("↑" accelerating / "→" stable / "↓" decelerating)
    """
    # Pre-compute SPY 3M return once (reused for every sector)
    try:
        from utils.cache import get_price_history as _gph
        _spy = _gph("SPY", period="1y")
        _sc  = _spy["Close"].squeeze()
        _spy_r3m = float(_sc.iloc[-1] / _sc.iloc[-63] - 1) * 100 if len(_sc) >= 64 else 0.0
    except Exception:
        _sc, _spy_r3m = None, 0.0

    results = []
    for label, etf in _ROTATION_SECTORS:
        s = _etf_strength(etf)
        if not s:
            continue

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

        # Momentum direction: 1M RS improving vs 3M RS baseline
        if rs1m > rs3m + 2:
            mom_dir = "↑"
        elif rs1m < rs3m - 2:
            mom_dir = "↓"
        else:
            mom_dir = "→"

        results.append({
            "label":        label,
            "etf":          etf,
            "price":        s.get("price"),
            "r1m":          s.get("r1m", 0),
            "r3m":          s.get("r3m", 0),
            "rs1m":         round(rs1m, 1),
            "rs3m":         round(rs3m, 1),
            "above_50":     s.get("above_50", False),
            "above_200":    s.get("above_200", False),
            "score":        s.get("score", 5.0),
            "grade":        s.get("grade", "Neutral ⚠"),
            "grade_color":  s.get("grade_color", "#f0b90b"),
            "momentum_dir": mom_dir,
        })

    return sorted(results, key=lambda x: x["rs1m"], reverse=True)
