import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Keys ───────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
FRED_API_KEY      = os.getenv("FRED_API_KEY", "")       # free at fred.stlouisfed.org
FINNHUB_API_KEY   = os.getenv("FINNHUB_API_KEY", "")    # free at finnhub.io
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")  # free at alphavantage.co (25 req/day)
FMP_API_KEY       = os.getenv("FMP_API_KEY", "")        # free at financialmodelingprep.com (250 req/day)

# ─── Scoring Weights ─────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "fundamental": 0.30,
    "technical":   0.20,
    "momentum":    0.15,
    "smart_money": 0.15,
    "macro":       0.10,
    "relative":    0.10,
}

SCORE_LABELS = {
    (8.5, 10):  ("Strong Buy",  "#00c853"),
    (7.0, 8.5): ("Buy",         "#64dd17"),
    (5.0, 7.0): ("Hold",        "#ffd600"),
    (3.5, 5.0): ("Watch",       "#ff6d00"),
    (0,   3.5): ("Avoid",       "#d50000"),
}

# ─── Central Color Palette ────────────────────────────────────────────────────
# Single source of truth for UI colors. Use in all NEW code; legacy hardcoded
# hex values are identical and will be migrated incrementally.
COLORS = {
    "pos":       "#16c784",   # positive / bullish / green
    "neg":       "#ea3a44",   # negative / bearish / red
    "neutral":   "#f0b90b",   # neutral / hold / amber
    "pos_soft":  "#a3e635",   # mild positive (e.g. "Buy" tier)
    "warn":      "#f97316",   # warning / trim
    "muted":     "#556070",   # secondary text / no-data
    "text":      "#e8edf8",   # primary text
    "text_soft": "#8a9bc2",   # softer body text
    "accent":    "#4da3ff",   # links / primary line color
    "bg_card":   "#161b27",   # card background
    "bg_panel":  "#1c2333",   # panel background
    "bg_chart":  "#131722",   # chart paper background
    "border":    "#2a3348",   # card/panel borders
    "grid":      "#1e2535",   # chart gridlines
}

# ─── Expert Investor Profiles ─────────────────────────────────────────────────
EXPERTS = {
    "Cathie": {
        "icon": "🚀",
        "title": "Cathie — Disruptive Tech",
        "style": "ARK Invest style. Focuses on disruptive innovation, 5-year TAM expansion, S-curve adoption, genomics/AI/robotics. Ignores near-term profitability if the platform opportunity is massive.",
    },
    "Leopold": {
        "icon": "🧠",
        "title": "Leopold — AI-Native Rising Star",
        "style": "Next-generation AI investor. Hunts for under-the-radar companies with AI moat, compute leverage, high NRR, and network effects before they become consensus. Think pre-hype Nvidia or Micron.",
    },
    "Jensen": {
        "icon": "⚡",
        "title": "Jensen — Mega-Cap Platform Allocator",
        "style": "Nvidia/Google-style thinking. Focuses on platform dominance, ecosystem lock-in, ROIC, and reinvestment rate. Backs companies that can compound at scale for 10+ years.",
    },
    "Ray": {
        "icon": "🌍",
        "title": "Ray — Global Macro Overlay",
        "style": "All-Weather macro investor. Evaluates every asset through the lens of interest rates, dollar strength, inflation cycle, geopolitical risk, and global capital flows. Recommends hedges when needed.",
    },
    "Peter": {
        "icon": "📊",
        "title": "Peter — GARP Pragmatist",
        "style": "Growth at a Reasonable Price. Uses PEG ratio, Rule of 40, earnings surprise history, and sector cycle positioning. Balances upside with valuation discipline. Sets clear entry price targets.",
    },
    "Michael": {
        "icon": "🐻",
        "title": "Michael — Devil's Advocate",
        "style": "Short-seller mindset. Hunts for overvalued narratives, flawed unit economics, eroding moats, and accounting red flags. Prone to SELL or WATCH — never buys on story alone. Always asks: what's the bear case the bulls are ignoring? Cites valuation multiples, burn rate, or competitive threats.",
    },
    "Charlie": {
        "icon": "🏰",
        "title": "Charlie — Fortress Value",
        "style": "Munger/Buffett-style deep value. Demands durable competitive moat, pricing power, high ROIC, and margin of safety before buying. Highly skeptical of negative FCF and elevated P/S ratios. Prefers boring compounders to exciting speculative plays. Will pass on most growth stocks unless the moat is undeniable.",
    },
    "Stanley": {
        "icon": "⚖️",
        "title": "Stanley — Asymmetry Hunter",
        "style": "Druckenmiller-inspired. Obsesses over risk/reward asymmetry — max upside must be at least 2.5× max downside. Sizes positions by conviction × asymmetry. Thinks about opportunity cost: is this the single best use of capital right now? Sets tight stops and large targets.",
    },
}

# ─── Peer groups for common tickers ──────────────────────────────────────────
PEER_GROUPS = {
    # ── Mega-cap tech ──────────────────────────────────────────────────────────
    "NVDA": ["AMD", "INTC", "AVGO", "QCOM", "TSM"],
    "AAPL": ["MSFT", "GOOGL", "META", "AMZN", "TSLA"],
    "MSFT": ["AAPL", "GOOGL", "AMZN", "CRM", "NOW"],
    "GOOGL": ["META", "MSFT", "AMZN", "SNAP", "TTD"],
    "AMZN": ["MSFT", "GOOGL", "SHOP", "WMT", "BABA"],
    "TSLA": ["RIVN", "LCID", "NIO", "GM", "F"],
    "META": ["GOOGL", "SNAP", "PINS", "TTD", "SPOT"],
    "AVGO": ["NVDA", "AMD", "QCOM", "MRVL", "INTC"],
    # ── Semiconductors ────────────────────────────────────────────────────────
    "AMD": ["NVDA", "INTC", "AVGO", "QCOM", "MRVL"],
    "ARM":  ["NVDA", "AMD", "QCOM", "AVGO", "MRVL"],
    "MU":   ["WDC", "STX", "LRCX", "KLAC", "AMAT"],
    "MRVL": ["AVGO", "QCOM", "AMD", "NVDA", "INTC"],
    "QCOM": ["NVDA", "AMD", "AVGO", "MRVL", "ARM"],
    "TSM":  ["INTC", "SSNC", "UMC", "GFS", "AMAT"],
    "AMAT": ["LRCX", "KLAC", "ASML", "TER", "MU"],
    # ── AI Infrastructure & Data ──────────────────────────────────────────────
    "PLTR": ["AI", "BBAI", "SNOW", "DDOG", "MSFT"],
    "DELL": ["HPE", "SMCI", "NTAP", "PSTG", "IBM"],
    "ORCL": ["CRM", "NOW", "WDAY", "SAP", "MSFT"],
    "ANET": ["CSCO", "JNPR", "HPE", "NTAP", "PALO"],
    "SMCI": ["DELL", "HPE", "NTAP", "PSTG", "IBM"],
    # ── Growth Software / Cloud / Security ────────────────────────────────────
    "CRWD": ["ZS", "PANW", "FTNT", "S", "NET"],
    "DDOG": ["NEWR", "DT", "ESTC", "SPLK", "SNOW"],
    "NET":  ["ZS", "PANW", "CRWD", "AKAM", "FSLY"],
    "SNOW": ["DDOG", "MDB", "ESTC", "PLTR", "CRM"],
    "APP":  ["TTD", "MGNI", "DV", "PUBM", "GOOGL"],
    "AXON": ["MSA", "TASER", "GEN", "MOTS", "SFPD"],
    "ZS":   ["PANW", "CRWD", "FTNT", "NET", "OKTA"],
    "GTLB": ["TEAM", "MSFT", "NOW", "JFROG", "DDOG"],
    "CRM":  ["NOW", "WDAY", "ORCL", "SAP", "MSFT"],
    "NOW":  ["CRM", "WDAY", "ORCL", "SAP", "MSFT"],
    "WDAY": ["CRM", "NOW", "ORCL", "SAP", "DAY"],
    # ── Consumer / Social / Ad-Tech ───────────────────────────────────────────
    "RDDT": ["META", "SNAP", "PINS", "YELP", "IAC"],
    "SPOT": ["AAPL", "GOOGL", "AMZN", "PANDORA", "SXM"],
    "PINS": ["META", "SNAP", "RDDT", "GOOGL", "TTD"],
    "TTD":  ["MGNI", "DV", "PUBM", "APP", "GOOGL"],
    "SHOP": ["BIGC", "WIX", "AMZN", "SQ", "MELI"],
    # ── Fintech / Crypto ──────────────────────────────────────────────────────
    "COIN": ["HOOD", "MSTR", "RIOT", "MARA", "SQ"],
    "SQ":   ["PYPL", "ADYEY", "AFRM", "GLOB", "HOOD"],
    "HOOD": ["SCHW", "IBKR", "AMTD", "COIN", "SQ"],
    # ── Health / BioGrowth ────────────────────────────────────────────────────
    "HIMS": ["TEVA", "GDRX", "DOCS", "CLOV", "ACCD"],
    "CELH": ["MNST", "KDP", "PEP", "FIZZ", "NVS"],
    # ── Space / Deep-Tech ─────────────────────────────────────────────────────
    "RKLB": ["SPCE", "LMT", "RTX", "BA", "NOC"],
    "IONQ": ["RGTI", "QUBT", "IBM", "GOOGL", "MSFT"],
    # ── IT Services / Consulting ──────────────────────────────────────────────
    "ACN":  ["IBM", "INFY", "WIT", "CTSH", "IT"],
    "IBM":  ["ACN", "INFY", "CTSH", "HPE", "DXC"],
    "INFY": ["WIT", "ACN", "CTSH", "HCL", "TCS"],
    "CTSH": ["INFY", "WIT", "ACN", "IBM", "EPAM"],
    "EPAM": ["CTSH", "GLOB", "FLUT", "ACN", "IBM"],
    "IT":   ["ACN", "IBM", "VRSK", "SAIC", "CACI"],
    # ── Traditional Enterprise Software ──────────────────────────────────────
    "SAP":  ["ORCL", "CRM", "NOW", "WDAY", "MSFT"],
    "ADBE": ["CRM", "MSFT", "FIGM", "CANV", "NOW"],
    "INTU": ["ADBE", "CRM", "HRB", "PAYX", "ADP"],
    # ── E-Commerce / Marketplace ──────────────────────────────────────────────
    "MELI": ["SHOP", "AMZN", "BABA", "JD", "SE"],
    "SE":   ["MELI", "GRAB", "BABA", "JD", "SHOP"],
    "JD":   ["BABA", "MELI", "AMZN", "SE", "PDD"],
    # ── Payments / Processing ─────────────────────────────────────────────────
    "PYPL": ["SQ", "V", "MA", "ADYEY", "AFRM"],
    "V":    ["MA", "PYPL", "AXP", "DFS", "SQ"],
    "MA":   ["V", "PYPL", "AXP", "DFS", "SQ"],
    "AXP":  ["V", "MA", "DFS", "COF", "PYPL"],
    # ── Cloud Infrastructure ──────────────────────────────────────────────────
    "MSCI": ["SPGI", "ICE", "CME", "MORN", "VRT"],
    "SPGI": ["MSCI", "ICE", "MCO", "MORN", "FDS"],
    # ── Streaming / Media ─────────────────────────────────────────────────────
    "NFLX": ["DIS", "WBD", "PARA", "AMZN", "AAPL"],
    "DIS":  ["NFLX", "WBD", "PARA", "CMCSA", "LGF"],
    # ── Semiconductors (extended) ─────────────────────────────────────────────
    "INTC": ["AMD", "NVDA", "AVGO", "TSM", "QCOM"],
    "KLAC": ["AMAT", "LRCX", "ASML", "TER", "NVDA"],
    "LRCX": ["AMAT", "KLAC", "ASML", "TER", "MU"],
    "ASML": ["AMAT", "LRCX", "KLAC", "TER", "TSM"],
    # ── Healthcare / Pharma / MedTech ────────────────────────────────────────
    "LLY":  ["NVO", "PFE", "MRK", "ABBV", "BMY"],
    "NVO":  ["LLY", "SGEN", "ABBV", "PFE", "MRK"],
    "ABBV": ["PFE", "LLY", "MRK", "BMY", "JNJ"],
    "ISRG": ["SYK", "MDT", "BSX", "ZBH", "ALGN"],
    # ── EV / Autos ────────────────────────────────────────────────────────────
    "RIVN": ["LCID", "NIO", "TSLA", "GM", "F"],
    "NIO":  ["XPEV", "LI", "TSLA", "RIVN", "BYD"],
    # ── Industrial / Defense ─────────────────────────────────────────────────
    "LMT":  ["RTX", "NOC", "GD", "BA", "L3HT"],
    "RTX":  ["LMT", "NOC", "GD", "BA", "HII"],
    # ── REITs ────────────────────────────────────────────────────────────────
    "AMT":  ["CCI", "SBAC", "EQIX", "DLR", "PLD"],
    "EQIX": ["DLR", "AMT", "CCI", "IRM", "CONE"],
}

# ─── Sector ETF Map ───────────────────────────────────────────────────────────
SECTOR_ETFS = {
    "Technology":     "XLK",
    "Communication":  "XLC",
    "Consumer Disc":  "XLY",
    "Healthcare":     "XLV",
    "Financials":     "XLF",
    "Energy":         "XLE",
    "Industrials":    "XLI",
    "Materials":      "XLB",
    "Real Estate":    "XLRE",
    "Utilities":      "XLU",
    "Semiconductors": "SOXX",
    "AI/Cloud":       "WCLD",
    "China Tech":     "KWEB",
    "Global":         "VT",
}

# ─── Market Radar Watchlist (under-the-radar candidates) ─────────────────────
RADAR_TICKERS = [
    "MU", "ARM", "CRDO", "SMCI", "MRVL",       # Semiconductors
    "AXON", "DDOG", "NET", "SNOW", "GTLB",      # Cloud/Software
    "CELH", "HIMS", "RDDT", "APP", "TTD",       # Emerging growth
    "KWEB", "CQQQ", "FXI",                       # China tech ETFs
    "SOXX", "SMH", "WCLD", "ARKK", "QQQ",       # Sector ETFs
]

# ─── Weekly Auto-Universe — comprehensive scan across all major themes ────────
# 223 liquid stocks across every major investment theme.
# First 30 = "anchor" — always scanned every week.
# Remaining 193 = "rotating pool" — 30 sampled per week (deterministic by calendar week).
# Full universe cycles in ~6 weeks → fresh opportunities surface every week.
WEEKLY_UNIVERSE = [
    # ════════════════════════════════════════════════════════════════════════
    # ANCHOR — always scanned (first 30)
    # ════════════════════════════════════════════════════════════════════════
    # Mega-cap AI / Platforms
    "NVDA", "MSFT", "AAPL", "META", "GOOGL", "AMZN", "TSLA", "AVGO",
    # Semiconductors (core)
    "AMD", "ARM", "MU", "MRVL", "AMAT",
    # AI Infrastructure
    "PLTR", "ORCL", "ANET",
    # Growth Security / Software
    "CRWD", "DDOG", "NET", "APP",
    # Healthcare (GLP-1 era)
    "LLY", "NVO",
    # Financials (payments)
    "V", "MA", "JPM",

    # ════════════════════════════════════════════════════════════════════════
    # ROTATING POOL — ~170 stocks, 30 sampled per week
    # ════════════════════════════════════════════════════════════════════════

    # ── SEMICONDUCTORS (extended) ────────────────────────────────────────────
    "QCOM", "TSM", "INTC", "KLAC", "LRCX", "ASML", "TER", "ON",
    "MCHP", "NXPI", "ADI", "TXN", "MPWR", "WOLF", "SMCI",

    # ── AI / CLOUD INFRASTRUCTURE ─────────────────────────────────────────────
    "DELL", "SNOW", "GTLB", "CRM", "NOW", "WDAY", "ADBE", "INTU",
    "HUBS", "BILL", "DOCN", "ESTC", "MDB", "CFLT", "DT",

    # ── CYBERSECURITY ─────────────────────────────────────────────────────────
    "AXON", "ZS", "PANW", "FTNT", "S", "OKTA", "CYBR", "QLYS",

    # ── CONSUMER INTERNET / SOCIAL / AD-TECH ──────────────────────────────────
    "RDDT", "SPOT", "PINS", "TTD", "SHOP", "DUOL", "U",
    "LYFT", "UBER", "ABNB",

    # ── FINTECH / PAYMENTS / CRYPTO ───────────────────────────────────────────
    "COIN", "SQ", "HOOD", "PYPL", "NU", "AFRM", "UPST", "SOFI",
    "MSTR", "RIOT", "MARA", "IBKR", "SCHW",

    # ── HEALTHCARE / BIOTECH / MEDTECH ────────────────────────────────────────
    "ISRG", "ABBV", "REGN", "VRTX", "DXCM", "HIMS", "CELH",
    "MRNA", "BMRN", "EXAS", "NTRA", "TMDX", "RXRX",
    "MDT", "BSX", "SYK", "EW", "ALGN",

    # ── CONSUMER DISCRETIONARY / BRANDS ───────────────────────────────────────
    "COST", "MCD", "SBUX", "NKE", "LULU", "CAVA", "CMG",
    "WINGSTOP", "DPZ", "YUM", "RCL", "HLT", "MAR",

    # ── DEFENSE / AEROSPACE / INDUSTRIALS ─────────────────────────────────────
    "LMT", "RTX", "NOC", "GD", "BA", "HII",
    "GE", "ETN", "HON", "CAT", "DE", "ITW", "CARR", "OTIS",
    "RKLB", "ASTS", "LUNR",

    # ── ENERGY (Traditional + Transition) ─────────────────────────────────────
    "XOM", "CVX", "COP", "SLB", "OXY", "EOG", "FANG", "DVN",
    "WMB", "KMI", "PSX",

    # ── CLEAN ENERGY / NUCLEAR / SOLAR ────────────────────────────────────────
    "NEE", "ENPH", "FSLR", "SEDG", "RUN",
    "CEG", "VST", "CCJ", "SMR", "OKLO", "NNE",

    # ── FINANCIALS / BANKS / INSURANCE ────────────────────────────────────────
    "AXP", "GS", "MS", "BAC", "WFC", "COF", "DFS",
    "BLK", "APO", "KKR", "BX", "MSCI", "ICE", "SPGI",
    "PGR", "CB", "MET",

    # ── REAL ESTATE / INFRASTRUCTURE / REITS ──────────────────────────────────
    "EQIX", "AMT", "PLD", "CCI", "DLR", "IRM",
    "VICI", "O", "PSA", "EXR",

    # ── MATERIALS / COMMODITIES / MINING ──────────────────────────────────────
    "FCX", "NEM", "GOLD", "AEM", "WPM",
    "LIN", "APD", "ALB", "SQM", "MP",

    # ── GLOBAL GROWTH / INTERNATIONAL ADRs ────────────────────────────────────
    "MELI", "SE", "BABA", "JD", "PDD",
    "GRAB", "WDS", "SAP",

    # ── QUANTUM / DEEP-TECH / FRONTIER ────────────────────────────────────────
    "IONQ", "RGTI", "QUBT",

    # ── MEDIA / STREAMING / GAMING ────────────────────────────────────────────
    "NFLX", "DIS", "WBD", "PARA", "SONY",
    "EA", "TTWO", "RBLX", "DKNG",

    # ── HEALTH INSURANCE / MANAGED CARE ───────────────────────────────────────
    "UNH", "CVS", "CI", "ELV", "CNC",

    # ── CONSUMER STAPLES / DEFENSIVE ──────────────────────────────────────────
    "PG", "KO", "PEP", "MDLZ", "GIS",
]
