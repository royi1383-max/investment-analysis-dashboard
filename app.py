"""
Investment Analysis Dashboard
Growth-focused stock & ETF research tool.
"""
import html as _html
import json
from pathlib import Path
from datetime import datetime, date as _date
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
import plotly.express as px
from plotly.subplots import make_subplots

from config import SCORE_LABELS, SCORE_WEIGHTS, RADAR_TICKERS, SECTOR_ETFS, ANTHROPIC_API_KEY, WEEKLY_UNIVERSE
from utils.cache import get_ticker_info, get_price_history, parallel_map, search_tickers
import utils.indicators as mod_ind
import modules.fundamental  as mod_fund
import modules.technical    as mod_tech
import modules.momentum     as mod_mom
import modules.institutional as mod_inst
import modules.macro_geo    as mod_macro
import modules.sector_compare as mod_sector
import modules.scoring      as mod_scoring
import modules.expert_panel as mod_experts
import modules.portfolio    as mod_portfolio
import modules.historical    as mod_hist
import modules.ai_screener   as mod_screen
import modules.market_health    as mod_mhealth
import modules.finnhub_data     as mod_finnhub
import modules.news_sources     as mod_news
import modules.portfolio_health as mod_phealth
import modules.weekly_picks     as mod_weekly
import modules.sector_strength  as mod_sector_str
import modules.earnings         as mod_earnings
import modules.risk_metrics     as mod_risk
import modules.macro_impact     as mod_macro_impact
import modules.etf_holdings     as mod_etf
import modules.seasonality      as mod_seasonal
import modules.sec_13f          as mod_13f
import modules.backtester       as mod_bt
import modules.paper_portfolio  as mod_pp
import modules.tracked_portfolio as mod_tp
import modules.dcf              as mod_dcf
import modules.fund_models      as mod_fm
import modules.excel_export     as mod_xlsx
import modules.risk_tools       as mod_rt
import modules.earnings_quality as mod_eq
import modules.metric_context   as mod_mctx
import modules.glossary         as mod_gloss
import modules.market_valuation as mod_mval
import modules.score_history    as mod_shist
import modules.briefing         as mod_brief
import modules.opportunity      as mod_opp
import modules.alpha_vantage    as mod_av
import modules.fmp              as mod_fmp
import modules.score_validation as mod_sv
import modules.trading_psychology as mod_psych
import modules.options_pricing   as mod_opt
import modules.portfolio_optimizer as mod_popt
from modules.historical import METRICS_CATALOG
from config import FINNHUB_API_KEY

# ─── Disk cache for Weekly Picks (survives app restarts) ─────────────────────
_WP_CACHE = Path(__file__).parent / ".wp_cache.json"
_WP_MAX_AGE_HOURS = 12   # results expire after 12 hours


from utils.persist import load_json as _load_json, save_json as _save_json


def _wp_save(output: dict) -> None:
    _save_json(_WP_CACHE, {"ts": datetime.now().isoformat(), "data": output}, indent=None)


def _wp_load() -> dict | None:
    """Load cached results if they exist and are fresh."""
    try:
        payload = _load_json(_WP_CACHE)
        if not payload:
            return None
        ts  = datetime.fromisoformat(payload["ts"])
        age = (datetime.now() - ts).total_seconds() / 3600
        if age > _WP_MAX_AGE_HOURS:
            return None
        data = payload["data"]
        data["_cached_at"] = ts.strftime("%d/%m/%Y %H:%M")
        data["_cached_age_h"] = round(age, 1)
        return data
    except Exception:
        return None


# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="📈 Stock Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/icon?family=Material+Icons');

/* ── SCANR Terminal tokens ── */
:root {
  --bg:      #131722;
  --bg2:     #161c2c;
  --panel:   #1c2333;
  --panel2:  #222b3d;
  --border:  #2a3348;
  --border2: #374461;
  --text:    #e8edf8;
  --dim:     #8a9bc2;
  --mute:    #556070;
  --accent:  #16c784;
  --amber:   #f0b90b;
  --up:      #16c784;
  --down:    #ea3a44;
  --mono:    'IBM Plex Mono', monospace;
  --sans:    'IBM Plex Sans', system-ui, sans-serif;
}

/* ── base — ONLY text content areas, never buttons ── */
p, label, input, select, textarea, th, td, li,
[data-testid="stMarkdownContainer"] *,
[data-testid="stText"],
[data-testid="stCaptionContainer"],
[data-testid="stMetricLabel"] > div,
[data-testid="stMetricValue"] > div,
[data-testid="stSidebar"] label {
  font-family: var(--sans) !important;
}
h1, h2, h3, h4 { font-family: var(--sans) !important; }
.stApp { background: var(--bg) !important; }
.stApp > header { background: var(--bg2) !important; border-bottom: 1px solid var(--border); }

section[data-testid="stSidebar"] {
  background: var(--bg2) !important;
  border-right: 1px solid var(--border) !important;
}
section[data-testid="stSidebar"] * { font-family: var(--sans) !important; }
/* Icon-font elements (expander chevrons etc.) use ligature text that the
   Material Icons font converts into a glyph — the blanket sans-serif rule
   above breaks that conversion and the raw ligature text ("arrow_right")
   renders literally, overlapping the label. Restore the icon font here. */
section[data-testid="stSidebar"] [data-testid="stIconMaterial"],
section[data-testid="stSidebar"] .material-icons,
section[data-testid="stSidebar"] [class*="material-icons"] {
  font-family: 'Material Icons' !important;
}

/* ── headings ── */
h1, h2, h3, h4 { color: var(--text) !important; font-family: var(--sans) !important; font-weight: 700; }

/* ── tabs ── */
.stTabs [data-baseweb="tab-list"] { background: transparent; border-bottom: 1px solid var(--border); gap: 0; }
.stTabs [data-baseweb="tab"] {
  font-family: var(--sans) !important; font-size: 13px; font-weight: 500;
  color: var(--dim) !important; background: transparent !important;
  border-bottom: 2px solid transparent; padding: 9px 16px;
}
.stTabs [aria-selected="true"] {
  color: var(--text) !important; border-bottom-color: var(--accent) !important;
  font-weight: 600 !important;
}

/* ── buttons ── */
.stButton > button {
  font-family: var(--mono) !important; font-size: 12px; font-weight: 600;
  letter-spacing: .5px; border-radius: 6px !important;
  background: var(--panel2) !important; border: 1px solid var(--border2) !important;
  color: var(--text) !important; transition: .15s !important;
}
.stButton > button[kind="primary"] {
  background: var(--accent) !important; border-color: var(--accent) !important;
  color: #04130c !important;
}
.stButton > button:hover { border-color: var(--accent) !important; }

/* ── inputs ── */
.stTextInput input, .stSelectbox select {
  font-family: var(--mono) !important; font-size: 13px;
  background: var(--panel) !important; border: 1px solid var(--border2) !important;
  border-radius: 7px !important; color: var(--text) !important;
}
.stTextInput input:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 3px rgba(22,199,132,.15) !important; }

/* ── metrics ── */
[data-testid="stMetric"] {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px;
}
[data-testid="stMetricLabel"] { font-family: var(--mono) !important; font-size: 10px !important;
  text-transform: uppercase; letter-spacing: 1px; color: var(--dim) !important; }
[data-testid="stMetricValue"] { font-family: var(--mono) !important; font-size: 20px !important;
  font-weight: 600; color: var(--text) !important; }

/* ── dataframes ── */
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 8px; overflow: hidden; }

/* ── scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: var(--dim); }
/* inner card scrollable areas */
[style*="overflow-y:auto"], [style*="overflow-y: auto"] {
  scrollbar-width: thin;
  scrollbar-color: var(--border2) transparent;
}

/* ── SCANR component classes ── */
.score-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 24px; text-align: center;
}
.metric-card { background: var(--panel); border-radius: 8px; padding: 12px; border: 1px solid var(--border); margin: 4px; }

/* metric grid (SCANR style) */
.metric-grid {
  display: grid; grid-template-columns: repeat(3, 1fr);
  gap: 1px; background: var(--border); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden; margin-bottom: 12px;
}
.mg-cell { background: var(--panel); padding: 12px 14px 14px; }
.mg-label {
  font-family: var(--mono); font-size: 10px; text-transform: uppercase;
  letter-spacing: .7px; color: var(--mute); margin-bottom: 5px;
}
.mg-val { font-family: var(--mono); font-size: 17px; font-weight: 600; line-height: 1; }
.mg-hint { font-family: var(--mono); font-size: 10.5px; color: var(--mute); margin-top: 3px; }
.mg-up   { color: var(--up); }
.mg-down { color: var(--down); }
.mg-warn { color: var(--amber); }
.mg-base { color: var(--text); }

/* ── unified card system ──────────────────────────────────────────────────
   Single source of truth for every card surface. Before this, cards were
   hand-styled inline per tab: 3 different backgrounds, 2 border colors,
   2 radii and ~6 padding combos — which read as visual noise when moving
   between tabs. Use these classes instead of new inline card styles. */
.ui-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px; margin-bottom: 12px;
}
.ui-card-accent { border-left-width: 4px; border-left-style: solid; }
.ui-card-hero { border-width: 2px; border-radius: 12px; padding: 18px 22px; }
.ui-card-title {
  font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 4px;
}
.ui-card-sub { font-size: 12px; color: var(--dim); line-height: 1.6; }
.ui-card-meta {
  font-family: var(--mono); font-size: 10px; text-transform: uppercase;
  letter-spacing: .8px; color: var(--mute); margin-bottom: 6px;
}
/* auto-fit card grid — cards keep a readable min width and reflow instead of
   being squeezed into fixed equal columns. Equal heights come free from grid. */
.ui-card-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px; margin-bottom: 12px;
}
.ui-card-grid > .ui-card { margin-bottom: 0; height: 100%; }

/* verdict chip */
.verdict {
  display: inline-block; font-family: var(--mono); font-size: 11px; font-weight: 700;
  letter-spacing: .5px; padding: 3px 10px; border-radius: 5px; text-transform: uppercase;
}
.verdict-buy  { color: var(--up);   background: rgba(22,199,132,.12); border: 1px solid rgba(22,199,132,.3); }
.verdict-hold { color: var(--amber); background: rgba(240,185,11,.12); border: 1px solid rgba(240,185,11,.3); }
.verdict-sell { color: var(--down);  background: rgba(234,58,68,.12);  border: 1px solid rgba(234,58,68,.3); }

/* panel header */
.panel-head {
  font-family: var(--mono); font-size: 11px; text-transform: uppercase;
  letter-spacing: 1.2px; font-weight: 600; color: var(--dim);
  padding: 10px 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 12px;
}

/* ticker tape */
.tape-wrap { overflow: hidden; background: var(--bg2); border-bottom: 1px solid var(--border); padding: 5px 0; margin-bottom: 8px; }
.tape-track { display: inline-flex; gap: 32px; white-space: nowrap; animation: scroll-tape 40s linear infinite; padding-left: 16px; }
.tape-wrap:hover .tape-track { animation-play-state: paused; }
@keyframes scroll-tape { to { transform: translateX(-50%); } }
.tape-item { font-family: var(--mono); font-size: 11.5px; display: inline-flex; gap: 7px; align-items: baseline; }
.tape-sym { color: var(--dim); font-weight: 600; }
.tape-px  { color: var(--text); }
.tape-chg { font-weight: 600; }

.signal-good { color: var(--up);   font-weight: bold; }
.signal-warn { color: var(--amber); font-weight: bold; }
.signal-bad  { color: var(--down); font-weight: bold; }

/* ── Overview / macro-impact cards ── */
.impact-card {
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;
}
.impact-label {
  font-family: var(--mono); font-size: 9px; text-transform: uppercase;
  letter-spacing: .7px; color: var(--mute); margin-bottom: 5px;
}
.impact-badge {
  display: inline-block; font-family: var(--mono); font-size: 11px;
  font-weight: 700; padding: 2px 8px; border-radius: 4px;
  text-transform: uppercase; letter-spacing: .3px;
}
.impact-pos  { color: var(--up);    background: rgba(22,199,132,.1);  border: 1px solid rgba(22,199,132,.35); }
.impact-neu  { color: var(--dim);   background: rgba(138,155,194,.1); border: 1px solid rgba(138,155,194,.3); }
.impact-neg  { color: var(--down);  background: rgba(234,58,68,.1);   border: 1px solid rgba(234,58,68,.35); }
.impact-expl { font-size: 11px; color: #cfd8dc; margin-top: 6px; line-height: 1.45; }
</style>
""", unsafe_allow_html=True)


# ─── Tooltips — used everywhere via help= or title= ─────────────────────────
_TIP = {
    # ── Valuation ─────────────────────────────────────────────────────────────
    "Price":           "Current share price in USD",
    "Market Cap":      "Total market value = price × shares. >$10B = Large Cap (stable), $2-10B = Mid, <$2B = Small (higher growth potential)",
    "P/S Ratio":       "Price-to-Sales. How much investors pay per $1 of revenue. <5 = cheap, 5–15 = fair for growth, >20 = expensive — compare to sector peers",
    "Forward P/E":     "Price ÷ next-year earnings estimate. <20 = cheap, 20–35 = avg tech, >50 = high-growth premium — only justified with strong growth",
    "PEG Ratio":       "P/E ÷ growth rate. <1 = cheap relative to growth. 1–2 = fair. >2 = expensive. Most useful for growth stocks",
    "52W Range":       "52-week price range. Near HIGH = strong momentum. Near LOW = weakness or opportunity — depends on the full analysis",
    # ── Growth ────────────────────────────────────────────────────────────────
    "Revenue Growth":  "Year-over-year revenue growth. <10% = mature, 10–20% = decent, 20–40% = strong, >40% = hypergrowth. Compare to prior quarters for trends",
    "Earnings Growth": "Year-over-year net earnings growth. >20% = strong. EPS growing faster than revenue = improving efficiency",
    "Rule of 40":      "SaaS health metric: Revenue Growth% + FCF Margin%. >40 = healthy, >60 = excellent, <40 = under pressure",
    # ── Margins ───────────────────────────────────────────────────────────────
    "Gross Margin":    "Gross Profit ÷ Revenue. SaaS: 70–85% excellent. Hardware: 30–50% normal. High margin = strong competitive moat",
    "FCF Yield":       "Free Cash Flow ÷ Market Cap. >3% = attractive, >5% = cheap. FCF = real cash left after all capital spending",
    "FCF Margin":      "% of revenue that becomes free cash. >15% = healthy. Best SaaS companies: 20–30%",
    "R&D % Revenue":   "% of revenue reinvested in R&D. >15% = true tech company. >25% = big bet on future growth",
    # ── Balance sheet ─────────────────────────────────────────────────────────
    "Debt/Equity":     "Total Debt ÷ Equity. <0.3 = clean balance sheet. 0.3–1 = moderate leverage. >2 = high leverage = risky in rising rate environment",
    # ── Technical ─────────────────────────────────────────────────────────────
    "Trend (MA)":      "Price vs 50-day and 200-day moving averages. Above both = uptrend. Below both = downtrend. Golden Cross (MA50 crosses above MA200) = strong buy signal",
    "RSI":             "Relative Strength Index — momentum speedometer. The textbook 30/70 bands are NOT universal: in a strong uptrend RSI 60-80 is the NORMAL zone (momentum, not a top), while in a downtrend RSI 60 is already a stretched bear rally. Judge RSI against the stock's own trend regime — see 'RSI in Context' in the Technical tab.",
    "MACD":            "Momentum indicator: difference between 12 and 26-day EMA. MACD above signal line = rising momentum (bullish). Below = bearish",
    "Volume":          "Current trading volume vs 20-day average. >1.5x = unusual demand — institutions entering. <0.7x = drying up, wait for breakout",
    "52W Position":    "Where price sits within its 52-week range. Near 100% (high) = strong trend. Near 0% (low) = check if opportunity or falling knife",
    # ── Institutional ─────────────────────────────────────────────────────────
    "Short Interest":  "% of shares borrowed and sold short. <3% = low. 5–10% = moderate. >10% = heavy short pressure — potential short squeeze if price rises",
    "Institutional Ownership": "% held by large funds. 50–70% = healthy. >80% = price is 'managed'. <30% = still under the radar — discovery potential",
    "Rate Sensitivity": "How much the stock reacts to interest rate changes. High = rate cuts help a lot (growth/REITs). Low = less affected (value/low-dividend)",
    "China Exposure":  "Revenue exposure to Chinese market. High = geopolitical risk, regulation, tariffs. None = more stable in tension scenarios",
    # ── Composite scores ──────────────────────────────────────────────────────
    "Fundamental":     "1–10 score for financial quality: growth, margins, FCF, debt, multiples. >7 = quality company. <4 = weak fundamentals",
    "Technical":       "1–10 score for chart health: MA50/200, RSI, MACD, volume, 52W position. >7 = healthy chart. <4 = broken trend",
    "Momentum":        "1–10 score for momentum: returns vs SPY and QQQ over 1M/3M/6M/1Y. >7 = outperforming. <4 = lagging the market",
    "Smart Money":     "1–10 score for institutional/insider activity: ownership, purchases, changes. >7 = big money entering",
    "Macro":           "1–10 score for macro/geopolitical environment: rates, dollar, AI cycle, China tensions. >7 = strong tailwind",
    "Relative":        "1–10 score vs sector peers. >7 = sector leader",
    # ── Expert Panel ──────────────────────────────────────────────────────────
    "Conviction":      "Expert's confidence level. 1 = tentative, 3 = moderate, 5 = high conviction — willing to put significant capital",
    "Position Size":   "Recommended % of portfolio. 1–3% = small position, 5–8% = medium, 10%+ = high-conviction bet. Size reflects confidence",
    "Stop Loss":       "% drop that forces an exit. 10–15% = short swing trade. 20–25% = longer term. Stop Loss = the line between a mistake and a disaster",
    "Target Price":    "12-month price target by the expert. Distance from current price = expected upside potential",
    # ── Market regime ─────────────────────────────────────────────────────────
    "VIX":             "Wall Street's Fear Index. <15 = euphoria. 15–20 = calm. 20–25 = worry. >25 = fear. >30 = panic — sometimes creates opportunity",
    "10Y Yield":       "10-year US Treasury yield. Rising = higher cost of capital = growth stocks suffer. >4.5% = significant headwind. Falling = tailwind for growth",
    "S&P 1M":          "S&P 500 performance over the last month. Positive = market rising = supportive environment. Negative = caution",
    "QQQ 1M":          "Nasdaq (tech-heavy index) performance last month. Closest proxy to the growth/tech sector",
    # ── Options / Weekly ──────────────────────────────────────────────────────
    "RVOL":            "Relative Volume: 5-day avg ÷ 20-day avg. >1.5x = unusual demand, institutions entering. <0.7x = quiet — wait for breakout",
    "Call/Put":        "Call vs Put volume ratio (3 nearest expirations). Normal market: ~0.7. >1.2 = bullish flow. >1.8 = highly unusual institutional call buying",
    "3M Ret":          "3-month price return. Positive momentum tends to continue. >+15% and above SPY = market leader",
    "PT Up":           "Average analyst price target upside from current price. >10% = meaningful potential per consensus",
    "Bulls":           "% analysts with Buy/Strong Buy rating. >70% = strong consensus to buy. <50% = controversial",
    "Rev Gr":          "Revenue growth YoY — is the business expanding? >20% = strong, >30% = exceptional growth",
    "GM":              "Gross Margin. >65% = product/service with competitive moat. Typical SaaS: 70–80%",
    "Weekly Score":    "Composite 1–10 weekly score: Model 30% + Analyst 20% + Options 15% + Breakout 15% + momentum/volume bonuses. >7.5 = strong opportunity",
    "Options":         "Options flow score 1–10. C/P >1.3 = institutions buying calls = bullish. >8 = highly unusual flow",
    "Breakout":        "Breakout setup score 1–10: proximity to 52W High + BB Squeeze + tight range + volume surge. >7.5 = pre-breakout entry",
    "Analyst":         "Analyst consensus score 1–10: % bulls + price target upside. >7 = most analysts recommend buying with significant upside",
    "Model":           "Internal model score: weighted average of Fundamental (30%) + Technical (20%) + Momentum (15%) + Smart Money + Macro. >7 = all parameters positive",
}

# ─── Absolute verdicts per metric+tone ──────────────────────────────────────
# Each entry: (label_text, color)
_VERDICT: dict[tuple[str, str], tuple[str, str]] = {
    # Revenue Growth
    ("Revenue Growth", "mg-up"):   ("✅ Strong growth — above 15% YoY", "#16c784"),
    ("Revenue Growth", "mg-warn"):  ("⚠ Moderate growth — 5–15%",        "#f0b90b"),
    ("Revenue Growth", "mg-down"):  ("❌ Weak growth — below 5%",          "#ea3a44"),
    # Earnings Growth
    ("Earnings Growth","mg-up"):   ("✅ Earnings growing well",            "#16c784"),
    ("Earnings Growth","mg-warn"):  ("⚠ Slow earnings growth",             "#f0b90b"),
    ("Earnings Growth","mg-down"):  ("❌ Earnings declining",               "#ea3a44"),
    # Gross Margin
    ("Gross Margin",   "mg-up"):   ("✅ Excellent margins — above 55%",   "#16c784"),
    ("Gross Margin",   "mg-warn"):  ("⚠ Average margins — 25–55%",         "#f0b90b"),
    ("Gross Margin",   "mg-down"):  ("❌ Low margins — below 25%",          "#ea3a44"),
    # FCF Yield
    ("FCF Yield",      "mg-up"):   ("✅ Attractive cash yield (>3%)",      "#16c784"),
    ("FCF Yield",      "mg-warn"):  ("⚠ Low cash yield",                   "#f0b90b"),
    ("FCF Yield",      "mg-down"):  ("❌ Negative FCF — burning cash",      "#ea3a44"),
    # FCF Margin
    ("FCF Margin",     "mg-up"):   ("✅ Strong cash generation — >15%",    "#16c784"),
    ("FCF Margin",     "mg-warn"):  ("⚠ Low cash margin",                  "#f0b90b"),
    ("FCF Margin",     "mg-down"):  ("❌ Negative FCF",                     "#ea3a44"),
    # Debt/Equity
    ("Debt/Equity",    "mg-up"):   ("✅ Low leverage — healthy balance (<0.5)", "#16c784"),
    ("Debt/Equity",    "mg-warn"):  ("⚠ Moderate leverage — 0.5 to 2",    "#f0b90b"),
    ("Debt/Equity",    "mg-down"):  ("❌ High leverage — rate risk (>2)",   "#ea3a44"),
    # P/S Ratio
    ("P/S Ratio",      "mg-up"):   ("✅ Low price-to-sales — cheap",       "#16c784"),
    ("P/S Ratio",      "mg-warn"):  ("⚠ Average price-to-sales",           "#f0b90b"),
    ("P/S Ratio",      "mg-down"):  ("⚠ High price-to-sales — check growth","#f97316"),
    # Forward P/E
    ("Forward P/E",    "mg-up"):   ("✅ Reasonable P/E — below 20",        "#16c784"),
    ("Forward P/E",    "mg-warn"):  ("⚠ Average P/E — 20–40",              "#f0b90b"),
    ("Forward P/E",    "mg-down"):  ("⚠ High P/E — growth premium priced in","#f97316"),
    # PEG
    ("PEG Ratio",      "mg-up"):   ("✅ Cheap vs growth — PEG <1",         "#16c784"),
    ("PEG Ratio",      "mg-warn"):  ("⚠ Fair vs growth — PEG 1–2",         "#f0b90b"),
    ("PEG Ratio",      "mg-down"):  ("❌ Expensive vs growth — PEG >2",     "#ea3a44"),
    # Rule of 40
    ("Rule of 40",     "mg-up"):   ("✅ Above threshold — healthy business","#16c784"),
    ("Rule of 40",     "mg-warn"):  ("⚠ Below 40 threshold — weak health", "#f0b90b"),
    ("Rule of 40",     "mg-down"):  ("❌ Negative — operational issue",     "#ea3a44"),
    # R&D
    ("R&D % Revenue",  "mg-up"):   ("✅ Heavy R&D investment (>15%)",      "#16c784"),
    ("R&D % Revenue",  "mg-warn"):  ("⚠ Average R&D spend",                "#f0b90b"),
    ("R&D % Revenue",  "mg-down"):  ("⚠ Low R&D investment",               "#8a9bc2"),
}

# Generic fallback for tones without a specific entry
_VERDICT_GENERIC = {
    "mg-up":   ("✅ Positive",  "#16c784"),
    "mg-warn": ("⚠ Average",   "#f0b90b"),
    "mg-down": ("❌ Weak",      "#ea3a44"),
}

# ─── Plain-language explanations — always visible, no hover needed ───────────
# Written for someone with zero finance background.
_EXPLAIN = {
    # Valuation
    "Market Cap":      "Total stock market value of the company — like the total price tag of the business",
    "P/S Ratio":       "How much investors pay per $1 of sales. 5x = reasonable, 30x = very expensive",
    "Forward P/E":     "Price divided by expected next-year earnings. Lower = cheaper relative to profit",
    "PEG Ratio":       "Is the price reasonable given how fast the company is growing? Below 1 = good deal",
    "52W Range":       "The highest and lowest price over the past 52 weeks",
    # Growth
    "Revenue Growth":  "How much did sales grow vs last year? This is the most important growth question",
    "Earnings Growth": "How much did net profit grow year over year",
    "Rule of 40":      "SaaS health check: growth% + profit margin%. Above 40 = healthy business",
    # Margins
    "Gross Margin":    "From every $100 in revenue, how much is left after direct production costs only (before salaries, marketing)",
    "FCF Yield":       "How much real free cash the company generates relative to its market value — like a dividend yield but for cash flow",
    "FCF Margin":      "From every $100 in revenue, how much becomes actual free cash in the bank",
    "R&D % Revenue":   "How much of revenue is reinvested into building new products and technology",
    # Balance sheet
    "Debt/Equity":     "How much debt the company carries vs its own equity — like a mortgage-to-home-value ratio",
    # Technical
    "Trend (MA)":      "Is the stock in an uptrend? Above its 50-day and 200-day averages = yes",
    "RSI":             "Is the stock overbought (>70, caution) or oversold (<30, potential buy opportunity)?",
    "MACD":            "Momentum indicator — is the buying/selling force accelerating or decelerating?",
    "Volume":          "How many shares traded vs the average — high volume = conviction behind the move",
    "52W Position":    "Where the price is within its 52-week range. Near the high = strong trend",
    # Institutional
    "Short Interest":  "How many traders are betting the stock will fall. >10% = significant pressure",
    "Institutional Ownership": "% held by large funds — 'smart money'. Healthy range: 50–70%",
    "Rate Sensitivity": "How much this stock is affected by central bank interest rate changes",
    "China Exposure":  "How dependent the company's revenue is on China — geopolitical and regulatory risk",
    # Composite scores
    "Fundamental":     "Quality of the financial foundation: growth, margins, FCF, debt",
    "Technical":       "Health of the price chart: trend, momentum, volume",
    "Momentum":        "Speed and direction: is this stock accelerating vs the market?",
    "Smart Money":     "Institutional activity: are big funds buying?",
    "Macro":           "Macro-economic and geopolitical environment for this stock",
    "Relative":        "Performance vs similar companies in the same sector",
}

# ─── Helpers ─────────────────────────────────────────────────────────────────
def fmt_pct(v):
    if v is None: return "N/A"
    return f"{v*100:+.1f}%"

def fmt_num(v, suffix=""):
    if v is None: return "N/A"
    if abs(v) >= 1e12: return f"${v/1e12:.2f}T{suffix}"
    if abs(v) >= 1e9:  return f"${v/1e9:.2f}B{suffix}"
    if abs(v) >= 1e6:  return f"${v/1e6:.2f}M{suffix}"
    return f"{v:.2f}{suffix}"

def score_color(s):
    if s >= 8.5: return "#16c784"
    if s >= 7.0: return "#16c784"
    if s >= 5.0: return "#f0b90b"
    if s >= 3.5: return "#f97316"
    return "#ea3a44"

def score_label(s):
    for (lo, hi), (lbl, _) in SCORE_LABELS.items():
        if lo <= s <= hi:
            return lbl
    return "N/A"


def _tone(val, good_thresh, bad_thresh, higher_is_better=True):
    if val is None: return "mg-base"
    return ("mg-up" if val >= good_thresh else "mg-down" if val <= bad_thresh else "mg-warn") \
        if higher_is_better else \
        ("mg-up" if val <= good_thresh else "mg-down" if val >= bad_thresh else "mg-warn")


def render_gauge(score: float, title: str, height: int = 200):
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": title, "font": {"color": "#8a9bc2", "size": 12, "family": "IBM Plex Mono"}},
        number={"font": {"color": score_color(score), "size": 26, "family": "IBM Plex Mono"}},
        gauge={
            "axis": {"range": [1, 10], "tickcolor": "#374461", "tickfont": {"size": 9, "color": "#556070"}},
            "bar": {"color": score_color(score), "thickness": 0.28},
            "bgcolor": "#222b3d",
            "bordercolor": "#2a3348",
            "borderwidth": 1,
            "steps": [
                {"range": [1, 3.5], "color": "#1a1c22"},
                {"range": [3.5, 5], "color": "#1c2018"},
                {"range": [5, 7],   "color": "#1c2218"},
                {"range": [7, 8.5], "color": "#182418"},
                {"range": [8.5, 10],"color": "#122518"},
            ],
        },
    ))
    fig.update_layout(
        paper_bgcolor="#131722", plot_bgcolor="#131722",
        height=height, margin=dict(t=40, b=10, l=20, r=20),
    )
    return fig


def render_price_chart(df: pd.DataFrame, symbol: str):
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.22, 0.23],
        vertical_spacing=0.08,
        subplot_titles=(f"{symbol} Price", "Volume", "RSI"),
    )

    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name="Price",
        increasing_line_color="#16c784", increasing_fillcolor="#16c784",
        decreasing_line_color="#ea3a44", decreasing_fillcolor="#ea3a44",
    ), row=1, col=1)

    if "MA50" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MA50"],  name="MA50",
                                  line=dict(color="#f0b90b", width=1.2)), row=1, col=1)
    if "MA200" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MA200"], name="MA200",
                                  line=dict(color="#a78bfa", width=1.2)), row=1, col=1)

    # ── Support/Resistance + trendlines — derived from the same swing-point
    # detection, not hand-picked, so they're reproducible from this price
    # series alone (see utils/indicators.py::support_resistance_levels /
    # trendlines for the method: clustered swing highs/lows for horizontal
    # levels, least-squares fit through the most recent swing points for
    # the trend channel lines).
    _sr = mod_ind.support_resistance_levels(df)
    for _lvl in _sr.get("resistance", []):
        fig.add_hline(y=_lvl, line_dash="dash", line_color="rgba(234,58,68,0.6)", line_width=1,
                      annotation_text=f"R {_lvl:.2f}", annotation_position="right",
                      annotation_font_color="#ea3a44", annotation_font_size=10,
                      row=1, col=1)
    for _lvl in _sr.get("support", []):
        fig.add_hline(y=_lvl, line_dash="dash", line_color="rgba(22,199,132,0.6)", line_width=1,
                      annotation_text=f"S {_lvl:.2f}", annotation_position="right",
                      annotation_font_color="#16c784", annotation_font_size=10,
                      row=1, col=1)

    _tl = mod_ind.trendlines(df)
    if _tl.get("support"):
        fig.add_trace(go.Scatter(x=_tl["support"]["x"], y=_tl["support"]["y"],
                                  name="Support trend", mode="lines",
                                  line=dict(color="#16c784", width=1.5, dash="dot")),
                     row=1, col=1)
    if _tl.get("resistance"):
        fig.add_trace(go.Scatter(x=_tl["resistance"]["x"], y=_tl["resistance"]["y"],
                                  name="Resistance trend", mode="lines",
                                  line=dict(color="#ea3a44", width=1.5, dash="dot")),
                     row=1, col=1)

    colors = ["#16c784" if float(c) >= float(o) else "#ea3a44"
              for c, o in zip(df["Close"], df["Open"])]
    fig.add_trace(go.Bar(x=df.index, y=df["Volume"], name="Volume",
                          marker_color=colors, opacity=0.6), row=2, col=1)

    if "RSI" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI"], name="RSI",
                                  line=dict(color="#60a5fa", width=1.5)), row=3, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ea3a44", row=3, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#16c784", row=3, col=1)

    fig.update_layout(
        paper_bgcolor="#131722", plot_bgcolor="#1c2333",
        font_color="#e8edf8", font_family="IBM Plex Mono",
        xaxis_rangeslider_visible=False,
        legend=dict(
            bgcolor="#1c2333", bordercolor="#2a3348",
            orientation="h",
            yanchor="bottom", y=1.02,
            xanchor="left", x=0,
        ),
        height=700, margin=dict(t=60, b=20, l=10, r=10),
    )
    fig.update_xaxes(gridcolor="#2a3348")
    fig.update_yaxes(gridcolor="#2a3348")
    return fig


def render_radar(breakdown: dict, weights: dict):
    categories = list(breakdown.keys())
    values = [breakdown[k] for k in categories]
    labels = [k.replace("_", " ").title() for k in categories]

    fig = go.Figure(go.Scatterpolar(
        r=values + [values[0]],
        theta=labels + [labels[0]],
        fill="toself",
        fillcolor="rgba(22,199,132,0.12)",
        line=dict(color="#16c784", width=2),
    ))
    fig.update_layout(
        polar=dict(
            bgcolor="#1c2333",
            radialaxis=dict(range=[0, 10], gridcolor="#2a3348", tickcolor="#556070",
                            tickfont=dict(size=9, family="IBM Plex Mono")),
            angularaxis=dict(gridcolor="#2a3348", tickcolor="#8a9bc2",
                             tickfont=dict(size=10, family="IBM Plex Mono")),
        ),
        paper_bgcolor="#131722", font_color="#e8edf8",
        showlegend=False, height=350,
        margin=dict(t=20, b=20, l=50, r=50),
    )
    return fig


def render_return_bar(returns: dict, spy_returns: dict, symbol: str):
    periods = list(returns.keys())
    tick_vals = [r * 100 if r else 0 for r in [returns[p] for p in periods]]
    spy_vals  = [r * 100 if r else 0 for r in [spy_returns[p] for p in periods]]

    fig = go.Figure()
    fig.add_trace(go.Bar(name=symbol, x=periods, y=tick_vals,
                          marker_color="#64b5f6"))
    fig.add_trace(go.Bar(name="SPY", x=periods, y=spy_vals,
                          marker_color="#f0b90b"))
    fig.update_layout(
        barmode="group",
        paper_bgcolor="#131722", plot_bgcolor="#1c2333",
        font_color="#e8edf8", font_family="IBM Plex Mono",
        yaxis_ticksuffix="%",
        title="Returns vs S&P 500", height=300,
        legend=dict(bgcolor="#1c2333", bordercolor="#2a3348"),
        margin=dict(t=40, b=10),
    )
    fig.update_yaxes(gridcolor="#2a3348")
    return fig


def _metric_cell(label: str, value: str, color: str = "#e8edf8") -> str:
    return (f'<div style="background:#222b3d;border-radius:6px;padding:7px 10px">'
            f'<div style="font-size:9px;color:#8a9bc2;font-family:\'IBM Plex Mono\',monospace;'
            f'text-transform:uppercase;letter-spacing:.5px">{label}</div>'
            f'<div style="font-size:13px;font-weight:600;color:{color};'
            f'font-family:\'IBM Plex Mono\',monospace;white-space:nowrap">{value}</div>'
            f'</div>')


def _safe_href(url) -> str:
    """HTML-escaped link target; anything that is not http(s) (e.g. javascript:) becomes '#'."""
    url = str(url or "")
    return _html.escape(url, quote=True) if url.lower().startswith(("http://", "https://")) else "#"


def render_ticker_tape():
    _TAPE = [
        ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"), ("^DJI", "Dow 30"),
        ("^VIX", "VIX"), ("BTC-USD", "BTC"), ("GC=F", "Gold"), ("^TNX", "10Y"),
    ]
    parallel_map(get_ticker_info, [sym for sym, _ in _TAPE])  # fetch all quotes side by side; the loop hits the cache
    items = []
    for sym, label in _TAPE:
        try:
            info = get_ticker_info(sym)
            px   = info.get("regularMarketPrice") or info.get("currentPrice") or 0
            chg  = info.get("regularMarketChangePercent") or 0
            sign = "▲" if chg >= 0 else "▼"
            col  = "#16c784" if chg >= 0 else "#ea3a44"
            items.append(
                f'<span class="tape-item">'
                f'<span class="tape-sym">{label}</span>'
                f'<span class="tape-px">{px:,.2f}</span>'
                f'<span class="tape-chg" style="color:{col}">{sign} {abs(chg):.2f}%</span>'
                f'</span>'
            )
        except Exception:
            pass
    if not items:
        return
    tape_html = "".join(items * 2)
    st.markdown(
        f'<div class="tape-wrap"><div class="tape-track">{tape_html}</div></div>',
        unsafe_allow_html=True,
    )



def _page_about(md: str) -> None:
    """Educational 'About this page' expander — essence, calculation, usage."""
    with st.expander("ⓘ About this page — what, how it's computed, how to use"):
        st.markdown(md)

# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Stock Analyzer")
    st.markdown("---")

    # Consume page_jump requests (e.g. "Deep Dive →" button from Weekly Picks)
    if "page_jump" in st.session_state:
        st.session_state["_nav_page"] = st.session_state.pop("page_jump")

    page = st.radio(
        "Navigation",
        ["🔍 Analyze",
         "⭐ Weekly Picks",
         "🏥 Market Health", "🔄 Sector Rotation", "📰 News Feed",
         "🔎 AI Screener", "🌍 Market Radar",
         "💼 Portfolio", "👁 Watchlist",
         "📝 Paper Portfolio", "🎯 Tracker",
         "📊 Backtester", "🧠 Alpha Lab", "📖 Glossary"],
        key="_nav_page",
        label_visibility="collapsed",
    )

    st.markdown("---")
    if not ANTHROPIC_API_KEY:
        st.warning("⚠️ Set ANTHROPIC_API_KEY for AI features")
    else:
        st.success("✅ AI Features Active")

    st.markdown("---")

    # ── API / Data Source Health ───────────────────────────────────────────
    # Key status renders instantly; live connectivity test only on button click
    # (previously fired SPY + AAPL network calls on EVERY rerun of EVERY page).
    with st.expander("🔌 Data Sources", expanded=False):
        from config import FRED_API_KEY as _fred_key
        st.markdown(("✅" if ANTHROPIC_API_KEY else "⚠️") + " **Claude AI** — " +
                    ("key configured" if ANTHROPIC_API_KEY else "key missing (Expert Panel, Macro AI disabled)"))
        st.markdown(("✅" if FINNHUB_API_KEY else "⚠️") + " **Finnhub** — " +
                    ("key configured" if FINNHUB_API_KEY else "key missing (Analyst tab uses Yahoo Finance fallback)"))
        st.markdown(("✅" if _fred_key else "⚠️") + " **FRED** — " +
                    ("key configured" if _fred_key else "key missing (Yield Curve uses yfinance approx)"))

        if st.button("🔄 Test live connectivity", key="_ds_test"):
            try:
                _yf_test = get_ticker_info("SPY")
                st.markdown("✅ **yfinance** — working" if _yf_test else "⚠️ **yfinance** — empty data")
            except Exception as _e:
                st.markdown(f"❌ **yfinance** — {_e}")
            if FINNHUB_API_KEY:
                try:
                    _fh_test = mod_finnhub.fetch_all("AAPL")
                    if "rec_error" in _fh_test or "error" in _fh_test:
                        _fh_err = _fh_test.get("rec_error") or _fh_test.get("error", "")
                        st.markdown(f"⚠️ **Finnhub** — call failed: {_fh_err[:60]}")
                    else:
                        st.markdown("✅ **Finnhub** — working")
                except Exception as _e:
                    st.markdown(f"❌ **Finnhub** — {str(_e)[:60]}")

    # ── 📰 Morning Briefing ────────────────────────────────────────────────
    _brief_cached = _load_json(Path(__file__).parent / ".briefing.json", default={})
    _brief_fresh = _brief_cached.get("date") == _date.today().isoformat()
    with st.expander("📰 Morning Briefing" + ("" if _brief_fresh else " ·🔴 new day"),
                     expanded=False):
        if st.button("☀️ Generate today's briefing" if not _brief_fresh else "🔄 Regenerate",
                     key="_brief_btn", width="stretch"):
            with st.spinner("Collecting overnight changes..."):
                st.session_state["_briefing"] = mod_brief.get_briefing(force=True)
        _brief = st.session_state.get("_briefing") or (_brief_cached if _brief_fresh else None)
        if _brief and _brief.get("summary"):
            st.markdown(_brief["summary"])
            _bf = _brief.get("facts", {})
            _fg_b = _bf.get("fear_greed", {})
            _meta_bits = []
            if _bf.get("regime", {}).get("label"):
                _meta_bits.append(f"Regime {_bf['regime']['label']}")
            if _fg_b.get("score") is not None:
                _meta_bits.append(f"F&G {_fg_b['score']}")
            if _bf.get("cape"):
                _meta_bits.append(f"CAPE {_bf['cape']:.1f}")
            if _meta_bits:
                st.caption(" · ".join(_meta_bits))
        elif not _brief:
            st.caption("Your day in 5 bullets: regime, portfolio moves, earnings ahead, "
                       "score deteriorations. Click to generate.")

    # ── 📚 Glossary (educational) ──────────────────────────────────────────
    with st.expander("📚 Glossary", expanded=False):
        _gl_q = st.text_input("Search term", key="_gloss_q",
                              placeholder="e.g. RSI, Kelly, drift...",
                              label_visibility="collapsed")
        _gl_items = sorted(mod_gloss.TIP.items())
        if _gl_q.strip():
            _q = _gl_q.strip().lower()
            _gl_items = [(k, v) for k, v in _gl_items
                         if _q in k.lower() or _q in v.lower()]
        for _gk, _gv in _gl_items[:12]:
            _gname = _gk.replace("_", " ").title()
            st.markdown(f"**{_gname}** — <span style='font-size:11px;color:#8a9bc2'>{_gv}</span>",
                        unsafe_allow_html=True)
        if len(_gl_items) > 12:
            st.caption(f"...{len(_gl_items) - 12} more — refine the search")

    st.markdown("---")
    st.caption("Data: Yahoo Finance · Refreshed every 15 min")


render_ticker_tape()

# Fix sidebar collapse button icon — uses window.parent to escape iframe
st.iframe("""
<script>
(function(){
  const doc = window.parent ? window.parent.document : document;
  const fix = () => {
    doc.querySelectorAll('button span, button div, header span, header div').forEach(el => {
      const txt = (el.innerText || el.textContent || '').trim();
      if (/^[a-z][a-z_]{3,}$/.test(txt) && !txt.includes(' ')) {
        el.style.setProperty('font-family', 'Material Icons', 'important');
        el.style.setProperty('font-size', '20px', 'important');
        el.style.setProperty('line-height', '1', 'important');
        el.style.setProperty('font-feature-settings', '"liga" 1', 'important');
        el.style.setProperty('-webkit-font-feature-settings', '"liga" 1', 'important');
      }
    });
  };
  fix();
  setTimeout(fix, 500);
  setTimeout(fix, 1500);
  const root = doc.body || doc.documentElement;
  new MutationObserver(fix).observe(root, {childList:true, subtree:true});
})();
</script>
""", height=1)

# ─── Page: Analyze ────────────────────────────────────────────────────────────
if page == "🔍 Analyze":
    st.title("🔍 Deep Stock Analysis")
    _page_about("""**What:** the full research workstation for one stock — 11 tabs from price action to DCF to fund rulebooks.
**How:** 6 scoring engines (fundamental, technical, momentum, institutional, macro, relative) blend into one composite; every metric in the 🎯 In-Context panel is judged against THIS stock's sector, size, growth and the market regime — never against naive universal thresholds.
**Use:** suggested flow — Overview for the verdict → Fundamentals for quality + context → Technical for timing → Experts + Panel Verdict for the decision → Risk & Sizing for HOW MUCH to buy. A great stock at the wrong size is still a mistake.""")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        # Typing filters the known tickers; any other ticker can still be typed and confirmed with Enter.
        _known = sorted({*WEEKLY_UNIVERSE, *RADAR_TICKERS, *SECTOR_ETFS.values()})
        _cur = st.session_state.get("symbol", "")
        _opts = _known if (not _cur or _cur in _known) else [_cur] + _known
        symbol = (st.selectbox(
            "Enter ticker", _opts,
            index=_opts.index(_cur) if _cur in _opts else None,
            accept_new_options=True,
            placeholder="Type a ticker (NVDA, AAPL, QQQ...) — suggestions appear as you type",
            label_visibility="collapsed",
        ) or "").upper().strip()
        with st.expander("Don't know the ticker? Search by company name"):
            _q = st.text_input("Company name", key="_az_name_q", placeholder="e.g. nvidia, palantir, semiconductor")
            if _q.strip():
                _hits = search_tickers(_q.strip())
                if not _hits:
                    st.caption("No matches.")
                for _h in _hits:
                    if st.button(f'{_h["symbol"]} — {_h["name"]}', key=f'_az_hit_{_h["symbol"]}'):
                        st.session_state["symbol"] = _h["symbol"]
                        st.rerun()
    with col_btn:
        run = st.button("Analyze →", type="primary", width="stretch")

    if symbol:
        st.session_state["symbol"] = symbol

    if run and symbol:
        st.session_state["_az_sym"] = symbol

    if symbol and st.session_state.get("_az_sym") == symbol:
        with st.spinner(f"Fetching data for {symbol}..." if run else ""):
            info  = get_ticker_info(symbol)
            name  = info.get("longName", symbol)
            price = info.get("currentPrice") or info.get("regularMarketPrice", 0)
            sector   = info.get("sector", "N/A")
            industry = info.get("industry", "N/A")
            desc  = info.get("longBusinessSummary", "")

        # Header
        c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
        c1.markdown(f"### {name} `{symbol}`")
        c1.caption(f"{sector} · {industry}")
        c2.metric("Price", f"${price:.2f}" if price else "N/A",
                  help=_TIP["Price"])
        c3.metric("Market Cap", fmt_num(info.get("marketCap")),
                  help=_TIP["Market Cap"])

        low52  = info.get('fiftyTwoWeekLow',  0)
        high52 = info.get('fiftyTwoWeekHigh', 0)
        tip_52w = _TIP["52W Range"]
        c4.markdown(
            f"<div style='font-size:13px;color:#9fa8da;margin-bottom:4px;cursor:help' title='{tip_52w}'>52W Range</div>"
            f"<div style='font-size:18px;font-weight:600;white-space:nowrap'>${low52:.0f} – ${high52:.0f}</div>",
            unsafe_allow_html=True,
        )

        if desc:
            with st.expander("About the company"):
                st.write(desc[:600] + "..." if len(desc) > 600 else desc)

        st.markdown("---")

        # Run all modules
        with st.spinner("Running analysis..."):
            f_data  = mod_fund.analyze(symbol)
            t_data  = mod_tech.analyze(symbol)
            mo_data = mod_mom.analyze(symbol)
            i_data  = mod_inst.analyze(symbol)

        with st.spinner("Loading macro, peer & earnings data..."):
            info_for_macro = get_ticker_info(symbol)
            m_data = mod_macro.analyze(symbol,
                                       info_for_macro.get("sector", ""),
                                       info_for_macro.get("industry", ""))
            p_data = mod_sector.analyze(symbol)
            e_data = mod_earnings.get_earnings_data(symbol)

        s_data = mod_scoring.compute(
            fundamental=f_data["score"],
            technical=t_data["score"],
            momentum=mo_data["score"],
            smart_money=i_data["score"],
            macro=m_data["score"],
            relative=p_data["score"],
        )
        st.session_state[f"scores_{symbol}"] = s_data
        _pattern = mod_scoring.classify_pattern(s_data["breakdown"])
        # Record today's score for trend tracking (deterioration-before-price signal)
        mod_shist.record(symbol, s_data["final"], f_data["score"],
                         t_data["score"], mo_data["score"])

        # Rich detail dict for Expert Panel — actual metric values, not just aggregate scores
        st.session_state[f"details_{symbol}"] = {
            "fundamental_metrics": {
                k: v for k, v in f_data.get("metrics", {}).items() if v is not None
            },
            "technical_signals":  t_data.get("signals", []),
            "technical_rsi":      t_data.get("rsi"),
            "momentum_r3m":       mo_data.get("r3m"),
            "momentum_r1m":       mo_data.get("r1m"),
            "analyst_bull_pct":   i_data.get("bull_pct"),
            "analyst_pt_upside":  i_data.get("pt_upside"),
            "macro_score":        m_data.get("score"),
            "macro_tailwinds":    m_data.get("tailwinds", []),
            "macro_headwinds":    m_data.get("headwinds", []),
        }

        # Quick score banner
        _BREAKDOWN_LABELS = {
            "fundamental": "Fundamental", "technical": "Technical",
            "momentum": "Momentum",       "smart_money": "Smart Money",
            "macro": "Macro",             "relative": "Relative",
        }

        def _score_card(label, val, color):
            pct     = max(0, min(100, (val - 1) / 9 * 100))
            val_str = str(round(val, 2))
            bar_w   = f"{pct:.0f}%"
            grade_txt = ("✅ Very Strong" if val >= 7.5 else
                         "✅ Good"        if val >= 6.0 else
                         "⚠ Average"     if val >= 4.5 else
                         "❌ Weak")
            gc  = ("#16c784" if val >= 7.5 else "#a3e635" if val >= 6.0 else
                   "#f0b90b" if val >= 4.5 else "#ea3a44")
            expl = _EXPLAIN.get(label, "")
            tip  = _TIP.get(label, expl)
            return f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:9px;
            padding:14px 16px;min-width:0;cursor:help" title="{tip}">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;text-transform:uppercase;
              letter-spacing:1px;color:#8a9bc2;margin-bottom:8px">{label}</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:26px;font-weight:700;
              color:{color};line-height:1;margin-bottom:6px">{val_str}</div>
  <div style="height:4px;background:#2a3348;border-radius:2px;margin-bottom:8px">
    <div style="height:100%;width:{bar_w};background:{color};border-radius:2px"></div>
  </div>
  <span style="font-size:11px;font-weight:700;color:{gc};background:{gc}1a;
               border:1px solid {gc}44;padding:2px 8px;border-radius:4px">{grade_txt}</span>
  {('<div style="font-size:10.5px;color:#6b7a99;margin-top:8px;line-height:1.45;font-family:sans-serif">' + expl + '</div>') if expl else ''}
</div>"""

        col_score, col_breakdown = st.columns([1, 3])
        with col_score:
            sc = s_data['final']
            verdict_cls = "verdict-buy" if sc >= 7 else "verdict-hold" if sc >= 5 else "verdict-sell"
            if sc >= 8.5:
                sc_explain = "All parameters positive — strong opportunity"
            elif sc >= 7.0:
                sc_explain = "Most parameters positive — buy candidate"
            elif sc >= 5.0:
                sc_explain = "Mixed signals — not clear enough"
            elif sc >= 3.5:
                sc_explain = "Weak parameters — caution"
            else:
                sc_explain = "Most parameters negative — avoid"
            st.markdown(f"""
<div class="score-card" style="height:100%">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;text-transform:uppercase;
              letter-spacing:1.2px;color:#8a9bc2;margin-bottom:12px">SCANNER VERDICT</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:58px;font-weight:700;
              color:{s_data['color']};line-height:1;margin-bottom:8px;
              white-space:nowrap">{s_data['final']}</div>
  <div style="color:#556070;font-size:11px;margin-bottom:8px">/ 10</div>
  <span class="verdict {verdict_cls}">{s_data['label']}</span>
  <div style="font-size:11px;color:#8a9bc2;margin-top:10px;line-height:1.5">{sc_explain}</div>
</div>""", unsafe_allow_html=True)
            if _pattern["pattern"] != "MIXED — NO DOMINANT STORY":
                st.markdown(
                    f'<div style="background:{_pattern["color"]}14;border:1px solid '
                    f'{_pattern["color"]}55;border-radius:9px;padding:10px 14px;margin-top:8px" '
                    f'title="{_html.escape(_pattern["note"], quote=True)}">'
                    f'<div style="font-size:10px;font-weight:700;color:{_pattern["color"]};'
                    f'letter-spacing:.3px">{_pattern["icon"]} {_pattern["pattern"]}</div>'
                    f'<div style="font-size:10.5px;color:#8a9bc2;margin-top:4px;line-height:1.4">'
                    f'Quality (fund.+macro) {_pattern["quality"]} vs. Confirmation '
                    f'(tech.+momentum) {_pattern["confirmation"]}</div>'
                    f'</div>', unsafe_allow_html=True,
                )

        with col_breakdown:
            cards_html = "".join(
                _score_card(_BREAKDOWN_LABELS.get(k, k), round(v, 2), score_color(v))
                for k, v in s_data["breakdown"].items()
            )
            st.markdown(
                f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px">{cards_html}</div>',
                unsafe_allow_html=True,
            )

        # ── Sector Strength ───────────────────────────────────────────────────
        with st.spinner("Loading sector context…"):
            sc_ctx = mod_sector_str.get_sector_context(symbol)

        if sc_ctx:
            st.markdown("#### 📊 Sector Context")
            lvl_cols = st.columns(3)
            for i, key in enumerate(["level1", "level2"]):
                lvl = sc_ctx.get(key)
                if not lvl:
                    continue
                with lvl_cols[i]:
                    lbl = lvl["label"]
                    etf = lvl.get("etf")
                    st_data = lvl.get("strength", {})
                    prefix = ["🏢 Sector", "📌 Sub-sector"][i]

                    if st_data:
                        r1m_v = st_data.get("r1m", 0)
                        r3m_v = st_data.get("r3m", 0)
                        grade = st_data.get("grade", "")
                        gc    = st_data.get("grade_color", "#8a9bc2")
                        a200  = "✅" if st_data.get("above_200") else "❌"
                        st.markdown(
                            f'<div style="background:var(--panel);border:1px solid var(--border);'
                            f'border-radius:8px;padding:12px 14px">'
                            f'<div style="font-size:9px;color:#556070;text-transform:uppercase;'
                            f'letter-spacing:.8px;margin-bottom:5px">{prefix}</div>'
                            f'<div style="font-size:15px;font-weight:700;color:#e8edf8;margin-bottom:4px">'
                            f'{lbl}</div>'
                            f'<div style="font-size:10px;color:#8a9bc2;margin-bottom:6px">'
                            f'ETF proxy: <b style="color:#60a5fa">{etf}</b></div>'
                            f'<span style="font-size:10px;font-weight:700;color:{gc};'
                            f'background:{gc}18;border:1px solid {gc}44;'
                            f'padding:2px 8px;border-radius:4px">{grade}</span>'
                            f'<div style="margin-top:6px;font-size:11px;color:#8a9bc2">'
                            f'1M: <b style="color:{"#16c784" if r1m_v>0 else "#ea3a44"}">'
                            f'{r1m_v:+.1f}%</b>&nbsp;&nbsp;'
                            f'3M: <b style="color:{"#16c784" if r3m_v>0 else "#ea3a44"}">'
                            f'{r3m_v:+.1f}%</b>&nbsp;&nbsp;'
                            f'MA200: {a200}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        # ETF strength unavailable — just show the label
                        st.markdown(
                            f'<div style="background:var(--panel);border:1px solid var(--border);'
                            f'border-radius:8px;padding:12px 14px">'
                            f'<div style="font-size:9px;color:#556070;text-transform:uppercase;'
                            f'letter-spacing:.8px;margin-bottom:5px">{prefix}</div>'
                            f'<div style="font-size:14px;font-weight:700;color:#a78bfa">{lbl}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            # Level 3 — niche tags. A LIST, not one label: a multi-thematic
            # stock (e.g. a "Semiconductors" company that's really an
            # optical/Ethernet connectivity play) gets every tag that fits
            # instead of being force-fit into a single generic one.
            _niches = sc_ctx.get("level3")
            if _niches:
                with lvl_cols[2]:
                    _niche_chips = "".join(
                        f'<span style="display:inline-block;background:#a78bfa18;'
                        f'border:1px solid #a78bfa44;color:#a78bfa;font-size:11px;'
                        f'font-weight:700;padding:3px 9px;border-radius:12px;'
                        f'margin:0 4px 6px 0">{_n["label"]}</span>'
                        for _n in _niches
                    )
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-radius:8px;padding:12px 14px">'
                        f'<div style="font-size:9px;color:#556070;text-transform:uppercase;'
                        f'letter-spacing:.8px;margin-bottom:7px">🔬 Niche Themes</div>'
                        f'<div>{_niche_chips}</div>'
                        f'<div style="font-size:9px;color:#556070;margin-top:6px">'
                        f'From industry classification + business description — '
                        f'descriptive, not a verified index/ETF weighting.</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # ── Risk Snapshot (compact — full interactive sizing/correlation/
        # Risk-of-Ruin tools live in 🧠 Alpha Lab, not duplicated here) ────────
        with st.expander("🛡 Risk Snapshot"):
            _rs_c1, _rs_c2, _rs_c3 = st.columns(3)
            with _rs_c1:
                _rs_ti = mod_rt.get_trade_inputs(symbol)
                _rs_plan = (mod_rt.trade_plan(_rs_ti["price"], _rs_ti["atr"], 50_000, 1.0)
                           if not _rs_ti.get("error") and _rs_ti.get("atr") else {"error": "n/a"})
                if _rs_plan.get("error"):
                    st.caption("Position sizing unavailable (no ATR data).")
                else:
                    st.metric("Size @ 1% risk / $50k acct", f"{_rs_plan['shares']:,} sh",
                             f"stop -{_rs_plan['stop_dist_pct']:.1f}%", delta_color="off",
                             help="Van Tharp 1R method, 2×ATR stop, illustrative $50k account. "
                                  "Custom sizing, Kelly, and Risk-of-Ruin live in Alpha Lab.")
            with _rs_c2:
                _rs_eq = mod_eq.analyze(symbol)
                if _rs_eq.get("error") or not _rs_eq.get("checks"):
                    st.caption("Earnings quality unavailable.")
                else:
                    _rs_flags = sum(1 for _, _st, _ in _rs_eq["checks"] if _st == "flag")
                    st.metric("Earnings Quality",
                             f"{_rs_eq['score']}/10" if _rs_eq.get("score") is not None else "—",
                             f"{_rs_flags} red flag(s)" if _rs_flags else "clean",
                             delta_color="inverse" if _rs_flags else "off",
                             help="Full forensic checklist (dilution, SBC, cash-backing, "
                                  "receivables, FCF conversion, debt trend) is in "
                                  "Fundamentals + Earnings.")
            with _rs_c3:
                _rs_fit_src = []
                try:
                    for _rs_n, _rs_tp in mod_tp.load_all()["portfolios"].items():
                        _rs_fit_src.append((f"Tracker: {_rs_n}",
                                           tuple(sorted(_rs_tp["positions"].keys()))))
                except Exception:
                    pass
                if not _rs_fit_src:
                    st.caption("No tracked portfolio yet — build one in 🎯 Tracker to check fit.")
                else:
                    _rs_n0, _rs_syms0 = _rs_fit_src[0]
                    _rs_fit = mod_rt.portfolio_fit(symbol, _rs_syms0)
                    if _rs_fit.get("error") or _rs_fit.get("avg_corr") is None:
                        st.caption("Portfolio fit unavailable.")
                    else:
                        st.metric(f"Fit vs {_rs_n0}", f"{_rs_fit['avg_corr']:.2f} avg corr",
                                 _rs_fit["verdict"].split(" — ")[0],
                                 delta_color="inverse" if "DUPLICATES" in _rs_fit["verdict"] else "off",
                                 help=_rs_fit["verdict"])
            st.caption("Interactive sizing, portfolio correlation/PCA, and Risk-of-Ruin tools "
                      "live in 🧠 Alpha Lab — this is a glance, not the full workflow.")

        st.markdown("---")

        # ── Tabs ─────────────────────────────────────────────────────────────
        tab_ov, tab_fund, tab_tech, tab_inst, tab_macro_peers, tab_panel, tab_seasonal, tab_13f, tab_dcf = st.tabs([
            "📊 Overview", "💰 Fundamentals + Earnings", "📐 Technical + Momentum",
            "🏦 Institutional + Analysts", "🌍 Macro + Peers + History", "🧑‍⚖️ Experts & Models",
            "📅 Seasonality", "🏛 13F Smart Money", "💎 DCF",
        ])

        # ── Overview ─────────────────────────────────────────────────────────
        with tab_ov:
            # ── 🎯 Opportunity Lens — quality vs condition, opportunity vs trap ──
            _opp = mod_opp.analyze(symbol)

            # ── 📋 Bottom Line — one decisive stance + concrete action steps,
            # synthesized from the Scanner Verdict, the quality-vs-confirmation
            # pattern (see modules/scoring.py::classify_pattern), and the
            # Opportunity Lens quadrant below. No LLM call — deterministic
            # from numbers already computed on this page, so it's always
            # available and reproducible.
            if not _opp.get("error"):
                _bl_sup = _bl_res = _bl_ma50 = None
                try:
                    _bl_df = t_data.get("df")
                    if _bl_df is not None and not _bl_df.empty:
                        _bl_levels = mod_ind.support_resistance_levels(_bl_df)
                        _bl_sup = _bl_levels["support"][0] if _bl_levels["support"] else None
                        _bl_res = _bl_levels["resistance"][0] if _bl_levels["resistance"] else None
                        _bl_ma50v = _bl_df["Close"].squeeze().rolling(50).mean().iloc[-1]
                        _bl_ma50 = float(_bl_ma50v) if pd.notna(_bl_ma50v) else None
                except Exception:
                    pass

                _plan = mod_scoring.action_plan(
                    score_label=s_data["label"], quadrant=_opp["quadrant"],
                    pattern=_pattern["pattern"], current_price=price,
                    nearest_support=_bl_sup, nearest_resistance=_bl_res, ma50=_bl_ma50,
                )
                _plan_steps_html = "".join(
                    f'<div style="font-size:12.5px;color:#cdd6f4;margin-top:6px;'
                    f'padding-left:14px;position:relative">'
                    f'<span style="position:absolute;left:0;color:{_plan["color"]}">→</span>'
                    f'{_html.escape(_step)}</div>'
                    for _step in _plan["steps"]
                )
                st.markdown(
                    f'<div style="background:{_plan["color"]}14;border:2px solid {_plan["color"]}60;'
                    f'border-radius:12px;padding:16px 20px;margin-bottom:14px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'flex-wrap:wrap;gap:8px">'
                    f'<span style="font-family:IBM Plex Mono,monospace;font-size:17px;'
                    f'font-weight:800;color:{_plan["color"]}">📋 {_html.escape(_plan["action"])}</span>'
                    f'<span style="font-size:11px;color:#8a9bc2">'
                    f'Verdict {s_data["final"]}/10 {_html.escape(s_data["label"])} · '
                    f'{_html.escape(_opp["quadrant"])} · {_pattern["icon"]} {_html.escape(_pattern["pattern"])}'
                    f'</span></div>{_plan_steps_html}</div>',
                    unsafe_allow_html=True,
                )

            if not _opp.get("error"):
                _opp_c = _opp["color"]
                _dd_s = (f' · {_opp["drawdown"]:+.0f}% from 52w high'
                         if _opp.get("drawdown") is not None else "")
                _sig_html = "".join(
                    f'<span style="font-size:11px;color:{"#16c784" if ok else "#556070"};'
                    f'margin-right:10px;cursor:help" title="{_html.escape(det, quote=True)}">'
                    f'{"●" if ok else "○"} {_html.escape(lbl)}</span>'
                    for lbl, ok, det in _opp["signals"]
                )
                _q_tip = _html.escape(
                    "QUALITY (momentum-free — is the business itself intact?):\n" +
                    "\n".join(f"• {l}: {d}" for l, _, _, d in _opp["quality_parts"]),
                    quote=True)
                _c_tip = _html.escape(
                    "CONDITION (price action — is the stock ACTING well right now?):\n"
                    f"• {_opp.get('condition_detail', 'n/a')}\n"
                    "Built from: price vs MA50, price vs MA200, 1-month return, 3-month return.",
                    quote=True)
                st.markdown(
                    f'<div style="background:var(--panel);border:2px solid {_opp_c};border-radius:12px;'
                    f'padding:16px 20px;margin-bottom:14px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'flex-wrap:wrap;gap:8px">'
                    f'<span style="font-family:IBM Plex Mono,monospace;font-size:18px;'
                    f'font-weight:800;color:{_opp_c}">🎯 {_html.escape(_opp["quadrant"])}</span>'
                    f'<span style="font-size:12px;color:#8a9bc2">'
                    f'<span style="cursor:help" title="{_q_tip}">Quality '
                    f'<b style="color:#e8edf8">{_opp["quality"]}/10</b> ⓘ</span> · '
                    f'<span style="cursor:help" title="{_c_tip}">Condition '
                    f'<b style="color:#e8edf8">{_opp["condition"]}/10</b> ⓘ</span>{_dd_s}</span>'
                    f'</div>'
                    f'<div style="font-size:12.5px;color:#cdd6f4;margin-top:8px;line-height:1.6">'
                    f'{_html.escape(_opp["guidance"])}</div>'
                    f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid #1e2535">'
                    f'<span style="font-size:10px;color:#556070;text-transform:uppercase;'
                    f'letter-spacing:1px;margin-right:10px">Reversal readiness '
                    f'{_opp["readiness"]}/5</span>{_sig_html}</div>'
                    + (
                        f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid #1e2535">'
                        f'<span style="font-size:10px;color:#556070;text-transform:uppercase;'
                        f'letter-spacing:1px;margin-right:10px">Context '
                        f'({_opp["n_support"]} supportive · {_opp["n_negative"]} negative)</span>'
                        + "".join(
                            f'<span style="font-size:11px;margin-right:10px;cursor:help;'
                            f'color:{"#16c784" if c["stance"] == "supportive" else "#ea3a44" if c["stance"] == "negative" else "#8a9bc2"}" '
                            f'title="{_html.escape(c["detail"], quote=True)}">'
                            f'{c["icon"]} {_html.escape(c["label"])}</span>'
                            for c in _opp["context"]
                        ) + '</div>'
                        if _opp.get("context") else ""
                    )
                    + '</div>',
                    unsafe_allow_html=True,
                )

                # 🤖 Why is it falling? — headline-driven driver classification
                if _opp.get("drawdown") is not None and _opp["drawdown"] <= -15:
                    if st.button(f"🤖 Why is {symbol} falling? (AI reads the headlines)",
                                 key=f"_whyfall_{symbol}"):
                        with st.spinner("Reading recent headlines..."):
                            _wf = mod_opp.why_falling(symbol, _opp["drawdown"])
                        st.session_state[f"_whyfall_res_{symbol}"] = _wf
                    _wf = st.session_state.get(f"_whyfall_res_{symbol}")
                    if _wf:
                        if _wf.get("error"):
                            st.info(_wf["error"])
                        else:
                            _dt_c = {"TRANSIENT": "#16c784", "STRUCTURAL": "#ea3a44",
                                     "MIXED": "#f0b90b", "UNCLEAR": "#8a9bc2"}.get(
                                         _wf.get("driver_type", ""), "#8a9bc2")
                            st.markdown(
                                f'<div style="background:var(--panel);border-left:3px solid {_dt_c};'
                                f'border-radius:6px;padding:10px 16px;margin-bottom:10px">'
                                f'<span style="color:{_dt_c};font-weight:700;font-size:12px">'
                                f'{_html.escape(_wf.get("driver_type", ""))} DECLINE</span>'
                                f'<div style="font-size:12.5px;color:#cdd6f4;margin-top:4px">'
                                f'{_html.escape(_wf.get("driver", ""))}</div>'
                                f'<div style="font-size:12px;color:#8a9bc2;margin-top:4px">'
                                f'♻️ {_html.escape(_wf.get("recoverable", ""))}</div>'
                                f'<div style="font-size:12px;color:#f0b90b;margin-top:4px">'
                                f'👁 Watch: {_html.escape(_wf.get("watch_for", ""))}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

            # ── 📡 AV News Sentiment (real NLP scores; on-demand — 25 req/day) ──
            from config import ALPHA_VANTAGE_API_KEY as _av_key
            if _av_key:
                _av_state = st.session_state.get(f"_av_sent_{symbol}")
                if _av_state is None:
                    if st.button("📡 Load news sentiment (Alpha Vantage NLP)",
                                 key=f"_av_btn_{symbol}",
                                 help="Real per-article sentiment scores from Alpha Vantage's NLP "
                                      "engine — one request per symbol per day (cached 24h). "
                                      "Free tier budget: 25 symbols/day."):
                        with st.spinner("Scoring recent news..."):
                            st.session_state[f"_av_sent_{symbol}"] = mod_av.news_sentiment(symbol)
                        st.rerun()
                else:
                    _av = _av_state
                    if _av.get("error"):
                        st.caption(f"📡 News sentiment unavailable: {_av['error']}")
                    else:
                        _av_d = _av["dist"]
                        _av_tops = "".join(
                            f'<div style="font-size:11px;color:#8a9bc2;padding:1px 0;'
                            f'white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'
                            f'<b style="color:{"#16c784" if t["score"] >= 0.15 else "#ea3a44" if t["score"] <= -0.15 else "#f0b90b"}">'
                            f'{t["score"]:+.2f}</b> {_html.escape(t["title"][:85])}</div>'
                            for t in _av["top"][:3]
                        )
                        st.markdown(
                            f'<div style="background:var(--panel);border:1px solid var(--border);'
                            f'border-left:4px solid {_av["color"]};border-radius:8px;'
                            f'padding:12px 18px;margin-bottom:14px">'
                            f'<div style="display:flex;justify-content:space-between;'
                            f'align-items:center;flex-wrap:wrap;gap:8px">'
                            f'<span style="font-weight:700;color:#e8edf8">📡 News Sentiment '
                            f'<span style="color:{_av["color"]}">{_av["label"]}</span> '
                            f'<span style="font-family:IBM Plex Mono,monospace;font-size:13px">'
                            f'({_av["avg_score"]:+.2f})</span></span>'
                            f'<span style="font-size:11px;color:#8a9bc2">'
                            f'{_av["n_articles"]} scored articles · '
                            f'<span style="color:#16c784">{_av_d["bullish"]}↑</span> '
                            f'<span style="color:#f0b90b">{_av_d["neutral"]}→</span> '
                            f'<span style="color:#ea3a44">{_av_d["bearish"]}↓</span> · '
                            f'Alpha Vantage NLP</span></div>'
                            f'{_av_tops}</div>',
                            unsafe_allow_html=True,
                        )

            col_radar, col_kpi = st.columns([1, 1.3])
            with col_radar:
                st.markdown('<div class="panel-head">SCORE RADAR</div>', unsafe_allow_html=True)
                st.plotly_chart(
                    render_radar(s_data["breakdown"], SCORE_WEIGHTS),
                    width="stretch",
                )
                # Score trend — deterioration/improvement before the price shows it
                _sdelta = mod_shist.get_delta(symbol, days=30)
                if _sdelta:
                    _sd_c = ("#16c784" if _sdelta["delta"] > 0.2 else
                             "#ea3a44" if _sdelta["delta"] < -0.2 else "#8a9bc2")
                    _sd_arrow = "▲" if _sdelta["delta"] > 0.2 else "▼" if _sdelta["delta"] < -0.2 else "→"
                    st.markdown(
                        f'<div style="font-family:IBM Plex Mono,monospace;font-size:12px;'
                        f'color:#8a9bc2;cursor:help" title="Composite score tracked each time '
                        f'you analyze this stock. A sliding score often precedes the price — '
                        f'the fundamentals/technicals deteriorate before the chart admits it.">'
                        f'Score trend: {_sdelta["then"]:.1f} ({_sdelta["then_date"]}) '
                        f'<b style="color:{_sd_c}">{_sd_arrow} {_sdelta["now"]:.1f} '
                        f'({_sdelta["delta"]:+.1f})</b></div>',
                        unsafe_allow_html=True,
                    )
            with col_kpi:
                st.markdown('<div class="panel-head">KEY METRICS</div>', unsafe_allow_html=True)
                st.caption("Colored vs. this stock's own peer group (same names as the "
                           "Relative tab) — not a fixed universal bar. A 25% gross margin "
                           "reads differently for a grocer than for a SaaS company.")
                _m_ov = f_data.get("metrics", {})
                _peer_df = p_data.get("df")

                def _peer_tone(col, val, higher_is_better=True):
                    """Percentile rank vs. this stock's own peer group instead of a fixed
                    universal threshold. Falls back to neutral if there's no usable peer
                    data (e.g. Haiku couldn't find real peers for this ticker)."""
                    if val is None or _peer_df is None or _peer_df.empty or col not in _peer_df.columns:
                        return "mg-base"
                    peers = _peer_df[_peer_df["Ticker"] != symbol.upper()][col].dropna()
                    peers = peers[peers.apply(lambda x: isinstance(x, (int, float)))]
                    if len(peers) < 2:
                        return "mg-base"
                    rank = (peers < val).mean() if higher_is_better else (peers > val).mean()
                    return "mg-up" if rank >= 0.66 else "mg-down" if rank <= 0.33 else "mg-warn"

                def _kpi_cell(label, val_str, tone="mg-base", peer_col=None):
                    _tip = _TIP.get(label) or _EXPLAIN.get(label, "")
                    if peer_col and _peer_df is not None and not _peer_df.empty:
                        _peers_list = _peer_df[_peer_df["Ticker"] != symbol.upper()]["Ticker"].tolist()
                        if _peers_list:
                            _tip = (_tip + f" Colored vs. peers: {', '.join(_peers_list)}.").strip()
                    _title = f' title="{_html.escape(_tip, quote=True)}"' if _tip else ""
                    return (f'<div class="mg-cell" style="cursor:help"{_title}>'
                            f'<div class="mg-label">{label}</div>'
                            f'<div class="mg-val {tone}">{val_str}</div></div>')

                _ov_cells = [
                    _kpi_cell("Revenue Growth", fmt_pct(_m_ov.get("Revenue Growth")),
                              _peer_tone("Rev Growth", _m_ov.get("Revenue Growth"), True),
                              "Rev Growth"),
                    _kpi_cell("Gross Margin",   fmt_pct(_m_ov.get("Gross Margin")),
                              _peer_tone("Gross Margin", _m_ov.get("Gross Margin"), True),
                              "Gross Margin"),
                    _kpi_cell("FCF Margin",     fmt_pct(_m_ov.get("FCF Margin")),
                              _peer_tone("FCF Margin", _m_ov.get("FCF Margin"), True),
                              "FCF Margin"),
                    _kpi_cell("P/S Ratio",
                              f'{_m_ov["P/S Ratio"]:.1f}x' if _m_ov.get("P/S Ratio") else "N/A",
                              _peer_tone("P/S", _m_ov.get("P/S Ratio"), False),
                              "P/S"),
                    _kpi_cell("Forward P/E",
                              f'{_m_ov["Forward P/E"]:.1f}x' if _m_ov.get("Forward P/E") else "N/A",
                              _peer_tone("Fwd P/E", _m_ov.get("Forward P/E"), False),
                              "Fwd P/E"),
                    _kpi_cell("Debt/Equity",
                              f'{_m_ov["Debt/Equity"]:.2f}' if _m_ov.get("Debt/Equity") else "N/A",
                              _peer_tone("Debt/Equity", _m_ov.get("Debt/Equity"), False),
                              "Debt/Equity"),
                ]
                st.markdown(f'<div class="metric-grid">{"".join(_ov_cells)}</div>',
                            unsafe_allow_html=True)

                # 52W range progress bar
                _low52_ov  = info.get("fiftyTwoWeekLow",  0) or 0
                _high52_ov = info.get("fiftyTwoWeekHigh", 0) or 0
                _pos52 = max(2, min(98, (price - _low52_ov) / (_high52_ov - _low52_ov) * 100)) \
                         if _high52_ov > _low52_ov else 50
                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px">'
                    f'<div class="mg-label">52W RANGE</div>'
                    f'<div style="position:relative;height:6px;background:#2a3348;border-radius:3px">'
                    f'<div style="position:absolute;left:0;width:{_pos52}%;height:100%;'
                    f'background:linear-gradient(90deg,#ea3a44,#f0b90b,#16c784);border-radius:3px"></div>'
                    f'<div style="position:absolute;left:{_pos52}%;top:-4px;width:14px;height:14px;'
                    f'background:#e8edf8;border-radius:50%;transform:translateX(-50%);'
                    f'box-shadow:0 0 6px rgba(255,255,255,.2)"></div>'
                    f'</div>'
                    f'<div style="display:flex;justify-content:space-between;margin-top:6px;'
                    f'font-family:var(--mono);font-size:10px">'
                    f'<span style="color:#ea3a44">Low ${_low52_ov:.0f}</span>'
                    f'<span style="color:#e8edf8;font-weight:700">${price:.2f}</span>'
                    f'<span style="color:#16c784">High ${_high52_ov:.0f}</span>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

            # Signals + Momentum + Analyst
            col_sig_ov, col_mo_ov, col_an_ov = st.columns(3)
            with col_sig_ov:
                st.markdown('<div class="panel-head">TECHNICAL SIGNALS</div>', unsafe_allow_html=True)
                _sigs_ov = t_data.get("signals", [])[:4]
                if _sigs_ov:
                    for _em, _msg in _sigs_ov:
                        st.markdown(f"{_em} {_msg}")
                else:
                    st.caption("No active signals.")
                _rsi_ov = t_data.get("rsi")
                if _rsi_ov:
                    # Context-aware: verdict + hover tooltip depend on THIS stock's trend regime
                    try:
                        _rctx_ov = mod_mctx.rsi_in_context(
                            get_price_history(symbol, period="2y")["Close"].squeeze())
                    except Exception:
                        _rctx_ov = {"error": True}
                    if not _rctx_ov.get("error"):
                        _rc_ov = _rctx_ov["verdict_color"]
                        _rb_lo_ov, _rb_hi_ov = _rctx_ov["normal_band"]
                        st.markdown(
                            f'<div style="margin-top:8px;font-family:var(--mono);font-size:12px;'
                            f'cursor:help" title="{_html.escape(_rctx_ov["tooltip"], quote=True)}">'
                            f'RSI: <b style="color:{_rc_ov}">{_rsi_ov:.1f}</b>'
                            f' <span style="color:{_rc_ov};font-size:11px">· {_html.escape(_rctx_ov["verdict"])}</span>'
                            f' <span style="color:#556070;font-size:10px">(normal here: {_rb_lo_ov}–{_rb_hi_ov} — hover ⓘ)</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        _rc_ov = "#ea3a44" if _rsi_ov > 70 else "#16c784" if _rsi_ov < 30 else "#8a9bc2"
                        st.markdown(
                            f'<div style="margin-top:8px;font-family:var(--mono);font-size:12px">'
                            f'RSI: <b style="color:{_rc_ov}">{_rsi_ov:.1f}</b></div>',
                            unsafe_allow_html=True,
                        )

            with col_mo_ov:
                st.markdown('<div class="panel-head">MOMENTUM</div>', unsafe_allow_html=True)
                _mo_ret_ov  = mo_data.get("returns", {})
                _spy_ret_ov = mo_data.get("spy_returns", {})
                for _period_ov in ["1M", "3M", "6M", "1Y"]:
                    _r_ov    = (_mo_ret_ov.get(_period_ov) or 0) * 100
                    _spy_ov  = (_spy_ret_ov.get(_period_ov) or 0) * 100
                    _diff_ov = _r_ov - _spy_ov
                    _rc2     = "#16c784" if _r_ov  > 0 else "#ea3a44"
                    _dc2     = "#16c784" if _diff_ov > 0 else "#ea3a44" if _diff_ov < 0 else "#8a9bc2"
                    st.markdown(
                        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
                        f'margin-bottom:5px;font-family:var(--mono);font-size:12px">'
                        f'<span style="color:#8a9bc2;min-width:28px">{_period_ov}:</span>'
                        f'<span style="color:{_rc2};font-weight:700">{_r_ov:+.1f}%</span>'
                        f'<span style="color:{_dc2};font-size:10px">vs SPY {_diff_ov:+.1f}%</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            with col_an_ov:
                st.markdown('<div class="panel-head">ANALYST CONSENSUS</div>', unsafe_allow_html=True)
                _rk_ov  = (info.get("recommendationKey") or "").lower().replace(" ", "_").replace("-", "_")
                _rm_ov  = info.get("recommendationMean")
                _pt_ov  = info.get("targetMeanPrice")
                _na_ov  = info.get("numberOfAnalystOpinions") or 0
                _kmap_ov = {
                    "strong_buy":   ("Strong Buy",   "#16c784"),
                    "buy":          ("Buy",          "#a3e635"),
                    "hold":         ("Hold",         "#f0b90b"),
                    "underperform": ("Underperform", "#f97316"),
                    "sell":         ("Sell",         "#ea3a44"),
                }
                _al_ov, _ac_ov = _kmap_ov.get(_rk_ov, ("N/A", "#8a9bc2"))
                _bp_ov = round(max(5, min(95, 95 - ((_rm_ov or 3) - 1) * 22.5)), 1) if _rm_ov else None
                if _rm_ov:
                    _up_ov   = f"{((_pt_ov / price - 1)*100):+.1f}%" if _pt_ov and price else "N/A"
                    _up_c_ov = "#16c784" if _pt_ov and price and _pt_ov > price else "#ea3a44"
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px">'
                        f'<div style="font-size:22px;font-weight:700;color:{_ac_ov};font-family:var(--mono)">{_al_ov}</div>'
                        f'<div style="font-size:11px;color:#8a9bc2;margin:3px 0">{_na_ov} analysts</div>'
                        f'<div style="height:4px;background:#2a3348;border-radius:2px;margin:8px 0 4px">'
                        f'<div style="width:{_bp_ov:.0f}%;height:100%;background:{_ac_ov};border-radius:2px"></div></div>'
                        f'<div style="font-size:10px;color:{_ac_ov};font-family:var(--mono)">{_bp_ov:.0f}% bullish</div>'
                        f'<div style="font-size:11px;color:{_up_c_ov};font-family:var(--mono);margin-top:6px">'
                        f'PT Upside: {_up_ov}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No analyst data.")

            st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)

            # Macro + Earnings + Peers
            col_mac_ov, col_ea_ov, col_peer_ov = st.columns(3)
            with col_mac_ov:
                st.markdown('<div class="panel-head">MACRO ENVIRONMENT</div>', unsafe_allow_html=True)
                _ms_ov = m_data.get("score", 5)
                _mc_ov = "#16c784" if _ms_ov >= 7 else "#f0b90b" if _ms_ov >= 5 else "#ea3a44"
                st.markdown(
                    f'<div style="font-size:28px;font-weight:700;color:{_mc_ov};font-family:var(--mono)">'
                    f'{_ms_ov}/10</div>',
                    unsafe_allow_html=True,
                )
                for _tw in m_data.get("tailwinds", [])[:2]:
                    st.markdown(
                        f'<div style="font-size:11px;color:#16c784;margin-top:3px">✅ {_html.escape(_tw)}</div>',
                        unsafe_allow_html=True)
                for _hw in m_data.get("headwinds", [])[:2]:
                    st.markdown(
                        f'<div style="font-size:11px;color:#ea3a44;margin-top:3px">⚠️ {_html.escape(_hw)}</div>',
                        unsafe_allow_html=True)

            with col_ea_ov:
                st.markdown('<div class="panel-head">EARNINGS</div>', unsafe_allow_html=True)
                _nxt_ov    = e_data.get("next_earnings")
                _timing_ov = e_data.get("timing", "—")
                if _nxt_ov:
                    _days_ov = (_nxt_ov - _date.today()).days
                    _dc_ov   = "#16c784" if _days_ov > 30 else "#f0b90b" if _days_ov > 7 else "#ea3a44"
                    st.markdown(
                        f'<div style="font-size:20px;font-weight:700;color:{_dc_ov};font-family:var(--mono)">'
                        f'{_nxt_ov.strftime("%b %d, %Y")}</div>'
                        f'<div style="font-size:11px;color:#8a9bc2">'
                        f'{"In " + str(_days_ov) + " days" if _days_ov >= 0 else str(-_days_ov) + " days ago"}'
                        f' · {_timing_ov}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("Next earnings date unknown.")
                _br_ov = e_data.get("beat_rate")
                if _br_ov is not None:
                    _bn_ov, _bt_ov = e_data.get("beat_n", 0), e_data.get("beat_total", 0)
                    _brc_ov = "#16c784" if _br_ov >= 70 else "#f0b90b" if _br_ov >= 50 else "#ea3a44"
                    st.markdown(
                        f'<div style="margin-top:8px;font-family:var(--mono);font-size:12px">'
                        f'Beat Rate: <b style="color:{_brc_ov}">{_br_ov}%</b> ({_bn_ov}/{_bt_ov})</div>',
                        unsafe_allow_html=True,
                    )
                _avg_surp_ov = e_data.get("avg_surprise")
                if _avg_surp_ov is not None:
                    _surc_ov = "#16c784" if _avg_surp_ov > 0 else "#ea3a44"
                    st.markdown(
                        f'<div style="font-family:var(--mono);font-size:12px">'
                        f'Avg Surprise: <b style="color:{_surc_ov}">{_avg_surp_ov:+.1f}%</b></div>',
                        unsafe_allow_html=True,
                    )

            with col_peer_ov:
                st.markdown('<div class="panel-head">PEER COMPARISON</div>', unsafe_allow_html=True)
                _ps_ov  = p_data.get("score", 5)
                _psc_ov = "#16c784" if _ps_ov >= 7 else "#f0b90b" if _ps_ov >= 5 else "#ea3a44"
                st.markdown(
                    f'<div style="font-size:20px;font-weight:700;color:{_psc_ov};font-family:var(--mono)">'
                    f'Score: {_ps_ov:.1f}/10</div>',
                    unsafe_allow_html=True,
                )
                _pl_ov = p_data.get("peers", [])
                if _pl_ov:
                    st.markdown(
                        f'<div style="font-size:11px;color:#8a9bc2;margin-top:3px">vs {len(_pl_ov)} peers</div>',
                        unsafe_allow_html=True,
                    )
                _pdf_ov = p_data.get("df", pd.DataFrame())
                if not _pdf_ov.empty and symbol.upper() in _pdf_ov["Ticker"].values:
                    _tr_ov = _pdf_ov[_pdf_ov["Ticker"] == symbol.upper()].iloc[0]
                    _rg_ov = _tr_ov.get("Rev Growth")
                    if pd.notna(_rg_ov):
                        _rgc_ov = "#16c784" if _rg_ov > 0.15 else "#f0b90b" if _rg_ov > 0 else "#ea3a44"
                        st.markdown(
                            f'<div style="font-family:var(--mono);font-size:12px;margin-top:6px">'
                            f'Rev Growth: <b style="color:{_rgc_ov}">{_rg_ov*100:.1f}%</b></div>',
                            unsafe_allow_html=True,
                        )
                if _pl_ov:
                    st.markdown(
                        f'<div style="font-size:10px;color:#556070;margin-top:5px">'
                        f'Peers: {", ".join(_pl_ov[:4])}</div>',
                        unsafe_allow_html=True,
                    )

            # ETF holdings (shown only when symbol is an ETF)
            if info.get("quoteType", "").upper() in ("ETF", "MUTUALFUND"):
                mod_etf.render_etf_holdings(symbol, max_rows=15)

            # Expert summary strip (shown when panel has been loaded)
            _ov_exp_key = f"experts_{symbol}"
            if _ov_exp_key in st.session_state:
                _ov_experts = st.session_state[_ov_exp_key]
                _all_fallback = all(
                    ex.get("decision") == "HOLD" and
                    any(x in str(ex.get("rationale", "")) for x in ("Error:", "No response", "Add ANTHROPIC"))
                    for ex in _ov_experts
                )
                if not _all_fallback:
                    st.markdown("---")
                    st.markdown('<div class="panel-head">EXPERT PANEL VERDICT</div>',
                                unsafe_allow_html=True)
                    _d_colors_ov = {
                        "BUY": "#00c853", "SELL": "#ff1744",
                        "HOLD": "#ffd600", "WATCH": "#ff9800",
                    }
                    _chips_html = "".join(
                        f'<span style="display:inline-flex;align-items:center;gap:5px;'
                        f'background:var(--panel);border:1px solid var(--border);border-radius:6px;'
                        f'padding:5px 10px;margin:3px">'
                        f'<span style="font-size:14px">{_html.escape(str(ex["profile"]["icon"]))}</span>'
                        f'<span style="font-family:var(--mono);font-size:11px;color:#8a9bc2">'
                        f'{_html.escape(ex["name"])}</span>'
                        f'<span style="font-family:var(--mono);font-size:11px;font-weight:700;'
                        f'color:{_d_colors_ov.get(ex.get("decision","HOLD"),"#8a9bc2")}">'
                        f'{ex.get("decision","?")}</span>'
                        f'</span>'
                        for ex in _ov_experts
                    )
                    st.markdown(f'<div style="display:flex;flex-wrap:wrap;gap:4px">{_chips_html}</div>',
                                unsafe_allow_html=True)
                    st.caption("Run the 🧠 Experts tab to refresh verdicts.")

        # ── Fundamental + Earnings ────────────────────────────────────────────
        with tab_fund:
            # ── 🎯 In-Context Read — every metric judged for THIS stock ──────
            try:
                from modules.market_context import get_regime as _icr_regime
                _icr_reg = _icr_regime()
            except Exception:
                _icr_reg = {}
            try:
                _icr_close = get_price_history(symbol, period="2y")["Close"].squeeze()
            except Exception:
                _icr_close = None
            _icr = mod_mctx.interpret_all(symbol, info, _icr_close, _icr_reg)
            if _icr:
                _icr_rows = ""
                for _lbl_i, _r_i in _icr.items():
                    _icr_rows += (
                        f'<div style="display:flex;justify-content:space-between;align-items:center;'
                        f'gap:10px;padding:7px 4px;border-bottom:1px solid #1e2535;cursor:help" '
                        f'title="{_html.escape(_r_i["detail"], quote=True)}">'
                        f'<span style="font-size:12px;color:#8a9bc2;min-width:105px">{_html.escape(_lbl_i)}</span>'
                        f'<span style="font-family:IBM Plex Mono,monospace;font-size:13px;'
                        f'font-weight:700;color:#e8edf8">{_html.escape(_r_i["value_s"])}</span>'
                        f'<span style="font-size:10px;color:#556070;flex:1;text-align:center">'
                        f'{_html.escape(_r_i["band_s"])}</span>'
                        f'<span style="font-size:10px;font-weight:700;color:{_r_i["color"]};'
                        f'background:{_r_i["color"]}1a;border:1px solid {_r_i["color"]}33;'
                        f'padding:2px 8px;border-radius:4px;white-space:nowrap">'
                        f'{_html.escape(_r_i["verdict"])}</span>'
                        f'</div>'
                    )
                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                    f'padding:14px 18px;margin-bottom:14px">'
                    f'<div style="font-size:11px;color:#556070;text-transform:uppercase;'
                    f'letter-spacing:1px;margin-bottom:6px">🎯 In-Context Read — each metric judged '
                    f'against THIS stock\'s sector, size, growth &amp; regime · hover any row for the why</div>'
                    f'{_icr_rows}</div>',
                    unsafe_allow_html=True,
                )

            # ── 📚 Metric Ranges for THIS stock (educational) ────────────────
            with st.expander("📚 What's a healthy range for THIS stock? (learning mode)", expanded=False):
                st.caption("The same P/E can be cheap for one company and absurd for another. "
                           "Claude assesses each metric against what's NORMAL for this stock's "
                           "sector, size, growth profile and the current macro regime.")
                if st.button("🎓 Assess metric ranges", key=f"_mctx_btn_{symbol}"):
                    with st.spinner("Building context-aware ranges..."):
                        try:
                            from modules.market_context import get_regime as _mr_regime
                            _mc_reg = _mr_regime()
                            _mc_reg_s = f"{_mc_reg.get('regime','')} — VIX {_mc_reg.get('signals',{}).get('vix','?')}"
                        except Exception:
                            _mc_reg_s = "Unknown"
                        _mc_profile = mod_mctx.build_profile(symbol, info, t_data.get("rsi"))
                        st.session_state[f"_mctx_{symbol}"] = mod_mctx.contextual_ranges(
                            symbol, json.dumps(_mc_profile, default=str), _mc_reg_s)
                _mctx_rows = st.session_state.get(f"_mctx_{symbol}")
                if _mctx_rows:
                    _as_c = {"LOW": "#4da3ff", "FAIR": "#16c784", "HIGH": "#ea3a44"}
                    for _mr in _mctx_rows:
                        _a = str(_mr.get("assessment", "")).upper()
                        _ac = _as_c.get(_a, "#556070")
                        st.markdown(
                            f'<div style="background:var(--panel);border-left:3px solid {_ac};'
                            f'border-radius:6px;padding:8px 14px;margin-bottom:6px">'
                            f'<div style="display:flex;justify-content:space-between;flex-wrap:wrap">'
                            f'<b style="color:#e8edf8">{_html.escape(str(_mr.get("metric","")))}'
                            f' = {_html.escape(str(_mr.get("value","")))}</b>'
                            f'<span style="color:{_ac};font-weight:700;font-size:12px">{_html.escape(_a)}'
                            f' <span style="color:#8a9bc2;font-weight:400">'
                            f'(normal here: {_html.escape(str(_mr.get("healthy_range","")))})</span></span></div>'
                            f'<div style="font-size:12px;color:#8a9bc2;margin-top:2px">'
                            f'{_html.escape(str(_mr.get("explanation","")))}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                elif _mctx_rows is not None:
                    st.info("No assessment returned — check ANTHROPIC_API_KEY and retry.")

            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown('<div class="panel-head">KEY METRICS & MULTIPLES</div>', unsafe_allow_html=True)
                metrics = f_data["metrics"]

                def _mg(label, val_str, hint="", tone="mg-base"):
                    v_text, v_color = _VERDICT.get(
                        (label, tone),
                        _VERDICT_GENERIC.get(tone, ("", "#556070"))
                    )
                    badge = (
                        f'<span style="display:inline-block;font-size:10px;font-weight:700;'
                        f'color:{v_color};background:{v_color}1a;border:1px solid {v_color}44;'
                        f'padding:2px 7px;border-radius:4px;margin-top:5px">{v_text}</span>'
                    ) if v_text else ""
                    explain = _EXPLAIN.get(label, "")
                    explain_html = (
                        f'<div style="font-size:10.5px;color:#6b7a99;margin-top:5px;'
                        f'line-height:1.45;font-family:sans-serif">{explain}</div>'
                    ) if explain else ""
                    _tip_mg = _TIP.get(label, "")
                    _title_mg = f' title="{_tip_mg}"' if _tip_mg else ""
                    return (
                        f'<div class="mg-cell" style="cursor:help"{_title_mg}>'
                        f'<div class="mg-label">{label}</div>'
                        f'<div class="mg-val {tone}">{val_str}</div>'
                        f'{badge}'
                        f'{explain_html}'
                        f'{"<div class=mg-hint>" + hint + "</div>" if hint else ""}'
                        f'</div>'
                    )

                m = metrics
                _is_pre_profit = f_data.get("is_pre_profit", False)
                _missing_f     = f_data.get("missing_metrics", [])

                def _pe_label():
                    if m.get("Forward P/E"): return f'{m["Forward P/E"]:.1f}x'
                    return "N/A — pre-profit" if _is_pre_profit else "N/A"
                def _peg_label():
                    if m.get("PEG Ratio"): return f'{m["PEG Ratio"]:.2f}'
                    return "N/A — pre-profit" if _is_pre_profit else "N/A"
                def _fcf_label():
                    if m.get("FCF Yield") is not None: return fmt_pct(m["FCF Yield"])
                    return "N/A — negative FCF" if _is_pre_profit else "N/A"
                def _r40_label():
                    if m.get("Rule of 40") is not None: return f'{m["Rule of 40"]:.1f}'
                    return "N/A — data incomplete"

                cells = [
                    _mg("Market Cap",     fmt_num(m.get("Market Cap")), ""),
                    _mg("P/S Ratio",      f'{m["P/S Ratio"]:.1f}x' if m.get("P/S Ratio") else "N/A",
                        "", _tone(m.get("P/S Ratio"), 10, 40, False)),
                    _mg("Forward P/E",    _pe_label(),
                        "FY est.", _tone(m.get("Forward P/E"), 20, 60, False)),
                    _mg("PEG Ratio",      _peg_label(),
                        "Growth-adj.", _tone(m.get("PEG Ratio"), 1, 2.5, False)),
                    _mg("Revenue Growth", fmt_pct(m.get("Revenue Growth")),
                        "YoY", _tone(m.get("Revenue Growth"), 0.15, 0, True)),
                    _mg("Gross Margin",   fmt_pct(m.get("Gross Margin")),
                        "", _tone(m.get("Gross Margin"), 0.55, 0.25, True)),
                    _mg("FCF Yield",      _fcf_label(),
                        "", _tone(m.get("FCF Yield"), 0.03, 0, True)),
                    _mg("FCF Margin",     fmt_pct(m.get("FCF Margin")),
                        "", _tone(m.get("FCF Margin"), 0.15, 0, True)),
                    _mg("Debt/Equity",    f'{m["Debt/Equity"]:.2f}' if m.get("Debt/Equity") else "N/A",
                        "", _tone(m.get("Debt/Equity"), 0.5, 2, False)),
                    _mg("R&D % Revenue",  fmt_pct(m.get("R&D % Revenue")), ""),
                    _mg("Earnings Growth",fmt_pct(m.get("Earnings Growth")),
                        "YoY", _tone(m.get("Earnings Growth"), 0.10, 0, True)),
                    _mg("Rule of 40",     _r40_label(),
                        "SaaS health", _tone(m.get("Rule of 40"), 40, 0, True)),
                ]
                st.markdown(
                    f'<div class="metric-grid">{"".join(cells)}</div>',
                    unsafe_allow_html=True,
                )

                if _is_pre_profit:
                    st.markdown(
                        '<div style="background:#f9731618;border-left:3px solid #f97316;'
                        'padding:8px 12px;border-radius:0 5px 5px 0;font-size:11px;color:#f97316;margin-top:8px">'
                        '⚠️ Pre-profit company — P/E, PEG, and FCF metrics are N/A. '
                        'Scored as neutral (5/10). Growth rate and gross margin carry full weight.</div>',
                        unsafe_allow_html=True,
                    )
                elif _missing_f:
                    _n = len(_missing_f)
                    _names = ", ".join(_missing_f[:3]) + ("…" if _n > 3 else "")
                    st.markdown(
                        f'<div style="background:#f0b90b18;border-left:3px solid #f0b90b;'
                        f'padding:8px 12px;border-radius:0 5px 5px 0;font-size:11px;color:#f0b90b;margin-top:8px">'
                        f'⚠️ {_n} metric{"s" if _n>1 else ""} unavailable ({_names}) — scored as neutral (5/10).</div>',
                        unsafe_allow_html=True,
                    )

                r40 = metrics.get("Rule of 40")
                if r40 is not None:
                    color = "#16c784" if r40 > 40 else "#f97316" if r40 > 0 else "#ea3a44"
                    label_r40 = "Above threshold — healthy growth" if r40 > 40 else "Below threshold — monitor" if r40 > 0 else "Negative — concern"
                    st.markdown(
                        f'<div style="background:{color}18;border-left:3px solid {color};padding:10px 14px;border-radius:4px;margin-top:10px;font-family:var(--mono,monospace);font-size:12px">'
                        f'Rule of 40: <b style="color:{color}">{r40:.1f}</b> — {label_r40}</div>',
                        unsafe_allow_html=True,
                    )

            with col_r:
                st.subheader("Score Breakdown")
                scores_df = pd.DataFrame({
                    "Metric": list(f_data["scores"].keys()),
                    "Score":  list(f_data["scores"].values()),
                })
                fig_f = px.bar(
                    scores_df, x="Score", y="Metric", orientation="h",
                    color="Score", color_continuous_scale=["#d50000","#ff6d00","#ffd600","#64dd17","#00c853"],
                    range_color=[1, 10], range_x=[0, 10],
                )
                fig_f.update_layout(
                    paper_bgcolor="#0e1117", plot_bgcolor="#1a1f2e",
                    font_color="#e8eaf6", showlegend=False,
                    height=350, margin=dict(t=10, b=10),
                )
                st.plotly_chart(fig_f, width="stretch")

            # ── Earnings ─────────────────────────────────────────────────────
            st.markdown("---")
            st.markdown('<div class="panel-head">EARNINGS HISTORY & ESTIMATES</div>',
                        unsafe_allow_html=True)

            _nxt_f    = e_data.get("next_earnings")
            _timing_f = e_data.get("timing", "—")
            col_ea1, col_ea2, col_ea3 = st.columns(3)
            with col_ea1:
                if _nxt_f:
                    _days_f = (_nxt_f - _date.today()).days
                    _dc_f   = "#16c784" if _days_f > 30 else "#f0b90b" if _days_f > 7 else "#ea3a44"
                    _eps_est_str = f"EPS est: ${e_data['eps_estimate']:.2f}" if e_data.get("eps_estimate") else ""
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px">'
                        f'<div class="mg-label">NEXT EARNINGS</div>'
                        f'<div style="font-size:22px;font-weight:700;color:{_dc_f};font-family:var(--mono)">'
                        f'{_nxt_f.strftime("%b %d, %Y")}</div>'
                        f'<div style="font-size:11px;color:#8a9bc2;margin-top:3px">'
                        f'{"In " + str(_days_f) + " days" if _days_f >= 0 else str(-_days_f) + " days ago"}'
                        f' · {_timing_f}</div>'
                        f'{"<div style=font-size:11px;color:#8a9bc2;margin-top:3px>" + _eps_est_str + "</div>" if _eps_est_str else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.info("Next earnings date not yet scheduled.")
            with col_ea2:
                _br_f = e_data.get("beat_rate")
                if _br_f is not None:
                    _brc_f = "#16c784" if _br_f >= 70 else "#f0b90b" if _br_f >= 50 else "#ea3a44"
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px">'
                        f'<div class="mg-label">BEAT RATE</div>'
                        f'<div style="font-size:28px;font-weight:700;color:{_brc_f};font-family:var(--mono)">'
                        f'{_br_f}%</div>'
                        f'<div style="font-size:11px;color:#8a9bc2;margin-top:3px">'
                        f'{e_data.get("beat_n",0)}/{e_data.get("beat_total",0)} quarters beat</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            with col_ea3:
                _as_f = e_data.get("avg_surprise")
                _ar_f = e_data.get("avg_reaction")
                if _as_f is not None:
                    _asc_f = "#16c784" if _as_f > 0 else "#ea3a44"
                    _arc_line = (f'<div style="font-size:11px;color:{"#16c784" if (_ar_f or 0)>0 else "#ea3a44"};margin-top:3px>'
                                 f'Avg price reaction: {_ar_f:+.1f}%</div>') if _ar_f is not None else ""
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px">'
                        f'<div class="mg-label">AVG EARNINGS SURPRISE</div>'
                        f'<div style="font-size:22px;font-weight:700;color:{_asc_f};font-family:var(--mono)">'
                        f'{_as_f:+.1f}%</div>'
                        f'{_arc_line}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            _eh_f = e_data.get("history", [])
            col_eah, col_eps_chart = st.columns(2)
            with col_eah:
                if _eh_f:
                    st.markdown(
                        '<div class="panel-head" style="margin-top:12px">EARNINGS HISTORY (8 QUARTERS)</div>',
                        unsafe_allow_html=True)
                    _eh_df_f = pd.DataFrame(_eh_f)

                    def _cs(val):
                        if not isinstance(val, (int, float)) or pd.isna(val): return ""
                        return "color:#16c784;font-weight:600" if val > 0 else "color:#ea3a44;font-weight:600"

                    def _cr(val):
                        if not isinstance(val, (int, float)) or pd.isna(val): return ""
                        return "color:#16c784" if val > 0 else "color:#ea3a44"

                    st.dataframe(
                        _eh_df_f.style
                                .format({
                                    "Date":             str,
                                    "EPS Estimate":     lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                    "Reported EPS":     lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                    "Surprise %":       lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A",
                                    "Price Reaction %": lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A",
                                })
                                .map(_cs, subset=["Surprise %"])
                                .map(_cr, subset=["Price Reaction %"]),
                        width="stretch", hide_index=True,
                    )
                else:
                    st.info("No earnings history available.")

            with col_eps_chart:
                _eps_trend_f = e_data.get("eps_trend", [])
                if _eps_trend_f:
                    st.markdown(
                        '<div class="panel-head" style="margin-top:12px">EPS TREND (QUARTERLY)</div>',
                        unsafe_allow_html=True)
                    _et_dates = [r["date"] for r in _eps_trend_f]
                    _et_vals  = [r["eps"]  for r in _eps_trend_f]
                    _et_cols  = ["#16c784" if v > 0 else "#ea3a44" for v in _et_vals]
                    _fig_eps = go.Figure(go.Bar(
                        x=_et_dates, y=_et_vals, marker_color=_et_cols,
                    ))
                    _fig_eps.update_layout(
                        paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                        font_color="#e8edf8", height=260, margin=dict(t=10, b=10),
                        yaxis_title="Reported EPS ($)",
                    )
                    _fig_eps.update_yaxes(gridcolor="#2a3348")
                    st.plotly_chart(_fig_eps, width="stretch")

            # ── Earnings Quality — forensic red flags (short-seller lens) ────
            st.markdown("---")
            st.markdown("#### 🔬 Earnings Quality — forensic red flags (short-seller lens)")
            _eq = mod_eq.analyze(symbol)
            if _eq.get("error"):
                st.info(_eq["error"])
            elif not _eq["checks"]:
                st.info("No financial statement data available.")
            else:
                if _eq.get("score") is not None:
                    _eq_c = ("#16c784" if _eq["score"] >= 7.5 else
                             "#f0b90b" if _eq["score"] >= 5 else "#ea3a44")
                    st.markdown(
                        f'<div style="font-family:IBM Plex Mono,monospace;font-size:15px;'
                        f'margin-bottom:8px">Quality Score: '
                        f'<b style="color:{_eq_c}">{_eq["score"]}/10</b></div>',
                        unsafe_allow_html=True,
                    )
                _eq_icons = {"good": "🟢", "warn": "🟡", "flag": "🔴", "na": "⚪"}
                _eq_tips = {
                    "Share Dilution": "Is the company issuing new shares? Each new share splits "
                        "the company's value across more owners — your slice shrinks even if the "
                        "business itself isn't doing anything wrong. Common with unprofitable "
                        "growth companies paying employees in stock instead of cash.",
                    "SBC / Revenue": "Stock-Based Compensation — paying employees in company shares "
                        "instead of cash salary. Doesn't cost cash today, but it dilutes existing "
                        "shareholders over time. High SBC relative to revenue is a red flag some "
                        "companies use to make their 'adjusted' profit look better than reality.",
                    "Cash Backing (OCF/NI)": "Compares Operating Cash Flow (real cash collected) to "
                        "Net Income (accounting profit, which includes non-cash items and estimates). "
                        "When cash flow is well below reported profit for a while, the earnings may "
                        "be more 'paper' than real — 'profit is an opinion, cash is a fact.'",
                    "Receivables vs Revenue": "Receivables = money customers owe but haven't paid "
                        "yet. If receivables are growing much faster than revenue, the company may "
                        "be booking sales to customers who aren't actually paying — a classic early "
                        "warning sign of aggressive revenue recognition.",
                    "FCF Conversion": "Free Cash Flow ÷ Net Income — how much of the accounting "
                        "profit actually becomes real spendable cash after running and investing in "
                        "the business. Below 1x for a long stretch means profits look good on paper "
                        "but aren't showing up in the bank account.",
                    "Debt Trend": "Is total debt growing faster than the business itself? Rising "
                        "debt isn't automatically bad (it can fund real growth), but debt growing "
                        "much faster than revenue is how healthy companies quietly turn fragile.",
                }
                for _nm, _stt, _dt in _eq["checks"]:
                    _tip_eq = _html.escape(_eq_tips.get(_nm, ""), quote=True)
                    st.markdown(
                        f'<div style="cursor:help" title="{_tip_eq}">'
                        f'{_eq_icons.get(_stt,"⚪")} <b>{_html.escape(_nm)} ⓘ</b> — {_html.escape(_dt)}'
                        f'</div>', unsafe_allow_html=True,
                    )
                st.caption("Checks: dilution, stock-comp burden, cash backing of earnings, "
                           "receivables vs revenue, FCF conversion, debt trend. "
                           "🔴 flags are what short sellers hunt for. Hover any check for what it means.")

        # ── Technical + Momentum ─────────────────────────────────────────────
        with tab_tech:
            st.markdown('<div class="panel-head">PRICE CHART</div>', unsafe_allow_html=True)
            period_opt = st.select_slider("Period", ["1mo","3mo","6mo","1y","2y","5y","max"], value="1y")
            df_price = get_price_history(symbol, period=period_opt)
            if not df_price.empty:
                df_price["MA50"]  = df_price["Close"].squeeze().rolling(50).mean()
                df_price["MA200"] = df_price["Close"].squeeze().rolling(200).mean()
                delta = df_price["Close"].squeeze().diff()
                gain  = delta.clip(lower=0).rolling(14).mean()
                loss  = (-delta.clip(upper=0)).rolling(14).mean()
                rs    = gain / loss.replace(0, np.nan)
                df_price["RSI"] = 100 - (100 / (1 + rs))
                st.plotly_chart(render_price_chart(df_price, symbol), width="stretch")

                # ── RSI in Context — trend-adjusted interpretation ────────────
                _rctx = mod_mctx.rsi_in_context(get_price_history(symbol, period="2y")["Close"].squeeze())
                if not _rctx.get("error"):
                    _rb_lo, _rb_hi = _rctx["normal_band"]
                    _rv_c = _rctx["verdict_color"]
                    _rsi_v = _rctx["rsi"]
                    # position of current RSI on a 0-100 strip + normal band overlay
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-left:4px solid {_rv_c};border-radius:8px;'
                        f'padding:14px 18px;margin:6px 0 14px 0" '
                        f'title="{_html.escape(_rctx["tooltip"], quote=True)}">'
                        f'<div style="display:flex;justify-content:space-between;align-items:center;'
                        f'flex-wrap:wrap;gap:8px">'
                        f'<span style="font-weight:700;color:#e8edf8">RSI in Context: '
                        f'<span style="font-family:IBM Plex Mono,monospace">{_rsi_v:.0f}</span>'
                        f' <span style="color:{_rv_c}">· {_html.escape(_rctx["verdict"])}</span></span>'
                        f'<span style="font-size:11px;color:#8a9bc2">{_html.escape(_rctx["regime"])} '
                        f'→ normal band here: <b style="color:#e8edf8">{_rb_lo}–{_rb_hi}</b> '
                        f'(not the textbook 30–70)</span></div>'
                        # visual strip: 0-100 with band + marker
                        f'<div style="position:relative;height:14px;background:#0e1117;'
                        f'border-radius:7px;margin:10px 0 4px 0">'
                        f'<div style="position:absolute;left:{_rb_lo}%;width:{_rb_hi-_rb_lo}%;height:100%;'
                        f'background:#16c78422;border-left:1px solid #16c78455;'
                        f'border-right:1px solid #16c78455;border-radius:2px"></div>'
                        f'<div style="position:absolute;left:calc({min(99, max(1, _rsi_v))}% - 5px);top:-3px;'
                        f'width:10px;height:20px;background:{_rv_c};border-radius:3px"></div>'
                        f'</div>'
                        f'<div style="display:flex;justify-content:space-between;font-size:9px;color:#556070">'
                        f'<span>0</span><span>25</span><span>50</span><span>75</span><span>100</span></div>'
                        f'<div style="font-size:12px;color:#cdd6f4;margin-top:8px;line-height:1.55">'
                        f'{_html.escape(_rctx["detail"])}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.warning("No price data available.")

            st.markdown("---")

            col_l_t, col_r_t = st.columns([2, 1])
            with col_l_t:
                _t_signals = t_data.get("signals", [])
                _t_scores  = t_data.get("scores", {})
                _sig_count = len(_t_signals)
                st.subheader(f"Signals ({_sig_count} active)")
                if _t_signals:
                    for emoji, msg in _t_signals:
                        st.markdown(f"{emoji} {msg}")
                else:
                    st.caption("No directional signals — price action is neutral or insufficient history for all indicators.")

                _default_scores = [k for k, v in _t_scores.items() if v == 5.0]
                if len(_default_scores) >= 2:
                    st.markdown(
                        f'<div style="background:#f0b90b18;border-left:3px solid #f0b90b;'
                        f'padding:7px 11px;border-radius:0 5px 5px 0;font-size:11px;color:#f0b90b;margin-top:6px">'
                        f'⚠️ {len(_default_scores)} indicator{"s" if len(_default_scores)>1 else ""} at neutral (5/10) — '
                        f'may reflect insufficient price history or low recent volatility.</div>',
                        unsafe_allow_html=True,
                    )

            with col_r_t:
                st.subheader("Scores")
                for k, v in t_data.get("scores", {}).items():
                    bar   = "█" * int(v) + "░" * (10 - int(v))
                    color = score_color(v)
                    expl  = _EXPLAIN.get(k, "")
                    if v >= 7.5:   grade, gc = "✅ Very Strong", "#16c784"
                    elif v >= 6.0: grade, gc = "✅ Good",       "#a3e635"
                    elif v >= 4.5: grade, gc = "⚠ Average",    "#f0b90b"
                    else:          grade, gc = "❌ Weak",       "#ea3a44"
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-radius:7px;padding:10px 14px;margin-bottom:8px">'
                        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:5px">'
                        f'<span style="color:#9fa8da;font-size:11px;font-family:IBM Plex Mono,monospace">{k}</span>'
                        f'<span style="color:{gc};font-size:10px;font-weight:700;background:{gc}1a;'
                        f'border:1px solid {gc}33;padding:1px 7px;border-radius:3px">{grade}</span>'
                        f'</div>'
                        f'<span style="color:{color};font-family:IBM Plex Mono,monospace;font-size:12px">{bar}</span>'
                        f'<span style="color:{color};font-family:IBM Plex Mono,monospace;font-size:11px"> {v}/10</span>'
                        f'{"<div style=font-size:10.5px;color:#6b7a99;margin-top:5px;line-height:1.45>" + expl + "</div>" if expl else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

            st.subheader("Returns vs Benchmark")
            st.plotly_chart(render_return_bar(
                mo_data["returns"], mo_data["spy_returns"], symbol
            ), width="stretch")

            if mo_data.get("rs_vs_qqq_3m") is not None:
                rs = mo_data["rs_vs_qqq_3m"]
                if rs > 0.10:
                    rs_col, rs_v = "#16c784", "✅ Market leader — significantly outperforming Nasdaq"
                elif rs > 0:
                    rs_col, rs_v = "#a3e635", "✅ Slight outperformance vs Nasdaq"
                elif rs > -0.10:
                    rs_col, rs_v = "#f0b90b", "⚠ Slight underperformance vs Nasdaq"
                else:
                    rs_col, rs_v = "#ea3a44", "❌ Significant underperformance vs Nasdaq"
                st.markdown(
                    f'<div style="padding:8px 12px;background:var(--panel);border-radius:6px;'
                    f'border-left:3px solid {rs_col}">'
                    f'<span style="color:#9fa8da;font-size:11px">RS vs QQQ (3M): </span>'
                    f'<span style="color:{rs_col};font-weight:700">{rs*100:+.1f}%</span>'
                    f'&nbsp;<span style="color:{rs_col};font-size:10px">{rs_v}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # ── Institutional + Analysts ──────────────────────────────────────────
        def _render_yf_analyst(sym_info: dict):
            _rec_key  = (sym_info.get("recommendationKey") or "").lower().replace(" ", "_").replace("-", "_")
            _rec_mean = sym_info.get("recommendationMean")
            _n_ana    = sym_info.get("numberOfAnalystOpinions") or 0
            _pt_mean  = sym_info.get("targetMeanPrice")
            _pt_high  = sym_info.get("targetHighPrice")
            _pt_low   = sym_info.get("targetLowPrice")
            _price    = sym_info.get("currentPrice") or sym_info.get("regularMarketPrice") or 0
            _key_map = {
                "strong_buy":   ("Strong Buy",   "#16c784"),
                "buy":          ("Buy",          "#a3e635"),
                "hold":         ("Hold",         "#f0b90b"),
                "underperform": ("Underperform", "#f97316"),
                "sell":         ("Sell",         "#ea3a44"),
            }
            _label, _color = _key_map.get(_rec_key, ("N/A", "#8a9bc2"))
            _bull_pct = round(max(5.0, min(95.0, 95.0 - ((_rec_mean or 3.0) - 1.0) * 22.5)), 1) if _rec_mean else 50.0
            col_cons2, col_pt2 = st.columns(2)
            with col_cons2:
                st.markdown('<div class="panel-head">ANALYST CONSENSUS</div>', unsafe_allow_html=True)
                if _rec_mean:
                    st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:36px;font-weight:700;
              color:{_color};margin-bottom:6px">{_label}</div>
  <div style="font-size:12px;color:#8a9bc2;margin-bottom:14px">{_n_ana} analysts · mean rating {_rec_mean:.1f}/5</div>
  <div style="height:6px;background:#2a3348;border-radius:3px;overflow:hidden">
    <div style="width:{_bull_pct}%;background:{_color}"></div>
  </div>
  <div style="font-size:10px;color:{_color};margin-top:4px;font-family:'IBM Plex Mono',monospace">
    ~{_bull_pct:.0f}% bullish
  </div>
</div>""", unsafe_allow_html=True)
                else:
                    st.info("No analyst data available for this stock.")
            with col_pt2:
                st.markdown('<div class="panel-head">PRICE TARGET</div>', unsafe_allow_html=True)
                if _pt_mean and _price:
                    _upside  = (_pt_mean / _price - 1) * 100
                    _u_color = "#16c784" if _upside > 0 else "#ea3a44"
                    _lo, _hi = _pt_low or 0, _pt_high or 0
                    _bar_pos = ((_price - _lo) / (_hi - _lo) * 100) if _hi > _lo else 50
                    _bar_pos = max(2, min(98, _bar_pos))
                    st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <div>
      <div style="font-size:11px;color:#8a9bc2;font-family:'IBM Plex Mono',monospace">MEAN TARGET</div>
      <div style="font-size:32px;font-weight:700;color:#e8edf8;font-family:'IBM Plex Mono',monospace">${_pt_mean:.2f}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#8a9bc2;font-family:'IBM Plex Mono',monospace">UPSIDE</div>
      <div style="font-size:28px;font-weight:700;color:{_u_color};font-family:'IBM Plex Mono',monospace">{_upside:+.1f}%</div>
    </div>
  </div>
  <div style="position:relative;height:8px;background:#2a3348;border-radius:4px;margin:16px 0 8px">
    <div style="position:absolute;left:{_bar_pos}%;top:-3px;width:14px;height:14px;
                background:#e8edf8;border-radius:50%;transform:translateX(-50%)"></div>
    <div style="position:absolute;left:0;width:{_bar_pos}%;height:100%;
                background:linear-gradient(90deg,#ea3a44,#f0b90b,#16c784);border-radius:4px"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:11px;font-family:'IBM Plex Mono',monospace">
    <span style="color:#ea3a44">Low ${_lo:.2f}</span>
    <span style="color:#8a9bc2">Current ${_price:.2f}</span>
    <span style="color:#16c784">High ${_hi:.2f}</span>
  </div>
  <div style="margin-top:10px;font-size:11px;color:#556070">Based on {_n_ana} analyst estimates</div>
</div>""", unsafe_allow_html=True)
                else:
                    st.info("No price target available.")
            st.caption("Source: Yahoo Finance — add FINNHUB_API_KEY for full EPS/revenue estimates & news")

        with tab_inst:
            col_l_i, col_r_i = st.columns(2)
            with col_l_i:
                _inst_df = i_data.get("inst_df", pd.DataFrame())
                _n_inst  = len(_inst_df)
                st.subheader(f"Institutional Holders (top {_n_inst} shown)")
                if not _inst_df.empty:
                    st.dataframe(_inst_df, width="stretch")
                    st.caption("Source: Yahoo Finance — shows up to 10 largest holders.")
                else:
                    st.info("No institutional holder data available for this stock.")

                if i_data.get("inst_pct"):
                    st.metric("Institutional Ownership", f'{i_data["inst_pct"]*100:.1f}%',
                              help=_TIP["Institutional Ownership"])
                else:
                    st.markdown(
                        '<div style="color:#556070;font-size:11px;padding:4px 0">'
                        'Institutional Ownership %: not reported by Yahoo Finance for this stock</div>',
                        unsafe_allow_html=True,
                    )

                if i_data.get("short_pct"):
                    st.metric("Short Interest", f'{i_data["short_pct"]*100:.1f}%',
                              help=_TIP["Short Interest"])
                else:
                    st.markdown(
                        '<div style="color:#556070;font-size:11px;padding:4px 0">'
                        'Short Interest: not reported</div>',
                        unsafe_allow_html=True,
                    )

            with col_r_i:
                _insider_df = i_data.get("insider_df", pd.DataFrame())
                st.subheader(f"Insider Transactions ({len(_insider_df)} recent)")
                if not _insider_df.empty:
                    st.dataframe(_insider_df.head(10), width="stretch")
                else:
                    st.info("No insider transaction data available.")
                for emoji, msg in i_data.get("signals", []):
                    st.markdown(f"{emoji} {msg}")

                buy_val     = i_data.get("buy_value", 0)
                sell_val    = i_data.get("sell_value", 0)
                sell_routine = i_data.get("sell_value_routine", 0)
                sell_disc    = i_data.get("sell_value_discretionary", 0)
                routine_pct  = i_data.get("routine_sell_pct")
                if buy_val + sell_val > 0:
                    if sell_routine or sell_disc:
                        _ins_x = ["Insider Buys", "Sells — routine\n(repeating pattern)",
                                  "Sells — discretionary"]
                        _ins_y = [buy_val / 1e6, sell_routine / 1e6, sell_disc / 1e6]
                        _ins_c = ["#00c853", "#8a9bc2", "#ff1744"]
                    else:
                        _ins_x = ["Insider Buys", "Insider Sells"]
                        _ins_y = [buy_val / 1e6, sell_val / 1e6]
                        _ins_c = ["#00c853", "#ff1744"]
                    fig_i = go.Figure(go.Bar(x=_ins_x, y=_ins_y, marker_color=_ins_c))
                    fig_i.update_layout(
                        yaxis_title="Value ($M)", height=250,
                        paper_bgcolor="#0e1117", plot_bgcolor="#1a1f2e",
                        font_color="#e8eaf6", margin=dict(t=10, b=10),
                    )
                    st.plotly_chart(fig_i, width="stretch")
                    if routine_pct is not None:
                        st.caption(
                            f"ℹ️ ~{routine_pct:.0f}% of dollar-value selling matches a "
                            "repeating-share-count pattern per insider (same count sold 3+ "
                            "times) — the signature of a scheduled 10b5-1 plan or recurring "
                            "RSU-vesting sale, not a fresh discretionary decision. The "
                            "Insider Activity score reacts to the discretionary slice only."
                        )

            # ── Insider Sentiment (MSPR, Finnhub) ─────────────────────────────
            if FINNHUB_API_KEY:
                st.markdown("---")
                st.subheader("Insider Sentiment — MSPR (12 months)")
                st.caption(
                    "Monthly Share Purchase Ratio, -100 to +100. Positive = insiders "
                    "net buying (bullish); negative = net selling. Source: Finnhub."
                )
                _mspr_rows = mod_finnhub.get_insider_sentiment(symbol)
                if _mspr_rows:
                    import calendar as _ins_cal
                    _mspr_x = [f"{_ins_cal.month_abbr[r['month']]} '{str(r['year'])[2:]}"
                               for r in _mspr_rows]
                    _mspr_y = [r.get("mspr") or 0 for r in _mspr_rows]
                    _mspr_colors = ["#16c784" if v >= 0 else "#ea3a44" for v in _mspr_y]
                    _fig_mspr = go.Figure(go.Bar(
                        x=_mspr_x, y=_mspr_y, marker_color=_mspr_colors,
                        hovertemplate="%{x}: MSPR %{y:.1f}<extra></extra>",
                    ))
                    _fig_mspr.add_hline(y=0, line=dict(color="#556070", width=1))
                    _fig_mspr.update_layout(
                        height=240, margin=dict(l=0, r=0, t=10, b=0),
                        paper_bgcolor="#0e1117", plot_bgcolor="#1a1f2e",
                        font_color="#e8eaf6",
                        yaxis=dict(title="MSPR", range=[-100, 100],
                                   gridcolor="#1e2535"),
                        xaxis=dict(showgrid=False),
                    )
                    st.plotly_chart(_fig_mspr, width="stretch")
                    _mspr_avg = sum(_mspr_y) / len(_mspr_y)
                    _mspr_recent = sum(_mspr_y[-3:]) / min(3, len(_mspr_y))
                    if _mspr_recent > 10:
                        st.markdown("🟢 **Recent insider sentiment is bullish** — net buying over the last 3 months.")
                    elif _mspr_recent < -10:
                        st.markdown("🔴 **Recent insider sentiment is bearish** — net selling over the last 3 months.")
                    else:
                        st.markdown("🟡 **Recent insider sentiment is neutral** — no strong buying or selling bias.")
                else:
                    st.info("No insider sentiment data available for this stock.")

            # ── Analyst Rating Actions (FMP) ────────────────────────────────
            from config import FMP_API_KEY as _fmp_key
            if _fmp_key:
                st.markdown("---")
                st.subheader("Analyst Rating Actions (90 days)", help=mod_gloss.tip("analyst_grades"))
                st.caption(
                    "Upgrade/downgrade momentum — not just where ratings stand, but which "
                    "direction they're MOVING. A cluster of upgrades often front-runs price "
                    "action; a cluster of downgrades often confirms weakness before it's obvious. "
                    "Source: Financial Modeling Prep."
                )
                _grades = mod_fmp.analyst_grades(symbol)
                if _grades.get("error"):
                    st.info(f"Rating actions unavailable: {_grades['error']}")
                else:
                    _gg1, _gg2, _gg3 = st.columns(3)
                    _gg1.metric("Upgrades (90d)", _grades["up_90d"])
                    _gg2.metric("Downgrades (90d)", _grades["down_90d"])
                    _gg3.metric("New Coverage (90d)", _grades["init_90d"])
                    st.markdown(
                        f'<div style="color:{_grades["color"]};font-weight:600;'
                        f'font-size:13px;margin:6px 0 10px 0">{_html.escape(_grades["verdict"])}</div>',
                        unsafe_allow_html=True,
                    )
                    if _grades["recent"]:
                        _ga_rows = ""
                        _ga_colors = {"upgrade": "#16c784", "downgrade": "#ea3a44",
                                     "initiate": "#4da3ff", "initiated coverage": "#4da3ff",
                                     "maintain": "#556070"}
                        for r in _grades["recent"][:10]:
                            _ac = _ga_colors.get(r["action"], "#8a9bc2")
                            _ga_rows += (
                                f'<tr>'
                                f'<td style="padding:5px 10px;color:#8a9bc2">{_html.escape(r["date"])}</td>'
                                f'<td style="padding:5px 10px;font-weight:600">{_html.escape(r["firm"])}</td>'
                                f'<td style="padding:5px 10px;color:{_ac};text-transform:uppercase;'
                                f'font-size:11px;font-weight:700">{_html.escape(r["action"])}</td>'
                                f'<td style="padding:5px 10px;color:#8a9bc2">'
                                f'{_html.escape(r["from"])} → {_html.escape(r["to"])}</td>'
                                f'</tr>'
                            )
                        st.markdown(
                            f'<div style="background:var(--panel);border:1px solid var(--border);'
                            f'border-radius:8px;padding:10px 14px;overflow-x:auto">'
                            f'<table style="width:100%;border-collapse:collapse;font-size:12px">'
                            f'<tbody>{_ga_rows}</tbody></table></div>',
                            unsafe_allow_html=True,
                        )

            # Analysts & News
            st.markdown("---")
            if not FINNHUB_API_KEY:
                _render_yf_analyst(info)
            else:
                with st.spinner("Loading analyst data from Finnhub..."):
                    fh = mod_finnhub.fetch_all(symbol)

                if "error" in fh:
                    st.error(fh["error"])
                    _render_yf_analyst(info)
                elif "rec_error" in fh and not fh.get("recommendations"):
                    st.caption(f"⚠️ Finnhub recommendations failed ({fh['rec_error'][:80]}) — showing Yahoo Finance data")
                    _render_yf_analyst(info)
                else:
                    col_cons, col_pt = st.columns(2)
                    with col_cons:
                        st.markdown('<div class="panel-head">ANALYST CONSENSUS</div>', unsafe_allow_html=True)
                        rec = fh.get("recommendations", {})
                        if rec:
                            color = rec["consensus_color"]
                            bull_pct = rec["bull_pct"]
                            bear_pct = round(rec["bears"] / rec["total"] * 100, 1) if rec["total"] else 0
                            hold_pct = round(rec["hold"] / rec["total"] * 100, 1) if rec["total"] else 0
                            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">
    <div>
      <div style="font-family:'IBM Plex Mono',monospace;font-size:36px;font-weight:700;
                  color:{color}">{rec['consensus']}</div>
      <div style="font-size:12px;color:#8a9bc2">{rec['total']} analysts · {rec['period']}</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:6px;text-align:center">
    <div style="background:#16c78422;border-radius:6px;padding:8px">
      <div style="font-size:18px;font-weight:700;color:#16c784;font-family:'IBM Plex Mono',monospace">{rec['strong_buy']}</div>
      <div style="font-size:10px;color:#8a9bc2">Strong Buy</div>
    </div>
    <div style="background:#a3e63522;border-radius:6px;padding:8px">
      <div style="font-size:18px;font-weight:700;color:#a3e635;font-family:'IBM Plex Mono',monospace">{rec['buy']}</div>
      <div style="font-size:10px;color:#8a9bc2">Buy</div>
    </div>
    <div style="background:#f0b90b22;border-radius:6px;padding:8px">
      <div style="font-size:18px;font-weight:700;color:#f0b90b;font-family:'IBM Plex Mono',monospace">{rec['hold']}</div>
      <div style="font-size:10px;color:#8a9bc2">Hold</div>
    </div>
    <div style="background:#f9731622;border-radius:6px;padding:8px">
      <div style="font-size:18px;font-weight:700;color:#f97316;font-family:'IBM Plex Mono',monospace">{rec['sell']}</div>
      <div style="font-size:10px;color:#8a9bc2">Sell</div>
    </div>
    <div style="background:#ea3a4422;border-radius:6px;padding:8px">
      <div style="font-size:18px;font-weight:700;color:#ea3a44;font-family:'IBM Plex Mono',monospace">{rec['strong_sell']}</div>
      <div style="font-size:10px;color:#8a9bc2">Strong Sell</div>
    </div>
  </div>
  <div style="margin-top:14px;height:6px;background:#2a3348;border-radius:3px;overflow:hidden;display:flex">
    <div style="width:{bull_pct}%;background:#16c784"></div>
    <div style="width:{hold_pct}%;background:#f0b90b"></div>
    <div style="width:{bear_pct}%;background:#ea3a44"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:10px;color:#8a9bc2;margin-top:4px;font-family:'IBM Plex Mono',monospace">
    <span style="color:#16c784">Bulls {bull_pct}%</span>
    <span style="color:#f0b90b">Hold {hold_pct}%</span>
    <span style="color:#ea3a44">Bears {bear_pct}%</span>
  </div>
</div>""", unsafe_allow_html=True)
                        else:
                            st.info("No analyst recommendations available.")

                    with col_pt:
                        st.markdown('<div class="panel-head">PRICE TARGET</div>', unsafe_allow_html=True)
                        pt = fh.get("price_target", {})
                        if pt and pt.get("mean"):
                            current = info.get("currentPrice") or info.get("regularMarketPrice") or 0
                            upside  = ((pt["mean"] - current) / current * 100) if current else 0
                            u_color = "#16c784" if upside > 0 else "#ea3a44"
                            lo, hi, mean = pt.get("low",0) or 0, pt.get("high",0) or 0, pt.get("mean",0) or 0
                            bar_pos = ((current - lo) / (hi - lo) * 100) if hi > lo else 50
                            bar_pos = max(2, min(98, bar_pos))
                            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px">
  <div style="display:flex;justify-content:space-between;margin-bottom:8px">
    <div>
      <div style="font-size:11px;color:#8a9bc2;font-family:'IBM Plex Mono',monospace">MEAN TARGET</div>
      <div style="font-size:32px;font-weight:700;color:#e8edf8;font-family:'IBM Plex Mono',monospace">${mean:.2f}</div>
    </div>
    <div style="text-align:right">
      <div style="font-size:11px;color:#8a9bc2;font-family:'IBM Plex Mono',monospace">UPSIDE</div>
      <div style="font-size:28px;font-weight:700;color:{u_color};font-family:'IBM Plex Mono',monospace">{upside:+.1f}%</div>
    </div>
  </div>
  <div style="position:relative;height:8px;background:#2a3348;border-radius:4px;margin:16px 0 8px">
    <div style="position:absolute;left:{bar_pos}%;top:-3px;width:14px;height:14px;
                background:#e8edf8;border-radius:50%;transform:translateX(-50%);
                box-shadow:0 0 6px rgba(255,255,255,0.3)"></div>
    <div style="position:absolute;left:0;width:{bar_pos}%;height:100%;
                background:linear-gradient(90deg,#ea3a44,#f0b90b,#16c784);border-radius:4px"></div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:11px;font-family:'IBM Plex Mono',monospace">
    <span style="color:#ea3a44">Low ${lo:.2f}</span>
    <span style="color:#8a9bc2">Current ${current:.2f}</span>
    <span style="color:#16c784">High ${hi:.2f}</span>
  </div>
  <div style="margin-top:12px;font-size:11px;color:#556070;font-family:'IBM Plex Mono',monospace">
    Based on {pt.get('analysts', 0)} analyst estimates
  </div>
</div>""", unsafe_allow_html=True)
                        else:
                            st.info("No price target data available.")

                    st.markdown("---")

                    col_eps, col_rev = st.columns(2)
                    with col_eps:
                        st.markdown('<div class="panel-head">EPS ESTIMATES — NEXT QUARTERS</div>', unsafe_allow_html=True)
                        eps_df = fh.get("eps_estimates")
                        if eps_df is not None and not eps_df.empty:
                            st.dataframe(eps_df.style.format({
                                "EPS Estimate": lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                "EPS High":     lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                "EPS Low":      lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                            }), width="stretch", hide_index=True)
                        else:
                            st.info("No EPS estimates available.")

                    with col_rev:
                        st.markdown('<div class="panel-head">EARNINGS SURPRISES — HISTORY</div>', unsafe_allow_html=True)
                        surp_df = fh.get("earnings_surprises")
                        if surp_df is not None and not surp_df.empty:
                            def _color_surp(val):
                                if pd.isna(val): return ""
                                return "color: #16c784" if val > 0 else "color: #ea3a44"
                            st.dataframe(surp_df.style.format({
                                "Actual EPS": lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                "Estimate":   lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
                                "Surprise %": lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A",
                            }).map(_color_surp, subset=["Surprise %"]),
                            width="stretch", hide_index=True)
                        else:
                            st.info("No earnings surprise data available.")

                    st.markdown("---")

                    st.markdown('<div class="panel-head">RECENT NEWS — LAST 30 DAYS</div>', unsafe_allow_html=True)
                    news = fh.get("news", [])
                    SENT_COLOR = {"positive": "#16c784", "negative": "#ea3a44", "neutral": "#556070"}
                    if news:
                        for n in news[:12]:
                            sc = SENT_COLOR[n["sentiment"]]
                            st.markdown(f"""
<div style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid #2a3348;align-items:flex-start">
  <div style="width:3px;min-height:40px;background:{sc};border-radius:2px;flex-shrink:0;margin-top:2px"></div>
  <div style="flex:1">
    <a href="{_safe_href(n['url'])}" target="_blank" rel="noopener noreferrer" style="color:#e8edf8;text-decoration:none;font-size:13px;
       font-weight:500;line-height:1.4">{_html.escape(str(n['headline']))}</a>
    <div style="font-size:11px;color:#556070;margin-top:4px;font-family:'IBM Plex Mono',monospace">
      {_html.escape(str(n['source']))} · {_html.escape(str(n['date']))}
      <span style="color:{sc};margin-left:8px">{n['sentiment'].upper()}</span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
                    else:
                        st.info("No recent news found.")

                    st.markdown("---")
                    st.markdown('<div class="panel-head">INSIDER TRANSACTIONS</div>', unsafe_allow_html=True)
                    ins_df = fh.get("insiders")
                    if ins_df is not None and not ins_df.empty:
                        def _color_type(val):
                            return "color: #16c784; font-weight:600" if val == "BUY" else "color: #ea3a44; font-weight:600"
                        st.dataframe(ins_df.style.format({
                            "Price":      lambda x: f"${x:.2f}" if pd.notna(x) and x else "N/A",
                            "Value ($K)": lambda x: f"${x:,.0f}K" if pd.notna(x) else "N/A",
                            "Shares":     lambda x: f"{int(x):,}" if pd.notna(x) else "N/A",
                        }).map(_color_type, subset=["Type"]),
                        width="stretch", hide_index=True)
                    else:
                        st.info("No insider transaction data available.")

            # ── Forward EPS & Revenue Estimates (Yahoo Finance, always free) ──
            # Finnhub's and FMP's price-target/estimates endpoints are BOTH
            # gated to paid plans on the tiers this app uses (verified live —
            # 402/403 even for a mega-cap), so neither can ever fill this gap
            # regardless of company size. Yahoo's own consensus tables (via
            # yfinance) come back populated even for a thinly-covered
            # micro-cap, so this is shown unconditionally, no API key needed.
            st.markdown("---")
            st.markdown('<div class="panel-head">📈 FORWARD EPS & REVENUE ESTIMATES</div>',
                       unsafe_allow_html=True)
            _est = mod_inst.get_eps_revenue_estimates(symbol)
            if _est.get("error") or (_est.get("eps") is None and _est.get("revenue") is None):
                st.info("No analyst consensus estimates available for this stock "
                        "(thin/no analyst coverage) — this is a real data gap, not "
                        "a missing API key.")
            else:
                _est_c1, _est_c2 = st.columns(2)
                with _est_c1:
                    st.caption("EPS estimate (avg / low-high / # analysts)")
                    if _est["eps"] is not None:
                        st.dataframe(
                            _est["eps"][["avg", "low", "high", "numberOfAnalysts", "growth"]]
                                .rename(columns={"avg": "Avg EPS", "low": "Low", "high": "High",
                                                 "numberOfAnalysts": "# Analysts", "growth": "YoY Growth"})
                                .style.format({"Avg EPS": "${:.2f}", "Low": "${:.2f}",
                                              "High": "${:.2f}", "YoY Growth": "{:+.1%}"}),
                            width="stretch",
                        )
                    else:
                        st.info("No EPS estimates available.")
                with _est_c2:
                    st.caption("Revenue estimate (avg / low-high / # analysts)")
                    if _est["revenue"] is not None:
                        st.dataframe(
                            _est["revenue"][["avg", "low", "high", "numberOfAnalysts", "growth"]]
                                .rename(columns={"avg": "Avg Revenue", "low": "Low", "high": "High",
                                                 "numberOfAnalysts": "# Analysts", "growth": "YoY Growth"})
                                .style.format({"Avg Revenue": "${:,.0f}", "Low": "${:,.0f}",
                                              "High": "${:,.0f}", "YoY Growth": "{:+.1%}"}),
                            width="stretch",
                        )
                    else:
                        st.info("No revenue estimates available.")
                if _est.get("eps_revision_pct") is not None:
                    _rev_pct = _est["eps_revision_pct"]
                    _rev_color = "#16c784" if _rev_pct > 0 else "#ea3a44" if _rev_pct < 0 else "#8a9bc2"
                    st.markdown(
                        f'<div style="font-size:12px;margin-top:6px">90-day forward-EPS revision: '
                        f'<b style="color:{_rev_color}">{_rev_pct:+.1f}%</b> — '
                        f'{"estimates rising ahead of price, a quiet-accumulation tell" if _rev_pct > 2 else "estimates falling — analysts turning more cautious" if _rev_pct < -2 else "estimates roughly stable"}'
                        f'</div>', unsafe_allow_html=True,
                    )
                st.caption("Source: Yahoo Finance analyst consensus (via yfinance) — free, no API key.")

        # ── Macro + Peers + History ───────────────────────────────────────────
        with tab_macro_peers:
            _macro_narrative = m_data.get("narrative", "")
            _macro_no_data   = (
                "Add ANTHROPIC_API_KEY" in _macro_narrative or
                "unavailable" in _macro_narrative.lower()
            )
            if _macro_no_data:
                if "Add ANTHROPIC_API_KEY" in _macro_narrative:
                    st.warning("🤖 Macro AI analysis requires ANTHROPIC_API_KEY — add it to your .env file to enable.")
                else:
                    st.warning(f"🤖 Macro analysis unavailable: {_macro_narrative}")
                st.info("Without Claude AI, macro scoring defaults to neutral (5/10).")

            col_l_m, col_r_m = st.columns([2, 1])
            with col_l_m:
                st.subheader("Macro Overview")
                if not _macro_no_data:
                    st.markdown(_macro_narrative)
                if m_data.get("tailwinds"):
                    st.markdown("**📈 Tailwinds:**")
                    for t in m_data["tailwinds"]:
                        st.markdown(f"✅ {t}")
                if m_data.get("headwinds"):
                    st.markdown("**📉 Headwinds:**")
                    for h in m_data["headwinds"]:
                        st.markdown(f"⚠️ {h}")
                if m_data.get("geopolitical"):
                    st.markdown("**🌍 Geopolitical Risks:**")
                    for g in m_data["geopolitical"]:
                        st.markdown(f"🔴 {g}")

            with col_r_m:
                st.plotly_chart(render_gauge(m_data["score"], "Macro Score"), width="stretch")
                mscore = m_data.get("score", 5)
                if mscore >= 7.5:
                    mv, mc = "✅ Strong macro tailwind — environment is supportive", "#16c784"
                elif mscore >= 5.5:
                    mv, mc = "⚠ Mixed macro signals — be selective", "#f0b90b"
                else:
                    mv, mc = "❌ Macro headwind — environment is a drag", "#ea3a44"
                st.markdown(
                    f'<div style="font-size:11px;color:{mc};font-weight:600;'
                    f'padding:6px 10px;background:{mc}15;border-radius:5px;margin-bottom:8px">'
                    f'{mv}</div>', unsafe_allow_html=True
                )
                st.metric("Rate Sensitivity", m_data.get("rate_sensitivity", "N/A").title(),
                          help=_TIP["Rate Sensitivity"])

            # Macro Impact
            st.markdown("---")
            st.markdown('<div class="panel-head">MACRO IMPACT — THIS STOCK SPECIFICALLY</div>',
                        unsafe_allow_html=True)
            st.caption("How does the current macro environment affect this company's specific business model?")
            if st.button("🏥 Analyze Macro Impact", key="macro_impact_btn"):
                with st.spinner("Analyzing macro impact..."):
                    _mh_raw   = mod_mhealth.fetch_all()
                    _mh_lines = []
                    for _k, _cfg in mod_mhealth.INDICATORS.items():
                        _mhd = _mh_raw.get(_k, {})
                        _mhv = _mhd.get("display_value") if _mhd.get("display_value") is not None else _mhd.get("value")
                        if _mhv is not None:
                            _cls = mod_mhealth._classify(_k, _mhv)
                            _mh_lines.append(f'{_cfg["label"]}: {_mhv:.2f} ({_cls["label"]})')
                    _mi_results = mod_macro_impact.analyze(
                        symbol, name, sector, industry, "\n".join(_mh_lines)
                    )
                    st.session_state[f"macro_impact_{symbol}"] = _mi_results

            if f"macro_impact_{symbol}" in st.session_state:
                _mi = st.session_state[f"macro_impact_{symbol}"]
                if _mi:
                    _IMPACT_COLOR = {"POSITIVE": "#16c784", "NEUTRAL": "#8a9bc2", "NEGATIVE": "#ea3a44"}
                    _mi_cols = st.columns(3)
                    for _idx, _ind in enumerate(_mi[:9]):
                        with _mi_cols[_idx % 3]:
                            _imp = _ind.get("impact", "NEUTRAL")
                            _ic  = _IMPACT_COLOR.get(_imp, "#8a9bc2")
                            _badge_cls = "impact-pos" if _imp == "POSITIVE" else "impact-neg" if _imp == "NEGATIVE" else "impact-neu"
                            st.markdown(
                                f'<div class="impact-card">'
                                f'<div class="impact-label">{_html.escape(str(_ind.get("indicator", "")))}</div>'
                                f'<span class="impact-badge {_badge_cls}">{_imp}</span>'
                                f'<div class="impact-expl">{_html.escape(str(_ind.get("explanation", "")))}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )

            # Peers
            st.markdown("---")
            st.markdown('<div class="panel-head">PEER COMPARISON</div>', unsafe_allow_html=True)
            peer_df = p_data["df"]
            if not peer_df.empty:
                def color_pct(val):
                    if pd.isna(val): return ""
                    color = "#00c853" if val > 0 else "#ff1744"
                    return f"color: {color}"

                styled = peer_df.style.format({
                    "P/S":          lambda x: f"{x:.1f}x" if pd.notna(x) else "N/A",
                    "Fwd P/E":      lambda x: f"{x:.1f}x" if pd.notna(x) else "N/A",
                    "PEG":          lambda x: f"{x:.2f}"  if pd.notna(x) else "N/A",
                    "Rev Growth":   lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A",
                    "Gross Margin": lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A",
                    "1M Return":    lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
                    "3M Return":    lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
                    "1Y Return":    lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
                    "Market Cap":   lambda x: fmt_num(x) if pd.notna(x) else "N/A",
                }).map(color_pct, subset=["1M Return","3M Return","1Y Return","Rev Growth"])
                st.dataframe(styled, width="stretch")

                fig_p = go.Figure()
                for _, row in peer_df.iterrows():
                    vals = [row.get("1M Return", 0) or 0,
                            row.get("3M Return", 0) or 0,
                            row.get("1Y Return", 0) or 0]
                    width = 3 if row["Ticker"] == symbol else 1
                    fig_p.add_trace(go.Scatter(
                        x=["1M", "3M", "1Y"], y=[v*100 for v in vals],
                        mode="lines+markers", name=row["Ticker"],
                        line=dict(width=width),
                    ))
                fig_p.update_layout(
                    title="Relative Performance (%)", yaxis_ticksuffix="%",
                    paper_bgcolor="#0e1117", plot_bgcolor="#1a1f2e",
                    font_color="#e8edf8", height=350,
                )
                st.plotly_chart(fig_p, width="stretch")

            # Sector ETF Holdings
            _sec_etf = SECTOR_ETFS.get(sector)
            if _sec_etf:
                st.markdown("---")
                with st.expander(f"📦 Sector ETF Holdings — {_sec_etf} ({sector})", expanded=False):
                    mod_etf.render_etf_holdings(_sec_etf, max_rows=15)

            # Historical Comparison
            st.markdown("---")
            st.markdown('<div class="panel-head">HISTORICAL COMPARISON VS PEERS</div>',
                        unsafe_allow_html=True)
            _hist_peers = [symbol.upper()] + [p for p in p_data.get("peers", [])[:3]
                                               if p != symbol.upper()]
            _metric_options_h = {v["label"]: k for k, v in METRICS_CATALOG.items()}
            _metric_label_h = st.selectbox(
                "Metric", list(_metric_options_h.keys()),
                key="hist_metric_analyze",
            )
            _metric_key_h = _metric_options_h[_metric_label_h]
            with st.spinner("Loading historical data..."):
                _hist_fig = go.Figure()
                for _hsym in _hist_peers:
                    _series = mod_hist.fetch_metric(_hsym, _metric_key_h)
                    if _series is not None and not _series.empty:
                        _lw = 2 if _hsym == symbol.upper() else 1
                        _hist_fig.add_trace(go.Scatter(
                            x=_series.index, y=_series.values,
                            name=_hsym, line=dict(width=_lw),
                        ))
                _hist_fig.update_layout(
                    title=_metric_label_h,
                    paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                    font_color="#e8edf8", height=350,
                    legend=dict(bgcolor="#1c2333", bordercolor="#2a3348"),
                    margin=dict(t=40, b=10),
                )
                _fmt_h = METRICS_CATALOG[_metric_key_h].get("format", "")
                if _fmt_h == "pct":
                    _hist_fig.update_yaxes(ticksuffix="%", gridcolor="#2a3348")
                elif _fmt_h == "index":
                    _hist_fig.update_yaxes(title="Index (start=100)", gridcolor="#2a3348")
                else:
                    _hist_fig.update_yaxes(gridcolor="#2a3348")
                st.plotly_chart(_hist_fig, width="stretch")

            _hcat = METRICS_CATALOG.get(_metric_key_h, {})
            if _hcat.get("signal_good"):
                st.markdown(
                    f'<div style="background:#16c78410;border-left:2px solid #16c784;'
                    f'padding:6px 10px;border-radius:0 4px 4px 0;font-size:11px;color:#8a9bc2">'
                    f'✅ {_hcat["signal_good"]}</div>',
                    unsafe_allow_html=True,
                )
            if _hcat.get("signal_bad"):
                st.markdown(
                    f'<div style="background:#ea3a4410;border-left:2px solid #ea3a44;'
                    f'padding:6px 10px;border-radius:0 4px 4px 0;font-size:11px;color:#8a9bc2">'
                    f'⚠️ {_hcat["signal_bad"]}</div>',
                    unsafe_allow_html=True,
                )

        # ── Experts ───────────────────────────────────────────────────────────
        with tab_panel:
            st.subheader("🧠 Expert Panel — 8 AI Investor Personas")
            st.caption("Each expert analyzes this stock through their own investment lens. Requires ANTHROPIC_API_KEY.")

            _fm_ov = mod_fm.analyze_stock(symbol)
            if not _fm_ov.get("error"):
                _cv_ov = mod_fm.combined_verdict(_fm_ov)
                _experts_key = f"experts_{symbol}"
                _ai_scores = {}
                if _experts_key in st.session_state:
                    _dec_base = {"BUY": 8.0, "WATCH": 6.0, "HOLD": 5.0, "SELL": 2.0}
                    for _ex_ov in st.session_state[_experts_key]:
                        _dec_ov = _ex_ov.get("decision", "HOLD")
                        _conv_ov = _ex_ov.get("conviction", 3)
                        _sc_ov = _dec_base.get(_dec_ov, 5.0) + (_conv_ov - 3) * 0.6
                        _ai_scores[f"AI · {_ex_ov.get('name', '?')}"] = max(0.0, min(10.0, _sc_ov))

                if _cv_ov["score"] is not None and _ai_scores:
                    _quant_avg_ov = _cv_ov["score"]
                    _ai_avg_ov = sum(_ai_scores.values()) / len(_ai_scores)
                    _overall_ov = round(_quant_avg_ov * 0.6 + _ai_avg_ov * 0.4, 1)
                    _all_breakdown_ov = {**_cv_ov["breakdown"], **_ai_scores}
                    _weight_note_ov = (f"60% weight: {_cv_ov['n_total']} mechanical guru/quant models "
                                       f"· 40% weight: {len(_ai_scores)} AI experts")
                elif _cv_ov["score"] is not None:
                    _overall_ov = _cv_ov["score"]
                    _all_breakdown_ov = dict(_cv_ov["breakdown"])
                    _weight_note_ov = (f"{_cv_ov['n_total']} mechanical guru/quant models only — "
                                       f"run the AI Expert Panel below to fold their votes into this score.")
                else:
                    _overall_ov = None
                    _all_breakdown_ov = {}
                    _weight_note_ov = ""

                if _overall_ov is not None:
                    _n_bull_ov = sum(1 for v in _all_breakdown_ov.values() if v >= 7)
                    _n_bear_ov = sum(1 for v in _all_breakdown_ov.values() if v <= 3)
                    _n_neu_ov  = len(_all_breakdown_ov) - _n_bull_ov - _n_bear_ov
                    _ov_label, _ov_color = (
                        ("BULLISH CONSENSUS", "#16c784") if _overall_ov >= 7 else
                        ("LEAN BULLISH", "#a3e635") if _overall_ov >= 5.5 else
                        ("MIXED / NO CONSENSUS", "#f0b90b") if _overall_ov >= 4.5 else
                        ("LEAN BEARISH", "#f97316") if _overall_ov >= 3 else
                        ("BEARISH CONSENSUS", "#ea3a44")
                    )
                    st.subheader("🏆 Overall Verdict — every model & expert, one number")
                    st.markdown(
                        f'<div style="background:{_ov_color}18;border:2px solid {_ov_color}70;'
                        f'border-radius:12px;padding:18px 22px;margin:8px 0">'
                        f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">'
                        f'<span style="font-family:IBM Plex Mono,monospace;font-size:30px;'
                        f'font-weight:900;color:{_ov_color}">{_overall_ov}/10</span>'
                        f'<span style="font-family:IBM Plex Mono,monospace;font-size:16px;'
                        f'font-weight:700;color:{_ov_color}">{_ov_label}</span>'
                        f'<span style="font-size:12px;color:#8a9bc2">{_n_bull_ov} say buy · '
                        f'{_n_neu_ov} neutral · {_n_bear_ov} say sell/avoid '
                        f'(of {len(_all_breakdown_ov)} voices)</span>'
                        f'</div>'
                        f'<div style="font-size:11px;color:#556070;margin-top:8px">{_weight_note_ov}</div>'
                        f'</div>', unsafe_allow_html=True,
                    )
                    with st.expander("Who says what — every model & expert, ranked"):
                        for _mname_ov, _mscore_ov in sorted(_all_breakdown_ov.items(), key=lambda x: -x[1]):
                            _mc_ov = ("#16c784" if _mscore_ov >= 7 else
                                     "#ea3a44" if _mscore_ov <= 3 else "#f0b90b")
                            st.markdown(
                                f'<div style="font-size:13px;padding:2px 0">{_mname_ov}: '
                                f'<b style="color:{_mc_ov}">{_mscore_ov:.1f}/10</b></div>',
                                unsafe_allow_html=True,
                            )
                st.markdown("---")

            price_now = info.get("currentPrice") or info.get("regularMarketPrice", 0)

            if st.button("🧠 Get Expert Opinions", type="primary", key="experts_tab_btn"):
                with st.spinner("Consulting 8 experts (1 batch call)..."):
                    _details = {
                        "fundamental_metrics": {k: v for k, v in f_data.get("metrics", {}).items() if v is not None},
                        "technical_signals":   t_data.get("signals", []),
                        "technical_rsi":       t_data.get("rsi"),
                        "momentum_r3m":        mo_data.get("r3m"),
                        "momentum_r1m":        mo_data.get("r1m"),
                        "analyst_bull_pct":    i_data.get("bull_pct"),
                        "analyst_pt_upside":   i_data.get("pt_upside"),
                        "macro_score":         m_data.get("score"),
                        "macro_tailwinds":     m_data.get("tailwinds", []),
                        "macro_headwinds":     m_data.get("headwinds", []),
                    }
                    _combined = json.dumps({**s_data, "details": _details}, default=str)
                    _experts = mod_experts.analyze(
                        symbol,
                        round(float(price_now or 0), 2),
                        _combined,
                    )
                    st.session_state[f"experts_{symbol}"] = _experts

            if f"experts_{symbol}" in st.session_state:
                _experts = st.session_state[f"experts_{symbol}"]

                def _is_expert_fallback(ex_list: list) -> bool:
                    if not ex_list:
                        return False
                    return all(
                        ex.get("decision") == "HOLD" and (
                            "Error:" in str(ex.get("rationale", "")) or
                            "Add ANTHROPIC_API_KEY" in str(ex.get("rationale", "")) or
                            "No response" in str(ex.get("rationale", ""))
                        )
                        for ex in ex_list
                    )

                if _is_expert_fallback(_experts):
                    _reason = _experts[0].get("rationale", "Unknown error")
                    if "Add ANTHROPIC_API_KEY" in _reason:
                        st.warning("⚠️ Expert Panel requires ANTHROPIC_API_KEY — add it to your .env file.")
                    else:
                        st.error(f"❌ Expert Panel failed: {_reason}")
                        st.info("Cache cleared — click **Get Expert Opinions** again to retry.")
                else:
                    _d_colors = {"BUY": "#00c853", "SELL": "#ff1744", "HOLD": "#ffd600", "WATCH": "#ff9800"}

                    def _fmt_px(v):
                        return f"${v:.2f}" if v and v > 0 else "N/A"

                    def _expert_card(ex):
                        decision   = ex.get("decision", "HOLD")
                        d_color    = _d_colors.get(decision, "#9fa8da")
                        conviction = ex.get("conviction", 3)
                        stars      = "★" * conviction + "☆" * (5 - conviction)
                        style_str  = ex["profile"]["title"].split("—", 1)[-1].strip()
                        target     = _fmt_px(ex.get("target_price"))
                        entry      = _fmt_px(ex.get("entry_price"))
                        rationale  = _html.escape(str(ex.get("rationale", "")))
                        pos        = ex.get("position_size_pct", 5)
                        sl         = ex.get("stop_loss_pct", 15)
                        name_e     = _html.escape(ex["name"])
                        style_e    = _html.escape(style_str)
                        horizon    = _html.escape(str(ex.get("time_horizon", "")))
                        horizon_html = (
                            f'<span style="font-size:9px;background:var(--panel2);color:#9fa8da;'
                            f'border-radius:4px;padding:2px 6px;margin-left:6px">{horizon}</span>'
                            if horizon else ""
                        )
                        t_entry = "Recommended entry price. Same as market = buy now. Lower = wait for a pullback"
                        t_target = _TIP["Target Price"]
                        t_pos    = _TIP["Position Size"]
                        t_sl     = _TIP["Stop Loss"]
                        t_conv   = _TIP["Conviction"]
                        # Key risks inline inside card
                        risks = ex.get("key_risks", [])
                        risks_html = ""
                        if risks:
                            items = "".join(
                                f'<div style="font-size:11px;color:#f0b90b;margin-top:4px">• {_html.escape(r)}</div>'
                                for r in risks
                            )
                            risks_html = (
                                f'<div style="margin-top:12px;padding-top:10px;border-top:1px solid var(--border)">'
                                f'<div style="font-size:9px;color:#556070;text-transform:uppercase;'
                                f'letter-spacing:.7px;margin-bottom:4px">⚠️ Key Risks</div>'
                                f'{items}</div>'
                            )
                        return (
                            # Uses the shared .ui-card surface + accent border in the decision
                            # colour, so these match every other card in the app.
                            f'<div class="ui-card ui-card-accent" '
                            f'style="border-left-color:{d_color};display:flex;flex-direction:column">'
                            # ── header ─────────────────────────────────────────────
                            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">'
                            f'<span style="font-size:22px;line-height:1">{ex["profile"]["icon"]}</span>'
                            f'<div style="min-width:0">'
                            f'<div class="ui-card-title" style="margin-bottom:1px">{name_e}</div>'
                            f'<div class="ui-card-sub">{style_e}{horizon_html}</div>'
                            f'</div></div>'
                            # ── decision + conviction on ONE row (was 3 stacked rows
                            #    eating vertical space and pushing text down) ────────
                            f'<div style="display:flex;align-items:baseline;gap:10px;'
                            f'flex-wrap:wrap;margin:8px 0 12px">'
                            f'<span style="font-family:var(--mono);font-size:26px;font-weight:800;'
                            f'color:{d_color};line-height:1">{decision}</span>'
                            f'<span title="{t_conv}" style="cursor:help;font-size:12px;color:#ffd600">'
                            f'{stars}</span>'
                            f'<span style="font-size:10px;color:var(--dim)">Conviction {conviction}/5</span>'
                            f'</div>'
                            # ── 4 stat tiles ───────────────────────────────────────
                            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);'
                            f'gap:1px;background:var(--border);border:1px solid var(--border);'
                            f'border-radius:8px;overflow:hidden">'
                            f'<div title="{t_entry}" style="background:var(--panel2);padding:8px 10px;cursor:help">'
                            f'<div class="ui-card-meta" style="margin-bottom:3px">ENTRY</div>'
                            f'<div style="font-family:var(--mono);font-size:13px;font-weight:600;'
                            f'color:var(--text)">{entry}</div></div>'
                            f'<div title="{t_target}" style="background:var(--panel2);padding:8px 10px;cursor:help">'
                            f'<div class="ui-card-meta" style="margin-bottom:3px">TARGET</div>'
                            f'<div style="font-family:var(--mono);font-size:13px;font-weight:600;'
                            f'color:var(--up)">{target}</div></div>'
                            f'<div title="{t_pos}" style="background:var(--panel2);padding:8px 10px;cursor:help">'
                            f'<div class="ui-card-meta" style="margin-bottom:3px">SIZE</div>'
                            f'<div style="font-family:var(--mono);font-size:13px;font-weight:600;'
                            f'color:var(--text)">{pos:.1f}%</div></div>'
                            f'<div title="{t_sl}" style="background:var(--panel2);padding:8px 10px;cursor:help">'
                            f'<div class="ui-card-meta" style="margin-bottom:3px">STOP</div>'
                            f'<div style="font-family:var(--mono);font-size:13px;font-weight:600;'
                            f'color:#ff6d00">-{sl:.0f}%</div></div>'
                            f'</div>'
                            # ── rationale + risks — full text, no clipping ─────────
                            f'<div style="margin-top:12px;padding-top:10px;'
                            f'border-top:1px solid var(--border)">'
                            f'<div style="font-size:13px;color:#cfd8dc;line-height:1.65">{rationale}</div>'
                            f'{risks_html}'
                            f'</div>'
                            f'</div>'
                        )

                    # One auto-fit grid instead of two fixed st.columns(4) rows —
                    # 4 forced columns squeezed each card to ~250px, so rationale
                    # text wrapped 2-3 words per line. Now cards hold a readable
                    # min width and reflow to fit the viewport.
                    # st.html (not st.markdown) — markdown pre-processing mangles a
                    # block this size/nesting, which blanked the whole panel.
                    # Style is inlined so the grid renders even if the global
                    # stylesheet isn't in scope for this element.
                    st.html(
                        '<style>'
                        '.xp-grid{display:grid;'
                        'grid-template-columns:repeat(auto-fit,minmax(300px,1fr));'
                        'gap:12px;margin-bottom:12px}'
                        '.xp-grid>div{height:100%;margin-bottom:0}'
                        # Card styles repeated here with literal values (not var())
                        # so the panel is not dependent on the global sheet.
                        '.xp-grid .ui-card{background:#1c2333;border:1px solid #2a3348;'
                        'border-radius:10px;padding:16px 18px}'
                        '.xp-grid .ui-card-accent{border-left-width:4px;border-left-style:solid}'
                        '.xp-grid .ui-card-title{font-size:15px;font-weight:700;color:#e8edf8}'
                        '.xp-grid .ui-card-sub{font-size:12px;color:#8a9bc2;line-height:1.6}'
                        '.xp-grid .ui-card-meta{font-size:10px;text-transform:uppercase;'
                        'letter-spacing:.8px;color:#556070}'
                        '</style>'
                        '<div class="xp-grid">'
                        + "".join(_expert_card(ex) for ex in _experts)
                        + '</div>'
                    )

                    # ── Panel Synthesis — the moderator's distilled verdict ──
                    st.markdown("---")
                    st.subheader("🧑‍⚖️ Panel Verdict — distilled committee decision")
                    st.caption("A moderator weighs all personas by fit to THIS stock, resolves "
                               "the debate, flags missing perspectives, and hands you a full "
                               "position strategy: sizing, leverage, hedging, entry/exit, warning signs.")
                    if st.button("⚖️ Distill Panel Verdict", type="primary", key="panel_verdict_btn"):
                        with st.spinner("Moderator is weighing the panel..."):
                            _exp_compact = json.dumps([{
                                "name": e["name"], "decision": e.get("decision"),
                                "conviction": e.get("conviction"),
                                "time_horizon": e.get("time_horizon"),
                                "entry_price": e.get("entry_price"),
                                "target_price": e.get("target_price"),
                                "stop_loss_pct": e.get("stop_loss_pct"),
                                "position_size_pct": e.get("position_size_pct"),
                                "rationale": e.get("rationale"),
                                "key_risks": e.get("key_risks", []),
                            } for e in _experts], default=str)
                            _summary_for_syn = json.dumps(s_data, default=str)
                            _syn = mod_experts.panel_synthesis(
                                symbol, round(float(price_now or 0), 2),
                                _exp_compact, _summary_for_syn,
                            )
                            st.session_state[f"panel_syn_{symbol}"] = _syn

                    if f"panel_syn_{symbol}" in st.session_state:
                        _syn = st.session_state[f"panel_syn_{symbol}"]
                        if _syn.get("error"):
                            st.error(_syn["error"])
                        else:
                            _sv = _syn.get("final_verdict", "HOLD")
                            _sv_c = {"STRONG BUY": "#00c853", "BUY": "#64dd17",
                                     "HOLD": "#ffd600", "WATCH": "#ff9800",
                                     "AVOID": "#ff6d00", "SELL": "#ff1744"}.get(_sv, "#9fa8da")
                            _sconv = _syn.get("conviction", 5)
                            st.markdown(
                                f'<div style="background:var(--panel);border:2px solid {_sv_c};'
                                f'border-radius:12px;padding:20px 24px;margin:10px 0">'
                                f'<div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">'
                                f'<span style="font-family:IBM Plex Mono,monospace;font-size:26px;'
                                f'font-weight:900;color:{_sv_c}">{_html.escape(_sv)}</span>'
                                f'<span style="font-size:13px;color:#8a9bc2">Conviction '
                                f'<b style="color:#e8edf8">{_sconv}/10</b></span></div>'
                                f'<div style="font-size:15px;color:#e8edf8;margin-top:10px;'
                                f'font-weight:600">{_html.escape(str(_syn.get("one_liner","")))}</div>'
                                f'<div style="font-size:12px;color:#8a9bc2;margin-top:8px">'
                                f'{_html.escape(str(_syn.get("weighing_note","")))}</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            if _syn.get("key_debate"):
                                st.markdown(f"**🥊 The Debate:** {_syn['key_debate']}")
                            if _syn.get("missing_perspectives"):
                                st.markdown("**🪑 Missing from the panel:**")
                                for _mp in _syn["missing_perspectives"]:
                                    st.markdown(f"- **{_mp.get('persona','')}** — {_mp.get('would_add','')}")

                            _ps = _syn.get("position_strategy", {})
                            if _ps:
                                st.markdown("#### 📋 Position Strategy")
                                _ps1, _ps2, _ps3 = st.columns(3)
                                _ps1.metric("Suggested Allocation",
                                            f"{_ps.get('allocation_pct', '—')}%",
                                            help=mod_gloss.tip("position_sizing"))
                                _lev = _ps.get("leverage") or "—"
                                _ps2.metric("Leverage", str(_lev),
                                            help=mod_gloss.tip("leverage"))
                                _hedge_short = "See below"
                                _ps3.metric("Hedging", _hedge_short,
                                            help=mod_gloss.tip("hedging"))

                                _ps_rows = [
                                    ("⚡ Leverage", _ps.get("leverage_note")),
                                    ("🛡 Hedging", _ps.get("hedging")),
                                    ("🚪 Entry Plan", _ps.get("entry_plan")),
                                    ("🏁 Exit Plan", _ps.get("exit_plan")),
                                    ("➕ Add Zones", _ps.get("add_zones")),
                                ]
                                for _lbl_ps, _txt_ps in _ps_rows:
                                    if _txt_ps:
                                        st.markdown(f"**{_lbl_ps}:** {_txt_ps}")
                                _wc1, _wc2 = st.columns(2)
                                with _wc1:
                                    if _ps.get("warning_signs"):
                                        st.markdown("**🚨 What should worry you:**")
                                        for _ws in _ps["warning_signs"]:
                                            st.markdown(f"- {_ws}")
                                with _wc2:
                                    if _ps.get("watch_carefully"):
                                        st.markdown("**👁 Watch carefully:**")
                                        for _wc in _ps["watch_carefully"]:
                                            st.markdown(f"- {_wc}")

            # ── 🎓 Guru Checklists — mechanical, no LLM, cross-check for the AI panel above ──
            st.markdown("---")
            st.subheader("🎓 Guru Checklists — the legends, mechanically applied")
            st.caption("No AI here — pure rules from each investor's published criteria. "
                       "Compare against the AI personas above: same investing philosophies, "
                       "one gives a live narrative opinion, this one just runs the numbers. "
                       "Hover any card title for who invented the method and how it's computed.")

            _fm = mod_fm.analyze_stock(symbol)
            if _fm.get("error"):
                st.info(f"Guru checklists unavailable: {_fm['error']}")
            else:
                _tip_g = {k: _html.escape(mod_gloss.tip(k), quote=True)
                          for k in ("buffett_method", "munger_method", "lynch_method",
                                    "graham_method", "greenblatt_method", "canslim_method",
                                    "bogle_method", "piotroski_method", "altman_method",
                                    "templeton_method")}

                def _guru_card(title, tip_key, verdict, verdict_color, body_html):
                    return (
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-left:4px solid {verdict_color};border-radius:8px;'
                        f'padding:14px 18px;margin-bottom:10px;cursor:help" '
                        f'title="{_tip_g[tip_key]}">'
                        f'<div style="font-weight:700;color:#e8edf8;margin-bottom:2px">{title} ⓘ</div>'
                        f'<div style="font-size:12px;color:{verdict_color};font-weight:600;'
                        f'margin-bottom:8px">{_html.escape(verdict)}</div>'
                        f'{body_html}</div>'
                    )

                def _checks_html(checks):
                    return "".join(
                        f'<div style="font-size:12px;color:{"#16c784" if ok else "#ea3a44"};'
                        f'padding:1px 0">{"✓" if ok else "✗"} {_html.escape(lbl)} '
                        f'<span style="color:#556070">({_html.escape(str(val))})</span></div>'
                        for lbl, ok, val in checks
                    )

                _gc1, _gc2 = st.columns(2)
                with _gc1:
                    # Buffett
                    _bf = _fm["buffett"]
                    _bf_c = ("#16c784" if _bf["passed"] == 5 else
                             "#f0b90b" if _bf["passed"] >= 3 else "#ea3a44")
                    st.markdown(_guru_card(
                        f'🏛 Buffett — Wonderful at Fair Price ({_bf["passed"]}/{_bf["total"]})',
                        "buffett_method", _bf["verdict"], _bf_c,
                        _checks_html(_bf["checks"])), unsafe_allow_html=True)

                    # Lynch
                    _ly = _fm["lynch"]
                    _ly_c = ("#16c784" if _ly.get("peg") and _ly["peg"] < 1 else
                             "#f0b90b" if _ly.get("peg") and _ly["peg"] <= 2 else "#8a9bc2")
                    _ly_body = (
                        f'<div style="font-size:12px;color:#cdd6f4">Category: '
                        f'<b>{_html.escape(_ly["category"])}</b> '
                        f'(growth {_ly["growth_pct"]:+.0f}%)</div>'
                        f'<div style="font-size:11px;color:#8a9bc2;margin:4px 0">'
                        f'{_html.escape(_ly["cat_note"])}</div>'
                        f'<div style="font-size:12px;color:#cdd6f4">{_html.escape(_ly["peg_verdict"])}</div>'
                    )
                    st.markdown(_guru_card("📗 Lynch — Know What You Own",
                                           "lynch_method", _ly["category"], _ly_c, _ly_body),
                                unsafe_allow_html=True)

                    # Graham
                    _gr = _fm["graham"]
                    _gr_c = ("#16c784" if (_gr.get("margin") or -1) >= 30 else
                             "#f0b90b" if (_gr.get("margin") or -1) >= 0 else "#8a9bc2")
                    _gr_body = ""
                    if _gr.get("graham_number"):
                        _gr_body = (f'<div style="font-size:12px;color:#cdd6f4">'
                                    f'Graham Number: <b>${_gr["graham_number"]:,.2f}</b> · '
                                    f'margin of safety {_gr["margin"]:+.0f}%</div>')
                    st.markdown(_guru_card("📜 Graham — Margin of Safety",
                                           "graham_method", _gr["verdict"], _gr_c, _gr_body),
                                unsafe_allow_html=True)

                    # Bogle
                    _bg = _fm["bogle"]
                    _bg_rows = "".join(
                        f'<div style="font-size:12px;color:#cdd6f4">{lbl}: stock '
                        f'<b style="color:{"#16c784" if v["beat"] else "#ea3a44"}">'
                        f'{v["stock"]:+.1f}%</b> vs SPY {v["spy"]:+.1f}%</div>'
                        for lbl, v in _bg.get("rows", {}).items()
                    )
                    _bg_c = "#16c784" if "every window" in _bg["verdict"] and "Beat" in _bg["verdict"] else "#f0b90b"
                    st.markdown(_guru_card("🗿 Bogle — Did You Even Beat the Index?",
                                           "bogle_method", _bg["verdict"], _bg_c, _bg_rows),
                                unsafe_allow_html=True)

                with _gc2:
                    # Munger
                    _mg_f = _fm["munger"]
                    _mg_c = "#16c784" if not _mg_f["flags"] else "#ea3a44"
                    _mg_body = "".join(
                        f'<div style="font-size:12px;color:#ea3a44;padding:1px 0">✗ {_html.escape(f)}</div>'
                        for f in _mg_f["flags"]
                    ) or '<div style="font-size:12px;color:#16c784">✓ No disqualifiers found</div>'
                    st.markdown(_guru_card("🧠 Munger — Inversion Filter",
                                           "munger_method", _mg_f["verdict"], _mg_c, _mg_body),
                                unsafe_allow_html=True)

                    # Greenblatt
                    _gb = _fm["greenblatt"]
                    _gb_c = ("#16c784" if "CANDIDATE" in _gb["verdict"] else
                             "#f0b90b" if "GOOD BUSINESS" in _gb["verdict"] else "#8a9bc2")
                    _gb_body = ""
                    if _gb.get("ey") is not None:
                        _gb_body = (f'<div style="font-size:12px;color:#cdd6f4">'
                                    f'Earnings yield (EBITDA/EV): <b>{_gb["ey"]:.1f}%</b> · '
                                    f'Return on capital: <b>{_gb["roc"]:.1f}%</b></div>')
                    st.markdown(_guru_card("✨ Greenblatt — Magic Formula",
                                           "greenblatt_method", _gb["verdict"], _gb_c, _gb_body),
                                unsafe_allow_html=True)

                    # CANSLIM
                    _cs = _fm["canslim"]
                    _cs_c = ("#16c784" if _cs["passed"] >= 6 else
                             "#f0b90b" if _cs["passed"] >= 4 else "#ea3a44")
                    st.markdown(_guru_card(
                        f'🚀 O\'Neil — CANSLIM ({_cs["passed"]}/{_cs["total"]})',
                        "canslim_method", _cs["verdict"], _cs_c,
                        _checks_html(_cs["checks"])), unsafe_allow_html=True)

                # ── Academic quant classics (full width, 2 cols) ─────────────
                _ac1, _ac2 = st.columns(2)
                with _ac1:
                    # Piotroski
                    _pi = _fm["piotroski"]
                    if _pi.get("score") is not None:
                        _pi_c = ("#16c784" if _pi["score"] >= 8 else
                                 "#f0b90b" if _pi["score"] >= 5 else "#ea3a44")
                        _pi_body = "".join(
                            f'<div style="font-size:12px;color:{"#16c784" if ok else "#ea3a44"};'
                            f'padding:1px 0">{"✓" if ok else "✗"} {_html.escape(lbl)}</div>'
                            for lbl, ok in _pi["checks"]
                        )
                        st.markdown(_guru_card(
                            f'🎓 Piotroski F-Score ({_pi["score"]}/9)',
                            "piotroski_method", _pi["verdict"], _pi_c, _pi_body),
                            unsafe_allow_html=True)
                    else:
                        st.info(f"Piotroski: {_pi.get('verdict', 'unavailable')}")

                with _ac2:
                    # Altman Z
                    _az = _fm["altman"]
                    if _az.get("z") is not None:
                        _az_c = ("#16c784" if _az["z"] > 2.99 else
                                 "#f0b90b" if _az["z"] >= 1.81 else "#ea3a44")
                        st.markdown(_guru_card(
                            f'⚗️ Altman Z-Score ({_az["z"]})',
                            "altman_method", _az["verdict"], _az_c, ""),
                            unsafe_allow_html=True)
                    else:
                        st.info(f"Altman Z: {_az.get('verdict', 'unavailable')}")

                    # Templeton
                    _tm = _fm["templeton"]
                    _tm_c = {"good": "#16c784", "warn": "#f0b90b",
                             "bad": "#ea3a44", "na": "#8a9bc2"}.get(_tm.get("color"), "#8a9bc2")
                    _tm_body = ""
                    if _tm.get("drawdown") is not None:
                        _tm_body = (f'<div style="font-size:12px;color:#cdd6f4">'
                                    f'Drawdown from 52w high: <b>{_tm["drawdown"]:+.0f}%</b>'
                                    + (f' · RSI {_tm["rsi"]:.0f}' if _tm.get("rsi") else '')
                                    + '</div>')
                    st.markdown(_guru_card(
                        "🌍 Templeton — Maximum Pessimism",
                        "templeton_method", _tm["verdict"], _tm_c, _tm_body),
                        unsafe_allow_html=True)

            _tip_minervini_method = _html.escape(mod_gloss.tip("minervini_method"), quote=True)
            _tip_turtle_method = _html.escape(mod_gloss.tip("turtle_method"), quote=True)
            _tip_trend_following_method = _html.escape(mod_gloss.tip("trend_following_method"), quote=True)
            _tip_druckenmiller_method = _html.escape(mod_gloss.tip("druckenmiller_method"), quote=True)
            _tip_kelly_method = _html.escape(mod_gloss.tip("kelly_method"), quote=True)
            if _fm.get("error"):
                st.info(f"Fund models unavailable: {_fm['error']}")
            else:
                _fm_c1, _fm_c2 = st.columns(2)

                # ── Minervini Trend Template ─────────────────────────────────
                with _fm_c1:
                    _min = _fm["minervini"]
                    _min_pass = _min["passed"]
                    _min_c = "#16c784" if _min_pass == 7 else ("#f0b90b" if _min_pass >= 5 else "#ea3a44")
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-left:4px solid {_min_c};'
                        f'border-radius:8px;padding:14px 18px;margin-bottom:10px;cursor:help" '
                        f'title="{_tip_minervini_method}">'
                        f'<div style="font-weight:700;color:#e8edf8;margin-bottom:2px">'
                        f'📈 Minervini Trend Template <span style="color:{_min_c}">'
                        f'{_min_pass}/{_min["total"]}</span></div>'
                        f'<div style="font-size:12px;color:#8a9bc2;margin-bottom:8px">{_min["verdict"]}</div>'
                        + "".join(
                            f'<div style="font-size:12px;color:{"#16c784" if ok else "#ea3a44"};'
                            f'padding:1px 0">{"✓" if ok else "✗"} {lbl}</div>'
                            for lbl, ok in _min["checks"]
                        ) + '</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Turtle / Donchian ────────────────────────────────────
                    _tur = _fm["turtle"]
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-radius:8px;padding:14px 18px;margin-bottom:10px;cursor:help" title="{_tip_turtle_method}">'
                        f'<div style="font-weight:700;color:#e8edf8;margin-bottom:6px">🐢 Turtle Breakout Rules</div>'
                        f'<div style="font-size:12px;color:#cdd6f4">System 1 (20d): {_tur["s1"]}</div>'
                        f'<div style="font-size:12px;color:#cdd6f4">System 2 (55d): {_tur["s2"]}</div>'
                        + (f'<div style="font-size:11px;color:#556070;margin-top:6px">'
                           f'20d high ${_tur["hi20"]:,.2f} · 55d high ${_tur["hi55"]:,.2f} · '
                           f'exit lows ${_tur["lo10"]:,.2f}/${_tur["lo20"]:,.2f}</div>'
                           if _tur.get("hi20") else "")
                        + '</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Trend following ──────────────────────────────────────
                    _tr = _fm["trend"]
                    _tr_c = {"LONG": "#16c784", "SHORT/AVOID": "#ea3a44",
                             "MIXED": "#f0b90b"}.get(_tr["signal"], "#556070")
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-radius:8px;padding:14px 18px;margin-bottom:10px;cursor:help" title="{_tip_trend_following_method}">'
                        f'<div style="font-weight:700;color:#e8edf8;margin-bottom:4px">'
                        f'📉 Managed-Futures Trend: <span style="color:{_tr_c}">{_tr["signal"]}</span></div>'
                        f'<div style="font-size:12px;color:#8a9bc2">{_tr["detail"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                with _fm_c2:
                    # ── Druckenmiller ────────────────────────────────────────
                    _dr = _fm["druck"]
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);'
                        f'border-radius:8px;padding:14px 18px;margin-bottom:10px;cursor:help" title="{_tip_druckenmiller_method}">'
                        f'<div style="font-weight:700;color:#e8edf8;margin-bottom:4px">🎯 Druckenmiller Playbook</div>'
                        f'<div style="font-size:12px;color:#f0b90b;margin-bottom:8px">{_dr["verdict"]}</div>'
                        + "".join(f'<div style="font-size:12px;color:#cdd6f4;padding:1px 0">{e} {m}</div>'
                                  for e, m in _dr.get("points", []))
                        + '</div>',
                        unsafe_allow_html=True,
                    )

                    # ── Kelly sizing ─────────────────────────────────────────
                    _ke = _fm["kelly"]
                    if _ke.get("kelly") is not None:
                        _ke_c = "#16c784" if _ke["kelly"] > 0 else "#ea3a44"
                        st.markdown(
                            f'<div style="background:var(--panel);border:1px solid var(--border);'
                            f'border-radius:8px;padding:14px 18px;margin-bottom:10px;cursor:help" title="{_tip_kelly_method}">'
                            f'<div style="font-weight:700;color:#e8edf8;margin-bottom:6px">🎲 Kelly Position Sizing</div>'
                            f'<div style="font-size:12px;color:#cdd6f4">'
                            f'Monthly win rate <b>{_ke["win_rate"]}%</b> · payoff ratio <b>{_ke["payoff"]}</b> '
                            f'({_ke["n_months"]} months)</div>'
                            f'<div style="font-size:13px;margin-top:6px">Full Kelly: '
                            f'<b style="color:{_ke_c}">{_ke["kelly"]}%</b> of capital · '
                            f'Half-Kelly (practical): <b style="color:{_ke_c}">{_ke["half_kelly"]}%</b></div>'
                            f'<div style="font-size:11px;color:#556070;margin-top:4px">{_ke["note"]}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.info(f"Kelly sizing: {_ke.get('note', 'unavailable')}")

                    # ── Factor profile radar ─────────────────────────────────
                    _fac = _fm["factors"]
                    _f_names = list(_fac["scores"].keys())
                    _f_vals  = list(_fac["scores"].values())
                    _fig_rad = go.Figure(go.Scatterpolar(
                        r=_f_vals + [_f_vals[0]],
                        theta=_f_names + [_f_names[0]],
                        fill="toself", fillcolor="rgba(77,163,255,0.15)",
                        line=dict(color="#4da3ff", width=2),
                    ))
                    _fig_rad.update_layout(
                        polar=dict(
                            bgcolor="#0e1117",
                            radialaxis=dict(range=[0, 10], gridcolor="#1e2535",
                                            tickfont=dict(size=9, color="#556070")),
                            angularaxis=dict(gridcolor="#1e2535",
                                             tickfont=dict(size=11, color="#cdd6f4")),
                        ),
                        paper_bgcolor="#0e1117", height=280,
                        margin=dict(l=40, r=40, t=25, b=25), showlegend=False,
                        title=dict(text="Factor Profile", font=dict(size=12, color="#cdd6f4"), x=0),
                    )
                    st.plotly_chart(_fig_rad, width="stretch",
                                    config={"displayModeBar": False})
                    st.markdown("**Style fit:**", help=mod_gloss.tip("factor_method"))
                    for _sf in _fac["style_fits"]:
                        st.markdown(f"- {_sf}")


        # ── Seasonality ──────────────────────────────────────────────────────────
        with tab_seasonal:
            st.subheader("📅 Monthly Seasonality")
            st.caption("Historical average monthly returns based on 10 years of data. Past patterns do not guarantee future returns.")

            with st.spinner("Loading seasonality data..."):
                _seas = mod_seasonal.get_seasonality(symbol, years=10)

            if not _seas or not _seas.get("monthly"):
                st.info("Seasonality data unavailable for this symbol.")
            else:
                _MNAMES = mod_seasonal.MONTH_NAMES
                _monthly  = _seas["monthly"]
                _best_m   = _seas["best_month"]
                _worst_m  = _seas["worst_month"]
                _cur_m    = _seas["current_month"]
                _yrs      = _seas["years_analyzed"]

                # Hero cards
                _c1, _c2, _c3, _c4 = st.columns(4)
                with _c1:
                    _bm = _monthly[_best_m]
                    st.metric("Best Month", _MNAMES[_best_m - 1],
                              f"+{_bm['avg_return']*100:.1f}% avg · {_bm['win_rate']*100:.0f}% win rate")
                with _c2:
                    _wm = _monthly[_worst_m]
                    st.metric("Worst Month", _MNAMES[_worst_m - 1],
                              f"{_wm['avg_return']*100:.1f}% avg · {_wm['win_rate']*100:.0f}% win rate")
                with _c3:
                    _cm = _monthly.get(_cur_m, {})
                    _cm_avg = _cm.get("avg_return", 0)
                    _cm_wr  = _cm.get("win_rate", 0)
                    _cm_lbl = f"{_cm_avg*100:+.1f}% avg · {_cm_wr*100:.0f}% win rate" if _cm else "No data"
                    st.metric(f"This Month ({_MNAMES[_cur_m-1]})", "Current", _cm_lbl)
                with _c4:
                    st.metric("Data Range", f"{_yrs} years", "Monthly close-to-close")

                # Monthly bar chart
                _avgs   = [_monthly.get(m, {}).get("avg_return", 0) * 100 for m in range(1, 13)]
                _wrates = [_monthly.get(m, {}).get("win_rate", 0) * 100   for m in range(1, 13)]
                _medns  = [_monthly.get(m, {}).get("median", 0) * 100     for m in range(1, 13)]
                _cnts   = [_monthly.get(m, {}).get("count", 0)            for m in range(1, 13)]
                _bar_colors = ["#16c784" if a >= 0 else "#ea3a44" for a in _avgs]

                _fig_seas = go.Figure()
                _fig_seas.add_trace(go.Bar(
                    x=_MNAMES, y=_avgs,
                    marker_color=_bar_colors,
                    text=[f"{a:+.1f}%" for a in _avgs],
                    textposition="outside",
                    customdata=list(zip(_wrates, _medns, _cnts)),
                    hovertemplate=(
                        "<b>%{x}</b><br>"
                        "Avg Return: %{y:+.2f}%<br>"
                        "Win Rate: %{customdata[0]:.0f}%<br>"
                        "Median: %{customdata[1]:+.2f}%<br>"
                        "Years: %{customdata[2]}<extra></extra>"
                    ),
                ))
                _fig_seas.update_layout(
                    title=dict(text=f"{symbol} — Average Monthly Return ({_yrs}Y)", font=dict(color="#b0bec5")),
                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                    font=dict(color="#b0bec5", family="IBM Plex Mono, monospace", size=11),
                    yaxis=dict(ticksuffix="%", gridcolor="#1e2738", zerolinecolor="#2a3348"),
                    xaxis=dict(gridcolor="#1e2738"),
                    height=330, margin=dict(l=0, r=0, t=40, b=0),
                    showlegend=False,
                )
                st.plotly_chart(_fig_seas, width="stretch")

                # Heatmap table
                _hmap = _seas.get("heatmap", {})
                if _hmap:
                    _all_returns = [v for yr in _hmap.values() for v in yr.values() if v is not None]
                    _max_abs = max(abs(r) for r in _all_returns) if _all_returns else 0.1

                    def _hmap_color(ret):
                        if ret is None:
                            return "#1e2738", "#556070"
                        intensity = min(abs(ret) / (_max_abs + 0.001), 1.0)
                        if ret > 0:
                            g_val = int(100 + 100 * intensity)
                            return f"rgba(22,{g_val},100,{0.15 + 0.5*intensity})", "#16c784"
                        else:
                            r_val = int(150 + 80 * intensity)
                            return f"rgba({r_val},58,68,{0.15 + 0.5*intensity})", "#ea3a44"

                    _header_cells = "".join(
                        f'<th style="padding:4px 6px;font-size:10px;color:#556070;'
                        f'font-family:IBM Plex Mono,monospace;text-align:center">{mn[:3]}</th>'
                        for mn in _MNAMES
                    )
                    _rows_html = ""
                    for yr in sorted(_hmap.keys(), reverse=True):
                        _row_cells = ""
                        for m in range(1, 13):
                            ret = _hmap[yr].get(m)
                            bg, fg = _hmap_color(ret)
                            val_str = f"{ret*100:+.1f}%" if ret is not None else "—"
                            _row_cells += (
                                f'<td style="padding:3px 5px;font-size:11px;font-family:IBM Plex Mono,monospace;'
                                f'color:{fg};background:{bg};text-align:center;border-radius:3px">{val_str}</td>'
                            )
                        _rows_html += (
                            f'<tr><td style="padding:3px 8px;font-size:11px;color:#b0bec5;'
                            f'font-family:IBM Plex Mono,monospace;white-space:nowrap">{yr}</td>'
                            f'{_row_cells}</tr>'
                        )

                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                        f'padding:12px 16px;margin-top:8px;overflow-x:auto">'
                        f'<div style="font-size:10px;font-family:IBM Plex Mono,monospace;color:#16c784;'
                        f'text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">'
                        f'MONTHLY RETURN HEATMAP — {symbol} — {_yrs} YEARS</div>'
                        f'<table style="width:100%;border-collapse:separate;border-spacing:2px">'
                        f'<thead><tr><th style="padding:4px 8px;font-size:10px;color:#556070;'
                        f'font-family:IBM Plex Mono,monospace;text-align:left">YEAR</th>'
                        f'{_header_cells}</tr></thead>'
                        f'<tbody>{_rows_html}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )

        # ── 13F Smart Money ───────────────────────────────────────────────────────
        with tab_13f:
            st.subheader("🏛 13F Smart Money Tracker")
            st.caption(
                f"Institutional 13F filings from {len(mod_13f.FAMOUS_FUNDS)} famous hedge funds. "
                "Data is ~45 days delayed (SEC mandatory filing deadline). "
                "Change vs. prior quarter."
            )

            with st.spinner("Fetching 13F filings from SEC EDGAR... (~15s on first load, cached 24h)"):
                _stock_long_name = info.get("longName") or info.get("shortName") or symbol
                _smart_money = mod_13f.get_smart_money_for_stock(symbol, _stock_long_name)

            if not _smart_money:
                st.info(
                    f"No tracked funds held **{symbol}** in the latest quarter. "
                    f"Tracked funds: {', '.join(mod_13f.FAMOUS_FUNDS.keys())}."
                )
            else:
                _sm_rows = ""
                for _sm in _smart_money:
                    _sm_rows += (
                        f'<tr>'
                        f'<td style="padding:6px 10px;font-family:IBM Plex Mono,monospace;'
                        f'font-weight:700;color:#e8eaf6;white-space:nowrap">{_sm["fund"]}</td>'
                        f'<td style="padding:6px 10px;color:#8a9bc2;font-size:12px">{_sm["style"]}</td>'
                        f'<td style="padding:6px 10px;font-family:IBM Plex Mono,monospace;'
                        f'color:#b0bec5;text-align:right">{_sm["shares_fmt"]}</td>'
                        f'<td style="padding:6px 10px;font-family:IBM Plex Mono,monospace;'
                        f'color:#b0bec5;text-align:right">{_sm["value_fmt"]}</td>'
                        f'<td style="padding:6px 10px;font-family:IBM Plex Mono,monospace;'
                        f'font-weight:700;color:{_sm["change_color"]};white-space:nowrap">'
                        f'{_sm["change_label"]}</td>'
                        f'<td style="padding:6px 10px;color:#556070;font-size:11px;white-space:nowrap">'
                        f'{_sm["filing_date"]}</td>'
                        f'</tr>'
                    )

                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                    f'padding:12px 16px;margin-top:8px;overflow-x:auto">'
                    f'<div style="font-size:10px;font-family:IBM Plex Mono,monospace;color:#16c784;'
                    f'text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;cursor:help" '
                    f'title="{_html.escape(mod_gloss.tip("13f"), quote=True)}">'
                    f'13F SMART MONEY · {len(_smart_money)} TRACKED FUND{"S" if len(_smart_money)>1 else ""} '
                    f'HOLDING {symbol} · SEC EDGAR ⓘ</div>'
                    f'<table style="width:100%;border-collapse:collapse">'
                    f'<thead><tr>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">FUND</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">STYLE</th>'
                    f'<th style="text-align:right;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">SHARES</th>'
                    f'<th style="text-align:right;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">VALUE</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">CHANGE</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 10px;'
                    f'font-family:IBM Plex Mono,monospace">FILED</th>'
                    f'</tr></thead>'
                    f'<tbody>{_sm_rows}</tbody>'
                    f'</table></div>',
                    unsafe_allow_html=True,
                )

                st.caption(
                    "Source: SEC EDGAR 13F-HR filings. "
                    "Data reflects Q-end positions filed ~45 days later. "
                    "Change = vs. prior quarter filing."
                )

        # ── DCF Valuation (dcf-valuation skill) ──────────────────────────────
        with tab_dcf:
            st.subheader(f"💎 DCF Intrinsic Value — {symbol}")
            st.caption("Two-stage discounted-cash-flow model: 5-year FCF projection + Gordon "
                       "terminal value. Adjust assumptions below — defaults come from the "
                       "stock's own history.")

            _dcf_in = mod_dcf.get_dcf_inputs(symbol)
            if _dcf_in.get("error"):
                st.info(f"DCF unavailable: {_dcf_in['error']}")

            elif _dcf_in.get("is_financial"):
                st.info("🏦 Financial-sector company — bank/insurer cash-flow statements mix "
                        "loan-book, trading-securities and reserve movements into 'Free Cash "
                        "Flow', so a standard FCF DCF isn't meaningful here. Valuing the "
                        "dividend stream instead (Dividend Discount Model).")
                _dps = _dcf_in.get("dividend_rate")
                if not _dps:
                    st.warning("No dividend data available — can't run a DDM either.")
                else:
                    _ddm1, _ddm2 = st.columns(2)
                    with _ddm1:
                        _beta_def = _dcf_in.get("beta") or 1.0
                        _rf = mod_dcf.get_risk_free_rate()
                        _coe_def = _rf + float(_beta_def) * 0.045
                        _coe = st.slider("Cost of equity (%)", 4.0, 18.0,
                                          round(_coe_def * 100, 1), 0.5,
                                          key=f"_ddm_coe_{symbol}",
                                          help=f"Default = 10Y yield ({_rf*100:.1f}%) + "
                                               f"beta × 4.5% equity premium") / 100
                    with _ddm2:
                        _roe = _dcf_in.get("roe")
                        _payout = _dcf_in.get("payout_ratio")
                        _sustain_g = (_roe * (1 - _payout)) \
                            if (_roe is not None and _payout is not None) else 0.03
                        _sustain_g = max(0.0, min(_coe - 0.005, _sustain_g))
                        _ddm_g = st.slider("Dividend growth (%)", 0.0,
                                            max(0.5, min(10.0, _coe * 100 - 0.5)),
                                            round(_sustain_g * 100, 1), 0.25,
                                            key=f"_ddm_g_{symbol}",
                                            help="Suggested = ROE × retention ratio "
                                                 "(sustainable growth rate)") / 100
                    _ddm_res = mod_dcf.run_ddm(_dps, _ddm_g, _coe)
                    if _ddm_res.get("error"):
                        st.error(_ddm_res["error"])
                    else:
                        _iv = _ddm_res["intrinsic_ps"]
                        _px = _dcf_in["price"]
                        _ups = (_iv / _px - 1) * 100 if _px > 0 else 0
                        _ups_c = "#16c784" if _ups > 15 else ("#ea3a44" if _ups < -15 else "#f0b90b")
                        _verdict = ("UNDERVALUED" if _ups > 15 else
                                    "OVERVALUED" if _ups < -15 else "FAIRLY VALUED")
                        _dm1, _dm2, _dm3 = st.columns(3)
                        _dm1.metric("Intrinsic Value (DDM)", f"${_iv:,.2f}")
                        _dm2.metric("Market Price", f"${_px:,.2f}")
                        _dm3.metric("Upside / Downside", f"{_ups:+.1f}%")
                        st.markdown(
                            f'<div style="background:{_ups_c}18;border:1px solid {_ups_c}50;'
                            f'border-radius:8px;padding:10px 16px;margin:8px 0;'
                            f'color:{_ups_c};font-weight:700;'
                            f'font-family:IBM Plex Mono,monospace">'
                            f'{_verdict} by DDM at these assumptions</div>',
                            unsafe_allow_html=True,
                        )
                        st.caption(f"Next-year dividend: ${_ddm_res['next_dps']:,.2f}/share · "
                                   f"Sustainable growth ≈ ROE × retention ratio.")

            elif _dcf_in.get("negative_fcf"):
                _rev = _dcf_in.get("revenue_ttm")
                if not _rev:
                    st.warning("This company has negative free cash flow and no revenue data "
                               "available for a path-to-profitability estimate.")
                else:
                    st.info("📈 Negative free cash flow today — a standard DCF would explode. "
                            "Instead, this projects revenue forward and ramps the FCF margin to "
                            "an assumed mature-state level, answering \"what is this worth once "
                            "it reaches a normal margin.\"")
                    _cur_margin = _dcf_in.get("current_fcf_margin")
                    if _cur_margin is None:
                        _cur_margin = -0.10
                    _rc1, _rc2, _rc3 = st.columns(3)
                    with _rc1:
                        _rev_g_def = _dcf_in.get("revenue_growth") or 0.15
                        _rev_g = st.slider("Revenue growth (5y, %/yr)", 0.0, 60.0,
                                            float(min(60.0, max(3.0, _rev_g_def * 100))), 1.0,
                                            key=f"_rdcf_g_{symbol}") / 100
                    with _rc2:
                        _target_m = st.slider("Target FCF margin at maturity (%)", 0.0, 35.0,
                                               15.0, 1.0, key=f"_rdcf_m_{symbol}",
                                               help="What % of revenue becomes free cash flow "
                                                    "once the business matures. 15% is a "
                                                    "reasonable software/SaaS default — adjust "
                                                    "for the sector.") / 100
                    with _rc3:
                        _rdcf_wacc = st.slider("Discount rate / WACC (%)", 6.0, 20.0, 12.0, 0.5,
                                                key=f"_rdcf_w_{symbol}") / 100
                    _rdcf_gt = 0.025
                    _rdcf_res = mod_dcf.run_revenue_dcf(
                        _rev, _rev_g, _cur_margin, _target_m, _rdcf_gt, _rdcf_wacc,
                        _dcf_in["net_debt"], _dcf_in["shares_out"],
                    )
                    if _rdcf_res.get("error"):
                        st.error(_rdcf_res["error"])
                    else:
                        _iv = _rdcf_res["intrinsic_ps"]
                        _px = _dcf_in["price"]
                        _ups = (_iv / _px - 1) * 100 if _px > 0 else 0
                        _ups_c = "#16c784" if _ups > 15 else ("#ea3a44" if _ups < -15 else "#f0b90b")
                        _verdict = ("UNDERVALUED" if _ups > 15 else
                                    "OVERVALUED" if _ups < -15 else "FAIRLY VALUED")
                        _dm1, _dm2, _dm3, _dm4 = st.columns(4)
                        _dm1.metric("Intrinsic Value", f"${_iv:,.2f}")
                        _dm2.metric("Market Price", f"${_px:,.2f}")
                        _dm3.metric("Upside / Downside", f"{_ups:+.1f}%")
                        _dm4.metric("Current FCF Margin", f"{_cur_margin*100:+.1f}%",
                                    help="Today's FCF ÷ revenue — negative means the business "
                                         "still burns cash")
                        st.markdown(
                            f'<div style="background:{_ups_c}18;border:1px solid {_ups_c}50;'
                            f'border-radius:8px;padding:10px 16px;margin:8px 0;'
                            f'color:{_ups_c};font-weight:700;'
                            f'font-family:IBM Plex Mono,monospace">'
                            f'{_verdict} by revenue-bridge DCF at these assumptions</div>',
                            unsafe_allow_html=True,
                        )
                        _rproj = _rdcf_res["fcf_projection"]
                        _fig_rdcf = go.Figure()
                        _fig_rdcf.add_trace(go.Bar(
                            x=[f"Y{p['year']}" for p in _rproj],
                            y=[p["revenue"] / 1e9 for p in _rproj],
                            name="Projected Revenue", marker_color="#8a9bc2", opacity=0.6,
                        ))
                        _fig_rdcf.add_trace(go.Bar(
                            x=[f"Y{p['year']}" for p in _rproj],
                            y=[p["fcf"] / 1e9 for p in _rproj],
                            name="Projected FCF (ramped margin)",
                            marker_color="#4da3ff", opacity=0.9,
                        ))
                        _fig_rdcf.update_layout(
                            barmode="group", height=240,
                            margin=dict(l=0, r=0, t=10, b=0),
                            paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                            font=dict(color="#cdd6f4"),
                            yaxis=dict(title="$B", gridcolor="#1e2535"),
                            legend=dict(orientation="h", y=1.1, x=0),
                        )
                        st.plotly_chart(_fig_rdcf, width="stretch",
                                        config={"displayModeBar": False})
                        st.caption("Margin ramps linearly from today's level to the target "
                                   "by Year 5.")

            else:
                _dc1, _dc2, _dc3 = st.columns(3)
                with _dc1:
                    _g5 = st.slider("FCF growth (5y, %/yr)", -10.0, 40.0,
                                    float(_dcf_in["suggested_g"] * 100), 0.5,
                                    key=f"_dcf_g_{symbol}",
                                    help="Suggested from historical FCF CAGR") / 100
                with _dc2:
                    _beta_def = _dcf_in.get("beta") or 1.0
                    _wacc_def = min(15.0, max(7.0, 4.5 + 5.0 * float(_beta_def)))
                    _wacc = st.slider("Discount rate / WACC (%)", 6.0, 18.0,
                                      round(_wacc_def, 1), 0.5,
                                      key=f"_dcf_w_{symbol}",
                                      help="Default ≈ risk-free 4.5% + beta × 5% equity premium") / 100
                with _dc3:
                    _gt = st.slider("Terminal growth (%)", 0.0, 4.0, 2.5, 0.25,
                                    key=f"_dcf_t_{symbol}") / 100

                _dcf_res = mod_dcf.run_dcf(
                    _dcf_in["base_fcf"], _g5, _gt, _wacc,
                    _dcf_in["net_debt"], _dcf_in["shares_out"],
                )
                if _dcf_res.get("error"):
                    st.error(_dcf_res["error"])
                else:
                    _iv    = _dcf_res["intrinsic_ps"]
                    _px    = _dcf_in["price"]
                    _ups   = (_iv / _px - 1) * 100 if _px > 0 else 0
                    _ups_c = "#16c784" if _ups > 15 else ("#ea3a44" if _ups < -15 else "#f0b90b")
                    _verdict = ("UNDERVALUED" if _ups > 15 else
                                "OVERVALUED" if _ups < -15 else "FAIRLY VALUED")

                    _dm1, _dm2, _dm3, _dm4 = st.columns(4)
                    _dm1.metric("Intrinsic Value", f"${_iv:,.2f}",
                                help=mod_gloss.tip("intrinsic_value"))
                    _dm2.metric("Market Price", f"${_px:,.2f}")
                    _dm3.metric("Upside / Downside", f"{_ups:+.1f}%",
                                help=mod_gloss.tip("dcf"))
                    _dm4.metric("Terminal Weight", f"{_dcf_res['terminal_weight']:.0f}%",
                                help="Share of value from the terminal period. Above ~80% = "
                                     "valuation highly sensitive to terminal assumptions.")
                    st.markdown(
                        f'<div style="background:{_ups_c}18;border:1px solid {_ups_c}50;'
                        f'border-radius:8px;padding:10px 16px;margin:8px 0;'
                        f'color:{_ups_c};font-weight:700;font-family:IBM Plex Mono,monospace">'
                        f'{_verdict} by DCF at these assumptions</div>',
                        unsafe_allow_html=True,
                    )

                    # FCF projection chart
                    _proj = _dcf_res["fcf_projection"]
                    _fig_dcf = go.Figure()
                    _fig_dcf.add_trace(go.Bar(
                        x=[f"Y{p['year']}" for p in _proj],
                        y=[p["fcf"] / 1e9 for p in _proj],
                        name="Projected FCF", marker_color="#4da3ff", opacity=0.8,
                    ))
                    _fig_dcf.add_trace(go.Bar(
                        x=[f"Y{p['year']}" for p in _proj],
                        y=[p["pv"] / 1e9 for p in _proj],
                        name="Present Value", marker_color="#16c784", opacity=0.8,
                    ))
                    _fig_dcf.update_layout(
                        barmode="group", height=240,
                        margin=dict(l=0, r=0, t=10, b=0),
                        paper_bgcolor="#0e1117", plot_bgcolor="#0e1117",
                        font=dict(color="#cdd6f4"),
                        yaxis=dict(title="$B", gridcolor="#1e2535"),
                        legend=dict(orientation="h", y=1.1, x=0),
                    )
                    st.plotly_chart(_fig_dcf, width="stretch",
                                    config={"displayModeBar": False})

                    # Sensitivity matrix
                    st.markdown("**Sensitivity — Intrinsic Value per Share**",
                                help="Each cell re-runs the DCF at a different growth/discount "
                                     "assumption pair, so you can see how much the answer swings "
                                     "when the inputs change — not just one number, a range.")
                    st.caption("Rows (left) = FCF growth rate assumption · "
                               "Columns (top) = discount rate / WACC assumption. "
                               "Every cell is a full DCF re-run at that combination.")
                    _sens = mod_dcf.sensitivity_matrix(
                        _dcf_in["base_fcf"], _gt, _dcf_in["net_debt"],
                        _dcf_in["shares_out"], _g5, _wacc,
                    )
                    def _sens_color(v):
                        if pd.isna(v):
                            return ""
                        return ("color: #16c784" if v > _px * 1.15 else
                                "color: #ea3a44" if v < _px * 0.85 else "color: #f0b90b")
                    st.dataframe(
                        _sens.style.format("${:,.0f}").map(_sens_color),
                        width="stretch",
                    )
                    st.caption("Green = >15% above market price at those assumptions · "
                               "Red = >15% below · Amber = near market price.")

# ─── Page: Market Radar ────────────────────────────────────────────────────────
elif page == "🌍 Market Radar":
    st.title("🌍 Market Radar — Growth Opportunities")
    _page_about("""**What:** a fixed watchlist of under-the-radar growth candidates + an insider cluster-buy scanner.
**How:** each candidate gets live price/momentum/fundamental snapshot; filters are yours. The insider scanner ranks stocks by 3-month average MSPR (net insider buying) — clusters (≥+20 for 3 months) are the strongest legal signal.
**Use:** radar = idea generation. Anything interesting goes through the full Analyze pipeline first.""")
    st.caption("Scanning for high-momentum growth stocks and ETFs with strong fundamentals.")

    # ── 👤 Insider Cluster Buys scanner ───────────────────────────────────────
    with st.expander("👤 Insider Cluster Buys — who's buying their own stock?", expanded=False):
        st.caption(
            "Scans the anchor universe + your watchlist for stocks where insiders are NET "
            "BUYING (MSPR). Insiders sell for many reasons but buy for only one. "
            "Requires FINNHUB_API_KEY · results cached 12h."
        )
        if not FINNHUB_API_KEY:
            st.warning("Add FINNHUB_API_KEY to enable the insider scanner.")
        else:
            if st.button("🔍 Scan for insider buying", type="primary", key="_ins_scan"):
                _ins_universe = list(dict.fromkeys(
                    WEEKLY_UNIVERSE[:60] +
                    [s.strip().upper() for s in
                     (_load_json(Path(__file__).parent / ".watchlist.json", default={})
                      .get("symbols", "")).split(",") if s.strip()]
                ))
                _ins_rows = []
                _ins_prog = st.progress(0, text="Scanning insider sentiment…")
                for _ii, _isym in enumerate(_ins_universe):
                    _ins_prog.progress((_ii + 1) / len(_ins_universe), text=f"Scanning {_isym}…")
                    try:
                        _srows = mod_finnhub.get_insider_sentiment(_isym)
                        if not _srows:
                            continue
                        _last3 = [r["mspr"] for r in _srows[-3:] if r.get("mspr") is not None]
                        if not _last3:
                            continue
                        _avg3 = sum(_last3) / len(_last3)
                        _pos_months = sum(1 for r in _srows[-6:]
                                          if (r.get("mspr") or 0) > 0)
                        _ins_rows.append({
                            "symbol":     _isym,
                            "mspr_3m":    round(_avg3, 1),
                            "pos_months": _pos_months,
                            "latest":     _srows[-1].get("mspr"),
                        })
                    except Exception:
                        continue
                _ins_prog.empty()
                # Cluster = sustained positive MSPR
                _ins_rows.sort(key=lambda r: -r["mspr_3m"])
                st.session_state["_ins_scan_res"] = _ins_rows

            _ins_res = st.session_state.get("_ins_scan_res")
            if _ins_res is not None:
                _clusters = [r for r in _ins_res if r["mspr_3m"] >= 20 and r["pos_months"] >= 3]
                _mild     = [r for r in _ins_res if 0 < r["mspr_3m"] < 20 and r["pos_months"] >= 3]
                st.markdown(f"**Scanned {len(_ins_res)} stocks with insider data** · "
                            f"🟢 {len(_clusters)} strong clusters · 🟡 {len(_mild)} mild accumulation")
                if _clusters or _mild:
                    _ins_rows_html = ""
                    for _ir in (_clusters + _mild)[:20]:
                        _ir_c = "#16c784" if _ir["mspr_3m"] >= 20 else "#f0b90b"
                        _ins_rows_html += (
                            f'<tr>'
                            f'<td style="padding:6px 12px;font-weight:700">{_ir["symbol"]}</td>'
                            f'<td style="padding:6px 12px;text-align:right;color:{_ir_c};'
                            f'font-weight:700">{_ir["mspr_3m"]:+.0f}</td>'
                            f'<td style="padding:6px 12px;text-align:right">'
                            f'{_ir["pos_months"]}/6</td>'
                            f'<td style="padding:6px 12px;text-align:right">'
                            f'{_ir["latest"]:+.0f}</td>'
                            f'<td style="padding:6px 12px">'
                            f'{"🟢 Strong cluster buying" if _ir["mspr_3m"] >= 20 else "🟡 Steady accumulation"}</td>'
                            f'</tr>'
                        )
                    _th_ins = "text-align:left;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
                    _tr_ins = "text-align:right;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
                    st.markdown(
                        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                        f'padding:12px 16px;overflow-x:auto">'
                        f'<table style="width:100%;border-collapse:collapse"><thead><tr>'
                        f'<th style="{_th_ins}">SYMBOL</th>'
                        f'<th style="{_tr_ins}" title="Avg MSPR last 3 months. +100 = pure buying, -100 = pure selling">MSPR 3M ⓘ</th>'
                        f'<th style="{_tr_ins}" title="Months with net insider buying out of last 6">POS MONTHS ⓘ</th>'
                        f'<th style="{_tr_ins}">LATEST</th>'
                        f'<th style="{_th_ins}">SIGNAL</th>'
                        f'</tr></thead><tbody>{_ins_rows_html}</tbody></table></div>',
                        unsafe_allow_html=True,
                    )
                    st.caption("MSPR ≥ +20 for 3 months straight = a cluster — multiple insiders "
                               "deploying real money. The strongest legal signal there is. "
                               "Deep-dive candidates → Analyze → Institutional tab.")
                else:
                    st.info("No meaningful insider accumulation found in the scanned universe right now.")

    # ── 🏛 Congress Trading feed (FMP) ────────────────────────────────────────
    with st.expander("🏛 Congress Trading — recent Senate disclosures", expanded=False):
        from config import FMP_API_KEY as _fmp_key_radar
        if not _fmp_key_radar:
            st.warning("Add FMP_API_KEY to enable the Congress trading feed.")
        else:
            st.caption(mod_gloss.tip("congress_trading"))
            st.caption(
                "Free tier exposes only the 25 MOST RECENT disclosures market-wide (no "
                "per-symbol lookup, no deep history) — treat this as a rolling snapshot of "
                "what Congress just filed, not a comprehensive scanner. Disclosures lag the "
                "actual trade by up to 45 days by law."
            )
            _sen_feed = mod_fmp.senate_latest()
            if not _sen_feed:
                st.info("No data returned — check the API key or try again shortly.")
            else:
                _sen_clusters = mod_fmp.senate_cluster_summary(_sen_feed)
                if _sen_clusters:
                    st.markdown("**Multiple senators active on the same symbol:**")
                    for c in _sen_clusters[:5]:
                        st.markdown(f"- **{c['symbol']}** — {c['senators']} senators, "
                                   f"{c['buys']} buys / {c['sells']} sells, latest {c['latest']}")
                    st.markdown("---")

                _sen_rows_html = ""
                for r in _sen_feed:
                    _sc = "#16c784" if "purchase" in r["type"].lower() else \
                          "#ea3a44" if "sale" in r["type"].lower() else "#f0b90b"
                    _sen_rows_html += (
                        f'<tr>'
                        f'<td style="padding:5px 10px;color:#8a9bc2">{r["tx_date"]}</td>'
                        f'<td style="padding:5px 10px;font-weight:700">{r["symbol"] or "—"}</td>'
                        f'<td style="padding:5px 10px">{_html.escape(r["name"])}</td>'
                        f'<td style="padding:5px 10px;color:{_sc};font-weight:600">{_html.escape(r["type"])}</td>'
                        f'<td style="padding:5px 10px;color:#8a9bc2;font-size:11px">{_html.escape(r["amount"])}</td>'
                        f'</tr>'
                    )
                _th_sen = "text-align:left;font-size:10px;color:#556070;padding:4px 10px;font-family:'IBM Plex Mono',monospace"
                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                    f'padding:12px 16px;overflow-x:auto">'
                    f'<table style="width:100%;border-collapse:collapse"><thead><tr>'
                    f'<th style="{_th_sen}">TX DATE</th><th style="{_th_sen}">SYMBOL</th>'
                    f'<th style="{_th_sen}">SENATOR</th><th style="{_th_sen}">TYPE</th>'
                    f'<th style="{_th_sen}">AMOUNT</th>'
                    f'</tr></thead><tbody>{_sen_rows_html}</tbody></table></div>',
                    unsafe_allow_html=True,
                )

    if st.button("🔄 Scan Market Now", type="primary"):
        rows = []
        prog = st.progress(0)
        for i, sym in enumerate(RADAR_TICKERS):
            prog.progress((i + 1) / len(RADAR_TICKERS), text=f"Scanning {sym}...")
            try:
                info   = get_ticker_info(sym)
                price_df = get_price_history(sym, period="6mo")
                close    = price_df["Close"].squeeze() if not price_df.empty else pd.Series([])

                r1m = float(close.iloc[-1] / close.iloc[-21]  - 1) if len(close) >= 22  else None
                r3m = float(close.iloc[-1] / close.iloc[-63]  - 1) if len(close) >= 64  else None
                r6m = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) >= 127 else None

                rows.append({
                    "Ticker":      sym,
                    "Name":        info.get("shortName", sym),
                    "Price":       info.get("currentPrice") or info.get("regularMarketPrice"),
                    "Market Cap":  info.get("marketCap"),
                    "Rev Growth":  info.get("revenueGrowth"),
                    "Gross Margin":info.get("grossMargins"),
                    "Fwd P/E":     info.get("forwardPE"),
                    "1M Return":   r1m,
                    "3M Return":   r3m,
                    "6M Return":   r6m,
                    "Sector":      info.get("sector", "ETF"),
                })
            except Exception:
                pass
        prog.empty()

        df = pd.DataFrame(rows)
        st.session_state["radar_df"] = df

    if "radar_df" in st.session_state:
        df = st.session_state["radar_df"]

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            min_rev_growth = st.slider("Min Revenue Growth", -50, 100, 15, 5, format="%d%%") / 100
        with col_f2:
            min_3m_return  = st.slider("Min 3M Return", -50, 100, 5, 5, format="%d%%") / 100

        mask = pd.Series([True] * len(df))
        if "Rev Growth" in df.columns:
            mask &= df["Rev Growth"].fillna(-99) >= min_rev_growth
        if "3M Return" in df.columns:
            mask &= df["3M Return"].fillna(-99) >= min_3m_return

        filtered = df[mask].copy()

        def highlight_row(row):
            if row.get("3M Return", 0) and row["3M Return"] > 0.2:
                return ["background-color: #002200"] * len(row)
            return [""] * len(row)

        if not filtered.empty:
            styled = filtered.style.format({
                "Price":       lambda x: f"${x:.2f}"      if pd.notna(x) else "N/A",
                "Market Cap":  lambda x: fmt_num(x)        if pd.notna(x) else "N/A",
                "Rev Growth":  lambda x: f"{x*100:.1f}%"  if pd.notna(x) else "N/A",
                "Gross Margin":lambda x: f"{x*100:.1f}%"  if pd.notna(x) else "N/A",
                "Fwd P/E":     lambda x: f"{x:.1f}x"      if pd.notna(x) else "N/A",
                "1M Return":   lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
                "3M Return":   lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
                "6M Return":   lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
            }).apply(highlight_row, axis=1)
            st.dataframe(styled, width="stretch")

            st.caption(f"Showing {len(filtered)} of {len(df)} tickers. Click Ticker → paste in Analyze tab.")

            # ETF holdings quick-view
            _radar_etf_opts = [r for r in RADAR_TICKERS if r in filtered["Ticker"].values
                               and r.upper() in ("SOXX","SMH","WCLD","ARKK","QQQ","KWEB","CQQQ","FXI")]
            if not _radar_etf_opts:
                _radar_etf_opts = [r for r in RADAR_TICKERS if r.upper() in
                                   ("SOXX","SMH","WCLD","ARKK","QQQ","KWEB","CQQQ","FXI")]
            if _radar_etf_opts:
                st.divider()
                st.markdown('<div class="panel-head">ETF HOLDINGS QUICK-VIEW</div>',
                            unsafe_allow_html=True)
                _radar_etf_sel = st.selectbox(
                    "Select ETF", _radar_etf_opts,
                    label_visibility="collapsed",
                    key="radar_etf_sel",
                )
                if _radar_etf_sel:
                    mod_etf.render_etf_holdings(_radar_etf_sel, max_rows=15)
        else:
            st.info("No tickers match the current filters.")


# ─── Page: Portfolio ──────────────────────────────────────────────────────────
elif page == "💼 Portfolio":
    st.title("💼 My Portfolio")
    _page_about("""**What:** upload your real broker positions (CSV/Excel, including Israeli broker format) and get live valuation, risk metrics and an AI health check.
**How:** positions enriched with live prices; risk section computes beta, volatility, max drawdown, VaR-95 and pairwise correlations from 1y daily returns; health check scores each holding and flags TRIM/EXIT candidates.
**Use:** the correlation heatmap is the most underrated view — 10 positions with 0.9 correlation are ONE bet. Export to Excel for records.""")
    st.caption("Upload your broker's CSV export or a standard CSV (Ticker, Shares, Avg Price).")

    col_up, col_dl = st.columns([3, 1])
    with col_up:
        uploaded = st.file_uploader("Upload portfolio CSV", type=["csv", "xlsx"],
                                    label_visibility="collapsed")
    with col_dl:
        sample_csv = "Ticker,Shares,Avg Price\nNVDA,10,500\nQQQ,5,450\nKWEB,20,30\n"
        st.download_button("📥 Sample CSV", sample_csv, "portfolio_sample.csv",
                           "text/csv", width="stretch")

    if uploaded:
        df_raw, fmt = mod_portfolio.load_portfolio(uploaded)

        if df_raw is None or df_raw.empty:
            st.error("Could not parse the file. Please check the format.")
            st.stop()

        # ── BROKER FORMAT ──────────────────────────────────────────────────────
        if fmt == "broker":
            st.success(f"Detected broker export format — {len(df_raw)} positions loaded.")

            with st.spinner("Fetching live prices for US stocks..."):
                df = mod_portfolio.enrich_portfolio_broker(df_raw)
                if "Sector" not in df.columns:
                    df["Sector"] = df["Type"]
                summary = mod_portfolio.portfolio_summary_broker(df)

            # KPIs
            c1, c2, c3, c4, c5 = st.columns(5)
            pnl_pct = summary["total_pnl_pct"]
            c1.metric("Total Value (NIS)", f"₪{summary['total_value_nis']:,.0f}")
            c2.metric("Total P&L (NIS)",   f"₪{summary['total_pnl_nis']:+,.0f}",
                      delta=f"{pnl_pct*100:+.1f}%")
            c3.metric("Positions",   summary["n_positions"])
            c4.metric("US Stocks",   summary["us_positions"])
            c5.metric("Israeli",     summary["il_positions"])

            st.markdown("---")

            # ── Holdings table (full width) ────────────────────────────────────
            st.markdown('<div class="panel-head">HOLDINGS</div>', unsafe_allow_html=True)

            def _cp(val):
                if not isinstance(val, (int, float)) or pd.isna(val): return ""
                return "color:#16c784" if val >= 0 else "color:#ea3a44"

            show_cols = ["Name", "Type", "Currency", "Shares",
                         "Avg Price", "Current Price", "Value (NIS)", "P&L (%)", "P&L (NIS)"]
            show_cols = [c for c in show_cols if c in df.columns]

            styled_b = df[show_cols].style.format({
                "Shares":        lambda x: f"{x:,.2f}" if pd.notna(x) else "N/A",
                "Avg Price":     lambda x: f"{x:,.2f}" if pd.notna(x) else "N/A",
                "Current Price": lambda x: f"{x:,.2f}" if pd.notna(x) else "N/A",
                "Value (NIS)":   lambda x: f"₪{x:,.0f}" if pd.notna(x) else "N/A",
                "P&L (%)":       lambda x: f"{x:+.1f}%" if pd.notna(x) else "N/A",
                "P&L (NIS)":     lambda x: f"₪{x:+,.0f}" if pd.notna(x) else "N/A",
            }).map(_cp, subset=["P&L (%)", "P&L (NIS)"])

            st.dataframe(styled_b, width="stretch", hide_index=True)

            try:
                st.download_button(
                    "📥 Download Excel report",
                    data=mod_xlsx.portfolio_xlsx(df, summary, title="Broker Portfolio"),
                    file_name=f"portfolio_broker_{_date.today().isoformat()}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="_pfb_xlsx",
                )
            except Exception:
                pass

            # Quick analyze buttons for US stocks
            us_tickers = df[df["Type"] == "US Stock"]["Ticker"].dropna().tolist()
            us_tickers = [t for t in us_tickers if t]
            if us_tickers:
                st.markdown('<div class="panel-head" style="margin-top:12px">QUICK ANALYZE</div>',
                            unsafe_allow_html=True)
                btn_cols = st.columns(min(len(us_tickers), 6))
                for i, tk in enumerate(us_tickers):
                    if btn_cols[i % 6].button(tk, key=f"pt_{tk}", width="stretch"):
                        st.session_state["symbol"] = tk
                        st.rerun()

            st.markdown("---")

            # ── Charts row ─────────────────────────────────────────────────────
            col_pie, col_bar = st.columns([1, 1])
            with col_pie:
                st.markdown('<div class="panel-head">SECTOR ALLOCATION</div>', unsafe_allow_html=True)
                sector_df = summary["sector_exposure"].reset_index()
                sector_df.columns = ["Sector", "Weight (%)"]
                fig = px.pie(
                    sector_df, values="Weight (%)", names="Sector",
                    color_discrete_sequence=["#16c784","#60a5fa","#f0b90b","#f472b6",
                                             "#a78bfa","#34d399","#fb923c","#94a3b8"],
                    hole=0.45,
                )
                fig.update_layout(
                    paper_bgcolor="#131722", font_color="#e8edf8",
                    font_family="IBM Plex Mono",
                    showlegend=True, height=320,
                    margin=dict(t=10, b=10, l=10, r=10),
                )
                st.plotly_chart(fig, width="stretch")

            with col_bar:
                st.markdown('<div class="panel-head">US vs ISRAELI SPLIT</div>', unsafe_allow_html=True)
                us_val = df[df["Type"]=="US Stock"]["Value (NIS)"].sum()
                il_val = df[df["Type"]=="Israeli"]["Value (NIS)"].sum()
                total  = us_val + il_val
                if total:
                    us_pct = us_val / total * 100
                    il_pct = il_val / total * 100
                    fig_bar = go.Figure()
                    fig_bar.add_trace(go.Bar(
                        name="US Stocks", x=["Portfolio"], y=[us_val],
                        marker_color="#60a5fa",
                        text=f"US {us_pct:.0f}%", textposition="inside",
                    ))
                    fig_bar.add_trace(go.Bar(
                        name="Israeli", x=["Portfolio"], y=[il_val],
                        marker_color="#16c784",
                        text=f"IL {il_pct:.0f}%", textposition="inside",
                    ))
                    fig_bar.update_layout(
                        barmode="stack", paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                        font_color="#e8edf8", font_family="IBM Plex Mono",
                        height=320, margin=dict(t=10, b=10, l=10, r=10),
                        yaxis_tickprefix="₪", yaxis_tickformat=",.0f",
                        legend=dict(bgcolor="#1c2333", bordercolor="#2a3348"),
                        showlegend=True,
                    )
                    fig_bar.update_yaxes(gridcolor="#2a3348")
                    st.plotly_chart(fig_bar, width="stretch")

            # ── Portfolio Health Check ─────────────────────────────────────────
            st.markdown("---")
            st.markdown('<div class="panel-head">🔬 PORTFOLIO HEALTH CHECK</div>',
                        unsafe_allow_html=True)

            if not ANTHROPIC_API_KEY:
                st.warning("Add ANTHROPIC_API_KEY to .env to enable AI portfolio analysis.")
            else:
                if st.button("🔬 Run Full Portfolio Analysis", type="primary",
                             key="run_health"):
                    total_val = df["Value (NIS)"].sum()
                    scored_positions = []

                    # Score US stocks
                    us_df = df[df["Type"] == "US Stock"].copy()
                    us_rows = [(_, row) for _, row in us_df.iterrows() if row.get("Ticker")]
                    if us_rows:
                        prog = st.progress(0, text="Scoring US positions...")
                        for idx, (_, row) in enumerate(us_rows):
                            tk = row.get("Ticker", "")
                            prog.progress((idx + 1) / len(us_rows), text=f"Scoring {tk}...")
                            sd = mod_phealth.score_position(tk)
                            weight = (row["Value (NIS)"] / total_val * 100) if total_val else 0
                            scored_positions.append({
                                "pos_type":   "US",
                                "ticker":     tk,
                                "name":       sd.get("name", row.get("Name", tk)),
                                "weight_pct": weight,
                                "value_nis":  row.get("Value (NIS)", 0),
                                "pnl_pct":    row.get("P&L (%)", 0) or 0,
                                "sector":     sd.get("sector", "Unknown"),
                                "score_data": sd,
                            })
                        prog.empty()

                    # Add Israeli positions (no live scoring — use P&L + name)
                    il_df = df[df["Type"] == "Israeli"].copy()
                    for _, row in il_df.iterrows():
                        name   = row.get("Name", "")
                        weight = (row["Value (NIS)"] / total_val * 100) if total_val else 0
                        scored_positions.append({
                            "pos_type":    "IL",
                            "ticker":      name[:12],
                            "name":        name,
                            "weight_pct":  weight,
                            "value_nis":   row.get("Value (NIS)", 0),
                            "pnl_pct":     row.get("P&L (%)", 0) or 0,
                            "asset_class": mod_phealth.classify_israeli(name),
                            "score_data":  {},
                        })

                    if not scored_positions:
                        st.info("No positions found to analyze.")
                    else:
                        with st.spinner("Claude is reviewing your full portfolio..."):
                            result = mod_phealth.run_health_check(scored_positions)
                        st.session_state["portfolio_health"] = result
                        st.session_state["portfolio_scored"] = scored_positions

                if "portfolio_health" in st.session_state:
                    result  = st.session_state["portfolio_health"]
                    scored  = st.session_state.get("portfolio_scored", [])

                    if "error" in result:
                        st.error(f"Analysis error: {result['error']}")
                    else:
                        hs_color = (
                            "#16c784" if result["health_score"] >= 7
                            else "#f0b90b" if result["health_score"] >= 5
                            else "#ea3a44"
                        )

                        # ── Health Score + Summary ─────────────────────────────
                        h1, h2 = st.columns([1, 2])
                        with h1:
                            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:24px;text-align:center">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8a9bc2;
              text-transform:uppercase;letter-spacing:1.2px;margin-bottom:10px">
    PORTFOLIO HEALTH</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:64px;font-weight:700;
              color:{hs_color};line-height:1;margin-bottom:8px;white-space:nowrap">
    {result['health_score']}</div>
  <div style="color:#556070;font-size:12px;margin-bottom:12px">/ 10</div>
  <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;
               padding:4px 12px;border-radius:5px;background:{hs_color}18;
               color:{hs_color};border:1px solid {hs_color}40">
    {result['health_label']}</span>
</div>""", unsafe_allow_html=True)

                        with h2:
                            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:20px;height:100%">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8a9bc2;
              text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
    THESIS ALIGNMENT</div>
  <div style="font-size:13px;color:#e8edf8;line-height:1.7;margin-bottom:14px">
    {result.get('thesis_alignment','')}</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#8a9bc2;
              text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">
    OVERALL ASSESSMENT</div>
  <div style="font-size:13px;color:#b0bec5;line-height:1.6">
    {result.get('health_summary','')}</div>
</div>""", unsafe_allow_html=True)

                        st.markdown("---")

                        # ── Position Actions ───────────────────────────────────
                        st.markdown('<div class="panel-head">POSITION RECOMMENDATIONS</div>',
                                    unsafe_allow_html=True)

                        pos_recs = {p["ticker"]: p for p in result.get("positions", [])}
                        ac = mod_phealth.SCORE_COLORS

                        # Build scored table
                        rows_disp = []
                        for sp in scored:
                            tk      = sp["ticker"]
                            is_il   = sp.get("pos_type") == "IL"
                            # Try match by ticker, then by first word of name
                            rec = (pos_recs.get(tk) or
                                   pos_recs.get(sp["name"][:12]) or
                                   next((v for k, v in pos_recs.items()
                                         if sp["name"].lower().startswith(k.lower())), {}))
                            sd = sp["score_data"]
                            rows_disp.append({
                                "Ticker":    tk if not is_il else "🇮🇱",
                                "Name":      sp["name"][:28],
                                "Type":      "IL Fund" if is_il else "US",
                                "Asset":     sp.get("asset_class", sd.get("sector", "?")),
                                "Weight":    f"{sp['weight_pct']:.1f}%",
                                "P&L":       f"{sp['pnl_pct']:+.1f}%",
                                "Score":     sd.get("score") if not is_il else "—",
                                "Fund":      sd.get("fundamental") if not is_il else "—",
                                "Mom":       sd.get("momentum") if not is_il else "—",
                                "Action":    rec.get("action", "N/A"),
                                "Reason":    rec.get("reason", ""),
                                "Risk":      rec.get("risk", ""),
                            })

                        for r in rows_disp:
                            action  = r["Action"]
                            col     = ac.get(action, "#556070")
                            score_v = r["Score"]
                            is_il_r = r["Type"] == "IL Fund"
                            try:
                                bar_w = f"{max(0, min(100, (float(score_v)-1)/9*100)):.0f}%" if score_v and score_v != "—" else "0%"
                            except Exception:
                                bar_w = "0%"

                            type_badge = (
                                f'<span style="font-size:10px;background:#2a3348;color:#8a9bc2;'
                                f'padding:2px 6px;border-radius:3px;margin-left:6px">🇮🇱 {r["Asset"]}</span>'
                                if is_il_r else
                                f'<span style="font-size:10px;background:#2a3348;color:#60a5fa;'
                                f'padding:2px 6px;border-radius:3px;margin-left:6px">🇺🇸 {r["Asset"]}</span>'
                            )
                            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-left:4px solid {col};
            border-radius:8px;padding:14px 18px;margin-bottom:8px">
  <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap">
    <div style="min-width:60px">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:16px;
                  font-weight:700;color:#e8edf8;white-space:nowrap">
        {r['Name'][:24]}{type_badge}</div>
    </div>
    <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;
                 padding:3px 10px;border-radius:4px;background:{col}20;
                 color:{col};border:1px solid {col}40;white-space:nowrap">{action}</span>
    <div style="display:grid;grid-template-columns:repeat(4,auto);gap:12px;font-size:12px;
                font-family:'IBM Plex Mono',monospace">
      <div><span style="color:#8a9bc2">Weight </span><b style="color:#e8edf8">{r['Weight']}</b></div>
      <div><span style="color:#8a9bc2">P&L </span>
           <b style="color:{'#16c784' if '+' in r['P&L'] else '#ea3a44'}">{r['P&L']}</b></div>
      <div><span style="color:#8a9bc2">Score </span>
           <b style="color:{col}">{score_v or '—'}</b></div>
      <div><span style="color:#8a9bc2">Mom </span>
           <b style="color:#e8edf8">{r['Mom'] or 'N/A'}</b></div>
    </div>
    <div style="flex:1;min-width:200px;font-size:12px;color:#b0bec5;line-height:1.5">
      {r['Reason']}
    </div>
  </div>
  <div style="height:2px;background:#2a3348;border-radius:1px;margin-top:10px">
    <div style="height:100%;width:{bar_w};background:{col};border-radius:1px"></div>
  </div>
</div>""", unsafe_allow_html=True)

                        st.markdown("---")

                        # ── Top 3 Changes + Missing Exposures ─────────────────
                        col_act, col_miss = st.columns(2)
                        with col_act:
                            st.markdown('<div class="panel-head">TOP 3 ACTIONS THIS WEEK</div>',
                                        unsafe_allow_html=True)
                            for i, change in enumerate(result.get("top_changes", []), 1):
                                st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:12px 16px;margin-bottom:8px;display:flex;gap:12px;align-items:flex-start">
  <span style="font-family:'IBM Plex Mono',monospace;font-size:18px;font-weight:700;
               color:#16c784;flex-shrink:0">{i}</span>
  <span style="font-size:13px;color:#e8edf8;line-height:1.6">{change}</span>
</div>""", unsafe_allow_html=True)

                        with col_miss:
                            st.markdown('<div class="panel-head">MISSING EXPOSURES</div>',
                                        unsafe_allow_html=True)
                            for me in result.get("missing_exposures", []):
                                st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:12px 16px;margin-bottom:8px">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;
               color:#f0b90b;margin-bottom:4px">+ {me.get('theme','')}</div>
  <div style="font-size:12px;color:#8a9bc2;line-height:1.5">{me.get('why','')}</div>
</div>""", unsafe_allow_html=True)

                        # Concentration risks
                        risks = result.get("concentration_risks", [])
                        if risks:
                            st.markdown('<div class="panel-head" style="margin-top:8px">CONCENTRATION RISKS</div>',
                                        unsafe_allow_html=True)
                            for risk in risks:
                                st.markdown(f"⚠️ {risk}")

            # ── ⚖️ Portfolio Risk & Correlation (Broker) ──────────────────────
            st.markdown("---")
            st.markdown('<div class="panel-head">⚖️ PORTFOLIO RISK & CORRELATION</div>',
                        unsafe_allow_html=True)

            _b_us = df[df["Type"] == "US Stock"].copy() if "Type" in df.columns else pd.DataFrame()
            _b_syms = _b_us["Ticker"].dropna().tolist() if not _b_us.empty else []
            _b_vals = _b_us["Value (NIS)"].tolist() if "Value (NIS)" in _b_us.columns else []
            _b_total = sum(_b_vals) if _b_vals else 1
            _b_wts   = [v / _b_total for v in _b_vals] if _b_vals else []

            if len(_b_syms) >= 2:
                if st.button("📐 Compute Risk Metrics", key="run_risk_broker"):
                    with st.spinner("Computing correlation matrix & risk metrics…"):
                        st.session_state["port_risk_broker"] = mod_risk.compute_risk(
                            _b_syms, _b_wts
                        )

                if "port_risk_broker" in st.session_state:
                    _pb = st.session_state["port_risk_broker"]
                    if "error" in _pb:
                        st.warning(_pb["error"])
                    else:
                        _pb_c1, _pb_c2, _pb_c3, _pb_c4, _pb_c5 = st.columns(5)
                        _pb_c1.metric("Portfolio Beta", f"{_pb['portfolio_beta']:.2f}",
                                      help=mod_gloss.tip("beta"))
                        _pb_c2.metric("Annual Vol", f"{_pb['annual_vol_pct']:.1f}%",
                                      help=mod_gloss.tip("volatility"))
                        _pb_c3.metric("Max Drawdown", f"{_pb['max_drawdown_pct']:.1f}%",
                                      help=mod_gloss.tip("max_drawdown"))
                        _pb_c4.metric("VaR 95% (1d)", f"{_pb['var_95_1d']:.2f}%",
                                      help=mod_gloss.tip("var"))
                        _pb_c5.metric("Sharpe", f"{_pb['sharpe_approx']:.2f}",
                                      help=mod_gloss.tip("sharpe"))

                        if _pb.get("risk_flags"):
                            st.markdown('<div class="panel-head" style="margin-top:8px">'
                                        'RISK FLAGS</div>', unsafe_allow_html=True)
                            for _flag in _pb["risk_flags"]:
                                st.warning(f"⚠ {_flag}")

                        _corr = _pb["correlation_matrix"]
                        if _corr is not None and not _corr.empty:
                            st.markdown('<div class="panel-head" style="margin-top:8px">'
                                        'CORRELATION MATRIX</div>', unsafe_allow_html=True)
                            fig_corr_b = go.Figure(data=go.Heatmap(
                                z=_corr.values,
                                x=_corr.columns.tolist(),
                                y=_corr.index.tolist(),
                                colorscale=[
                                    [0.0, "#ea3a44"],
                                    [0.5, "#1c2333"],
                                    [1.0, "#16c784"],
                                ],
                                zmin=-1, zmax=1,
                                text=_corr.round(2).values,
                                texttemplate="%{text}",
                                hovertemplate="%{y} ↔ %{x}<br>r = %{z:.2f}<extra></extra>",
                            ))
                            fig_corr_b.update_layout(
                                paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                                font_color="#e8edf8", font_family="IBM Plex Mono",
                                height=max(300, len(_corr) * 45 + 60),
                                margin=dict(t=10, b=10, l=10, r=10),
                            )
                            st.plotly_chart(fig_corr_b, width="stretch")
            else:
                st.info("Need at least 2 US stock positions to compute risk metrics.")

        # ── STANDARD FORMAT ────────────────────────────────────────────────────
        else:
            run_scores = st.checkbox("Run full scores (slower)", value=False)
            with st.spinner("Loading portfolio data..."):
                df = mod_portfolio.enrich_portfolio(df_raw, run_scores=run_scores)
                summary = mod_portfolio.portfolio_summary(df)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Value",  fmt_num(summary["total_value"]))
            c2.metric("Total Cost",   fmt_num(summary["total_cost"]))
            pnl_pct = summary["total_pnl_pct"]
            c3.metric("Total P&L",    fmt_num(summary["total_pnl"]),
                      delta=f"{pnl_pct*100:+.1f}%")
            c4.metric("Positions", summary["n_positions"])

            st.markdown("---")
            col_t, col_p = st.columns([3, 2])
            with col_t:
                st.subheader("Holdings")
                if "Price Stale" in df.columns and df["Price Stale"].any():
                    _stale_syms = df.loc[df["Price Stale"], "Ticker"].tolist()
                    st.warning(f"⚠ Live price unavailable for {', '.join(_stale_syms)} — shown at cost (P&L not real).")
                cols_show = ["Ticker","Name","Shares","Avg Price","Current Price",
                             "Market Value","P&L ($)","P&L (%)","Sector"]
                if "Score" in df.columns:
                    cols_show += ["Score","Rating"]

                def color_pnl(val):
                    if isinstance(val, str): return ""
                    color = "#16c784" if val >= 0 else "#ea3a44"
                    return f"color: {color}"

                styled_p = df[cols_show].style.format({
                    "Avg Price":     "${:.2f}",
                    "Current Price": "${:.2f}",
                    "Market Value":  lambda x: fmt_num(x),
                    "P&L ($)":       lambda x: f"${x:+,.0f}",
                    "P&L (%)":       lambda x: f"{x*100:+.1f}%",
                }).map(color_pnl, subset=["P&L ($)", "P&L (%)"])
                st.dataframe(styled_p, width="stretch")

                try:
                    st.download_button(
                        "📥 Download Excel report",
                        data=mod_xlsx.portfolio_xlsx(df, summary),
                        file_name=f"portfolio_{_date.today().isoformat()}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="_pf_xlsx",
                    )
                except Exception:
                    pass

            with col_p:
                st.subheader("Sector Exposure")
                sector_df = summary["sector_exposure"].reset_index()
                sector_df.columns = ["Sector", "Weight (%)"]
                fig = px.pie(
                    sector_df, values="Weight (%)", names="Sector",
                    color_discrete_sequence=px.colors.qualitative.Set3,
                    hole=0.4,
                )
                fig.update_layout(
                    paper_bgcolor="#131722", font_color="#e8edf8",
                    showlegend=True, height=350, margin=dict(t=10, b=10),
                )
                st.plotly_chart(fig, width="stretch")

            # ── ⚖️ Portfolio Risk & Correlation ───────────────────────────────
            st.markdown("---")
            st.markdown('<div class="panel-head">⚖️ PORTFOLIO RISK & CORRELATION</div>',
                        unsafe_allow_html=True)

            risk_syms = (
                df["Ticker"].dropna().tolist()
                if "Ticker" in df.columns else []
            )
            total_val_std = df["Market Value"].sum() if "Market Value" in df.columns else 1
            risk_wts = (
                (df["Market Value"] / total_val_std).tolist()
                if "Market Value" in df.columns and total_val_std > 0
                else [1 / len(risk_syms)] * len(risk_syms)
            )

            if st.button("📐 Compute Risk Metrics", key="run_risk_std"):
                with st.spinner("Computing correlation matrix & risk metrics…"):
                    st.session_state["port_risk"] = mod_risk.compute_risk(
                        risk_syms, risk_wts
                    )

            if "port_risk" in st.session_state:
                _pr = st.session_state["port_risk"]
                if "error" in _pr:
                    st.warning(_pr["error"])
                else:
                    _pr_c1, _pr_c2, _pr_c3, _pr_c4, _pr_c5 = st.columns(5)
                    _pr_c1.metric("Portfolio Beta", f"{_pr['portfolio_beta']:.2f}",
                                  help=mod_gloss.tip("beta"))
                    _pr_c2.metric("Annual Vol", f"{_pr['annual_vol_pct']:.1f}%",
                                  help=mod_gloss.tip("volatility"))
                    _pr_c3.metric("Max Drawdown", f"{_pr['max_drawdown_pct']:.1f}%",
                                  help=mod_gloss.tip("max_drawdown"))
                    _pr_c4.metric("VaR 95% (1d)", f"{_pr['var_95_1d']:.2f}%",
                                  help=mod_gloss.tip("var"))
                    _pr_c5.metric("Sharpe (approx)", f"{_pr['sharpe_approx']:.2f}",
                                  help=mod_gloss.tip("sharpe"))

                    if _pr.get("risk_flags"):
                        st.markdown('<div class="panel-head" style="margin-top:8px">'
                                    'RISK FLAGS</div>', unsafe_allow_html=True)
                        for flag in _pr["risk_flags"]:
                            st.warning(f"⚠ {flag}")

                    # Correlation heatmap
                    corr_df = _pr["correlation_matrix"]
                    if corr_df is not None and not corr_df.empty:
                        st.markdown('<div class="panel-head" style="margin-top:8px">'
                                    'CORRELATION MATRIX</div>', unsafe_allow_html=True)
                        fig_corr = go.Figure(data=go.Heatmap(
                            z=corr_df.values,
                            x=corr_df.columns.tolist(),
                            y=corr_df.index.tolist(),
                            colorscale=[
                                [0.0,  "#ea3a44"],
                                [0.5,  "#1c2333"],
                                [1.0,  "#16c784"],
                            ],
                            zmin=-1, zmax=1,
                            text=corr_df.round(2).values,
                            texttemplate="%{text}",
                            hovertemplate="%{y} ↔ %{x}<br>r = %{z:.2f}<extra></extra>",
                        ))
                        fig_corr.update_layout(
                            paper_bgcolor="#131722", plot_bgcolor="#1c2333",
                            font_color="#e8edf8", font_family="IBM Plex Mono",
                            height=max(300, len(corr_df) * 45 + 60),
                            margin=dict(t=10, b=10, l=10, r=10),
                        )
                        st.plotly_chart(fig_corr, width="stretch")


# ─── Page: Watchlist ──────────────────────────────────────────────────────────
elif page == "👁 Watchlist":
    st.title("👁 Watchlist")
    _page_about("""**What:** quick composite scores for a list of tickers you're stalking — saved to disk, survives restarts.
**How:** each ticker gets fundamental + technical + momentum scores (same engines as Analyze, macro/smart-money pillars neutral at 5), blended into one 1-10 score.
**Use:** a triage table — sort by score, deep-dive the top in Analyze. Watchlist symbols also feed the earnings-alert scanner automatically.""")
    st.caption("Track multiple tickers with quick scores. Your list is saved to disk automatically.")

    # Persisted to .watchlist.json — survives refresh and app restarts
    _WL_FILE = Path(__file__).parent / ".watchlist.json"
    _wl_saved = _load_json(_WL_FILE, default={})
    default_watch = _wl_saved.get("symbols", "NVDA, QQQ, KWEB, ARM, DDOG")

    watchlist_input = st.text_input("Tickers (comma-separated)", value=default_watch)
    tickers = [t.strip().upper() for t in watchlist_input.split(",") if t.strip()]

    # Save whenever the list changes
    if watchlist_input.strip() and watchlist_input != _wl_saved.get("symbols"):
        _save_json(_WL_FILE, {"symbols": watchlist_input.strip(),
                              "updated": datetime.now().isoformat()})

    if st.button("📊 Load Watchlist", type="primary"):
        rows = []
        prog = st.progress(0)
        for i, sym in enumerate(tickers):
            prog.progress((i + 1) / len(tickers), text=f"Loading {sym}...")
            try:
                info  = get_ticker_info(sym)
                df_p  = get_price_history(sym, period="6mo")
                close = df_p["Close"].squeeze() if not df_p.empty else pd.Series([])
                price = info.get("currentPrice") or info.get("regularMarketPrice")
                r1m = float(close.iloc[-1] / close.iloc[-21]  - 1) if len(close) >= 22  else None
                r3m = float(close.iloc[-1] / close.iloc[-63]  - 1) if len(close) >= 64  else None

                f = mod_fund.analyze(sym)
                t = mod_tech.analyze(sym)
                mo = mod_mom.analyze(sym)
                s = mod_scoring.compute(f["score"], t["score"], mo["score"], 5, 5, 5)

                rows.append({
                    "Ticker":       sym,
                    "Name":         info.get("shortName", sym),
                    "Price":        price,
                    "1M Return":    r1m,
                    "3M Return":    r3m,
                    "Rev Growth":   info.get("revenueGrowth"),
                    "Fwd P/E":      info.get("forwardPE"),
                    "Score":        s["final"],
                    "Rating":       s["label"],
                })
            except Exception as e:
                rows.append({"Ticker": sym, "Score": None, "Rating": "Error"})
        prog.empty()

        st.session_state["watchlist_df"] = pd.DataFrame(rows)

    if "watchlist_df" in st.session_state:
        df = st.session_state["watchlist_df"].sort_values("Score", ascending=False, na_position="last")

        def color_rating(val):
            colors = {"Strong Buy": "#00c853", "Buy": "#64dd17", "Hold": "#ffd600",
                      "Watch": "#ff6d00", "Avoid": "#d50000"}
            return f"color: {colors.get(val, '#9fa8da')}"

        styled = df.style.format({
            "Price":      lambda x: f"${x:.2f}" if pd.notna(x) else "N/A",
            "1M Return":  lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
            "3M Return":  lambda x: f"{x*100:+.1f}%" if pd.notna(x) else "N/A",
            "Rev Growth": lambda x: f"{x*100:.1f}%"  if pd.notna(x) else "N/A",
            "Fwd P/E":    lambda x: f"{x:.1f}x"      if pd.notna(x) else "N/A",
            "Score":      lambda x: f"{x:.1f}"        if pd.notna(x) else "N/A",
        }).map(color_rating, subset=["Rating"])

        st.dataframe(styled, width="stretch")


# ─── Page: Weekly Picks ──────────────────────────────────────────────────────
elif page == "⭐ Weekly Picks":
    import datetime as _dt_wp
    _wp_week_num = _dt_wp.date.today().isocalendar()[1]
    st.title("⭐ Weekly Buy Recommendations")
    _page_about("""**What:** an automatic scanner that surfaces up to 15 buyable ideas *this week* — swing setups, quality stocks knocked down to a price their business doesn't justify, and trending theme ETFs.
**How:** ~80 stocks scanned weekly from a broad universe (curated list + the live S&P 500, not a fixed closed list) plus ~42 theme ETFs. Three paths feed one ranked list: 🔥 Swing (passes 4/6 technical+fundamental entry conditions), 💎 Quality Dip (strong business, price out of favor — Opportunity Lens' "quality on sale" read), 📊 ETF Theme (trend/relative-strength scan, no fundamentals gate). Repeat stock picks get a recency penalty; max 2 stocks per sector; ETFs capped at 5 of the 15 slots.
**Use:** treat picks as a curated shortlist for deep-dive in Analyze — not as blind buy orders. The regime banner tells you how aggressive the environment allows you to be.""")
    st.caption(
        f"Week {_wp_week_num} · Scanning ~80 stocks from a "
        f"{st.session_state.get('wp_output', {}).get('universe_size', '500+')}-stock universe "
        f"(curated list + live S&P 500) plus ~42 theme ETFs · "
        "Recency penalty + sector cap ensure fresh picks every week · "
        "Max 15 picks shown, at most 5 of them ETFs"
    )

    if not ANTHROPIC_API_KEY:
        st.warning("Add ANTHROPIC_API_KEY for Claude buy theses.")

    # ── Auto-load from disk cache on first visit ──────────────────────────────
    if "wp_output" not in st.session_state:
        cached = _wp_load()
        if cached:
            st.session_state["wp_output"] = cached

    # ── Header: last scan info + refresh button ───────────────────────────────
    if "wp_output" in st.session_state:
        _age_h = st.session_state["wp_output"].get("_cached_age_h", 0)
        _at    = st.session_state["wp_output"].get("_cached_at", "")
        _lbl   = f"Last scanned: {_at} ({_age_h:.1f}h ago)" if _at else ""
        hcol1, hcol2 = st.columns([4, 1])
        with hcol1:
            if _lbl:
                st.caption(f"💾 {_lbl} — results auto-saved between sessions")
        with hcol2:
            run_weekly = st.button("🔄 Refresh Scan", type="primary", width="stretch")
    else:
        run_weekly = st.button("🔍 Scan for This Week's Opportunities", type="primary")

    if run_weekly:
        prog = st.progress(0, text="Reading market conditions…")
        output = mod_weekly.run_recommendations(
            progress_cb=lambda pct, txt: prog.progress(pct, text=txt)
        )
        prog.empty()
        _wp_save(output)                          # persist to disk
        st.session_state["wp_output"] = output

    if "wp_output" not in st.session_state:
        st.info("Click Scan to begin — results are saved automatically for future sessions.")
        st.stop()

    output       = st.session_state["wp_output"]
    regime       = output["regime"]
    recs         = output["recommendations"]
    scanned      = output["scanned"]
    filtered_out = output["filtered_out"]
    mkt          = regime["signals"]

    if output.get("thesis_error"):
        st.error(f"⚠ Claude buy-thesis generation failed: {output['thesis_error']} — "
                 f"picks are shown without AI theses. Re-run the scan to retry.")
    elif output.get("thesis_warning"):
        st.warning(f"⚠ {output['thesis_warning']}")

    # ── Market Regime banner (native Streamlit) ───────────────────────────────
    rc = regime["regime_color"]
    st.markdown(
        f'<div style="border-left:5px solid {rc};padding:10px 16px;'
        f'background:{rc}10;border-radius:0 8px 8px 0;margin-bottom:12px">'
        f'<b style="color:{rc};font-size:16px">'
        f'{regime["regime_emoji"]} {regime["regime"]}</b>&nbsp;&nbsp;'
        f'<span style="color:#8a9bc2;font-size:12px">{regime["regime_desc"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Missing feeds show N/A instead of fabricated numbers
    for _dw in regime.get("data_warnings", []):
        st.warning(f"⚠ {_dw}")
    rm1, rm2, rm3, rm4 = st.columns(4)
    rm1.metric("VIX", f"{mkt.get('vix') if mkt.get('vix') is not None else 'N/A'}",
               help="Market fear index. Below 18 = calm, rising market. 18-25 = neutral. Above 25 = fear, elevated risk. Above 30 = panic.")
    rm2.metric("S&P 1M", f"{(mkt.get('spy_r1m') or 0)*100:+.1f}%" if mkt.get('spy_r1m') is not None else "N/A",
               help="S&P 500 performance last month. Positive = market rising = supportive environment.")
    rm3.metric("QQQ 1M", f"{(mkt.get('qqq_r1m') or 0)*100:+.1f}%" if mkt.get('qqq_r1m') is not None else "N/A",
               help="Nasdaq (QQQ) performance last month. Indicator of tech and growth sector strength.")
    rm4.metric("10Y Yield", f"{mkt.get('tnx')}%" if mkt.get('tnx') is not None else "N/A",
               help="10-year Treasury yield. Rising yields = pressure on growth stocks. Above 4.5% = headwind warning.")

    st.divider()

    # ── Summary ───────────────────────────────────────────────────────────────
    strong_buys = [r for r in recs if r.get("thesis", {}).get("action") == "STRONG BUY"]
    buys        = [r for r in recs if r.get("thesis", {}).get("action") == "BUY"]

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Scanned",    scanned,
              help="Stocks evaluated this week: 30 anchor names + 50 rotating from the full universe (curated list ∪ live S&P 500). Rotation ensures fresh candidates surface every week.")
    s2.metric("Qualified",  len(recs), delta=f"{filtered_out} filtered out",
              help="Combines 3 paths, capped at 15 total: 🔥 Swing (≥4/6 entry conditions at regime-set thresholds), "
                   "💎 Quality Dip (strong business, beaten-down price), 📊 ETF Theme (trend strength, no fundamentals gate).")
    s3.metric("Strong Buy", len(strong_buys),
              help=mod_gloss.tip("weekly_score"))
    s4.metric("Buy",        len(buys),
              help=mod_gloss.tip("conviction"))

    _n_swing = output.get("n_swing", len(recs))
    _n_dip   = output.get("n_dip", 0)
    _n_etf   = output.get("n_etf", 0)
    st.caption(
        f"This week's list: 🔥 {sum(1 for r in recs if r.get('category')=='SWING')} swing · "
        f"💎 {sum(1 for r in recs if r.get('category')=='QUALITY_DIP')} quality dip · "
        f"📊 {sum(1 for r in recs if r.get('category')=='ETF_THEME')} ETF theme "
        f"(of {_n_swing} swing-qualified, {_n_dip} quality-dip-qualified, {_n_etf} ETF-qualified found this week — capped to 15)"
    )

    if not recs:
        thresh = output.get("thresholds", {})
        st.warning(
            f"No stocks passed entry conditions for **{regime['regime']}** regime. "
            f"A stock needs ≥4 of 6 criteria:"
        )
        st.markdown(
            f"- Fundamental ≥ **{thresh.get('fundamental', '?')}** / 10\n"
            f"- Technical ≥ **{thresh.get('technical', '?')}** / 10\n"
            f"- Analyst Bull% ≥ **{thresh.get('bull_pct', '?')}%**\n"
            f"- Above MA200\n"
            f"- 3M return ≥ **{thresh.get('r3m_min', 0)*100:.0f}%**\n"
            f"- Options C/P ≥ 0.7 (or no data)"
        )
        near = output.get("near_misses", [])
        if near:
            st.markdown("**Closest candidates (didn't qualify):**")
            _nm_cols = st.columns(min(len(near), 5))
            for _col, _nm in zip(_nm_cols, near):
                _r3m_pct = f"{_nm.get('r3m',0)*100:+.0f}%" if _nm.get("r3m") is not None else "N/A"
                _bp = f"{_nm.get('bull_pct',0):.0f}%"
                _ma = "✅" if _nm.get("above_ma200") else "❌"
                _f  = f"{_nm.get('fundamental',0):.1f}" if _nm.get("fundamental") else "—"
                _t  = f"{_nm.get('technical',0):.1f}" if _nm.get("technical") else "—"
                _col.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:10px;font-size:11px">'
                    f'<div style="color:#e8edf8;font-weight:700;font-size:13px;margin-bottom:6px">{_nm["symbol"]}</div>'
                    f'<div style="color:#8a9bc2">Fund: <span style="color:#e8edf8">{_f}</span></div>'
                    f'<div style="color:#8a9bc2">Tech: <span style="color:#e8edf8">{_t}</span></div>'
                    f'<div style="color:#8a9bc2">Bull%: <span style="color:#e8edf8">{_bp}</span></div>'
                    f'<div style="color:#8a9bc2">MA200: {_ma}</div>'
                    f'<div style="color:#8a9bc2">3M: <span style="color:#e8edf8">{_r3m_pct}</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        st.stop()

    top3 = " · ".join(r["symbol"] for r in recs[:3])
    st.success(f"🏆 Top picks this week: **{top3}**")
    st.divider()

    ACTION_COL = {"STRONG BUY": "#16c784", "BUY": "#a3e635"}

    # ── Helpers: score bar + metric indicator (numbers-only = safe HTML) ─────
    def _score_bar(v, color):
        pct = max(0, min(100, (v - 1) / 9 * 100)) if v else 0
        grade, gc = (("STRONG", "#16c784") if v and v >= 7.5 else
                     ("GOOD",   "#a3e635") if v and v >= 6.0 else
                     ("OK",     "#f0b90b") if v and v >= 4.5 else
                     ("WEAK",   "#ea3a44"))
        return (
            f'<div style="text-align:center;padding:12px 6px 10px;background:#161c2c;'
            f'border-radius:8px;border:1px solid var(--border)">'
            f'<div style="font-size:26px;font-weight:700;color:{color};line-height:1">'
            f'{v:.1f}</div>'
            f'<div style="background:#2a3348;border-radius:3px;height:5px;margin:6px 0 4px">'
            f'<div style="width:{pct:.0f}%;height:100%;background:{color};border-radius:3px"></div></div>'
            f'<div style="font-size:9px;color:{gc};font-weight:700;letter-spacing:.8px">{grade}</div>'
            f'</div>'
        )

    def _met_cell(label, value, ind_label, ind_color, help_txt):
        return (
            f'<div title="{ind_label}: {help_txt}" '
            f'style="padding:10px 8px;background:#161c2c;border-radius:8px;border:1px solid var(--border)">'
            f'<div style="font-size:9px;color:#556070;text-transform:uppercase;'
            f'letter-spacing:.7px;margin-bottom:5px">{label}</div>'
            f'<div style="font-size:17px;font-weight:600;color:#e8edf8;line-height:1">{value}</div>'
            f'<div style="font-size:9px;color:{ind_color};font-weight:700;margin-top:4px">'
            f'{ind_label}</div>'
            f'</div>'
        )

    _CATEGORY_BADGE = {
        "SWING":      ("🔥 SWING SETUP",  "#f97316"),
        "QUALITY_DIP": ("💎 QUALITY DIP", "#4da3ff"),
        "ETF_THEME":  ("📊 ETF THEME",    "#a78bfa"),
    }

    # ── One card per recommendation ───────────────────────────────────────────
    for rank, r in enumerate(recs, 1):
        thesis = r.get("thesis", {})
        action = thesis.get("action", "BUY")
        col    = ACTION_COL.get(action, "#a3e635")
        conv   = thesis.get("conviction", 0) or 0
        stars  = "★" * conv + "☆" * (5 - conv)
        qflag  = thesis.get("quality_flag", "")
        cat_lbl, cat_color = _CATEGORY_BADGE.get(r.get("category"), ("", "#8a9bc2"))

        # ── ETF theme cards get a simpler, dedicated layout — they don't
        # have fundamentals/analyst/options data, so force-fitting them into
        # the stock card template would just show misleading zeros. ─────────
        if r.get("category") == "ETF_THEME":
            ws = r["weekly_score"]
            st.markdown(
                f'<div style="border-left:5px solid {cat_color};padding:8px 0 8px 16px;margin-bottom:2px">'
                f'<span style="color:#556070;font-size:11px">#{rank}&nbsp;&nbsp;</span>'
                f'<span style="font-size:26px;font-weight:700;color:#e8edf8">{r["symbol"]}</span>'
                f'&nbsp;&nbsp;<span style="font-size:13px;color:#8a9bc2">{r.get("name","")[:40]}</span>'
                f'&nbsp;&nbsp;<span style="background:{cat_color}22;color:{cat_color};border:1px solid {cat_color}44;'
                f'padding:4px 14px;border-radius:6px;font-size:12px;font-weight:700">{cat_lbl}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
            _etf_c1, _etf_c2, _etf_c3, _etf_c4 = st.columns(4)
            _etf_c1.markdown('<div style="font-size:10px;color:#556070;text-transform:uppercase">Strength Score</div>' +
                             _score_bar(ws, "#a78bfa"), unsafe_allow_html=True)
            _etf_c2.metric("1M Return", f"{(r.get('r1m') or 0):+.1f}%")
            _etf_c3.metric("3M Return", f"{(r.get('r3m') or 0):+.1f}%")
            _etf_c4.metric("vs SPY (1M)", f"{(r.get('rs1m') or 0):+.1f}%")
            st.markdown(
                f"📐 Breakout: **{r.get('breakout_setup') or 'No clear setup'}** &nbsp;·&nbsp; "
                f"📈 {'✅ Above MA200' if r.get('above_200') else '❌ Below MA200'}"
            )
            st.write("")
            if thesis:
                with st.expander("📋 Theme Thesis — Why · When · Target · Risk", expanded=True):
                    if thesis.get("headline"):
                        st.markdown(f'### *{thesis["headline"]}*')
                    why_items = thesis.get("why_buy") or []
                    if why_items:
                        st.markdown("#### ▸ Why")
                        for w in why_items:
                            st.markdown(f"- {w}")
                    t1, t2, t3 = st.columns(3)
                    with t1:
                        st.markdown("**⏱ When**"); st.write(thesis.get("when_buy") or "—")
                    with t2:
                        st.markdown("**🛑 Stop**"); st.write(thesis.get("stop_loss") or "—")
                    with t3:
                        st.markdown("**⚠️ Risk**"); st.write(thesis.get("key_risk") or "—")
            _, etf_btn_col = st.columns([5, 1])
            with etf_btn_col:
                if st.button("Deep Dive →", key=f"wp_etf_{r['symbol']}", width="stretch"):
                    st.session_state["symbol"] = r["symbol"]
                    st.session_state["_az_sym"] = r["symbol"]
                    st.session_state["page_jump"] = "🔍 Analyze"
                    st.rerun()
            st.divider()
            continue

        ws   = r["weekly_score"]
        ms   = r.get("model_score") or 5
        als  = r.get("analyst_score") or 5
        opts = r.get("options_score") or 5
        brk  = r.get("breakout_score") or 5
        bp   = r.get("bull_pct") or 0
        price = r.get("price") or 0

        pt_up  = ((r.get("pt_mean") or 0) / price - 1) * 100 if r.get("pt_mean") and price else None
        r3m    = r.get("r3m") or 0
        rsi    = r.get("rsi")
        rvol   = r.get("rvol")
        cp     = r.get("cp_ratio")
        rg     = r.get("revenue_growth") or 0
        gm     = r.get("gross_margin") or 0

        r3m_s  = f"{r3m*100:+.1f}%"
        rsi_s  = f"{rsi:.0f}"     if rsi   else "—"
        rvol_s = f"{rvol:.2f}x"   if rvol  else "—"
        cp_s   = f"{cp:.2f}"      if cp    else "—"
        pt_s   = f"{pt_up:+.1f}%" if pt_up is not None else "N/A"
        ma200  = "✅ ABOVE MA200" if r.get("above_ma200") else "❌ BELOW MA200" if r.get("above_ma200") is False else "—"
        rg_s   = f"{rg*100:+.1f}%"
        gm_s   = f"{gm*100:.0f}%"
        pt_range = (f"\\${r['pt_low']:.0f} – \\${r['pt_high']:.0f}"
                    if r.get("pt_low") and r.get("pt_high") else "")

        # Indicator labels + colors
        rvol_ind, rvol_c  = (("VERY HIGH", "#16c784") if (rvol or 0)>1.5 else
                              ("HIGH",      "#a3e635") if (rvol or 0)>1.2 else
                              ("NORMAL",    "#f0b90b") if (rvol or 0)>0.8 else
                              ("LOW",       "#ea3a44"))
        cp_ind,   cp_c    = (("VERY BULLISH", "#16c784") if (cp or 0)>1.8 else
                              ("BULLISH",      "#a3e635") if (cp or 0)>1.2 else
                              ("NEUTRAL",      "#f0b90b") if (cp or 0)>0.7 else
                              ("BEARISH",      "#ea3a44"))
        r3m_ind,  r3m_c   = (("STRONG",   "#16c784") if r3m>0.15 else
                              ("POSITIVE", "#a3e635") if r3m>0.02 else
                              ("FLAT",     "#f0b90b") if r3m>-0.05 else
                              ("WEAK",     "#ea3a44"))
        rsi_v = rsi or 50
        rsi_ind, rsi_c    = (("OVERSOLD",    "#f0b90b") if rsi_v < 35 else
                              ("BUY ZONE",    "#16c784") if rsi_v < 55 else
                              ("HEALTHY",     "#a3e635") if rsi_v < 65 else
                              ("CAUTION",     "#f0b90b") if rsi_v < 72 else
                              ("OVERBOUGHT",  "#ea3a44"))
        pt_ind,   pt_c    = (("VERY ATT.",  "#16c784") if (pt_up or 0)>20 else
                              ("ATTRACTIVE", "#a3e635") if (pt_up or 0)>10 else
                              ("MODEST",     "#f0b90b") if (pt_up or 0)>3  else
                              ("LOW",        "#ea3a44"))
        bp_ind,   bp_c    = (("STRONG BUY", "#16c784") if bp>75 else
                              ("BUY",        "#a3e635") if bp>60 else
                              ("MIXED",      "#f0b90b") if bp>45 else
                              ("BEARISH",    "#ea3a44"))
        rg_ind,   rg_c    = (("HYPERGROWTH", "#16c784") if rg>0.30 else
                              ("HIGH",        "#a3e635") if rg>0.15 else
                              ("MODERATE",    "#f0b90b") if rg>0.05 else
                              ("LOW",         "#ea3a44"))
        gm_ind,   gm_c    = (("EXCELLENT", "#16c784") if gm>0.65 else
                              ("GOOD",      "#a3e635") if gm>0.45 else
                              ("OK",        "#f0b90b") if gm>0.30 else
                              ("LOW",       "#ea3a44"))

        # ── Freshness badge ───────────────────────────────────────────────────
        _penalty  = r.get("recency_penalty", 0)
        _r1w_val  = r.get("r1w") or 0
        _squeeze  = r.get("bb_squeeze", False)
        _vol_surge = r.get("vol_surge", False)
        if _penalty == 0:
            _fresh_label = "🆕 New this week"
            _fresh_color = "#16c784"
        elif _r1w_val > 0.03:
            _fresh_label = f"⚡ +{_r1w_val*100:.1f}% this week"
            _fresh_color = "#a3e635"
        elif _squeeze:
            _fresh_label = "🔥 Bollinger Squeeze"
            _fresh_color = "#f0b90b"
        elif _vol_surge:
            _fresh_label = "📈 Volume Surge"
            _fresh_color = "#f0b90b"
        else:
            _fresh_label = ""
            _fresh_color = "#8a9bc2"

        _fresh_html = (
            f'&nbsp;&nbsp;<span style="font-size:11px;background:{_fresh_color}18;'
            f'color:{_fresh_color};border:1px solid {_fresh_color}44;'
            f'padding:2px 8px;border-radius:4px">{_fresh_label}</span>'
            if _fresh_label else ""
        )

        # ── HEADER ───────────────────────────────────────────────────────────
        st.markdown(
            f'<div style="border-left:5px solid {col};padding:8px 0 8px 16px;margin-bottom:2px">'
            f'<span style="color:#556070;font-size:11px">#{rank}&nbsp;&nbsp;</span>'
            f'<span style="font-size:26px;font-weight:700;color:#e8edf8">{r["symbol"]}</span>'
            f'&nbsp;&nbsp;<span style="font-size:13px;color:#8a9bc2">{r.get("name","")[:30]}</span>'
            f'&nbsp;&nbsp;<span style="background:{col}22;color:{col};border:1px solid {col}44;'
            f'padding:4px 14px;border-radius:6px;font-size:13px;font-weight:700">{action}</span>'
            f'&nbsp;&nbsp;<span style="background:{cat_color}22;color:{cat_color};border:1px solid {cat_color}44;'
            f'padding:4px 14px;border-radius:6px;font-size:12px;font-weight:700">{cat_lbl}</span>'
            f'{_fresh_html}'
            f'</div>'
            f'<div style="padding:0 0 10px 21px;color:#556070;font-size:12px">'
            f'{r.get("sector","")}'
            f'{"&nbsp;&nbsp;·&nbsp;&nbsp;<span style=color:#f0b90b>" + qflag + "</span>" if qflag else ""}'
            f'{"&nbsp;&nbsp;<span style=color:#f0b90b>" + stars + "</span>" if stars else ""}'
            f'{"&nbsp;&nbsp;·&nbsp;&nbsp;" + r.get("analyst_source","") + "&nbsp;" + str(r.get("total_analysts","")) + " analysts" if r.get("total_analysts") else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if r.get("category") == "QUALITY_DIP" and r.get("opportunity_guidance"):
            st.caption(
                f"💎 Quality-dip read (Opportunity Lens — quality {r.get('quality_score','?')}/10, "
                f"condition {r.get('condition_score','?')}/10): {r['opportunity_guidance']}"
            )

        # ── SCORES (progress bars) ────────────────────────────────────────────
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        mc = ("#16c784" if ws >= 7.5 else "#a3e635" if ws >= 6 else "#f0b90b")
        sc1.markdown(
            '<div style="font-size:10px;color:#556070;text-transform:uppercase;letter-spacing:.8px;'
            'margin-bottom:4px">Weekly Score</div>' +
            _score_bar(ws, mc),
            unsafe_allow_html=True,
        )
        sc2.markdown('<div style="font-size:10px;color:#556070;text-transform:uppercase;'
                     'letter-spacing:.8px;margin-bottom:4px" '
                     'title="Weighted average of fundamental + technical + momentum. Above 7 = quality company with strong technicals.">Model &#9432;</div>' +
                     _score_bar(ms, r.get("model_color", "#8a9bc2")),
                     unsafe_allow_html=True)
        sc3.markdown('<div style="font-size:10px;color:#556070;text-transform:uppercase;'
                     'letter-spacing:.8px;margin-bottom:4px" '
                     'title="Options flow score based on C/P Ratio. Above 7 = unusual call demand = institutions entering.">Options &#9432;</div>' +
                     _score_bar(opts, "#a78bfa"),
                     unsafe_allow_html=True)
        sc4.markdown('<div style="font-size:10px;color:#556070;text-transform:uppercase;'
                     'letter-spacing:.8px;margin-bottom:4px" '
                     'title="BB Squeeze + proximity to 52W High + narrow range. Above 7.5 = stock with potential breakout energy.">Breakout &#9432;</div>' +
                     _score_bar(brk, "#60a5fa"),
                     unsafe_allow_html=True)
        sc5.markdown('<div style="font-size:10px;color:#556070;text-transform:uppercase;'
                     'letter-spacing:.8px;margin-bottom:4px" '
                     'title="% bulls and price target upside. Above 7 = strong buy consensus with meaningful upside potential.">Analyst &#9432;</div>' +
                     _score_bar(als, "#f0b90b"),
                     unsafe_allow_html=True)

        st.write("")  # spacing

        # ── METRICS (8 cells with colored indicators) ─────────────────────────
        # Row 1: momentum + options
        row1 = "".join([
            _met_cell("RVOL",     rvol_s, rvol_ind, rvol_c,
                      "5-day avg volume vs 20-day avg. >1.3x = unusual demand, institutions entering"),
            _met_cell("Call/Put", cp_s,   cp_ind,   cp_c,
                      "Call vs Put volume ratio. >1.3 = bullish. >1.8 = institutional call buying"),
            _met_cell("3M Return",r3m_s,  r3m_ind,  r3m_c,
                      "3-month return. Positive and above SPY = strong momentum"),
            _met_cell("RSI",      rsi_s,  rsi_ind,  rsi_c,
                      "30-55 = optimal entry zone. Above 70 = overbought, caution."),
        ])
        # Row 2: analyst + fundamental
        row2 = "".join([
            _met_cell("PT Upside", pt_s,  pt_ind,  pt_c,
                      "Analyst price target upside. Above 10% = meaningful upside potential."),
            _met_cell("Bulls",  f"{bp:.0f}%", bp_ind, bp_c,
                      "% analysts with Buy/Strong Buy rating. Above 70% = strong consensus."),
            _met_cell("Rev Growth", rg_s, rg_ind, rg_c,
                      "Revenue growth YoY. Above 20% = growth company."),
            _met_cell("Gross Margin", gm_s, gm_ind, gm_c,
                      "Gross profit margin. Above 60% = competitive advantage and high entry barrier."),
        ])
        st.markdown(
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:8px">{row1}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px">{row2}</div>',
            unsafe_allow_html=True,
        )

        # ── OPTIONS EXTREME VALUE NOTE ────────────────────────────────────────
        if (cp or 0) > 3:
            st.caption(
                f"⚠️ Call/Put ratio {cp:.2f}x is unusually high — may reflect hedging, "
                "event positioning, or very low put volume. Verify with full options chain before sizing."
            )

        st.write("")  # spacing

        # ── TECHNICAL STRIP ───────────────────────────────────────────────────
        brk_label = r.get("breakout_setup") or "No clear setup"
        opt_sig   = r.get("options_signal", "") if r.get("options_has_data") else ""
        strip_parts = [f"📐 Breakout: **{brk_label}**", f"📈 {ma200}"]
        if pt_range:
            strip_parts.append(f"🎯 PT Range: **{pt_range}**")
        if opt_sig:
            strip_parts.append(f"🔖 {opt_sig}")
        st.markdown("&nbsp;&nbsp;·&nbsp;&nbsp;".join(strip_parts))

        st.write("")  # spacing

        # ── CLAUDE BUY THESIS ─────────────────────────────────────────────────
        if thesis:
            with st.expander("📋 Buy Thesis — Why · When · Target · Risk", expanded=True):
                if thesis.get("headline"):
                    st.markdown(f'### *"{thesis["headline"]}"*')
                    st.write("")

                why_items = thesis.get("why_buy") or []
                if why_items:
                    st.markdown("#### ▸ Why Buy")
                    for w in why_items:
                        st.markdown(f"- {w}")
                    st.write("")

                ta, tb = st.columns(2)
                with ta:
                    st.markdown("#### 🌍 Macro / Geo")
                    st.write(thesis.get("macro_relevance") or "—")
                with tb:
                    st.markdown("#### 🧠 Investor Psychology")
                    st.write(thesis.get("investor_psychology") or "—")

                st.write("")
                t1, t2, t3, t4 = st.columns(4)
                with t1:
                    st.markdown("**⏱ When to Buy**")
                    st.write(thesis.get("when_buy") or "—")
                with t2:
                    st.markdown("**🎯 Target**")
                    st.write(thesis.get("target_zone") or "—")
                with t3:
                    st.markdown("**🛑 Stop Loss**")
                    st.write(thesis.get("stop_loss") or "—")
                with t4:
                    st.markdown("**⚠️ Key Risk**")
                    st.write(thesis.get("key_risk") or "—")

                if thesis.get("catalyst_this_week"):
                    st.write("")
                    st.info(f"📌 **This week catalyst:** {thesis['catalyst_this_week']}")

        # ── SECTOR ETF HOLDINGS CONTEXT ───────────────────────────────────────
        _wp_sector  = r.get("sector", "")
        _wp_etf_sym = SECTOR_ETFS.get(_wp_sector)
        if _wp_etf_sym:
            with st.expander(f"📦 Sector ETF Holdings — {_wp_etf_sym} ({_wp_sector})", expanded=False):
                mod_etf.render_etf_holdings(_wp_etf_sym, max_rows=10)

        # ── OPTIONAL NEWS SENTIMENT DEEP-DIVE (Alpha Vantage — manual only,
        # never runs automatically for the whole list; free tier is 25
        # symbols/day so it's opt-in per name, same pattern as Analyze) ──────
        from config import ALPHA_VANTAGE_API_KEY as _wp_av_api_key
        if _wp_av_api_key:
            _wp_av_key = f"_av_sent_{r['symbol']}"
            with st.expander(f"📡 News sentiment for {r['symbol']} (optional — Alpha Vantage NLP)", expanded=False):
                if _wp_av_key not in st.session_state:
                    if st.button("Load news sentiment", key=f"wp_av_btn_{r['symbol']}"):
                        with st.spinner("Scoring recent news..."):
                            st.session_state[_wp_av_key] = mod_av.news_sentiment(r["symbol"])
                        st.rerun()
                else:
                    _wp_av = st.session_state[_wp_av_key]
                    if _wp_av.get("error"):
                        st.caption(f"Unavailable: {_wp_av['error']}")
                    else:
                        _wp_av_d = _wp_av["dist"]
                        st.markdown(
                            f"**{_wp_av['label']}** ({_wp_av['avg_score']:+.2f}) — "
                            f"{_wp_av['n_articles']} articles · "
                            f"{_wp_av_d['bullish']}↑ {_wp_av_d['neutral']}→ {_wp_av_d['bearish']}↓"
                        )
                        for _t in _wp_av["top"][:3]:
                            st.caption(f"{_t['score']:+.2f} — {_t['title'][:90]}")

        # ── DEEP DIVE ─────────────────────────────────────────────────────────
        _, btn_col = st.columns([5, 1])
        with btn_col:
            if st.button("Deep Dive →", key=f"wp_{r['symbol']}", width="stretch"):
                st.session_state["symbol"] = r["symbol"]
                st.session_state["_az_sym"] = r["symbol"]
                st.session_state["page_jump"] = "🔍 Analyze"
                st.rerun()

        st.divider()

    # ── Export ────────────────────────────────────────────────────────────────
    export_rows = []
    for r in recs:
        t   = r.get("thesis", {})
        why = " | ".join(t.get("why_buy") or [])
        export_rows.append({
            "Symbol": r["symbol"], "Name": r.get("name", ""),
            "Action": t.get("action", ""), "Quality Flag": t.get("quality_flag", ""),
            "Conviction": t.get("conviction", ""), "Weekly Score": r["weekly_score"],
            "Model": r.get("model_score", ""), "Options": r.get("options_score", ""),
            "Breakout": r.get("breakout_score", ""), "Analyst": r.get("analyst_score", ""),
            "Bull %": r.get("bull_pct", ""), "Call/Put": r.get("cp_ratio", ""),
            "RVOL": r.get("rvol", ""), "Breakout Setup": r.get("breakout_setup", ""),
            "3M Return %": round((r.get("r3m", 0) or 0)*100, 1),
            "PT Upside %": round(((r.get("pt_mean",0) or 0)/(r.get("price",1) or 1)-1)*100, 1) if r.get("pt_mean") and r.get("price") else "",
            "Why Buy": why, "Macro": t.get("macro_relevance", ""),
            "Psychology": t.get("investor_psychology", ""),
            "When to Buy": t.get("when_buy", ""), "Target": t.get("target_zone", ""),
            "Stop Loss": t.get("stop_loss", ""), "Key Risk": t.get("key_risk", ""),
            "Catalyst": t.get("catalyst_this_week", ""), "Regime": regime["regime"],
        })
    csv_wp = pd.DataFrame(export_rows).to_csv(index=False)
    st.download_button("📥 Export Recommendations CSV", csv_wp,
                       "weekly_recommendations.csv", "text/csv")

# ─── Page: Market Health ─────────────────────────────────────────────────────
elif page == "🏥 Market Health":
    st.title("🏥 Market Health Dashboard")
    _page_about("""**What:** the macro backdrop in one composite — should you be aggressive or defensive right now, and where is money actually rotating?
**How:** 11 indicators (VIX, yield curve, 10Y yield, Fed rate, headline + core CPI, unemployment, credit spreads, dollar, gold-vs-trend, S&P trend) each classified green/yellow/red, blended into a weighted 0-100 composite. Above 70 = risk-on; below 40 = defense. A Claude-generated narrative reads the CURRENT combination of readings (not each in isolation) to call out money-flow direction and sector rotation.
**Use:** this sets position SIZING and aggressiveness, not stock picks. Great stock + hostile macro = smaller size, wider stops.""")
    st.caption("Real-time macro & sentiment indicators to assess market conditions and timing for new investments.")

    col_ref, col_load = st.columns([4, 1])
    with col_load:
        refresh = st.button("🔄 Refresh", type="primary", width="stretch")

    if refresh or "mhealth_data" not in st.session_state:
        with st.spinner("Loading macro & market data..."):
            st.session_state["mhealth_data"] = mod_mhealth.fetch_all()

    data = st.session_state.get("mhealth_data", {})

    # ── 🌡 Valuation & Sentiment Gauges (Shiller / Buffett / Fear & Greed) ────
    st.markdown('<div class="panel-head">🌡 VALUATION &amp; SENTIMENT GAUGES</div>',
                unsafe_allow_html=True)
    with st.spinner("Loading valuation gauges..."):
        _cape = mod_mval.get_shiller_cape()
        _buff = mod_mval.get_buffett_indicator()
        _fg   = mod_mval.get_fear_greed()

    _vg1, _vg2, _vg3 = st.columns(3)

    def _gauge_card(title, tip_key, value_s, color, verdict, extra=""):
        return (
            f'<div style="background:var(--panel);border:1px solid var(--border);'
            f'border-left:4px solid {color};border-radius:10px;'
            f'padding:16px 18px;height:100%;cursor:help" '
            f'title="{_html.escape(mod_gloss.tip(tip_key), quote=True)}">'
            f'<div style="font-size:11px;color:#556070;text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:6px">{title} ⓘ</div>'
            f'<div style="font-size:26px;font-weight:800;color:{color};'
            f'font-family:IBM Plex Mono,monospace">{value_s}</div>'
            f'<div style="font-size:11.5px;color:#cdd6f4;margin-top:6px;'
            f'line-height:1.5">{_html.escape(verdict)}</div>{extra}</div>'
        )

    with _vg1:
        st.markdown(_gauge_card(
            "Shiller CAPE (S&P 500)", "shiller_method",
            f"{_cape['cape']:.1f}" if _cape.get("cape") else "N/A",
            _cape["color"], _cape["verdict"]), unsafe_allow_html=True)
    with _vg2:
        st.markdown(_gauge_card(
            "Buffett Indicator (Mkt Cap / GDP)", "buffett_indicator",
            f"{_buff['ratio']:.0f}%" if _buff.get("ratio") else "N/A",
            _buff["color"], _buff["verdict"]), unsafe_allow_html=True)
    with _vg3:
        _fg_extra = ""
        if _fg.get("components"):
            _fg_extra = ('<div style="font-size:10px;color:#556070;margin-top:6px">' +
                         " · ".join(f"{k.split(' (')[0]}: {v}"
                                    for k, v in _fg["components"].items()) + "</div>")
        st.markdown(_gauge_card(
            "Fear & Greed (local composite)", "fear_greed",
            f"{_fg['score']} — {_fg['label']}" if _fg.get("score") is not None else "N/A",
            _fg["color"], _fg.get("note", ""), _fg_extra), unsafe_allow_html=True)

    st.markdown("---")

    # Show FRED key missing callout when any FRED-sourced indicator has no value
    from config import FRED_API_KEY as _fred_key_mh
    if not _fred_key_mh:
        _fred_missing = [k for k, v in data.items() if v.get("value") is None and "FRED" in str(v.get("error", ""))]
        if _fred_missing or not data:
            st.info(
                "⚠️ Some macro indicators require a FRED API key (free at [fred.stlouisfed.org](https://fred.stlouisfed.org)).\n\n"
                "Affected: Fed Rate, CPI, Core CPI, Unemployment, HY Spread. "
                "Yield Curve is approximated from yfinance (10Y–5Y spread); "
                "10Y Yield falls back to yfinance ^TNX directly.\n\n"
                "Add `FRED_API_KEY=your_key` to your `.env` file for full data."
            )

    result = mod_mhealth.compute_composite(data)

    # ── Composite score ────────────────────────────────────────────────────────
    c_score, c_rec = st.columns([1, 2])
    with c_score:
        score = result["score"]
        arc_pct = score / 100
        st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:24px;text-align:center">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;
              text-transform:uppercase;letter-spacing:1.2px;color:#8a9bc2;
              margin-bottom:12px;cursor:help" title="{_html.escape(mod_gloss.tip('composite_health'), quote=True)}">MARKET HEALTH SCORE ⓘ</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:72px;font-weight:700;
              color:{result['color']};line-height:1">{score:.0f}</div>
  <div style="color:#556070;font-size:12px;margin-bottom:12px">/ 100</div>
  <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;font-weight:700;
               letter-spacing:.5px;padding:4px 12px;border-radius:5px;
               background:{result['color']}18;color:{result['color']};
               border:1px solid {result['color']}40">{result['label']}</span>
</div>""", unsafe_allow_html=True)

    with c_rec:
        st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:24px;height:100%">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;
              text-transform:uppercase;letter-spacing:1.2px;color:#8a9bc2;
              margin-bottom:12px">INVESTMENT RECOMMENDATION</div>
  <div style="font-size:15px;color:#e8edf8;line-height:1.7;margin-bottom:16px">
    {result['recommendation']}
  </div>
  <div style="font-size:11px;color:#556070">
    Score is a weighted composite of 9 of the 11 macro & sentiment indicators below
    (Core CPI and 10Y Yield feed the narrative, not the composite, to avoid
    double-weighting inflation/rates against CPI and the yield curve).
    Not financial advice — always do your own research.
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── 🌊 Dynamic money-flow narrative ────────────────────────────────────────
    # The invest_signal strings on each indicator card below are always true
    # in isolation; this reads how TODAY's specific combination interacts —
    # e.g. rising yields + strong dollar + sticky core CPI tells a different
    # story than rising yields + weak dollar + falling core CPI, even though
    # both have "rising yields." Same pattern as the per-stock macro
    # narrative in Analyze (modules/macro_geo.py), generalized market-wide.
    st.markdown('<div class="panel-head">🌊 WHERE IS MONEY FLOWING — DYNAMIC READ</div>',
               unsafe_allow_html=True)
    _mh_snapshot = mod_mhealth._narrative_snapshot(data, result)
    _mh_narr = mod_mhealth.macro_narrative(_mh_snapshot)
    if _mh_narr.get("error"):
        st.info(_mh_narr["error"])
    else:
        st.markdown(
            f'<div style="background:var(--panel);border:1px solid var(--border);'
            f'border-left:4px solid {result["color"]};border-radius:10px;'
            f'padding:18px 22px;margin-bottom:14px">'
            f'<div style="font-size:15px;font-weight:700;color:#e8edf8;margin-bottom:10px">'
            f'{_html.escape(_mh_narr.get("headline",""))}</div>'
            f'<div style="font-size:13px;color:#cdd6f4;line-height:1.7">'
            f'{_html.escape(_mh_narr.get("narrative",""))}</div>'
            f'</div>', unsafe_allow_html=True,
        )
        _mhc1, _mhc2 = st.columns(2)
        with _mhc1:
            st.markdown("**📥 Money flowing INTO**")
            for _x in _mh_narr.get("money_flowing_into", []):
                st.markdown(f"- {_x}")
            st.markdown("**🏆 Sectors favored**")
            for _x in _mh_narr.get("sectors_favored", []):
                st.markdown(f"- {_x}")
        with _mhc2:
            st.markdown("**📤 Money flowing OUT OF**")
            for _x in _mh_narr.get("money_flowing_out_of", []):
                st.markdown(f"- {_x}")
            st.markdown("**⚠️ Sectors at risk**")
            for _x in _mh_narr.get("sectors_at_risk", []):
                st.markdown(f"- {_x}")
        if _mh_narr.get("watch_for"):
            st.caption(f"👁 **Watch for:** {_mh_narr['watch_for']}")

    st.markdown("---")

    # ── Indicator cards by category ────────────────────────────────────────────
    COLOR_HEX = {"green": "#16c784", "yellow": "#f0b90b", "red": "#ea3a44", "gray": "#556070"}
    CATEGORIES = ["Fear & Sentiment", "Market Trend", "Macro Environment"]

    for cat in CATEGORIES:
        st.markdown(f'<div class="panel-head">{cat.upper()}</div>', unsafe_allow_html=True)
        cat_keys = [k for k, v in mod_mhealth.INDICATORS.items() if v["category"] == cat]
        cols = st.columns(min(len(cat_keys), 3))
        for col, key in zip(cols * 2, cat_keys):
            ind  = mod_mhealth.INDICATORS[key]
            sig  = result["signals"].get(key, {})
            col_hex = COLOR_HEX.get(sig.get("color", "gray"), "#556070")
            val_str = sig.get("display", "N/A")

            col.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-left:3px solid {col_hex};
            border-radius:8px;padding:16px;margin-bottom:10px;height:100%">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;
              text-transform:uppercase;letter-spacing:.8px;color:#8a9bc2;
              margin-bottom:6px">{ind['label']}</div>
  <div style="font-family:'IBM Plex Mono',monospace;font-size:26px;
              font-weight:700;color:{col_hex};margin-bottom:4px">{val_str}</div>
  <div style="font-size:11px;color:#8a9bc2;margin-bottom:8px">{sig.get('label','')}</div>
  <div style="font-size:11px;color:#556070;line-height:1.5;border-top:1px solid #2a3348;
              padding-top:8px;margin-top:4px">{ind['desc']}</div>
  <div style="font-size:11px;color:{col_hex};margin-top:8px;font-style:italic">
    💡 {ind['invest_signal']}
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Historical chart of key indicators ────────────────────────────────────
    st.markdown('<div class="panel-head">HISTORICAL — VIX & YIELD CURVE (1Y)</div>',
                unsafe_allow_html=True)
    try:
        vix_hist  = yf.Ticker("^VIX").history(period="1y")["Close"]
        spy_hist  = yf.Ticker("^GSPC").history(period="1y")["Close"]
        spy_ma200 = spy_hist.rolling(200).mean()

        fig_h = make_subplots(rows=2, cols=1, shared_xaxes=True,
                               row_heights=[0.6, 0.4], vertical_spacing=0.12,
                               subplot_titles=("S&P 500 vs MA200", "VIX — Fear Index"))
        fig_h.add_trace(go.Scatter(x=spy_hist.index, y=spy_hist.values,
                                    name="S&P 500", line=dict(color="#16c784", width=2)),
                         row=1, col=1)
        fig_h.add_trace(go.Scatter(x=spy_ma200.index, y=spy_ma200.values,
                                    name="MA200", line=dict(color="#a78bfa", width=1.2, dash="dot")),
                         row=1, col=1)
        fig_h.add_trace(go.Scatter(x=vix_hist.index, y=vix_hist.values,
                                    name="VIX", line=dict(color="#f0b90b", width=1.5),
                                    fill="tozeroy", fillcolor="rgba(240,185,11,0.08)"),
                         row=2, col=1)
        fig_h.add_hline(y=20, line_dash="dot", line_color="#ea3a44", annotation_text="20",
                         row=2, col=1)
        fig_h.add_hline(y=30, line_dash="dot", line_color="#ea3a44", annotation_text="30 (Fear)",
                         row=2, col=1)
        fig_h.update_layout(
            paper_bgcolor="#131722", plot_bgcolor="#1c2333",
            font_color="#e8edf8", font_family="IBM Plex Mono",
            height=560, margin=dict(t=50, b=20, l=10, r=10),
            legend=dict(bgcolor="#1c2333", bordercolor="#2a3348"),
            hovermode="x unified",
        )
        fig_h.update_xaxes(gridcolor="#2a3348")
        fig_h.update_yaxes(gridcolor="#2a3348")
        st.plotly_chart(fig_h, width="stretch")
    except Exception as e:
        st.warning(f"Could not load historical chart: {e}")


# ─── Page: Sector Rotation ───────────────────────────────────────────────────
elif page == "🔄 Sector Rotation":
    st.title("🔄 Sector Rotation Monitor")
    st.caption(
        "11 SPDR broad sectors + 48 thematic sub-sectors — ranked by 1M Relative Strength vs SPY. "
        "↑ accelerating · → stable · ↓ decelerating momentum."
    )
    with st.expander("ⓘ How to read this page", expanded=False):
        st.markdown(f"- **Relative Strength (RS):** {mod_gloss.tip('rs')}")
        st.markdown(f"- **Momentum direction (↑→↓):** {mod_gloss.tip('momentum_dir')}")
        st.markdown(f"- **Grade (A-F):** {mod_gloss.tip('grade')}")
        st.markdown(f"- **Why rotation matters:** {mod_gloss.tip('sector_rotation')}")
        st.markdown(
            "- **🆕 Early signal:** the latest **week's** RS breaking away from the "
            "1-month trend — a heads-up days before it's big enough to flip the "
            "↑→↓ momentum arrow, which needs a full month of drift to move."
        )

    if st.button("🔄 Load Sector Data", type="primary") or "sector_rot" not in st.session_state:
        with st.spinner("Fetching sector ETF data…"):
            st.session_state["sector_rot"] = mod_sector_str.get_sector_rotation()

    rot = st.session_state.get("sector_rot", [])
    if not rot:
        st.info("No sector data available. Click Load Sector Data.")
        st.stop()

    # ── Earliest-possible change detection ────────────────────────────────────
    _early_up   = sorted([r for r in rot if r.get("early_signal") == "up"],
                         key=lambda x: x["rs1w"] - x["rs1m"], reverse=True)
    _early_down = sorted([r for r in rot if r.get("early_signal") == "down"],
                         key=lambda x: x["rs1w"] - x["rs1m"])
    _movers_up   = sorted([r for r in rot if (r.get("rs1m_delta") or 0) > 0],
                          key=lambda x: x["rs1m_delta"], reverse=True)[:5]
    _movers_down = sorted([r for r in rot if (r.get("rs1m_delta") or 0) < 0],
                          key=lambda x: x["rs1m_delta"])[:5]

    if _early_up or _early_down:
        st.markdown('<div class="panel-head">🆕 EARLY ROTATION SIGNALS — THIS WEEK BREAKING FROM TREND</div>',
                    unsafe_allow_html=True)
        ec1, ec2 = st.columns(2)
        with ec1:
            st.markdown("**🆕 Turning up**")
            if _early_up:
                for r in _early_up[:6]:
                    st.markdown(f"- **{r['label']}** ({r['etf']}) — 1W RS {r['rs1w']:+.1f}% vs 1M RS {r['rs1m']:+.1f}%")
            else:
                st.caption("None right now.")
        with ec2:
            st.markdown("**⚠ Turning down**")
            if _early_down:
                for r in _early_down[:6]:
                    st.markdown(f"- **{r['label']}** ({r['etf']}) — 1W RS {r['rs1w']:+.1f}% vs 1M RS {r['rs1m']:+.1f}%")
            else:
                st.caption("None right now.")
        st.divider()

    if _movers_up or _movers_down:
        st.markdown('<div class="panel-head">📊 MOVED SINCE LAST CHECK</div>', unsafe_allow_html=True)
        mc1, mc2 = st.columns(2)
        with mc1:
            st.markdown("**📈 RS improved most**")
            for r in _movers_up:
                st.markdown(f"- **{r['label']}** ({r['etf']}) — RS 1M {r['rs1m_delta']:+.1f}pt")
            if not _movers_up:
                st.caption("Nothing improved since last check.")
        with mc2:
            st.markdown("**📉 RS worsened most**")
            for r in _movers_down:
                st.markdown(f"- **{r['label']}** ({r['etf']}) — RS 1M {r['rs1m_delta']:+.1f}pt")
            if not _movers_down:
                st.caption("Nothing worsened since last check.")
        st.divider()

    # ── Summary bar chart: RS vs SPY — grouped by category for readability ────
    st.markdown('<div class="panel-head">RELATIVE STRENGTH VS SPY — 1 MONTH</div>',
                unsafe_allow_html=True)
    _cats_avail = ["🔥 Top 15", "All"] + [c for c in mod_sector_str.ROTATION_CATEGORIES
                                          if any(r.get("category") == c for r in rot)]
    _cat_sel = st.radio("Category", _cats_avail, horizontal=True,
                        label_visibility="collapsed", key="_rot_cat")
    if _cat_sel == "🔥 Top 15":
        _rot_view = rot[:15]   # already sorted by RS 1M desc
    elif _cat_sel == "All":
        _rot_view = rot
    else:
        _rot_view = [r for r in rot if r.get("category") == _cat_sel]

    rs_colors = ["#16c784" if r["rs1m"] >= 0 else "#ea3a44" for r in _rot_view]
    fig_rs = go.Figure(go.Bar(
        x=[r["label"] for r in _rot_view],
        y=[r["rs1m"] for r in _rot_view],
        marker_color=rs_colors,
        text=[f"{r['rs1m']:+.1f}%" for r in _rot_view],
        textposition="outside",
        customdata=[[r["etf"], r.get("category", ""), r["momentum_dir"]] for r in _rot_view],
        hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>"
                      "RS 1M vs SPY: %{y:+.1f}%<br>"
                      "Category: %{customdata[1]} · Momentum %{customdata[2]}<extra></extra>",
    ))
    fig_rs.update_layout(
        paper_bgcolor="#131722", plot_bgcolor="#1c2333",
        font_color="#e8edf8", font_family="IBM Plex Mono",
        height=420 if len(_rot_view) > 20 else 360,
        margin=dict(t=20, b=80, l=10, r=10),
        yaxis=dict(gridcolor="#2a3348", zeroline=True,
                   zerolinecolor="#556070", ticksuffix="%"),
        xaxis=dict(tickfont=dict(size=10 if len(_rot_view) <= 20 else 8),
                   tickangle=-45),
        showlegend=False,
    )
    st.plotly_chart(fig_rs, width="stretch")

    st.divider()

    # ── 1M vs 3M scatter: rotation quadrants ─────────────────────────────────
    st.markdown('<div class="panel-head">ROTATION QUADRANT — 1M RETURN vs 3M RETURN</div>',
                unsafe_allow_html=True)
    st.caption("Top-right = Leading (strong short + long momentum)  ·  "
               "Top-left = Improving  ·  Bottom-right = Weakening  ·  Bottom-left = Lagging  ·  "
               f"filtered to: **{_cat_sel}**")
    st.caption("🎨 Color = RS vs SPY 1M (red → yellow → green, same scale as the bar chart above)  ·  "
               "⬤ Size = overall strength score (MA position + momentum) — bigger = higher conviction.")

    def _rs_gradient_color(rs1m: float, cap: float = 15.0) -> str:
        """Red→yellow→green diverging scale centered at 0, same red/green
        hexes as the RS bar chart above — so both charts speak one color
        language instead of the quadrant using an unrelated grade bucket."""
        t = max(-1.0, min(1.0, rs1m / cap))
        if t >= 0:
            a, b = (240, 185, 11), (22, 199, 132)
        else:
            a, b = (240, 185, 11), (234, 58, 68)
            t = -t
        rgb = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
        return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"

    def _score_bubble_size(score: float) -> float:
        return 10 + max(0.0, min(9.0, score - 1.0)) / 9.0 * 26

    fig_quad = go.Figure()
    for r in _rot_view:
        fig_quad.add_trace(go.Scatter(
            x=[r["r3m"]], y=[r["r1m"]],
            mode="markers+text",
            text=[f"{r['etf']} {r['momentum_dir']}"],
            textposition="top center",
            textfont=dict(size=10, color="#e8edf8"),
            marker=dict(size=_score_bubble_size(r["score"]),
                        color=_rs_gradient_color(r["rs1m"]),
                        line=dict(width=1, color="#2a3348")),
            hovertemplate=(
                f"<b>{r['label']} ({r['etf']})</b><br>"
                f"1M: {r['r1m']:+.1f}%<br>"
                f"3M: {r['r3m']:+.1f}%<br>"
                f"RS 1M: {r['rs1m']:+.1f}%<br>"
                f"Score: {r['score']}<extra></extra>"
            ),
            name=r["label"],
            showlegend=False,
        ))
    # Quadrant lines
    fig_quad.add_hline(y=0, line_color="#556070", line_dash="dot")
    fig_quad.add_vline(x=0, line_color="#556070", line_dash="dot")
    fig_quad.update_layout(
        paper_bgcolor="#131722", plot_bgcolor="#1c2333",
        font_color="#e8edf8", font_family="IBM Plex Mono",
        height=440, margin=dict(t=20, b=20, l=10, r=10),
        xaxis=dict(title="3M Return (%)", gridcolor="#2a3348",
                   zeroline=False, ticksuffix="%"),
        yaxis=dict(title="1M Return (%)", gridcolor="#2a3348",
                   zeroline=False, ticksuffix="%"),
    )
    st.plotly_chart(fig_quad, width="stretch")

    st.divider()

    # ── Detail table ─────────────────────────────────────────────────────────
    st.markdown('<div class="panel-head">SECTOR DETAIL TABLE</div>',
                unsafe_allow_html=True)
    rot_rows = []
    for r in rot:
        rot_rows.append({
            "Dir": r["momentum_dir"],
            "Sector":     r["label"],
            "ETF":        r["etf"],
            "1M Ret":     r["r1m"],
            "3M Ret":     r["r3m"],
            "RS vs SPY":  r["rs1m"],
            "Above 50d":  "✅" if r["above_50"]  else "❌",
            "Above 200d": "✅" if r["above_200"] else "❌",
            "Score":      r["score"],
            "Grade":      r["grade"],
        })
    rot_df = pd.DataFrame(rot_rows)

    def _color_ret(val):
        if not isinstance(val, (int, float)): return ""
        return "color:#16c784" if val >= 0 else "color:#ea3a44"

    styled_rot = rot_df.style.format({
        "1M Ret":    lambda x: f"{x:+.1f}%",
        "3M Ret":    lambda x: f"{x:+.1f}%",
        "RS vs SPY": lambda x: f"{x:+.1f}%",
        "Score":     lambda x: f"{x:.1f}",
    }).map(_color_ret, subset=["1M Ret", "3M Ret", "RS vs SPY"])
    st.dataframe(styled_rot, width="stretch", hide_index=True)

    st.caption(
        "↑ = 1M RS accelerating vs 3M baseline  ·  → = stable  ·  ↓ = decelerating. "
        "Thematic sub-sectors: AI/Tech (SOXX, IGV, WCLD, CIBR, BOTZ, PNQI, HERO) · "
        "Healthcare (XBI, IHI, ARKG, XPH) · Finance (FINX, IPAY, KRE, IBIT) · "
        "Energy Transition (ICLN, TAN, URA) · Industrial (ITA, PAVE, LIT) · "
        "Consumer (ONLN, JETS) · Global (GDX, KWEB, INDA, IWO)."
    )

    st.divider()

    # ── Ecosystem drill-down — full holdings of every ETF in the picked
    # category, so a theme like "AI & Compute" shows every underlying name
    # (chips, cloud, data-center REITs, grid…) instead of one ETF at a time.
    if _cat_sel not in ("🔥 Top 15", "All"):
        st.markdown(f'<div class="panel-head">🔬 {_cat_sel.upper()} ECOSYSTEM — TOP HOLDINGS</div>',
                    unsafe_allow_html=True)
        st.caption("Every ETF in this theme, expanded — the underlying stocks are the actual ecosystem.")
        for r in _rot_view:
            with st.expander(f"{r['label']} — {r['etf']}  ({r['grade']})", expanded=False):
                mod_etf.render_etf_holdings(r["etf"], max_rows=10)
        st.divider()

    st.markdown('<div class="panel-head">ETF HOLDINGS EXPLORER</div>', unsafe_allow_html=True)
    _etf_options = sorted(set(r["etf"] for r in rot))
    _sel_etf = st.selectbox(
        "Select ETF to view top holdings",
        _etf_options,
        label_visibility="collapsed",
        key="rot_etf_sel",
    )
    if _sel_etf:
        mod_etf.render_etf_holdings(_sel_etf, max_rows=15)


# ─── Page: News Feed ──────────────────────────────────────────────────────────
elif page == "📰 News Feed":
    st.title("📰 Unified News Feed")
    _page_about("""**What:** all headlines for your tracked symbols in one stream, with sentiment tagging and a monthly momentum chart.
**How:** headlines fetched per symbol (Finnhub + extra sources), sentiment = keyword scoring (positive/negative word lists — crude but consistent). The chart counts monthly positive/neutral/negative + a Net line (pos − neg) to quantify NARRATIVE momentum.
**Use:** the Net line trend matters more than any single headline — narrative turning up/down often precedes multiple expansion/compression.""")
    st.caption(
        "Latest news across your watchlist — sorted by date, filtered by sentiment. "
        "Sources: Finnhub, Yahoo Finance, Seeking Alpha, StockTwits."
    )

    DEFAULT_NF = ", ".join(["NVDA", "MSFT", "AAPL", "META", "GOOGL",
                            "AMZN", "TSLA", "AMD", "PLTR", "CRWD"])
    nf_input = st.text_input(
        "Symbols to track",
        value=st.session_state.get("nf_symbols", DEFAULT_NF),
        placeholder="NVDA, AAPL, MSFT, …",
        label_visibility="collapsed",
    )
    if nf_input:
        st.session_state["nf_symbols"] = nf_input
    nf_syms = [t.strip().upper() for t in nf_input.split(",") if t.strip()][:20]

    _NF_ALL_SOURCES = ["Finnhub", "Yahoo Finance", "Seeking Alpha", "StockTwits"]
    _NF_DEFAULT_SOURCES = [s for s in _NF_ALL_SOURCES if s != "Finnhub" or FINNHUB_API_KEY]
    nf_sources = st.multiselect(
        "Sources", _NF_ALL_SOURCES, default=_NF_DEFAULT_SOURCES,
        label_visibility="collapsed",
    )
    if "Finnhub" in nf_sources and not FINNHUB_API_KEY:
        st.warning("Add FINNHUB_API_KEY to .env to include Finnhub — continuing with the other sources.")
        nf_sources = [s for s in nf_sources if s != "Finnhub"]

    _NF_SENT_OPTS = {"All": None, "Positive only": "positive",
                     "Negative only": "negative", "Neutral only": "neutral"}
    nf_col1, nf_col2 = st.columns([2, 1])
    with nf_col2:
        sent_filter = st.selectbox("Sentiment", list(_NF_SENT_OPTS.keys()))
    with nf_col1:
        run_nf = st.button("🗞 Load News", type="primary", width="stretch",
                            disabled=not nf_sources)

    if run_nf:
        all_news = []
        prog_nf = st.progress(0, text="Fetching news…")
        for i, sym in enumerate(nf_syms):
            prog_nf.progress((i + 1) / len(nf_syms), text=f"Fetching {sym}…")
            if "Finnhub" in nf_sources:
                try:
                    fh = mod_finnhub.fetch_all(sym)
                    for n in fh.get("news", []):
                        all_news.append({**n, "symbol": sym})
                except Exception:
                    pass
            if "Yahoo Finance" in nf_sources:
                try:
                    for n in mod_news.fetch_yahoo_news(sym):
                        all_news.append({**n, "symbol": sym})
                except Exception:
                    pass
            if "Seeking Alpha" in nf_sources:
                try:
                    for n in mod_news.fetch_seekingalpha_news(sym):
                        all_news.append({**n, "symbol": sym})
                except Exception:
                    pass
            if "StockTwits" in nf_sources:
                try:
                    for n in mod_news.fetch_stocktwits(sym):
                        all_news.append({**n, "symbol": sym})
                except Exception:
                    pass
        prog_nf.empty()
        # Sort by date, newest first. Date strings lack a year ("MMM DD"),
        # so months after the current month are assumed to be last year.
        try:
            from datetime import datetime as _dt
            _today_nf = _date.today()
            def _parse_date(n):
                raw = (n.get("date") or "").strip()
                for fmt in ("%b %d", "%Y-%m-%d", "%b %d, %Y"):
                    try:
                        d = _dt.strptime(raw, fmt)
                        if d.year == 1900:  # year-less format
                            year = _today_nf.year if d.month <= _today_nf.month else _today_nf.year - 1
                            d = d.replace(year=year)
                        return d
                    except Exception:
                        continue
                return _dt.min
            all_news.sort(key=_parse_date, reverse=True)
        except Exception:
            pass
        st.session_state["nf_data"] = all_news

    if "nf_data" not in st.session_state:
        st.info("Click **Load News** to fetch the latest headlines.")
        st.stop()

    news_items = st.session_state["nf_data"]
    sent_val = _NF_SENT_OPTS[sent_filter]
    if sent_val:
        news_items = [n for n in news_items if n.get("sentiment") == sent_val]

    if not news_items:
        st.info("No news items match the current filter.")
        st.stop()

    st.caption(f"Showing {len(news_items)} headlines across {len(nf_syms)} symbols")

    # ── Sentiment Momentum Chart ───────────────────────────────────────────────
    # Uses ALL loaded news (ignore current filter) so the chart is always complete
    import calendar as _cal
    _all_news_data = st.session_state["nf_data"]
    _today_d = _date.today()
    _month_counts: dict[str, dict] = {}

    for _ni in _all_news_data:
        try:
            _nd = datetime.strptime(_ni.get("date", ""), "%b %d")
            # Assign year: month > current month → last year
            _year = _today_d.year if _nd.month <= _today_d.month else _today_d.year - 1
            _mk = f"{_year}-{_nd.month:02d}"
            _sent_k = _ni.get("sentiment", "neutral")
            _month_counts.setdefault(_mk, {"positive": 0, "neutral": 0, "negative": 0})
            _month_counts[_mk][_sent_k] = _month_counts[_mk].get(_sent_k, 0) + 1
        except Exception:
            pass

    if _month_counts and len(_month_counts) >= 1:
        _months_sorted = sorted(_month_counts.keys())
        _mlabels = [
            _cal.month_abbr[int(_mk.split("-")[1])] + " '" + _mk.split("-")[0][2:]
            for _mk in _months_sorted
        ]
        _pos_vals = [_month_counts[m]["positive"] for m in _months_sorted]
        _neu_vals = [_month_counts[m]["neutral"]  for m in _months_sorted]
        _neg_vals = [_month_counts[m]["negative"] for m in _months_sorted]
        # Net sentiment = positive - negative (momentum line)
        _net_vals = [p - n for p, n in zip(_pos_vals, _neg_vals)]
        _total_vals = [p + nu + n for p, nu, n in zip(_pos_vals, _neu_vals, _neg_vals)]

        _fig_sm = go.Figure()
        _fig_sm.add_trace(go.Bar(
            name="Positive", x=_mlabels, y=_pos_vals,
            marker_color="#16c784", opacity=0.85,
        ))
        _fig_sm.add_trace(go.Bar(
            name="Neutral", x=_mlabels, y=_neu_vals,
            marker_color="#f0b90b", opacity=0.85,
        ))
        _fig_sm.add_trace(go.Bar(
            name="Negative", x=_mlabels, y=_neg_vals,
            marker_color="#ea3a44", opacity=0.85,
        ))
        # Net sentiment line on secondary axis
        _fig_sm.add_trace(go.Scatter(
            name="Net (Pos − Neg)", x=_mlabels, y=_net_vals,
            mode="lines+markers",
            line=dict(color="#4da3ff", width=2.5),
            marker=dict(size=7),
            yaxis="y2",
        ))
        _fig_sm.update_layout(
            barmode="stack",
            height=290,
            margin=dict(l=0, r=0, t=70, b=0),
            title=dict(
                text="News Sentiment Momentum — by Month",
                font=dict(size=13, color="#cdd6f4"), x=0, y=1.0, yanchor="top",
            ),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#cdd6f4", size=11),
            xaxis=dict(showgrid=False, color="#556070"),
            yaxis=dict(
                title="Articles", showgrid=True,
                gridcolor="#1e2535", color="#556070",
            ),
            yaxis2=dict(
                title="Net Sentiment", overlaying="y", side="right",
                showgrid=False, color="#4da3ff",
                zeroline=True, zerolinecolor="#2a3348",
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.15, x=0),
            hovermode="x unified",
        )
        st.plotly_chart(_fig_sm, width="stretch", config={"displayModeBar": False})

        # Quick KPI row below chart
        _total_all = sum(_total_vals)
        _pos_all   = sum(_pos_vals)
        _neg_all   = sum(_neg_vals)
        _neu_all   = sum(_neu_vals)
        _net_all   = _pos_all - _neg_all
        _net_color = "#16c784" if _net_all > 0 else ("#ea3a44" if _net_all < 0 else "#f0b90b")
        _kc1, _kc2, _kc3, _kc4, _kc5 = st.columns(5)
        _kc1.metric("Total Articles", f"{_total_all}")
        _kc2.metric("Positive", f"{_pos_all}", f"{_pos_all/_total_all*100:.0f}%" if _total_all else "")
        _kc3.metric("Neutral",  f"{_neu_all}", f"{_neu_all/_total_all*100:.0f}%" if _total_all else "")
        _kc4.metric("Negative", f"{_neg_all}", f"{_neg_all/_total_all*100:.0f}%" if _total_all else "")
        _kc5.metric("Net Momentum", f"{_net_all:+d}")

    st.divider()

    _SENT_COLOR = {
        "positive": "#16c784",
        "negative": "#ea3a44",
        "neutral":  "#f0b90b",
    }
    _e = lambda v: _html.escape(str(v or ""), quote=False)

    for n in news_items[:80]:
        sym      = _e(n.get("symbol", ""))
        headline = _e(n.get("headline", ""))
        date_str = _e(n.get("date", ""))
        source   = _e(n.get("source", ""))
        sent     = n.get("sentiment", "neutral")
        sc       = _SENT_COLOR.get(sent, "#556070")
        url      = _safe_href(n.get("url"))
        summary  = _e((n.get("summary") or "")[:160])

        sym_badge = (
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:11px;'
            f'font-weight:700;padding:2px 8px;border-radius:4px;'
            f'background:{sc}18;color:{sc};border:1px solid {sc}40">{sym}</span>'
        )
        sent_badge = (
            f'<span style="font-size:10px;color:{sc};margin-left:6px">'
            f'&#9679; {sent.upper()}</span>'
        )
        meta = (
            f'<span style="font-size:11px;color:#556070">'
            f'{date_str} &nbsp;&#183;&nbsp; {source}</span>'
        )
        headline_link = (
            f'<a href="{url}" target="_blank" rel="noopener noreferrer" style="color:#e8edf8;text-decoration:none;'
            f'font-size:14px;font-weight:600;line-height:1.5">{headline}</a>'
        )
        summary_html = (
            f'<div style="font-size:12px;color:#8a9bc2;margin-top:4px;line-height:1.5">'
            f'{summary}{"…" if summary else ""}</div>'
            if summary else ""
        )

        st.markdown(
            f'<div style="background:var(--panel);border:1px solid var(--border);border-left:3px solid {sc};'
            f'border-radius:8px;padding:14px 16px;margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:6px">'
            f'{sym_badge}{sent_badge}'
            f'<span style="margin-left:auto">{meta}</span></div>'
            f'{headline_link}'
            f'{summary_html}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ─── Page: AI Screener ────────────────────────────────────────────────────────
elif page == "🔎 AI Screener":
    st.title("🔎 AI Screener & Portfolio Builder")
    _page_about("""**What:** describe what you want in plain language — Claude turns it into a screen or a full weighted portfolio.
**How:** Screen mode parses your criteria into filters and scores live candidates. Build mode designs 4-8 positions with weights, roles and rationale; Agent mode actively fetches live metrics via tools before deciding. Track button hands the result to the 🎯 Tracker.
**Use:** be specific ('SaaS, >20% growth, P/S<10, above MA200'). Treat output as a research shortlist — validate in Analyze before committing.""")
    if not ANTHROPIC_API_KEY:
        st.error("ANTHROPIC_API_KEY required.")
        st.stop()

    # ── Mode toggle ───────────────────────────────────────────────────────────
    mode = st.radio("Mode", ["🔍 Screen Stocks", "💼 Build Portfolio", "🤖 Agent Mode"],
                    horizontal=True, label_visibility="collapsed")
    if mode == "🤖 Agent Mode":
        st.caption(
            "Claude actively looks up live data (price, valuation, growth, momentum) for each "
            "candidate via a tool call before deciding whether to include it — not just recalling "
            "tickers from memory."
        )
    st.markdown("---")

    # ── Example prompts ───────────────────────────────────────────────────────
    if mode == "🔍 Screen Stocks":
        examples = [
            "AI and semiconductor stocks, revenue growth > 20%, P/E < 35, above MA200",
            "SaaS gross margin > 70%, positive 3M momentum, P/S < 15, mid-cap",
            "Beaten-down growth stocks: down > 30% from highs, but fundamentals intact",
            "Dividend growth stocks, low debt, positive FCF, not tech sector",
        ]
    else:
        examples = [
            "5-stock AI infrastructure portfolio with conviction weights",
            "Defensive portfolio for recession: 6 positions, low beta, strong FCF",
            "High-growth emerging tech, 4 stocks under $10B market cap",
            "Semiconductor cycle recovery portfolio, 5 stocks, mix of fabless and equipment",
        ]

    st.markdown('<div class="panel-head">EXAMPLES</div>', unsafe_allow_html=True)
    ecols = st.columns(2)
    for i, ex in enumerate(examples):
        if ecols[i % 2].button(f"💬 {ex[:60]}", key=f"ex_{i}", width="stretch"):
            st.session_state["screener_query"] = ex

    query = st.text_area(
        "Your query",
        value=st.session_state.get("screener_query", ""),
        placeholder="Describe what you're looking for...",
        height=80, label_visibility="collapsed",
    )
    if query:
        st.session_state["screener_query"] = query

    run_btn_label = {
        "🔍 Screen Stocks": "🔍 Screen",
        "💼 Build Portfolio": "💼 Build Portfolio",
        "🤖 Agent Mode": "🤖 Run Agent",
    }[mode]
    run_btn = st.button(run_btn_label, type="primary", disabled=not (query or "").strip())

    # ════════════════════════════════════════════════════════════════════════
    # PORTFOLIO BUILDER MODE (with or without live tool-use agent)
    # ════════════════════════════════════════════════════════════════════════
    if run_btn and mode in ("💼 Build Portfolio", "🤖 Agent Mode") and query.strip():
        spinner_text = ("Claude is researching live data and designing your portfolio..."
                         if mode == "🤖 Agent Mode" else "Claude is designing your portfolio...")
        with st.spinner(spinner_text):
            port = (mod_screen.build_portfolio_agentic(query) if mode == "🤖 Agent Mode"
                    else mod_screen.build_portfolio(query))

        if "error" in port:
            st.error(port["error"])
            st.stop()

        if port.get("tickers_researched_live"):
            st.success(
                "🔎 Agent looked up live data for: "
                + ", ".join(port["tickers_researched_live"])
            )

        # Header
        risk_color = {"Conservative":"#16c784","Moderate":"#f0b90b","Aggressive":"#ea3a44"}.get(
            port.get("risk_level",""), "#8a9bc2")
        st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px;margin:12px 0">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:700;
              color:#e8edf8;margin-bottom:6px">{port.get('theme','Portfolio')}</div>
  <div style="font-size:13px;color:#b0bec5;line-height:1.6;margin-bottom:12px">
    {port.get('thesis','')}</div>
  <div style="display:flex;gap:12px">
    <span style="font-size:11px;font-family:'IBM Plex Mono',monospace;color:#8a9bc2">
      ⏱ {port.get('time_horizon','')}</span>
    <span style="font-size:11px;font-family:'IBM Plex Mono',monospace;color:{risk_color}">
      ⚡ Risk: {port.get('risk_level','')}</span>
  </div>
</div>""", unsafe_allow_html=True)

        # Fetch live data for each position
        positions = port.get("positions", [])
        prog = st.progress(0, text="Loading market data...")
        live_data = {}
        for i, pos in enumerate(positions):
            prog.progress((i+1)/len(positions), text=f"Loading {pos['ticker']}...")
            d = mod_screen.fetch_stock_data(pos["ticker"])
            if d:
                live_data[pos["ticker"]] = d
        prog.empty()

        # Allocation chart + position cards
        col_chart, col_cards = st.columns([1, 2])
        with col_chart:
            st.markdown('<div class="panel-head">ALLOCATION</div>', unsafe_allow_html=True)
            labels  = [p["ticker"] for p in positions]
            weights = [p["weight"] for p in positions]
            colors  = ["#16c784","#60a5fa","#f0b90b","#f472b6","#a78bfa","#34d399","#fb923c","#94a3b8"]
            fig_pie = go.Figure(go.Pie(
                labels=labels, values=weights,
                hole=0.5, textinfo="label+percent",
                marker=dict(colors=colors[:len(labels)],
                           line=dict(color="#131722", width=2)),
            ))
            fig_pie.update_layout(
                paper_bgcolor="#131722", font_color="#e8edf8",
                font_family="IBM Plex Mono",
                showlegend=False, height=300,
                margin=dict(t=10, b=10, l=10, r=10),
            )
            st.plotly_chart(fig_pie, width="stretch")

        with col_cards:
            st.markdown('<div class="panel-head">POSITIONS</div>', unsafe_allow_html=True)
            role_colors = {"Core":"#16c784","Growth":"#60a5fa","Satellite":"#f0b90b",
                           "Hedge":"#f97316","Value":"#a78bfa"}
            for pos in positions:
                tk   = pos["ticker"]
                ld   = live_data.get(tk, {})
                rc   = role_colors.get(pos.get("role","Core"), "#8a9bc2")
                rg_s = f"{ld['revenue_growth']*100:+.1f}%" if ld.get("revenue_growth") else "N/A"
                r3_s = f"{ld['r3m']*100:+.1f}%" if ld.get("r3m") else "N/A"
                px_s = f"${ld['price']:.2f}" if ld.get("price") else "N/A"
                st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            padding:12px 16px;margin-bottom:8px;border-left:3px solid {rc}">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <div>
      <span style="font-family:'IBM Plex Mono',monospace;font-size:16px;font-weight:700;
                   color:#e8edf8">{tk}</span>
      <span style="font-size:11px;color:#8a9bc2;margin-left:8px">{ld.get('name',pos.get('ticker',''))}</span>
      <span style="font-size:10px;background:{rc}20;color:{rc};border:1px solid {rc}40;
                   padding:1px 6px;border-radius:3px;margin-left:6px">{pos.get('role','')}</span>
    </div>
    <div style="text-align:right;font-family:'IBM Plex Mono',monospace">
      <span style="font-size:18px;font-weight:700;color:{rc}">{pos['weight']}%</span>
      <span style="font-size:11px;color:#8a9bc2;margin-left:6px">{px_s}</span>
    </div>
  </div>
  <div style="font-size:12px;color:#8a9bc2;margin-bottom:6px">{pos.get('rationale','')}</div>
  <div style="display:flex;gap:16px;font-size:11px;font-family:'IBM Plex Mono',monospace;color:#556070">
    <span>Rev Growth <b style="color:#e8edf8">{rg_s}</b></span>
    <span>3M <b style="color:{'#16c784' if '+' in r3_s else '#ea3a44'}">{r3_s}</b></span>
    <span>Sector <b style="color:#e8edf8">{ld.get('sector','')[:18]}</b></span>
  </div>
</div>""", unsafe_allow_html=True)
                if st.button(f"Deep dive {tk}", key=f"pd_{tk}", width="content"):
                    st.session_state["symbol"] = tk
                    st.session_state["_az_sym"] = tk
                    st.session_state["page_jump"] = "🔍 Analyze"
                    st.rerun()

        # Risks + rebalance trigger
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="panel-head">KEY RISKS</div>', unsafe_allow_html=True)
            for risk in port.get("key_risks", []):
                st.markdown(f"⚠️ {risk}")
        with c2:
            st.markdown('<div class="panel-head">REBALANCE TRIGGER</div>', unsafe_allow_html=True)
            st.markdown(f"🔄 {port.get('rebalance_trigger','')}")

        # Keep the built portfolio available across reruns for the Track button
        st.session_state["_last_built_port"] = port

    # ── Track the last built portfolio (persists across reruns) ───────────────
    if mode in ("💼 Build Portfolio", "🤖 Agent Mode") and st.session_state.get("_last_built_port"):
        _lbp = st.session_state["_last_built_port"]
        st.markdown("---")
        _tk_c1, _tk_c2, _tk_c3 = st.columns([2, 1.5, 1.5])
        with _tk_c1:
            st.markdown(f"**🎯 Put \"{_lbp.get('theme','Portfolio')}\" under tracking?** "
                        f"Drift, momentum, insider and valuation triggers will monitor it.")
        with _tk_c2:
            _tk_capital = st.number_input("Virtual capital ($)", value=100_000, step=10_000,
                                          key="_tk_capital")
        with _tk_c3:
            st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
            if st.button("🎯 Track this portfolio", type="primary", key="_tk_btn"):
                _tk_data, _tk_err = mod_tp.create_from_positions(
                    _lbp.get("theme", "AI Portfolio"),
                    _lbp.get("positions", []),
                    float(_tk_capital),
                    thesis=_lbp.get("thesis", ""),
                    risk_level=_lbp.get("risk_level", ""),
                )
                if _tk_err:
                    st.error(_tk_err)
                else:
                    st.success(f"Now tracking \"{_lbp.get('theme','')}\" — open the 🎯 Tracker page.")
                    st.session_state.pop("_last_built_port", None)

    # ════════════════════════════════════════════════════════════════════════
    # SCREEN STOCKS MODE
    # ════════════════════════════════════════════════════════════════════════
    elif run_btn and mode == "🔍 Screen Stocks" and query.strip():
        with st.spinner("Claude is parsing your query..."):
            parsed = mod_screen.parse_query(query)

        if "error" in parsed:
            st.error(parsed["error"])
            st.stop()

        st.markdown(f"""
<div style="background:var(--panel);border:1px solid #16c784;border-radius:10px;padding:14px 16px;margin:12px 0">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#16c784;
              text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">SCREENING FOR</div>
  <div style="font-size:13px;color:#e8edf8">{parsed.get('explanation','')}</div>
</div>""", unsafe_allow_html=True)

        candidates = [t.strip().upper() for t in parsed.get("candidate_tickers", []) if t.strip()][:30]
        filters    = parsed.get("filters", {})

        if not candidates:
            st.warning("No candidates suggested. Try rephrasing.")
            st.stop()

        # Fetch market data for each candidate
        prog = st.progress(0, text="Fetching market data...")
        stocks = []
        for i, sym in enumerate(candidates):
            prog.progress((i+1)/len(candidates), text=f"Loading {sym}...")
            d = mod_screen.fetch_stock_data(sym)
            if d:
                stocks.append(d)
        prog.empty()

        # Apply filters
        results = mod_screen.apply_filters(stocks, filters)
        if not results:
            st.info(f"No stocks passed all filters ({len(stocks)} fetched). Showing all candidates.")
            results = stocks

        # Run full scoring model
        prog2 = st.progress(0, text="Running scoring model...")
        for i, r in enumerate(results):
            prog2.progress((i+1)/len(results), text=f"Scoring {r['symbol']}...")
            sc = mod_screen.run_full_score(r["symbol"])
            r["score_data"] = sc
            r["composite"]  = sc.get("composite")
            r["sig_score"]  = mod_screen.signal_score(r)
        prog2.empty()

        # Sort by composite score, fallback to signal score
        results.sort(key=lambda x: x.get("composite") or x.get("sig_score", 0), reverse=True)

        st.markdown(f'<div class="panel-head">{len(results)} RESULTS — sorted by score</div>',
                    unsafe_allow_html=True)

        # Result cards
        SCORE_C = {"Strong Buy":"#16c784","Buy":"#a3e635","Hold":"#f0b90b",
                   "Watch":"#f97316","Avoid":"#ea3a44"}

        for r in results:
            sc   = r.get("score_data", {})
            comp = r.get("composite")
            sig  = r.get("sig_score", 0)
            lbl  = sc.get("label", "N/A")
            col  = SCORE_C.get(lbl, "#8a9bc2")

            cap   = r.get("market_cap")
            cap_s = f"${cap/1e9:.1f}B" if cap else "N/A"
            pe_s  = f"{r['forward_pe']:.1f}x"          if r.get("forward_pe")    else "N/A"
            ps_s  = f"{r['ps_ratio']:.1f}x"             if r.get("ps_ratio")     else "N/A"
            rg_s  = f"{r['revenue_growth']*100:+.1f}%"  if r.get("revenue_growth") else "N/A"
            eg_s  = f"{r['earnings_growth']*100:+.1f}%" if r.get("earnings_growth") else "N/A"
            gm_s  = f"{r['gross_margin']*100:.0f}%"     if r.get("gross_margin")  else "N/A"
            r3_s  = f"{r['r3m']*100:+.1f}%"             if r.get("r3m")          else "N/A"
            r6_s  = f"{r['r6m']*100:+.1f}%"             if r.get("r6m")          else "N/A"
            rsi_s = f"{r['rsi']:.0f}"                   if r.get("rsi")          else "N/A"
            ma200_s = "✅" if r.get("above_ma200") else "❌" if r.get("above_ma200") is False else "—"
            ma50_s  = "✅" if r.get("above_ma50")  else "❌" if r.get("above_ma50")  is False else "—"

            # Score bar
            fund_v = sc.get("fundamental", 0) or 0
            tech_v = sc.get("technical", 0) or 0
            mom_v  = sc.get("momentum", 0) or 0

            st.markdown(f"""
<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;
            border-left:4px solid {col};padding:16px 20px;margin-bottom:10px">

  <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:12px">

    <div style="min-width:140px">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:22px;font-weight:700;
                  color:#e8edf8">{r['symbol']}</div>
      <div style="font-size:12px;color:#8a9bc2">{r.get('name','')[:30]}</div>
      <div style="font-size:11px;color:#556070">{r.get('sector','')} · {r.get('industry','')[:20]}</div>
    </div>

    <div style="display:flex;gap:8px;align-items:center">
      {'<div style="text-align:center;background:#222b3d;border-radius:8px;padding:10px 16px;border:1px solid ' + col + '40">'
       '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:32px;font-weight:700;color:' + col + ';line-height:1">' + str(comp) + '</div>'
       '<div style="font-size:10px;color:' + col + ';margin-top:2px">' + lbl + '</div>'
       '</div>' if comp else
       '<div style="text-align:center;background:#222b3d;border-radius:8px;padding:10px 16px">'
       '<div style="font-family:\'IBM Plex Mono\',monospace;font-size:20px;color:#f0b90b">' + str(sig) + '%</div>'
       '<div style="font-size:10px;color:#8a9bc2">Signal</div>'
       '</div>'}

      {'<div style="display:flex;flex-direction:column;gap:4px;font-size:11px;font-family:\'IBM Plex Mono\',monospace">'
       f'<div><span style="color:#8a9bc2">Fund </span><span style="color:#16c784">{fund_v}/10</span></div>'
       f'<div><span style="color:#8a9bc2">Tech </span><span style="color:#60a5fa">{tech_v}/10</span></div>'
       f'<div><span style="color:#8a9bc2">Mom  </span><span style="color:#f0b90b">{mom_v}/10</span></div>'
       '</div>' if comp else ''}
    </div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;flex:1;min-width:300px">
      {_metric_cell("Market Cap", cap_s, "#e8edf8")}
      {_metric_cell("Fwd P/E",    pe_s,  "#e8edf8")}
      {_metric_cell("P/S",        ps_s,  "#e8edf8")}
      {_metric_cell("Gross Margin",gm_s, "#16c784" if r.get("gross_margin",0) and r["gross_margin"]>0.5 else "#f0b90b")}
      {_metric_cell("Rev Growth", rg_s, "#16c784" if "+" in rg_s and rg_s!="N/A" and float(rg_s.replace("%","").replace("+",""))>15 else "#e8edf8")}
      {_metric_cell("EPS Growth", eg_s, "#16c784" if "+" in eg_s else "#ea3a44" if eg_s!="N/A" else "#e8edf8")}
      {_metric_cell("3M Return",  r3_s, "#16c784" if "+" in r3_s else "#ea3a44" if r3_s!="N/A" else "#e8edf8")}
      {_metric_cell("6M Return",  r6_s, "#16c784" if "+" in r6_s else "#ea3a44" if r6_s!="N/A" else "#e8edf8")}
      {_metric_cell("RSI",       rsi_s, "#16c784" if r.get("rsi") and 40<=r["rsi"]<=65 else "#f97316" if r.get("rsi") and r["rsi"]>70 else "#e8edf8")}
      {_metric_cell("MA200", ma200_s, "#e8edf8")}
      {_metric_cell("MA50",  ma50_s,  "#e8edf8")}
      {_metric_cell("Short%", f"{r['short_pct']*100:.1f}%" if r.get("short_pct") else "N/A",
                    "#f97316" if r.get("short_pct") and r["short_pct"]>0.1 else "#e8edf8")}
    </div>
  </div>

</div>""", unsafe_allow_html=True)

            c1, c2 = st.columns([3, 1])
            with c2:
                if st.button(f"Deep dive {r['symbol']}", key=f"dd_{r['symbol']}",
                             width="stretch"):
                    st.session_state["symbol"] = r["symbol"]
                    st.session_state["_az_sym"] = r["symbol"]
                    st.session_state["page_jump"] = "🔍 Analyze"
                    st.rerun()
            # Inline ETF holdings (auto-shown for ETFs)
            if r.get("quoteType", "").upper() in ("ETF", "MUTUALFUND") or \
               r["symbol"].upper() in ("QQQ","SPY","IWM","SOXX","SMH","WCLD","ARKK","KWEB","XLK","XLF","XLE","XLV","XLC","XLY","XLI","XLB","XLRE","XLU"):
                with st.expander(f"📦 ETF Holdings — {r['symbol']}", expanded=False):
                    mod_etf.render_etf_holdings(r["symbol"], max_rows=15)


# ─── Page: Tracker (dynamic portfolio monitoring + rebalance engine) ──────────
elif page == "🎯 Tracker":
    import html as _h_tp
    _etp = lambda v: _h_tp.escape(str(v or ""), quote=False)

    st.title("🎯 Portfolio Tracker")
    _page_about("""**What:** the command center for a LIVE portfolio/index you built — drift, triggers, rebalancing, risk.
**How:** weights drift with prices; triggers fire on drift ≥ threshold, momentum crashes (-12%/1M), momentum leaders (+20%/3M), RSI extremes, insider activity (MSPR), health downgrades, concentration >30%. The rebalance plan only proposes trades that clear the drift threshold AND minimum size, with cost estimated in bps. Risk parity, stress scenarios and Monte Carlo live in the expanders below.
**Use:** check weekly, not daily. Act when triggers CLUSTER on a position — one trigger is noise, three is a message. The Claude advisor weighs it all including whether rebalancing is worth the cost.""")
    st.caption("Dynamic monitoring of tracked portfolios: drift vs target, momentum, insider "
               "and valuation triggers, cost-aware rebalancing, and a Claude rebalance advisor.")

    _tpdata = mod_tp.load_all()
    _tp_names = list(_tpdata["portfolios"].keys())

    # ── Manual creation ────────────────────────────────────────────────────────
    with st.expander("➕ Create tracked portfolio manually", expanded=not _tp_names):
        st.caption("Enter positions as SYMBOL:WEIGHT pairs, e.g. `NVDA:25, MSFT:20, LLY:20, XOM:15, COST:20`")
        _mc1, _mc2 = st.columns([3, 1])
        with _mc1:
            _man_name  = st.text_input("Portfolio name", key="_tp_man_name",
                                       placeholder="My Growth Mix")
            _man_alloc = st.text_input("Allocations", key="_tp_man_alloc",
                                       placeholder="NVDA:25, MSFT:20, LLY:20, XOM:15, COST:20")
        with _mc2:
            _man_cap = st.number_input("Capital ($)", value=100_000, step=10_000, key="_tp_man_cap")
        if st.button("Create & Track", type="primary", key="_tp_man_btn"):
            _man_positions = []
            try:
                for pair in _man_alloc.split(","):
                    if ":" in pair:
                        s, w = pair.split(":")
                        _man_positions.append({"ticker": s.strip().upper(),
                                               "weight": float(w.strip())})
            except Exception:
                _man_positions = []
            if not _man_name.strip() or not _man_positions:
                st.error("Need a name and at least one SYMBOL:WEIGHT pair.")
            else:
                _tpdata, _man_err = mod_tp.create_from_positions(
                    _man_name, _man_positions, float(_man_cap))
                if _man_err:
                    st.error(_man_err)
                else:
                    st.success(f"Tracking \"{_man_name}\".")
                    st.rerun()

    if not _tp_names:
        st.info("No tracked portfolios yet. Create one above, or build one in "
                "🔎 AI Screener → Build Portfolio and click **🎯 Track this portfolio**.")
        st.stop()

    # ── Portfolio selector ─────────────────────────────────────────────────────
    _sel_c1, _sel_c2 = st.columns([4, 1])
    with _sel_c1:
        _tp_sel = st.selectbox("Tracked portfolio", _tp_names, key="_tp_selector")
    with _sel_c2:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        if st.button("🗑 Delete", key="_tp_del"):
            _tpdata = mod_tp.delete_portfolio(_tpdata, _tp_sel)
            st.rerun()

    _tp = _tpdata["portfolios"][_tp_sel]
    if _tp.get("thesis"):
        st.caption(f"📜 {_etp(_tp['thesis'])}")

    # ── Settings ───────────────────────────────────────────────────────────────
    with st.expander("⚙️ Rebalance settings", expanded=False):
        _s1, _s2, _s3 = st.columns(3)
        _set = _tp.setdefault("settings", dict(mod_tp.DEFAULT_SETTINGS))
        with _s1:
            _new_dth = st.slider("Drift threshold (pp)", 2.0, 15.0,
                                 float(_set.get("drift_threshold_pct", 5.0)), 0.5,
                                 help="Rebalance a position only when |current − target| weight exceeds this")
        with _s2:
            _new_cbps = st.slider("Transaction cost (bps)", 0, 50,
                                  int(_set.get("cost_bps", 10)),
                                  help="One-way cost assumption per trade — commissions + spread")
        with _s3:
            _new_mint = st.number_input("Min trade ($)", value=int(_set.get("min_trade_usd", 200)),
                                        step=100)
        if (_new_dth, _new_cbps, _new_mint) != (_set.get("drift_threshold_pct"),
                                                _set.get("cost_bps"), _set.get("min_trade_usd")):
            _set.update({"drift_threshold_pct": _new_dth, "cost_bps": _new_cbps,
                         "min_trade_usd": _new_mint})
            mod_tp.save_all(_tpdata)

    # ── Live analysis (cached in session per day/portfolio) ───────────────────
    _an_key = f"_tp_analysis_{_tp_sel}"
    if st.button("🔄 Refresh analysis", key="_tp_refresh") or _an_key not in st.session_state:
        with st.spinner(f"Analyzing {len(_tp['positions'])} positions (prices, momentum, insiders, health)..."):
            st.session_state[_an_key] = mod_tp.analyze(_tp)
        mod_tp.record_snapshot(_tpdata, _tp_sel, st.session_state[_an_key]["total_value"])
    _an = st.session_state[_an_key]

    # ── Header metrics ─────────────────────────────────────────────────────────
    _hm1, _hm2, _hm3, _hm4, _hm5 = st.columns(5)
    _hm1.metric("Total Value", f"${_an['total_value']:,.0f}")
    _hm2.metric("Return", f"{_an['total_return']:+.2f}%",
                help=mod_gloss.tip("alpha"))
    _hm3.metric("Positions", len(_an["positions"]))
    _hm4.metric("Fired Triggers", _an["n_triggers"],
                help=mod_gloss.tip("drift"))
    _regime = _an.get("regime", {})
    _hm5.metric("Market Regime", f"{_regime.get('regime_emoji','')} {_regime.get('regime','N/A')}")

    for _w in _an.get("warnings", []):
        st.warning(f"⚠ {_w}")

    # ── Positions table ────────────────────────────────────────────────────────
    st.subheader("Holdings — Target vs Current")
    _rows_tp = ""
    for _r in sorted(_an["positions"], key=lambda x: -x["current_weight"]):
        _dr_c = "#ea3a44" if abs(_r["drift"]) >= _tp["settings"]["drift_threshold_pct"] else \
                ("#f0b90b" if abs(_r["drift"]) >= _tp["settings"]["drift_threshold_pct"] * 0.6 else "#16c784")
        _ret_c = "#16c784" if _r["ret_since_entry"] >= 0 else "#ea3a44"
        _r1m_s = f"{_r['r1m']*100:+.1f}%" if _r["r1m"] is not None else "—"
        _r1m_c = "#16c784" if (_r["r1m"] or 0) >= 0 else "#ea3a44"
        _rsi_s = f"{_r['rsi']:.0f}" if _r["rsi"] is not None else "—"
        _mspr_s = f"{_r['mspr']:+.0f}" if _r["mspr"] is not None else "—"
        _trig_s = " ".join(_t[0] for _t in _r["triggers"]) or "✓"
        _stale_s = " ⚠" if _r.get("price_stale") else ""
        _rows_tp += (
            f'<tr>'
            f'<td style="padding:6px 10px;font-weight:700">{_etp(_r["symbol"])}{_stale_s}</td>'
            f'<td style="padding:6px 10px;color:#8a9bc2;font-size:11px">{_etp(_r["role"])}</td>'
            f'<td style="padding:6px 10px;text-align:right">{_r["target_weight"]:.1f}%</td>'
            f'<td style="padding:6px 10px;text-align:right">{_r["current_weight"]:.1f}%</td>'
            f'<td style="padding:6px 10px;text-align:right;color:{_dr_c};font-weight:600">'
            f'{_r["drift"]:+.1f}pp</td>'
            f'<td style="padding:6px 10px;text-align:right;color:{_ret_c}">'
            f'{_r["ret_since_entry"]:+.1f}%</td>'
            f'<td style="padding:6px 10px;text-align:right;color:{_r1m_c}">{_r1m_s}</td>'
            f'<td style="padding:6px 10px;text-align:right">{_rsi_s}</td>'
            f'<td style="padding:6px 10px;text-align:right">{_mspr_s}</td>'
            f'<td style="padding:6px 10px;text-align:right">'
            f'{_r["score"] if _r["score"] is not None else "—"}</td>'
            f'<td style="padding:6px 10px;font-size:13px">{_trig_s}</td>'
            f'</tr>'
        )
    _th_tp = "text-align:left;font-size:10px;color:#556070;padding:4px 10px;font-family:'IBM Plex Mono',monospace"
    _tr_tp = "text-align:right;font-size:10px;color:#556070;padding:4px 10px;font-family:'IBM Plex Mono',monospace"
    st.markdown(
        f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
        f'padding:12px 16px;overflow-x:auto">'
        f'<table style="width:100%;border-collapse:collapse">'
        f'<thead><tr>'
        f'<th style="{_th_tp}">SYMBOL</th><th style="{_th_tp}">ROLE</th>'
        f'<th style="{_tr_tp}">TARGET</th><th style="{_tr_tp}">CURRENT</th>'
        f'<th style="{_tr_tp}">DRIFT</th><th style="{_tr_tp}">SINCE ENTRY</th>'
        f'<th style="{_tr_tp}">1M</th><th style="{_tr_tp}">RSI</th>'
        f'<th style="{_tr_tp}">MSPR</th><th style="{_tr_tp}">SCORE</th>'
        f'<th style="{_th_tp}">TRIGGERS</th>'
        f'</tr></thead><tbody>{_rows_tp}</tbody></table></div>',
        unsafe_allow_html=True,
    )
    st.caption("Triggers: ⚖️ drift · 📉 momentum crash · 🚀 momentum leader · 🔥 overbought · "
               "🧊 oversold · 👤 insider activity · 🏥 health · ⚠️ concentration · ✓ none")

    # ── Fired triggers detail ──────────────────────────────────────────────────
    _fired = [(r["symbol"], t) for r in _an["positions"] for t in r["triggers"]]
    if _fired:
        with st.expander(f"🚨 Fired triggers ({len(_fired)})", expanded=True):
            for _sym_f, (_em, _msg) in _fired:
                st.markdown(f"{_em} **{_sym_f}** — {_msg}")

    # ── Rebalance plan ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("⚖️ Rebalance Plan (cost-aware)")
    _plan = mod_tp.build_rebalance_plan(_an, _tp)
    if _plan["actions"]:
        for _a in _plan["actions"]:
            _a_c = "#16c784" if _a["action"] == "BUY" else "#ea3a44"
            st.markdown(
                f'<span style="color:{_a_c};font-weight:700">{_a["action"]}</span> '
                f'**{_a["symbol"]}** — ${abs(_a["amount_usd"]):,.0f} '
                f'<span style="color:#8a9bc2">(drift {_a["drift"]:+.1f}pp)</span>',
                unsafe_allow_html=True,
            )
        _pc1, _pc2, _pc3 = st.columns(3)
        _pc1.metric("Turnover", f"${_plan['turnover_usd']:,.0f}")
        _pc2.metric("Est. Cost", f"${_plan['est_cost_usd']:,.2f}")
        _pc3.metric("Worth It?", "✅ Yes" if _plan["worth_it"] else "❌ Marginal")
        for _sk in _plan["skipped"]:
            st.caption(f"⏭ Skipped: {_sk}")
        if st.button("✅ Apply rebalance (reset to targets)", key="_tp_apply"):
            _tpdata = mod_tp.apply_rebalance(_tpdata, _tp_sel, _plan["actions"],
                                             note="Mechanical drift rebalance")
            st.session_state.pop(_an_key, None)
            st.success("Rebalanced — share counts reset to target weights at current prices.")
            st.rerun()
    else:
        st.success(f"✓ All positions within ±{_tp['settings']['drift_threshold_pct']:.1f}pp "
                   f"of target — no mechanical rebalance needed.")

    # ── Claude Rebalance Advisor ───────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🤖 Claude Rebalance Advisor")
    if st.button("Get full rebalance review", type="primary", key="_tp_claude"):
        with st.spinner("Claude is weighing momentum, valuation, insiders, regime and costs..."):
            _fp_tp = mod_tp.portfolio_fingerprint(_tp, _an)
            _pos_json = json.dumps([{
                k: v for k, v in r.items()
                if k in ("symbol", "role", "target_weight", "current_weight", "drift",
                         "ret_since_entry", "r1m", "r3m", "rsi", "fwd_pe", "mspr",
                         "score", "score_label", "sector",
                         "triggers")
            } for r in _an["positions"]], default=str, indent=1)
            _regime_s = (f"{_regime.get('regime','?')} (score {_regime.get('score','?')}) — "
                         f"VIX {_regime.get('signals',{}).get('vix','?')}, "
                         f"SPY 1M {_regime.get('signals',{}).get('spy_r1m','?')}")
            _rev = mod_tp.claude_rebalance_review(
                _fp_tp, _pos_json, json.dumps(_plan, default=str),
                _regime_s, _tp.get("thesis", ""), " | ".join(_an.get("warnings", [])),
            )
        if "error" in _rev:
            st.error(_rev["error"])
        else:
            _urg = _rev.get("urgency", "NONE")
            _urg_c = {"NONE": "#16c784", "LOW": "#a3e635",
                      "MEDIUM": "#f0b90b", "HIGH": "#ea3a44"}.get(_urg, "#556070")
            st.markdown(
                f'<div style="background:var(--panel);border-left:4px solid {_urg_c};'
                f'border-radius:8px;padding:14px 18px;margin:8px 0">'
                f'<span style="color:{_urg_c};font-weight:700;font-size:12px">'
                f'URGENCY: {_etp(_urg)}</span><br>'
                f'<span style="color:#cdd6f4;font-size:13px">'
                f'{_etp(_rev.get("overall_assessment",""))}</span></div>',
                unsafe_allow_html=True,
            )
            for _act in _rev.get("actions", []):
                _ac = {"HOLD": "#8a9bc2", "TRIM": "#f97316", "ADD": "#16c784",
                       "EXIT": "#ea3a44", "REPLACE": "#a78bfa"}.get(_act.get("action"), "#8a9bc2")
                _ntw = _act.get("new_target_weight")
                _ntw_s = f" → new target {_ntw}%" if _ntw is not None else ""
                _repl = _act.get("replacement_candidate")
                _repl_s = f" (candidate: **{_repl}**)" if _repl else ""
                st.markdown(
                    f'<span style="color:{_ac};font-weight:700">{_etp(_act.get("action",""))}'
                    f'</span> **{_etp(_act.get("symbol",""))}**{_ntw_s}{_repl_s} — '
                    f'{_etp(_act.get("reason",""))}',
                    unsafe_allow_html=True,
                )
            _rc1, _rc2 = st.columns(2)
            with _rc1:
                if _rev.get("alpha_ideas"):
                    st.markdown("**💡 Alpha Ideas**")
                    for _ai in _rev["alpha_ideas"]:
                        st.markdown(f"- {_ai}")
            with _rc2:
                if _rev.get("risk_flags"):
                    st.markdown("**⚠️ Risk Flags**")
                    for _rf in _rev["risk_flags"]:
                        st.markdown(f"- {_rf}")
            if _rev.get("cost_note"):
                st.caption(f"💸 {_rev['cost_note']}")

    # ── Value history + rebalance log ──────────────────────────────────────────
    _vh = _tp.get("value_history", [])
    if len(_vh) >= 2:
        st.markdown("---")
        _vh_df = pd.DataFrame(_vh)
        _vh_df["date"] = pd.to_datetime(_vh_df["date"])
        _fig_vh = go.Figure(go.Scatter(
            x=_vh_df["date"], y=_vh_df["value"], mode="lines+markers",
            line=dict(color="#4da3ff", width=2), name=_tp_sel,
        ))
        _fig_vh.update_layout(
            title=dict(text="Tracked Value Over Time", font=dict(size=13, color="#cdd6f4"), x=0),
            height=220, margin=dict(l=0, r=0, t=32, b=0),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#cdd6f4"),
            yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#1e2535"),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(_fig_vh, width="stretch", config={"displayModeBar": False})

    if _tp.get("rebalance_log"):
        with st.expander(f"📜 Rebalance history ({len(_tp['rebalance_log'])})"):
            for _rl in reversed(_tp["rebalance_log"]):
                _acts = ", ".join(f"{a['action']} {a['symbol']} ${abs(a['amount_usd']):,.0f}"
                                  for a in _rl.get("actions", []))
                st.markdown(f"**{_rl['date']}** — {_acts} · est. cost ${_rl.get('est_cost', 0):,.2f}")

    # ── Risk Parity check (Dalio) ──────────────────────────────────────────────
    st.markdown("---")
    with st.expander("⚖️ Risk Parity Check (Dalio) — volatility-balanced weights", expanded=False):
        st.caption("Simplified risk parity: each position sized inversely to its volatility, "
                   "so every holding contributes similar RISK (not similar dollars). Compare "
                   "to your current weights to see where risk is concentrated.")
        _rp = mod_fm.risk_parity_weights(tuple(sorted(_tp["positions"].keys())))
        if _rp:
            _rp_rows = ""
            for _r in sorted(_an["positions"], key=lambda x: -x["current_weight"]):
                _sym_rp = _r["symbol"]
                _rpw = _rp.get(_sym_rp, {})
                if not _rpw:
                    continue
                _gap = _r["current_weight"] - _rpw["rp_weight"]
                _gap_c = "#ea3a44" if abs(_gap) > 8 else ("#f0b90b" if abs(_gap) > 4 else "#16c784")
                _rp_rows += (
                    f'<tr>'
                    f'<td style="padding:5px 10px;font-weight:600">{_etp(_sym_rp)}</td>'
                    f'<td style="padding:5px 10px;text-align:right">{_rpw["vol_ann"]:.1f}%</td>'
                    f'<td style="padding:5px 10px;text-align:right">{_r["current_weight"]:.1f}%</td>'
                    f'<td style="padding:5px 10px;text-align:right">{_rpw["rp_weight"]:.1f}%</td>'
                    f'<td style="padding:5px 10px;text-align:right;color:{_gap_c};font-weight:600">'
                    f'{_gap:+.1f}pp</td>'
                    f'</tr>'
                )
            _th_rp = "text-align:left;font-size:10px;color:#556070;padding:4px 10px;font-family:'IBM Plex Mono',monospace"
            _tr_rp = "text-align:right;font-size:10px;color:#556070;padding:4px 10px;font-family:'IBM Plex Mono',monospace"
            st.markdown(
                f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                f'padding:12px 16px;overflow-x:auto">'
                f'<table style="width:100%;border-collapse:collapse"><thead><tr>'
                f'<th style="{_th_rp}">SYMBOL</th>'
                f'<th style="{_tr_rp}">ANN. VOL</th>'
                f'<th style="{_tr_rp}">CURRENT WT</th>'
                f'<th style="{_tr_rp}">RISK-PARITY WT</th>'
                f'<th style="{_tr_rp}">GAP</th>'
                f'</tr></thead><tbody>{_rp_rows}</tbody></table></div>',
                unsafe_allow_html=True,
            )
            st.caption("Positive gap = position carries MORE risk than a vol-balanced book "
                       "would give it. Red = risk concentration >8pp.")
        else:
            st.info("Volatility data unavailable for risk parity calculation.")

    # ── Scenario Stress Test ───────────────────────────────────────────────────
    with st.expander("🧪 Scenario Stress Test — what happens to this portfolio if...", expanded=False):
        st.caption("Estimated P&L per macro scenario via beta × sector sensitivity. "
                   "Heuristic, not a forecast — use it to find hidden concentration.")
        if st.button("Run stress test", key="_tp_stress"):
            with st.spinner("Stress testing across 5 scenarios..."):
                _stress_pos = [{"symbol": r["symbol"], "value": r["value"],
                                "sector": r.get("sector", "")}
                               for r in _an["positions"]]
                st.session_state[f"_tp_stress_{_tp_sel}"] = mod_rt.stress_scenarios(_stress_pos)
        _stress = st.session_state.get(f"_tp_stress_{_tp_sel}")
        if _stress:
            for _sc_name, _sc in _stress.items():
                _sc_c = "#16c784" if _sc["pnl_usd"] >= 0 else "#ea3a44"
                _worst = _sc.get("worst") or {}
                _best  = _sc.get("best") or {}
                st.markdown(
                    f'<div style="background:var(--panel);border-left:3px solid {_sc_c};'
                    f'border-radius:6px;padding:10px 16px;margin-bottom:8px">'
                    f'<div style="display:flex;justify-content:space-between">'
                    f'<b style="color:#e8edf8">{_etp(_sc_name)}</b>'
                    f'<b style="color:{_sc_c};font-family:IBM Plex Mono,monospace">'
                    f'{_sc["pnl_pct"]:+.1f}% (${_sc["pnl_usd"]:+,.0f})</b></div>'
                    f'<div style="font-size:11px;color:#8a9bc2;margin:4px 0">{_etp(_sc["desc"])}</div>'
                    f'<div style="font-size:11px;color:#556070">'
                    f'Worst: {_etp(_worst.get("symbol",""))} {_worst.get("impact_pct",0):+.1f}% · '
                    f'Best: {_etp(_best.get("symbol",""))} {_best.get("impact_pct",0):+.1f}%</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Monte Carlo projection ─────────────────────────────────────────────────
    with st.expander("🎲 Monte Carlo — 1-year projection cone", expanded=False):
        st.caption("500 simulated paths from the portfolio's own 1y return distribution (GBM). "
                   "The cone shows the 5th-95th percentile range — plan for the whole cone, "
                   "not the median.")
        if st.button("Run simulation", key="_tp_mc"):
            with st.spinner("Simulating 500 paths..."):
                _mc_wts = tuple(
                    (r["symbol"], r["current_weight"] / 100)
                    for r in _an["positions"] if r["current_weight"] > 0
                )
                st.session_state[f"_tp_mc_{_tp_sel}"] = mod_rt.monte_carlo(
                    _mc_wts, _an["total_value"])
        _mc = st.session_state.get(f"_tp_mc_{_tp_sel}")
        if _mc:
            if _mc.get("error"):
                st.info(_mc["error"])
            else:
                _mc1, _mc2, _mc3, _mc4 = st.columns(4)
                _mc1.metric("Median (1y)", f"${_mc['median_end']:,.0f}",
                            help=mod_gloss.tip("monte_carlo"))
                _mc2.metric("Bear 5%", f"${_mc['p5_end']:,.0f}")
                _mc3.metric("Bull 95%", f"${_mc['p95_end']:,.0f}")
                _mc4.metric("P(loss)", f"{_mc['prob_loss']:.0f}%",
                            help=mod_gloss.tip("volatility"))
                _pcts = _mc["percentiles"]
                _x_mc = list(range(1, len(_pcts["50"]) + 1))
                _fig_mc = go.Figure()
                _fig_mc.add_trace(go.Scatter(x=_x_mc, y=_pcts["95"], mode="lines",
                                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
                _fig_mc.add_trace(go.Scatter(x=_x_mc, y=_pcts["5"], mode="lines",
                                             line=dict(width=0), fill="tonexty",
                                             fillcolor="rgba(77,163,255,0.10)",
                                             name="5-95%", hoverinfo="skip"))
                _fig_mc.add_trace(go.Scatter(x=_x_mc, y=_pcts["75"], mode="lines",
                                             line=dict(width=0), showlegend=False, hoverinfo="skip"))
                _fig_mc.add_trace(go.Scatter(x=_x_mc, y=_pcts["25"], mode="lines",
                                             line=dict(width=0), fill="tonexty",
                                             fillcolor="rgba(77,163,255,0.18)",
                                             name="25-75%", hoverinfo="skip"))
                _fig_mc.add_trace(go.Scatter(x=_x_mc, y=_pcts["50"], mode="lines",
                                             line=dict(color="#4da3ff", width=2), name="Median"))
                _fig_mc.add_hline(y=_an["total_value"],
                                  line=dict(color="#556070", dash="dot", width=1))
                _fig_mc.update_layout(
                    height=260, margin=dict(l=0, r=0, t=10, b=0),
                    plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                    font=dict(color="#cdd6f4"),
                    xaxis=dict(title="Trading days ahead", showgrid=False),
                    yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#1e2535"),
                    legend=dict(orientation="h", y=1.05, x=0),
                )
                st.plotly_chart(_fig_mc, width="stretch",
                                config={"displayModeBar": False})
                st.caption(f"Annualized portfolio vol: {_mc['ann_vol']}%")

    # ── Excel export ───────────────────────────────────────────────────────────
    st.markdown("---")
    try:
        _xlsx_bytes = mod_xlsx.tracked_portfolio_xlsx(_tp, _an, _plan)
        st.download_button(
            "📥 Download Excel report",
            data=_xlsx_bytes,
            file_name=f"tracker_{_tp_sel.replace(' ', '_')}_{_date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="_tp_xlsx",
        )
    except Exception as _xe:
        st.caption(f"Excel export unavailable: {_xe}")


# ─── Page: Backtester ─────────────────────────────────────────────────────────
elif page == "📊 Backtester":
    st.title("📊 Strategy Backtester")
    _page_about("""**What:** test a mechanical strategy on real history before risking money on the idea.
**How:** signals computed bar-by-bar (no lookahead: yesterday's signal → today's return); equity curve compounds daily returns vs a Buy & Hold benchmark on the same capital. Metrics: CAGR, Sharpe (return per unit of risk), max drawdown, win rate, profit factor.
**Use:** beating Buy & Hold is the bar — most strategies don't. Beware overfitting: parameters tuned to look great on ONE period usually fail on the next. Test 2-3 different periods.""")
    st.caption("Simulate trading strategies on historical price data. Compare vs. Buy & Hold.")

    # ── Controls ──────────────────────────────────────────────────────────────
    col_sym, col_strat, col_period, col_cap = st.columns([2, 2, 1.5, 1.5])
    with col_sym:
        bt_symbol = st.text_input("Symbol", value="NVDA", key="bt_symbol").upper().strip()
    with col_strat:
        bt_strategy = st.selectbox("Strategy", list(mod_bt.STRATEGIES.keys()), key="bt_strategy")
    with col_period:
        bt_period = st.selectbox("Period", ["1y", "2y", "3y", "5y"], index=1, key="bt_period")
    with col_cap:
        bt_capital = float(st.number_input("Capital ($)", value=10000, step=1000, min_value=1000, key="bt_capital"))

    # ── Parameter overrides ───────────────────────────────────────────────────
    _default_p = mod_bt.STRATEGIES[bt_strategy].copy()
    with st.expander("⚙️ Strategy Parameters", expanded=False):
        bt_params: dict = {}
        _pcols = st.columns(len(_default_p))
        for i, (k, v) in enumerate(_default_p.items()):
            with _pcols[i]:
                if isinstance(v, float):
                    bt_params[k] = st.number_input(k, value=float(v), step=0.1, format="%.1f", key=f"btp_{k}")
                else:
                    bt_params[k] = st.number_input(k, value=int(v), step=1, min_value=1, key=f"btp_{k}")

    st.markdown("---")

    if st.button("▶ Run Backtest", type="primary", width="content"):
        st.session_state["_bt_result"] = None  # clear previous
        with st.spinner(f"Backtesting {bt_strategy} on {bt_symbol} ({bt_period})..."):
            _bt_res = mod_bt.run_backtest(bt_symbol, bt_strategy, bt_period, bt_capital, bt_params)
        st.session_state["_bt_result"] = _bt_res

    _bt_res = st.session_state.get("_bt_result")

    if _bt_res is not None:
        if _bt_res.get("error"):
            st.error(_bt_res["error"])
        else:
            # ── Metric cards ─────────────────────────────────────────────────
            _tot   = _bt_res["total_return"]
            _bm    = _bt_res["benchmark_return"]
            _alpha = _tot - _bm
            _dd    = _bt_res["max_drawdown"]
            _sh    = _bt_res["sharpe"]
            _wr    = _bt_res["win_rate"]
            _tr    = _bt_res["total_trades"]
            _cagr  = _bt_res["cagr"]

            def _bt_metric(label, value, color="#e8edf8", tip=""):
                _tip_attr = f' title="{_html.escape(tip, quote=True)}"' if tip else ""
                _cursor = "cursor:help;" if tip else ""
                return (
                    f'<div style="background:#1a2035;border:1px solid var(--border);border-radius:8px;'
                    f'padding:12px 16px;text-align:center;{_cursor}"{_tip_attr}>'
                    f'<div style="font-size:10px;font-family:\'IBM Plex Mono\',monospace;'
                    f'color:#556070;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px">{label}{" ⓘ" if tip else ""}</div>'
                    f'<div style="font-size:20px;font-weight:700;color:{color};'
                    f'font-family:\'IBM Plex Mono\',monospace">{value}</div>'
                    f'</div>'
                )

            _c1, _c2, _c3, _c4, _c5, _c6 = st.columns(6)
            _metric_cols = [_c1, _c2, _c3, _c4, _c5, _c6]
            _metrics = [
                ("Total Return",   f"{'+' if _tot>=0 else ''}{_tot*100:.1f}%",
                 "#16c784" if _tot >= 0 else "#ea3a44", mod_gloss.tip("backtest")),
                ("vs Buy & Hold",  f"{'+' if _alpha>=0 else ''}{_alpha*100:.1f}%",
                 "#16c784" if _alpha >= 0 else "#ea3a44", mod_gloss.tip("benchmark")),
                ("CAGR",           f"{'+' if _cagr>=0 else ''}{_cagr*100:.1f}%",
                 "#16c784" if _cagr >= 0 else "#ea3a44", mod_gloss.tip("cagr")),
                ("Sharpe Ratio",   f"{_sh:.2f}",
                 "#16c784" if _sh >= 1 else "#f0b90b" if _sh >= 0.5 else "#ea3a44",
                 mod_gloss.tip("sharpe")),
                ("Max Drawdown",   f"{_dd*100:.1f}%",
                 "#ea3a44" if _dd < -0.2 else "#f0b90b" if _dd < -0.1 else "#16c784",
                 mod_gloss.tip("max_drawdown")),
                ("Win Rate",       f"{_wr*100:.0f}% ({_tr}T)",
                 "#16c784" if _wr >= 0.5 else "#f0b90b", mod_gloss.tip("win_rate")),
            ]
            for col, (lbl, val, clr, _tip_m) in zip(_metric_cols, _metrics):
                with col:
                    st.markdown(_bt_metric(lbl, val, clr, _tip_m), unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)

            # ── Equity curve chart ────────────────────────────────────────────
            _eq  = _bt_res["equity_curve"]
            _bmc = _bt_res["benchmark_curve"]

            _fig = go.Figure()
            _fig.add_trace(go.Scatter(
                x=_eq.index, y=_eq.values,
                name=bt_strategy, line=dict(color="#60a5fa", width=2),
            ))
            _fig.add_trace(go.Scatter(
                x=_bmc.index, y=_bmc.values,
                name="Buy & Hold", line=dict(color="#556070", width=1.5, dash="dash"),
            ))

            # Drawdown shading
            _peak = _eq.cummax()
            _dd_series = (_eq - _peak) / _peak
            _dd_thresh = -0.05
            _in_dd = False
            _dd_start = None
            for _idx, _v in _dd_series.items():
                if _v < _dd_thresh and not _in_dd:
                    _in_dd = True
                    _dd_start = _idx
                elif _v >= _dd_thresh and _in_dd:
                    _in_dd = False
                    _fig.add_vrect(
                        x0=_dd_start, x1=_idx,
                        fillcolor="rgba(234,58,68,0.08)", line_width=0,
                    )
            if _in_dd and _dd_start is not None:
                _fig.add_vrect(
                    x0=_dd_start, x1=_eq.index[-1],
                    fillcolor="rgba(234,58,68,0.08)", line_width=0,
                )

            _fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0d1117", plot_bgcolor="#0d1117",
                height=380,
                margin=dict(l=0, r=0, t=30, b=0),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor="#1a2035", tickprefix="$"),
                font=dict(family="IBM Plex Mono", color="#b0bec5"),
                title=dict(
                    text=f"{bt_symbol} · {bt_strategy} · {bt_period}",
                    font=dict(size=13, color="#e8edf8"),
                ),
            )
            st.plotly_chart(_fig, width="stretch")

            # ── Trade log ─────────────────────────────────────────────────────
            _trades = _bt_res["trades"]
            if _trades:
                st.markdown(
                    '<div style="font-size:10px;font-family:\'IBM Plex Mono\',monospace;'
                    'color:#16c784;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px">'
                    f'TRADE LOG · {len([t for t in _trades if t["action"]=="SELL"])} completed trades'
                    '</div>',
                    unsafe_allow_html=True,
                )
                _sell_trades = [t for t in _trades if t["action"] == "SELL"][-20:]
                _buy_trades  = {t["date"]: t for t in _trades if t["action"] == "BUY"}

                _rows_html = ""
                for t in _sell_trades:
                    _pnl_color = "#16c784" if (t["pnl"] or 0) >= 0 else "#ea3a44"
                    _pnl_str   = f"+{t['pnl']:.2f}%" if (t["pnl"] or 0) >= 0 else f"{t['pnl']:.2f}%"
                    _cum_str   = f"+{t['cum_return']:.1f}%" if (t["cum_return"] or 0) >= 0 else f"{t['cum_return']:.1f}%"
                    _cum_color = "#16c784" if (t["cum_return"] or 0) >= 0 else "#ea3a44"
                    _rows_html += (
                        f'<tr>'
                        f'<td style="padding:4px 12px;color:#b0bec5;font-size:12px">{t["date"]}</td>'
                        f'<td style="padding:4px 12px;color:#ea3a44;font-weight:700;font-size:12px">SELL</td>'
                        f'<td style="padding:4px 12px;color:#e8edf8;font-size:12px">${t["price"]:.2f}</td>'
                        f'<td style="padding:4px 12px;color:{_pnl_color};font-weight:700;font-size:12px">{_pnl_str}</td>'
                        f'<td style="padding:4px 12px;color:{_cum_color};font-size:12px">{_cum_str}</td>'
                        f'</tr>'
                    )

                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                    f'padding:12px 16px;overflow-x:auto">'
                    f'<table style="width:100%;border-collapse:collapse">'
                    f'<thead><tr>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 12px;'
                    f'font-family:\'IBM Plex Mono\',monospace">DATE</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 12px;'
                    f'font-family:\'IBM Plex Mono\',monospace">ACTION</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 12px;'
                    f'font-family:\'IBM Plex Mono\',monospace">PRICE</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 12px;'
                    f'font-family:\'IBM Plex Mono\',monospace">P&amp;L</th>'
                    f'<th style="text-align:left;font-size:10px;color:#556070;padding:2px 12px;'
                    f'font-family:\'IBM Plex Mono\',monospace">CUM RETURN</th>'
                    f'</tr></thead>'
                    f'<tbody>{_rows_html}</tbody>'
                    f'</table>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("No completed trades in this period.")


# ─── Page: Paper Portfolio ─────────────────────────────────────────────────────
elif page == "📝 Paper Portfolio":
    import html as _h
    _e = lambda v: _h.escape(str(v or ""), quote=False)

    st.title("📝 Paper Portfolio")
    _page_about("""**What:** virtual portfolios ($50K each) for practicing decisions with zero risk — with an AI coach reviewing every move.
**How:** trades execute at live prices; dividends auto-credit on ex-dates; Claude comments on each trade instantly (Haiku) and grades the whole portfolio on demand (Sonnet): what worked, what didn't, lessons. Multiple portfolios let you A/B different styles (Bull/Bear/Neutral).
**Use:** the journal is the point — after 20+ trades your patterns (cutting winners early, holding losers) become visible and fixable.""")
    st.caption("AI-managed demo portfolios — track trades, compare strategies, learn from market events.")

    # ── Load data ──────────────────────────────────────────────────────────────
    _ppdata = mod_pp.load_all()
    _pp_names = list(_ppdata["portfolios"].keys())

    # ── Portfolio Selector ─────────────────────────────────────────────────────
    _sel_col, _new_col, _del_col = st.columns([3, 1, 1])
    with _sel_col:
        _active_name = st.selectbox(
            "Active Portfolio",
            _pp_names,
            index=_pp_names.index(_ppdata["active"]) if _ppdata["active"] in _pp_names else 0,
            key="_pp_selector",
        )
        if _active_name != _ppdata["active"]:
            _ppdata["active"] = _active_name
            mod_pp.save_all(_ppdata)
            st.rerun()

    with _new_col:
        if st.button("➕ New Portfolio", width="stretch"):
            st.session_state["_pp_show_new"] = True

    with _del_col:
        if len(_pp_names) > 1:
            if st.button("🗑 Delete", width="stretch"):
                st.session_state["_pp_confirm_delete"] = True

    # Confirm delete
    if st.session_state.get("_pp_confirm_delete"):
        st.warning(f"Delete **{_active_name}**? This cannot be undone.")
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("Yes, delete", type="primary"):
                _ppdata = mod_pp.delete_portfolio(_ppdata, _active_name)
                st.session_state.pop("_pp_confirm_delete", None)
                st.rerun()
        with _c2:
            if st.button("Cancel"):
                st.session_state.pop("_pp_confirm_delete", None)
                st.rerun()

    # New portfolio form
    if st.session_state.get("_pp_show_new"):
        with st.expander("➕ Create New Portfolio", expanded=True):
            _nc1, _nc2 = st.columns(2)
            with _nc1:
                _new_name = st.text_input("Name (e.g. Tech Only 💻)", key="_pp_new_name")
                _new_sent = st.selectbox("Sentiment", ["risk-on", "neutral", "risk-off"], key="_pp_new_sent")
            with _nc2:
                _new_desc = st.text_input("Description", key="_pp_new_desc")
                _new_cap  = st.number_input("Initial Capital ($)", value=50000, step=5000, key="_pp_new_cap")
            if st.button("Create Portfolio", type="primary"):
                if _new_name.strip():
                    _ppdata = mod_pp.create_portfolio(_ppdata, _new_name, _new_sent, _new_desc, float(_new_cap))
                    st.session_state.pop("_pp_show_new", None)
                    st.rerun()
                else:
                    st.error("Please enter a portfolio name.")

    # ── Active portfolio ───────────────────────────────────────────────────────
    _pp = mod_pp.get_portfolio(_ppdata, _active_name)
    if not _pp:
        st.error("Portfolio not found.")
        st.stop()

    _pp_meta = _pp
    st.markdown(f"**{_e(_pp['sentiment'].upper())}** · {_e(_pp['description'])}")

    # ── Market regime suggestion ───────────────────────────────────────────────
    try:
        from modules.market_context import get_regime as _get_regime
        _regime_info = _get_regime()
        _regime_lbl  = _regime_info.get("regime", "")
        if _regime_lbl == "RISK-ON" and _active_name != "Bull 🟢":
            st.info("📊 Market regime is RISK-ON — consider switching to the Bull 🟢 portfolio.")
        elif _regime_lbl == "RISK-OFF" and _active_name != "Bear 🔴":
            st.warning("🛡 Market regime is RISK-OFF — consider switching to the Bear 🔴 portfolio.")
    except Exception:
        pass

    st.markdown("---")

    # ── Dividend accrual (auto — credits any ex-dates passed since entry) ──────
    _new_divs = mod_pp.accrue_dividends(_pp)
    if _new_divs:
        mod_pp.save_all(_ppdata)
        for _dv in _new_divs:
            st.success(f"💰 Dividend credited: **{_dv['symbol']}** — "
                       f"${_dv['dps']:.4f}/share × {_dv['shares']} = **${_dv['total']:.2f}**")

    # ── Valuation header ───────────────────────────────────────────────────────
    with st.spinner("Fetching live prices..."):
        _val = mod_pp.get_current_value(_pp)

    _pnl_color = "#16c784" if _val["pnl_usd"] >= 0 else "#ea3a44"
    _hc1, _hc2, _hc3, _hc4, _hc5 = st.columns(5)
    _hc1.metric("Total Value",     f"${_val['total']:,.0f}",
                help="Cash + market value of all holdings at live prices.")
    _hc2.metric("Cash",            f"${_val['cash']:,.0f}",
                help="Uninvested capital. Cash is a position too — it's dry powder for pullbacks and a drag in rallies.")
    _hc3.metric("Holdings Value",  f"${_val['holdings_value']:,.0f}")
    _hc4.metric("Total P&L $",     f"${_val['pnl_usd']:+,.0f}",
                help="Unrealized + realized profit vs initial capital, including collected dividends.")
    _hc5.metric("Total P&L %",     f"{_val['pnl_pct']:+.2f}%",
                help=mod_gloss.tip("alpha"))

    # ── Mini equity curve ──────────────────────────────────────────────────────
    _eq_curve = mod_pp.get_equity_curve(_pp)
    if not _eq_curve.empty and len(_eq_curve) >= 2:
        # Normalize vs SPY
        try:
            _spy_hist = get_price_history("SPY", period="2y")
            _spy_c    = _spy_hist["Close"].squeeze()
            _start    = _eq_curve.index[0]
            _spy_sub  = _spy_c[_spy_c.index >= _start]
            _spy_norm = _spy_sub / _spy_sub.iloc[0] * _pp.get("initial_capital", 50_000)
        except Exception:
            _spy_norm = None

        _fig_eq = go.Figure()
        _fig_eq.add_trace(go.Scatter(
            x=_eq_curve.index, y=_eq_curve["total_value"],
            mode="lines", name=_active_name,
            line=dict(color="#4da3ff", width=2),
        ))
        if _spy_norm is not None and not _spy_norm.empty:
            _fig_eq.add_trace(go.Scatter(
                x=_spy_norm.index, y=_spy_norm.values,
                mode="lines", name="SPY (normalized)",
                line=dict(color="#556070", width=1.5, dash="dot"),
            ))
        _fig_eq.update_layout(
            height=200, margin=dict(l=0, r=0, t=10, b=0),
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#cdd6f4"),
            xaxis=dict(showgrid=False, color="#556070"),
            yaxis=dict(showgrid=True, gridcolor="#1e2535", color="#556070",
                       tickprefix="$", tickformat=",.0f"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            hovermode="x unified",
        )
        st.plotly_chart(_fig_eq, width="stretch", config={"displayModeBar": False})

    # ── Add Trade Form ─────────────────────────────────────────────────────────
    st.subheader("Execute Trade")
    _tf1, _tf2, _tf3, _tf4, _tf5, _tf6 = st.columns([1.5, 1, 1, 1.5, 3, 1.5])

    with _tf1:
        _tr_sym    = st.text_input("Symbol", value="", placeholder="NVDA", key="_pp_sym").upper().strip()
    with _tf2:
        _tr_action = st.selectbox("Action", ["BUY", "SELL"], key="_pp_action")
    with _tf3:
        _tr_shares = st.number_input("Shares", min_value=1, value=10, step=1, key="_pp_shares")
    with _tf4:
        # Auto-fill price
        _auto_price = 0.0
        if _tr_sym:
            try:
                _inf = get_ticker_info(_tr_sym)
                _auto_price = float(_inf.get("currentPrice") or _inf.get("regularMarketPrice") or 0)
            except Exception:
                pass
        _tr_price = st.number_input("Price ($)", min_value=0.01, value=max(0.01, _auto_price),
                                     step=0.01, format="%.2f", key="_pp_price")
    with _tf5:
        _tr_reason = st.text_input("Why this trade?", placeholder="e.g. Breakout above 200MA on volume surge", key="_pp_reason")
    with _tf6:
        st.markdown("<div style='margin-top:28px'></div>", unsafe_allow_html=True)
        _tr_exec = st.button("▶ Execute", type="primary", width="stretch", key="_pp_exec")

    if _tr_exec and _tr_sym:
        _updated_pp, _err = mod_pp.add_trade(
            dict(_pp), _tr_sym, _tr_action, _tr_shares, _tr_price, _tr_reason
        )
        if _err:
            st.error(_err)
        else:
            # Build portfolio context summary for Claude
            _pctx = (
                f"Cash: ${_updated_pp['cash']:,.0f} | "
                f"Holdings: {list(_updated_pp['holdings'].keys())} | "
                f"Portfolio: {_active_name} ({_pp.get('sentiment','')})"
            )
            # Haiku comment (fast)
            _comment = mod_pp.claude_trade_comment(
                _tr_sym, _tr_action, _tr_shares, _tr_price, _tr_reason,
                _active_name, _pctx,
            )
            # Save trade + journal entry
            _ppdata["portfolios"][_active_name] = _updated_pp
            if _comment:
                _updated_pp.setdefault("claude_journal", []).append({
                    "date":   str(_date.today()),
                    "type":   "trade_comment",
                    "symbol": _tr_sym,
                    "action": _tr_action,
                    "text":   _comment,
                })
            mod_pp.save_all(_ppdata)

            if _comment:
                st.info(f"💬 **Claude on this trade:** {_comment}")
            st.success(f"{_tr_action} {_tr_shares} × {_tr_sym} @ ${_tr_price:.2f} executed.")
            st.rerun()

    # ── Current Holdings ───────────────────────────────────────────────────────
    st.subheader("Current Holdings")
    _review_col, _spacer = st.columns([2, 5])
    with _review_col:
        _do_review = st.button("💬 Get Full Portfolio Review", key="_pp_review_btn")

    if _val["positions"]:
        _rows_h = ""
        for _pos in _val["positions"]:
            _sym_v  = _e(_pos["symbol"])
            if _pos.get("price_stale"):
                _pnl_c, _pnl_s = "#556070", "⚠ stale"
            else:
                _pnl_c  = "#16c784" if _pos["pnl_pct"] >= 0 else "#ea3a44"
                _pnl_s  = f'+{_pos["pnl_pct"]:.1f}%' if _pos["pnl_pct"] >= 0 else f'{_pos["pnl_pct"]:.1f}%'
            try:
                _scored = mod_phealth.score_position(_pos["symbol"])
                _lbl    = _e(_scored.get("label", "—"))
                _lbl_c  = mod_phealth.SCORE_COLORS.get(_scored.get("label", ""), "#556070")
                _score_v = f'{_scored.get("score", 0):.1f}'
            except Exception:
                _lbl, _lbl_c, _score_v = "—", "#556070", "—"

            _rows_h += (
                f'<tr>'
                f'<td style="padding:6px 12px;font-weight:600">{_sym_v}</td>'
                f'<td style="padding:6px 12px;text-align:right">{_pos["shares"]}</td>'
                f'<td style="padding:6px 12px;text-align:right">${_pos["avg_cost"]:.2f}</td>'
                f'<td style="padding:6px 12px;text-align:right">${_pos["price"]:.2f}</td>'
                f'<td style="padding:6px 12px;text-align:right">${_pos["value"]:,.0f}</td>'
                f'<td style="padding:6px 12px;text-align:right;color:{_pnl_c}">'
                f'${_pos["pnl_usd"]:+,.0f}</td>'
                f'<td style="padding:6px 12px;text-align:right;color:{_pnl_c}">{_pnl_s}</td>'
                f'<td style="padding:6px 12px;text-align:right">{_score_v}</td>'
                f'<td style="padding:6px 12px;text-align:center">'
                f'<span style="background:{_lbl_c};color:#000;border-radius:4px;'
                f'padding:2px 8px;font-size:11px;font-weight:700">{_lbl}</span></td>'
                f'</tr>'
            )
        _th_style = "text-align:left;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
        _thr_style = "text-align:right;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
        st.markdown(
            f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 16px;overflow-x:auto">'
            f'<table style="width:100%;border-collapse:collapse">'
            f'<thead><tr>'
            f'<th style="{_th_style}">SYMBOL</th>'
            f'<th style="{_thr_style}">SHARES</th>'
            f'<th style="{_thr_style}">AVG COST</th>'
            f'<th style="{_thr_style}">CURRENT</th>'
            f'<th style="{_thr_style}">VALUE</th>'
            f'<th style="{_thr_style}">P&amp;L $</th>'
            f'<th style="{_thr_style}">P&amp;L %</th>'
            f'<th style="{_thr_style}">SCORE</th>'
            f'<th style="text-align:center;font-size:10px;color:#556070;padding:4px 12px;'
            f'font-family:\'IBM Plex Mono\',monospace">SIGNAL</th>'
            f'</tr></thead>'
            f'<tbody>{_rows_h}</tbody>'
            f'</table></div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No open positions. Execute a trade above to get started.")

    # Full review
    if _do_review:
        with st.spinner("Claude is reviewing your portfolio..."):
            _fp     = mod_pp.portfolio_fingerprint(_pp)
            _h_json = json.dumps(_val["positions"], indent=2, default=str)
            _c_json = json.dumps(mod_pp.get_closed_pnl(_pp)[-10:], indent=2, default=str)
            try:
                _regime_ctx = f"Regime: {_regime_info.get('regime','')} | VIX: {_regime_info['signals'].get('vix','')} | SPY 1M: {_regime_info['signals'].get('spy_r1m','')}"
            except Exception:
                _regime_ctx = "Market data unavailable"
            _review = mod_pp.claude_portfolio_review(
                _fp, _h_json, _c_json, _regime_ctx, _active_name, _pp.get("sentiment", "")
            )

        if "error" in _review:
            st.error(_review["error"])
        else:
            _grade    = _review.get("portfolio_grade", "?")
            _grade_c  = {"A": "#16c784", "B": "#a3e635", "C": "#f0b90b",
                          "D": "#f97316", "F": "#ea3a44"}.get(_grade, "#556070")
            st.markdown(
                f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px 24px;margin:12px 0">'
                f'<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px">'
                f'<span style="font-size:36px;font-weight:900;color:{_grade_c}">{_grade}</span>'
                f'<div style="font-size:14px;color:#cdd6f4;line-height:1.5">{_e(_review.get("overall_assessment",""))}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            _rv1, _rv2 = st.columns(2)
            with _rv1:
                if _review.get("what_worked"):
                    st.markdown("**✅ What Worked**")
                    for _w in _review["what_worked"]:
                        st.markdown(f"- {_w}")
                if _review.get("lessons"):
                    st.markdown("**🎓 Lessons**")
                    for _l in _review["lessons"]:
                        st.markdown(f"- {_l}")
            with _rv2:
                if _review.get("what_didnt"):
                    st.markdown("**❌ What Didn't Work**")
                    for _w in _review["what_didnt"]:
                        st.markdown(f"- {_w}")
                if _review.get("suggested_actions"):
                    st.markdown("**💡 Suggested Actions**")
                    for _a in _review["suggested_actions"]:
                        st.markdown(f"- {_a}")
            if _review.get("current_risks"):
                st.markdown("**⚠️ Current Risks**")
                st.markdown(" · ".join(_review["current_risks"]))
            if _review.get("market_impact_notes"):
                st.markdown("**🌍 Market Impact Notes**")
                for _n in _review["market_impact_notes"]:
                    st.markdown(f"- {_n}")

            # Save to journal
            _pp.setdefault("claude_journal", []).append({
                "date": str(_date.today()),
                "type": "weekly_review",
                "text": _review.get("overall_assessment", ""),
                "grade": _grade,
            })
            mod_pp.save_all(_ppdata)

    # ── Tabs ───────────────────────────────────────────────────────────────────
    st.markdown("---")
    _tab_j, _tab_perf, _tab_les, _tab_closed, _tab_cmp = st.tabs([
        "📋 Journal", "📈 Performance", "🎓 Lessons", "🔴 Closed Positions", "⚖️ Compare"
    ])

    # ── Journal ────────────────────────────────────────────────────────────────
    with _tab_j:
        _journal = list(reversed(_pp.get("claude_journal", [])))
        if _journal:
            for _jent in _journal:
                _jtype = _jent.get("type", "")
                _jdate = _jent.get("date", "")
                _jtext = _jent.get("text", "")
                if _jtype == "trade_comment":
                    _jsym = _jent.get("symbol", "")
                    _jact = _jent.get("action", "")
                    _badge_c = "#16c784" if _jact == "BUY" else "#ea3a44"
                    st.markdown(
                        f'<div style="background:var(--panel);border-left:3px solid {_badge_c};'
                        f'border-radius:6px;padding:10px 16px;margin-bottom:8px">'
                        f'<div style="font-size:11px;color:#556070;margin-bottom:4px">'
                        f'{_e(_jdate)} · '
                        f'<span style="color:{_badge_c};font-weight:700">{_e(_jact)}</span>'
                        f' {_e(_jsym)}</div>'
                        f'<div style="font-size:13px;color:#cdd6f4">{_e(_jtext)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif _jtype == "weekly_review":
                    _jgrade = _jent.get("grade", "?")
                    _jg_c   = {"A": "#16c784", "B": "#a3e635", "C": "#f0b90b",
                                "D": "#f97316", "F": "#ea3a44"}.get(_jgrade, "#556070")
                    st.markdown(
                        f'<div style="background:var(--panel);border-left:3px solid {_jg_c};'
                        f'border-radius:6px;padding:10px 16px;margin-bottom:8px">'
                        f'<div style="font-size:11px;color:#556070;margin-bottom:4px">'
                        f'{_e(_jdate)} · Full Review · Grade: '
                        f'<span style="color:{_jg_c};font-weight:700">{_e(_jgrade)}</span></div>'
                        f'<div style="font-size:13px;color:#cdd6f4">{_e(_jtext)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif _jtype == "dividend":
                    st.markdown(
                        f'<div style="background:var(--panel);border-left:3px solid #f0b90b;'
                        f'border-radius:6px;padding:10px 16px;margin-bottom:8px">'
                        f'<div style="font-size:11px;color:#556070;margin-bottom:4px">'
                        f'{_e(_jdate)} · 💰 Dividend · {_e(_jent.get("symbol",""))}</div>'
                        f'<div style="font-size:13px;color:#cdd6f4">{_e(_jtext)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
        else:
            st.info("No journal entries yet. Execute trades and get reviews to build your journal.")

    # ── Performance ────────────────────────────────────────────────────────────
    with _tab_perf:
        _stats = mod_pp.get_performance_stats(_pp)
        _total_div = mod_pp.total_dividends(_pp)
        _pc1, _pc2, _pc3, _pc4, _pc5, _pc6, _pc7 = st.columns(7)
        _pc1.metric("Win Rate",     f"{_stats['win_rate']:.0f}%",
                    help=mod_gloss.tip("win_rate"))
        _pc2.metric("Avg Win",      f"{_stats['avg_win']:+.1f}%",
                    help=mod_gloss.tip("expectancy"))
        _pc3.metric("Avg Loss",     f"{_stats['avg_loss']:+.1f}%",
                    help="Average % loss on losing trades. Keep it smaller than your average win — cut losers fast, let winners run.")
        _pc4.metric("Best Trade",   f"{_stats['best_trade']:+.1f}%")
        _pc5.metric("Worst Trade",  f"{_stats['worst_trade']:+.1f}%",
                    help="Your worst realized loss. If it dwarfs the average, the stop discipline failed once — one blowup can erase many good trades.")
        _pc6.metric("Realized P&L", f"${_stats['total_realized']:+,.0f}",
                    help="Profit locked in from CLOSED positions only. Paper gains can vanish; realized gains can't.")
        _pc7.metric("💰 Dividends", f"${_total_div:,.2f}",
                    help="Cash dividends credited automatically for ex-dates passed while holding. Reinvested dividends are a quiet compounding engine.")

        if not _eq_curve.empty and len(_eq_curve) >= 2:
            _fig_perf = go.Figure()
            _fig_perf.add_trace(go.Scatter(
                x=_eq_curve.index, y=_eq_curve["total_value"],
                mode="lines+markers", name=_active_name,
                line=dict(color="#4da3ff", width=2),
                fill="tozeroy", fillcolor="rgba(77,163,255,0.08)",
            ))
            _fig_perf.update_layout(
                height=280, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="#cdd6f4"),
                xaxis=dict(showgrid=False, color="#556070"),
                yaxis=dict(showgrid=True, gridcolor="#1e2535", color="#556070",
                           tickprefix="$", tickformat=",.0f"),
                hovermode="x unified",
            )
            st.plotly_chart(_fig_perf, width="stretch", config={"displayModeBar": False})

    # ── Lessons ────────────────────────────────────────────────────────────────
    with _tab_les:
        _lessons_entries = [j for j in _pp.get("claude_journal", []) if j.get("type") == "lesson"]
        if _lessons_entries:
            for _le in reversed(_lessons_entries):
                st.markdown(
                    f'<div style="background:var(--panel);border:1px solid var(--border);'
                    f'border-radius:8px;padding:12px 16px;margin-bottom:8px">'
                    f'<div style="font-size:11px;color:#556070;margin-bottom:4px">{_e(_le.get("date",""))}</div>'
                    f'<div style="font-size:13px;color:#cdd6f4">{_e(_le.get("text",""))}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("Lessons appear here when Claude identifies key takeaways during portfolio reviews.")

    # ── Closed Positions ───────────────────────────────────────────────────────
    with _tab_closed:
        _closed = mod_pp.get_closed_pnl(_pp)
        if _closed:
            _crow_h = ""
            for _cp in reversed(_closed):
                _cp_c = "#16c784" if _cp["pnl_pct"] >= 0 else "#ea3a44"
                _cp_pnl_s = f'+{_cp["pnl_pct"]:.1f}%' if _cp["pnl_pct"] >= 0 else f'{_cp["pnl_pct"]:.1f}%'
                try:
                    _dur = (
                        _date.fromisoformat(_cp["exit_date"]) -
                        _date.fromisoformat(_cp["entry_date"])
                    ).days
                    _dur_s = f"{_dur}d"
                except Exception:
                    _dur_s = "—"
                _crow_h += (
                    f'<tr>'
                    f'<td style="padding:6px 12px;font-weight:600">{_e(_cp["symbol"])}</td>'
                    f'<td style="padding:6px 12px">{_e(_cp["entry_date"])}</td>'
                    f'<td style="padding:6px 12px">{_e(_cp["exit_date"])}</td>'
                    f'<td style="padding:6px 12px;text-align:right">${_cp["entry_price"]:.2f}</td>'
                    f'<td style="padding:6px 12px;text-align:right">${_cp["exit_price"]:.2f}</td>'
                    f'<td style="padding:6px 12px;text-align:right;color:{_cp_c}">{_cp_pnl_s}</td>'
                    f'<td style="padding:6px 12px;text-align:right;color:{_cp_c}">${_cp["pnl_usd"]:+,.0f}</td>'
                    f'<td style="padding:6px 12px;text-align:right">{_dur_s}</td>'
                    f'</tr>'
                )
            _th = "text-align:left;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
            _tr = "text-align:right;font-size:10px;color:#556070;padding:4px 12px;font-family:'IBM Plex Mono',monospace"
            st.markdown(
                f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 16px;overflow-x:auto">'
                f'<table style="width:100%;border-collapse:collapse">'
                f'<thead><tr>'
                f'<th style="{_th}">SYMBOL</th>'
                f'<th style="{_th}">ENTRY</th>'
                f'<th style="{_th}">EXIT</th>'
                f'<th style="{_tr}">ENTRY $</th>'
                f'<th style="{_tr}">EXIT $</th>'
                f'<th style="{_tr}">P&amp;L %</th>'
                f'<th style="{_tr}">P&amp;L $</th>'
                f'<th style="{_tr}">DAYS</th>'
                f'</tr></thead>'
                f'<tbody>{_crow_h}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("No closed positions yet.")

    # ── Compare Portfolios ─────────────────────────────────────────────────────
    with _tab_cmp:
        st.subheader("Portfolio Comparison")
        _cmp_df = mod_pp.compare_portfolios(_ppdata)
        if not _cmp_df.empty:
            # Normalized equity curves
            _fig_cmp = go.Figure()
            _cmp_colors = ["#4da3ff", "#ea3a44", "#f0b90b", "#16c784", "#a855f7"]
            for _ci, (_cmp_name, _cmp_pp) in enumerate(_ppdata["portfolios"].items()):
                _ceq = mod_pp.get_equity_curve(_cmp_pp)
                if _ceq.empty or len(_ceq) < 2:
                    continue
                _cinit = _cmp_pp.get("initial_capital", 50_000)
                _cnorm = (_ceq["total_value"] / _cinit - 1) * 100
                _fig_cmp.add_trace(go.Scatter(
                    x=_ceq.index, y=_cnorm,
                    mode="lines", name=_cmp_name,
                    line=dict(color=_cmp_colors[_ci % len(_cmp_colors)], width=2),
                ))
            _fig_cmp.add_hline(y=0, line=dict(color="#556070", dash="dot", width=1))
            _fig_cmp.update_layout(
                height=250, margin=dict(l=0, r=0, t=10, b=0),
                plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                font=dict(color="#cdd6f4"),
                xaxis=dict(showgrid=False, color="#556070"),
                yaxis=dict(showgrid=True, gridcolor="#1e2535", color="#556070",
                           ticksuffix="%"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                hovermode="x unified",
            )
            st.plotly_chart(_fig_cmp, width="stretch", config={"displayModeBar": False})

            # Summary table
            _cmp_display = _cmp_df.copy()
            _cmp_display["Total Return"] = _cmp_display["Total Return"].map(lambda x: f"{x:+.2f}%")
            _cmp_display["Total P&L $"]  = _cmp_display["Total P&L $"].map(lambda x: f"${x:+,.0f}")
            _cmp_display["Win Rate"]     = _cmp_display["Win Rate"].map(lambda x: f"{x:.0f}%")
            _cmp_display["Best Trade %"] = _cmp_display["Best Trade %"].map(lambda x: f"{x:+.1f}%")
            _cmp_display["Sharpe"]       = _cmp_display["Sharpe"].map(lambda x: f"{x:.2f}")
            st.dataframe(
                _cmp_display[["Portfolio", "Sentiment", "Total Return", "Total P&L $",
                               "Holdings", "Closed Trades", "Win Rate", "Best Trade %", "Sharpe"]],
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Add trades to multiple portfolios to enable comparison.")


# ─── Page: Alpha Lab ────────────────────────────────────────────────────────────
elif page == "🧠 Alpha Lab":
    st.title("🧠 Alpha Lab")
    _page_about("""**What:** the consensus of every mechanical model in Fund Models, scanned across a universe and ranked — plus every framework/risk tool/quant model RN SB's own notes name that wasn't in the app yet (guru screens, a trading-psychology bias check, options pricing, portfolio optimization), and an honest look at whether any of this actually produces alpha.
**How:** the Consensus Scanner runs `fund_models.combined_verdict()` (17 guru checklists, equal-weighted) across a ticker list. Validation splits the honest cases (price-only technical signals, walk-forward backtested without look-ahead bias) from the live-evidence cases (fundamentals-based scores, tracked forward via score history).
**Use:** scan for consensus leaders before deep-diving in Analyze; run the bias check before you pull the trigger; price options against real market chains; build an efficient frontier for a basket; use Validation to see whether the scoring actually beats the index out of sample.""")

    _tab_scan, _tab_new, _tab_psych, _tab_opt, _tab_popt, _tab_val, _tab_src = st.tabs(
        ["📊 Consensus Scanner", "🧩 New Frameworks", "🧭 Trading Psychology",
         "📐 Options Lab", "🌐 Portfolio Optimizer", "🔬 Validation", "📚 Sources & Principles"]
    )

    # ── Tab 1: Consensus Scanner ─────────────────────────────────────────────
    with _tab_scan:
        st.subheader("Consensus Scanner — rank a universe by the combined guru read")
        _al_wl = _load_json(Path(__file__).parent / ".watchlist.json", default={}).get("symbols", "")
        _al_default = _al_wl.strip() or ", ".join(WEEKLY_UNIVERSE[:20])
        _al_universe_input = st.text_area(
            "Tickers to scan (comma-separated)", value=_al_default, height=70,
            help="Defaults to your Watchlist if set, otherwise the first 20 Weekly Picks universe tickers.",
        )
        _al_syms_raw = [s.strip().upper() for s in _al_universe_input.split(",") if s.strip()]
        _al_syms = list(dict.fromkeys(_al_syms_raw))[:40]
        if len(set(_al_syms_raw)) > 40:
            st.caption("Capped at 40 tickers per scan to keep it fast.")

        if st.button("🔍 Scan Consensus", type="primary", key="_al_scan_btn"):
            _al_rows = []
            _al_prog = st.progress(0)
            for _ai, _asym in enumerate(_al_syms):
                _al_prog.progress((_ai + 1) / len(_al_syms), text=f"Scoring {_asym}…")
                try:
                    _al_fm = mod_fm.analyze_stock(_asym)
                    if _al_fm.get("error"):
                        continue
                    _al_cv = mod_fm.combined_verdict(_al_fm)
                    if _al_cv["score"] is None:
                        continue
                    _al_rows.append({
                        "Ticker": _asym, "Consensus": _al_cv["score"], "Read": _al_cv["label"],
                        "Bullish": _al_cv["n_bullish"], "Neutral": _al_cv["n_neutral"],
                        "Bearish": _al_cv["n_bearish"], "Models": _al_cv["n_total"],
                    })
                except Exception:
                    continue
            _al_prog.empty()
            st.session_state["_al_scan_df"] = pd.DataFrame(_al_rows)

        if "_al_scan_df" in st.session_state and not st.session_state["_al_scan_df"].empty:
            _al_df = st.session_state["_al_scan_df"].sort_values("Consensus", ascending=False)
            st.dataframe(_al_df, width="stretch", hide_index=True)
            st.caption("Open a ticker in Analyze → Fund Models for the full per-model breakdown.")

    # ── Tab 2: New Frameworks ─────────────────────────────────────────────────
    with _tab_new:
        st.subheader("New Frameworks — models RN SB names that weren't in the app yet")
        _al_sym2 = st.text_input("Ticker", value="AAPL", key="_al_sym2").strip().upper()

        if _al_sym2:
            _al_fm2 = mod_fm.analyze_stock(_al_sym2)
            if _al_fm2.get("error"):
                st.warning(_al_fm2["error"])
            else:
                _al_c1, _al_c2 = st.columns(2)
                with _al_c1:
                    st.markdown("#### O'Shaughnessy Cornerstone Growth",
                               help=mod_gloss.tip("oshaughnessy_method"))
                    _osh = _al_fm2["oshaughnessy"]
                    for _lbl, _ok, _det in _osh["checks"]:
                        st.markdown(f"{'✅' if _ok else '❌'} {_lbl} — *{_det}*")
                    st.caption(f"{_osh['passed']}/{_osh['total']} — {_osh['verdict']}")
                with _al_c2:
                    st.markdown("#### Kirkpatrick Relative Strength",
                               help=mod_gloss.tip("kirkpatrick_method"))
                    _kp = _al_fm2["kirkpatrick"]
                    if _kp.get("score") is not None:
                        st.metric("RS Score", f"{_kp['score']}/10")
                        st.caption(f"3M: {_kp['r3m']:+.1f}pp · 6M: {_kp['r6m']:+.1f}pp · "
                                  f"12M: {_kp['r12m']:+.1f}pp vs SPY")
                    st.caption(_kp["verdict"])

                st.markdown("---")
                st.markdown("#### Risk of Ruin", help=mod_gloss.tip("risk_of_ruin_method"))
                _ror_c1, _ror_c2, _ror_c3, _ror_c4 = st.columns(4)
                with _ror_c1:
                    _ror_wr = st.slider("Win rate", 0.10, 0.90, 0.45, 0.05, key="_al_ror_wr")
                with _ror_c2:
                    _ror_win = st.number_input("Avg win %", value=8.0, step=0.5, key="_al_ror_win")
                with _ror_c3:
                    _ror_loss = st.number_input("Avg loss %", value=4.0, step=0.5, key="_al_ror_loss")
                with _ror_c4:
                    _ror_risk = st.slider("Risk per trade %", 0.25, 5.0, 1.0, 0.25, key="_al_ror_risk")
                _ror = mod_rt.risk_of_ruin(_ror_wr, _ror_win, _ror_loss, _ror_risk)
                if _ror.get("error"):
                    st.info(_ror["error"])
                else:
                    st.markdown(
                        f"Risk of Ruin: **{_ror['payoff_ror_pct']}%** "
                        f"(even-money formula for comparison: {_ror['classic_ror_pct']}%) · "
                        f"Expectancy: **{_ror['expectancy_r']}R**"
                    )
                    st.caption(_ror["verdict"])

                st.markdown("---")
                st.markdown("#### Murphy's 20-Point Money Management Checklist",
                           help=mod_gloss.tip("murphy_method"))
                _murphy_answers = {}
                _mc1, _mc2 = st.columns(2)
                for _mi, _mitem in enumerate(mod_rt.MURPHY_CHECKLIST):
                    with (_mc1 if _mi % 2 == 0 else _mc2):
                        _murphy_answers[_mi] = st.checkbox(_mitem, key=f"_al_murphy_{_mi}")
                _murphy_res = mod_rt.murphy_checklist(_murphy_answers)
                if _murphy_res["total"] > 0:
                    st.markdown(f"**{_murphy_res['passed']}/{_murphy_res['total']} "
                               f"({_murphy_res['pct']:.0f}%)** — {_murphy_res['verdict']}")

    # ── Tab 3: Trading Psychology ─────────────────────────────────────────────
    with _tab_psych:
        st.subheader("Trading Psychology — a bias self-check, not a model")
        st.caption("Distilled from RN SB's behavioral-finance notes into a Murphy-style "
                  "yes/no checklist. Every 'no' flags a specific bias pattern — answer it "
                  "honestly before you place the trade, not after.", help=mod_gloss.tip("trading_psychology_method"))

        _psych_answers = {}
        _pc1, _pc2 = st.columns(2)
        for _pi, _pitem in enumerate(mod_psych.BIAS_CHECKLIST):
            with (_pc1 if _pi % 2 == 0 else _pc2):
                _psych_answers[_pitem["key"]] = st.checkbox(
                    _pitem["q"], key=f"_al_psych_{_pitem['key']}", help=_pitem["bias"])

        _psych_res = mod_psych.bias_checklist(_psych_answers)
        if _psych_res["total"] > 0:
            st.markdown(f"**{_psych_res['passed']}/{_psych_res['total']} "
                       f"({_psych_res['pct']:.0f}%)** — {_psych_res['verdict']}")
            if _psych_res["flags"]:
                st.warning("Active flags: " + "; ".join(_psych_res["flags"]))

    # ── Tab 4: Options Lab ────────────────────────────────────────────────────
    with _tab_opt:
        st.subheader("Options Lab — pricing models checked against real market chains")
        st.caption("Pulls the actual option chain (yfinance) so theoretical prices are "
                  "compared to what the market is really quoting — not synthetic inputs.")

        _opt_sym = st.text_input("Ticker", value="AAPL", key="_al_opt_sym").strip().upper()
        _opt_expiries = mod_opt.get_expiries(_opt_sym) if _opt_sym else []

        if not _opt_expiries:
            st.info("No option chain found for this ticker (or it has none listed).")
        else:
            _oc1, _oc2 = st.columns(2)
            with _oc1:
                _opt_expiry = st.selectbox("Expiry", _opt_expiries, key="_al_opt_expiry")
            with _oc2:
                _opt_kind = st.radio("Type", ["call", "put"], horizontal=True, key="_al_opt_kind")

            _opt_info = get_ticker_info(_opt_sym)
            _opt_S = _opt_info.get("currentPrice") or _opt_info.get("regularMarketPrice")
            _opt_chain = mod_opt.get_chain(_opt_sym, _opt_expiry)

            if _opt_chain.get("error") or not _opt_S:
                st.warning(_opt_chain.get("error") or "No current price available.")
            else:
                _opt_df = _opt_chain["calls"] if _opt_kind == "call" else _opt_chain["puts"]
                if _opt_df is None or _opt_df.empty:
                    st.info("No contracts in this chain.")
                else:
                    _strikes = _opt_df["strike"].tolist()
                    _atm_idx = int(np.argmin([abs(k - _opt_S) for k in _strikes]))
                    _opt_K = st.selectbox("Strike", _strikes, index=_atm_idx, key="_al_opt_strike")

                    _row = _opt_df[_opt_df["strike"] == _opt_K].iloc[0]
                    _mkt_price = float(_row.get("lastPrice") or 0)
                    _mkt_iv = float(_row.get("impliedVolatility") or 0)

                    from datetime import date as _dt_date
                    _days_to_exp = (pd.Timestamp(_opt_expiry).date() - _dt_date.today()).days
                    _opt_T = max(_days_to_exp, 1) / 365

                    _r_c1, _r_c2 = st.columns(2)
                    with _r_c1:
                        _opt_r = st.slider("Risk-free rate %", 0.0, 8.0, mod_opt.RISK_FREE_RATE * 100, 0.25,
                                          key="_al_opt_r") / 100
                    with _r_c2:
                        _hist_vol = mod_opt.historical_vol(_opt_sym)
                        st.caption(f"Realized vol (60d, annualized): "
                                  f"{_hist_vol*100:.1f}%" if _hist_vol else "Realized vol unavailable")

                    st.markdown(f"**Market:** last price ${_mkt_price:.2f} · "
                               f"yfinance implied vol {_mkt_iv*100:.1f}% · "
                               f"{_days_to_exp}d to expiry")

                    _bsm_at_iv = mod_opt.bsm_price(_opt_S, _opt_K, _opt_T, _opt_r, _mkt_iv, _opt_kind) if _mkt_iv else None
                    _bsm_at_hist = mod_opt.bsm_price(_opt_S, _opt_K, _opt_T, _opt_r, _hist_vol, _opt_kind) if _hist_vol else None
                    _binom_euro = mod_opt.binomial_price(_opt_S, _opt_K, _opt_T, _opt_r, _mkt_iv or _hist_vol or 0.3,
                                                         200, _opt_kind, american=False)
                    _binom_amer = mod_opt.binomial_price(_opt_S, _opt_K, _opt_T, _opt_r, _mkt_iv or _hist_vol or 0.3,
                                                         200, _opt_kind, american=True)
                    _mc = mod_opt.monte_carlo_price(_opt_S, _opt_K, _opt_T, _opt_r, _mkt_iv or _hist_vol or 0.3, _opt_kind)
                    _solved_iv = mod_opt.implied_vol(_mkt_price, _opt_S, _opt_K, _opt_T, _opt_r, _opt_kind)

                    _m1, _m2, _m3, _m4 = st.columns(4)
                    with _m1:
                        st.metric("BSM @ market IV", f"${_bsm_at_iv:.2f}" if _bsm_at_iv else "—",
                                 help=mod_gloss.tip("bsm_method"))
                    with _m2:
                        st.metric("BSM @ realized vol", f"${_bsm_at_hist:.2f}" if _bsm_at_hist else "—",
                                 help="If this differs a lot from market price, options are pricing "
                                      "meaningfully more/less future turbulence than recent history showed.")
                    with _m3:
                        st.metric("Binomial (American)", f"${_binom_amer:.2f}", help=mod_gloss.tip("binomial_method"))
                    with _m4:
                        st.metric("Monte Carlo", f"${_mc['price']:.2f} ± {_mc['std_error']:.2f}",
                                 help=mod_gloss.tip("monte_carlo_options_method"))

                    if _solved_iv:
                        st.caption(f"Solved implied vol from market price: {_solved_iv*100:.1f}% "
                                  f"(yfinance reports {_mkt_iv*100:.1f}%) — small gaps are normal "
                                  f"(stale quotes, dividend/rate assumptions).",
                                  help=mod_gloss.tip("implied_vol_method"))
                    if _hist_vol and _mkt_iv:
                        _vrp = (_mkt_iv - _hist_vol) * 100
                        st.caption(f"Volatility risk premium (implied − realized): {_vrp:+.1f}pp — "
                                  f"{'options pricing in MORE turbulence than realized' if _vrp > 0 else 'options pricing in LESS turbulence than realized'}.")

                    _greeks = mod_opt.bsm_greeks(_opt_S, _opt_K, _opt_T, _opt_r, _mkt_iv or _hist_vol or 0.3, _opt_kind)
                    st.markdown("**Greeks** (BSM, at market/realized vol): " +
                               " · ".join(f"{k}: {v}" for k, v in _greeks.items() if v is not None))

    # ── Tab 5: Portfolio Optimizer ────────────────────────────────────────────
    with _tab_popt:
        st.subheader("Portfolio Optimizer — Efficient Frontier & PCA")

        _popt_tp_data = mod_tp.load_all().get("portfolios", {})
        _popt_wl_syms = [s.strip().upper() for s in
                        _load_json(Path(__file__).parent / ".watchlist.json", default={})
                        .get("symbols", "").split(",") if s.strip()]

        _popt_source_opts = ["✏️ Custom (type below)"]
        _popt_source_opts += [f"🎯 Tracked: {name}" for name in _popt_tp_data.keys()]
        if _popt_wl_syms:
            _popt_source_opts.append("👁 Watchlist")
        _popt_source = st.selectbox("Load holdings from", _popt_source_opts, key="_al_popt_source")

        _popt_current_weights = None
        if _popt_source.startswith("🎯 Tracked: "):
            _popt_tp_name = _popt_source[len("🎯 Tracked: "):]
            _popt_positions = _popt_tp_data[_popt_tp_name]["positions"]
            _popt_syms = tuple(_popt_positions.keys())
            _popt_current_weights = {s: p["target_weight"] for s, p in _popt_positions.items()}
            st.caption(f"Loaded {len(_popt_syms)} positions from Tracker portfolio '{_popt_tp_name}'.")
        elif _popt_source == "👁 Watchlist":
            _popt_syms = tuple(dict.fromkeys(_popt_wl_syms))
            st.caption(f"Loaded {len(_popt_syms)} tickers from your Watchlist.")
        else:
            _popt_syms_input = st.text_input(
                "Tickers (comma-separated, 3+)", value="AAPL, MSFT, GOOGL, AMZN, NVDA",
                key="_al_popt_syms")
            _popt_syms = tuple(dict.fromkeys(
                s.strip().upper() for s in _popt_syms_input.split(",") if s.strip()
            ))

        if st.button("📈 Build Frontier & Run PCA", type="primary", key="_al_popt_run"):
            st.session_state["_al_ef"] = mod_popt.efficient_frontier(_popt_syms)
            st.session_state["_al_pca"] = mod_popt.pca_factors(_popt_syms)
            st.session_state["_al_popt_current_weights"] = _popt_current_weights

        _ef = st.session_state.get("_al_ef")
        if _ef:
            if _ef.get("error"):
                st.error(_ef["error"])
            else:
                st.markdown("#### Efficient Frontier", help=mod_gloss.tip("efficient_frontier_method"))
                _fig_ef = go.Figure()
                _fig_ef.add_trace(go.Scatter(
                    x=_ef["cloud"]["vol"] * 100, y=_ef["cloud"]["return"] * 100,
                    mode="markers", marker=dict(size=4, color=_ef["cloud"]["sharpe"],
                                                colorscale="Viridis", showscale=True,
                                                colorbar=dict(title="Sharpe")),
                    name="Random portfolios",
                ))
                if _ef["max_sharpe"]:
                    _fig_ef.add_trace(go.Scatter(
                        x=[_ef["max_sharpe"]["vol_pct"]], y=[_ef["max_sharpe"]["return_pct"]],
                        mode="markers", marker=dict(size=14, color="red", symbol="star"),
                        name="Max Sharpe"))
                if _ef["min_vol"]:
                    _fig_ef.add_trace(go.Scatter(
                        x=[_ef["min_vol"]["vol_pct"]], y=[_ef["min_vol"]["return_pct"]],
                        mode="markers", marker=dict(size=14, color="lime", symbol="star"),
                        name="Min Vol"))
                _fig_ef.update_layout(
                    xaxis_title="Annualized Volatility %", yaxis_title="Annualized Return %",
                    paper_bgcolor="#0e1117", plot_bgcolor="#0e1117", height=420,
                    font=dict(color="#cdd6f4"), margin=dict(l=40, r=40, t=20, b=40),
                )
                st.plotly_chart(_fig_ef, width="stretch", config={"displayModeBar": False})

                _efc1, _efc2 = st.columns(2)
                with _efc1:
                    if _ef["max_sharpe"]:
                        st.markdown(f"**Max Sharpe** — Return {_ef['max_sharpe']['return_pct']}% · "
                                   f"Vol {_ef['max_sharpe']['vol_pct']}% · Sharpe {_ef['max_sharpe']['sharpe']}")
                        st.dataframe(pd.DataFrame(_ef["max_sharpe"]["weights"].items(),
                                                  columns=["Ticker", "Weight %"]),
                                    width="stretch", hide_index=True)
                with _efc2:
                    if _ef["min_vol"]:
                        st.markdown(f"**Min Vol** — Return {_ef['min_vol']['return_pct']}% · "
                                   f"Vol {_ef['min_vol']['vol_pct']}% · Sharpe {_ef['min_vol']['sharpe']}")
                        st.dataframe(pd.DataFrame(_ef["min_vol"]["weights"].items(),
                                                  columns=["Ticker", "Weight %"]),
                                    width="stretch", hide_index=True)

                _popt_cur = st.session_state.get("_al_popt_current_weights")
                if _popt_cur:
                    st.markdown("---")
                    st.markdown("#### Your Current Weights vs. Optimal")
                    _cmp_rows = []
                    for _sym in _ef["symbols"]:
                        _cmp_rows.append({
                            "Ticker":     _sym,
                            "Current %":  _popt_cur.get(_sym, 0.0),
                            "Max Sharpe %": (_ef["max_sharpe"]["weights"].get(_sym, 0.0)
                                            if _ef["max_sharpe"] else None),
                            "Min Vol %":  (_ef["min_vol"]["weights"].get(_sym, 0.0)
                                          if _ef["min_vol"] else None),
                        })
                    st.dataframe(pd.DataFrame(_cmp_rows), width="stretch", hide_index=True)
                    st.caption("How far your actual allocation sits from the mean-variance-optimal "
                              "mix — a large gap isn't automatically wrong (conviction/taxes/thesis "
                              "matter too), but it's worth knowing it exists.")

        _pca = st.session_state.get("_al_pca")
        if _pca:
            st.markdown("---")
            if _pca.get("error"):
                st.error(_pca["error"])
            else:
                st.markdown("#### PCA Factor Decomposition", help=mod_gloss.tip("pca_method"))
                st.caption("Loading sign is arbitrary (SVD sign ambiguity) — only magnitude matters.")
                st.markdown(f"**PC1 explains {_pca['market_factor_pct']}% of variance** "
                           f"— {'a HIGH shared-market bet' if _pca['market_factor_pct'] > 50 else 'meaningful real diversification exists'}.")
                st.caption(f"Explained variance by component: "
                          f"{', '.join(f'PC{i+1}: {p}%' for i, p in enumerate(_pca['explained_pct']))}")
                st.markdown("**Most PC1-exposed (highest shared-factor bet):**")
                st.dataframe(pd.DataFrame(_pca["top_pc1_exposure"].items(),
                                          columns=["Ticker", "|PC1 loading|"]),
                            width="stretch", hide_index=True)
                st.markdown("**Least PC1-exposed (best diversifiers in this set):**")
                st.dataframe(pd.DataFrame(_pca["bottom_pc1_exposure"].items(),
                                          columns=["Ticker", "|PC1 loading|"]),
                            width="stretch", hide_index=True)

    # ── Tab 6: Validation ─────────────────────────────────────────────────────
    with _tab_val:
        st.subheader("Validation — does any of this actually produce alpha?")
        st.warning(
            "⚠️ **Honest limitation:** fundamentals-based checklists (Buffett, Piotroski, Graham, ...) "
            "can't be walk-forward backtested — yfinance only exposes CURRENT fundamentals, not "
            "point-in-time history, so any such backtest would bake in look-ahead bias. The two "
            "sections below split the evidence into what CAN be tested honestly (price-only "
            "technical signals) and what's tracked live going forward instead."
        )

        st.markdown("#### Walk-Forward Backtest — technical signals only")
        _wf_c1, _wf_c2, _wf_c3 = st.columns(3)
        with _wf_c1:
            _wf_sym = st.text_input("Ticker", value="SPY", key="_al_wf_sym").strip().upper()
        with _wf_c2:
            _wf_strat_opts = list(mod_bt.STRATEGIES.keys())
            _wf_strat = st.selectbox("Strategy", _wf_strat_opts,
                                     index=_wf_strat_opts.index("Technical Consensus"),
                                     key="_al_wf_strat")
        with _wf_c3:
            _wf_period = st.selectbox("History", ["2y", "3y", "5y"], index=1, key="_al_wf_period")

        if st.button("▶️ Run Walk-Forward Test", type="primary", key="_al_wf_run"):
            st.session_state["_al_wf_result"] = mod_bt.run_backtest_walkforward(
                _wf_sym, _wf_strat, period=_wf_period)

        _wf = st.session_state.get("_al_wf_result")
        if _wf:
            if _wf.get("error"):
                st.error(_wf["error"])
            else:
                st.caption(f"Chosen params (fit on train window only): `{_wf['chosen_params']}`")
                _wfc1, _wfc2 = st.columns(2)
                with _wfc1:
                    st.markdown(f"**In-Sample** ({_wf['train_period'][0]} → {_wf['train_period'][1]})")
                    st.metric("Sharpe", f"{_wf['in_sample']['sharpe']:.2f}")
                    st.metric("Total Return", f"{_wf['in_sample']['total_return']*100:+.1f}%")
                    st.metric("Max Drawdown", f"{_wf['in_sample']['max_drawdown']*100:.1f}%")
                with _wfc2:
                    st.markdown(f"**Out-of-Sample** ({_wf['test_period'][0]} → {_wf['test_period'][1]})")
                    st.metric("Sharpe", f"{_wf['out_of_sample']['sharpe']:.2f}")
                    st.metric("Total Return", f"{_wf['out_of_sample']['total_return']*100:+.1f}%")
                    st.metric("Max Drawdown", f"{_wf['out_of_sample']['max_drawdown']*100:.1f}%")
                st.info(_wf["verdict"])

        st.markdown("---")
        st.markdown("#### Live Score Validation — composite score vs. actual forward return")
        st.caption("Reads .score_history.json (recorded automatically every time you open Analyze). "
                  "Accumulates over time — thin at first, more meaningful after months of use.")
        _sv_c1, _sv_c2 = st.columns(2)
        with _sv_c1:
            _sv_horizon = st.select_slider("Forward horizon (days)", [7, 14, 30, 60, 90], value=30,
                                           key="_al_sv_horizon")
        with _sv_c2:
            _sv_min_age = st.select_slider("Minimum score age (days)", [7, 14, 30, 60], value=30,
                                           key="_al_sv_min_age")
        _sv = mod_sv.bucket_analysis(horizon_days=_sv_horizon, min_age_days=_sv_min_age)
        if _sv["n_total"] == 0:
            _sv_note = f" (oldest record: {_sv['oldest_record']})" if _sv["oldest_record"] else ""
            st.info(f"No forward-return-eligible scores yet{_sv_note}. Keep using Analyze/Weekly "
                   f"Picks — this fills in over time.")
        else:
            st.dataframe(pd.DataFrame(_sv["buckets"]), width="stretch", hide_index=True)
            st.caption(f"{_sv['n_total']} samples, {_sv_horizon}-day forward horizon, "
                      f"oldest record {_sv['oldest_record']}.")

    # ── Tab 7: Sources & Principles ───────────────────────────────────────────
    with _tab_src:
        st.subheader("Sources & Principles — where each model comes from")
        st.caption("Every mechanical model in Fund Models / Alpha Lab traces back to a named "
                  "investor, book, or academic paper — not an arbitrary rule. Use this to go "
                  "back and study the source material in full.")
        _src_rows = [
            {"Framework": "Minervini Trend Template", "Source": "Mark Minervini — Trade Like a Stock Market Wizard"},
            {"Framework": "Turtle / Donchian Breakout", "Source": "Richard Dennis's Turtles — Curtis Faith, Way of the Turtle"},
            {"Framework": "Managed-Futures Trend Following", "Source": "AQR/Man AHL-style trend following; RN SB Markets & Trading"},
            {"Framework": "Druckenmiller Playbook", "Source": "Stanley Druckenmiller interviews/letters"},
            {"Framework": "Kelly Sizing", "Source": "J.L. Kelly (1956); Ed Thorp practice — RN SB Risk-of-Ruin/Kelly cluster"},
            {"Framework": "Factor Profile", "Source": "Fama-French factors; AQR factor-investing research"},
            {"Framework": "Risk Parity", "Source": "Ray Dalio / Bridgewater All Weather"},
            {"Framework": "Buffett Checklist", "Source": "Warren Buffett shareholder letters"},
            {"Framework": "Munger Filter", "Source": "Charlie Munger — inversion / Poor Charlie's Almanack"},
            {"Framework": "Lynch Check", "Source": "Peter Lynch — One Up on Wall Street"},
            {"Framework": "Graham Number", "Source": "Benjamin Graham — The Intelligent Investor"},
            {"Framework": "Greenblatt Magic Formula", "Source": "Joel Greenblatt — The Little Book That Beats the Market"},
            {"Framework": "CANSLIM", "Source": "William O'Neil — How to Make Money in Stocks"},
            {"Framework": "Bogle Test", "Source": "John Bogle — Vanguard founder, passive-investing case"},
            {"Framework": "Piotroski F-Score", "Source": "Joseph Piotroski (2000), University of Chicago"},
            {"Framework": "Altman Z-Score", "Source": "Edward Altman (1968), NYU"},
            {"Framework": "Templeton", "Source": "Sir John Templeton — maximum pessimism"},
            {"Framework": "O'Shaughnessy Cornerstone Growth", "Source": "James O'Shaughnessy — What Works on Wall Street; RN SB relative-strength-systems note"},
            {"Framework": "Kirkpatrick Relative Strength", "Source": "Kirkpatrick & Dahlquist — Technical Analysis: The Complete Resource; RN SB same note"},
            {"Framework": "Risk of Ruin", "Source": "Classic gambling/trading theory; Ralph Vince payoff-adjusted variant — RN SB Technical Analysis & Trading Systems"},
            {"Framework": "Murphy Money Management", "Source": "John Murphy — Technical Analysis of the Financial Markets; RN SB same folder"},
            {"Framework": "Calmar Ratio / Ulcer Index", "Source": "Calmar (1991); Peter Martin's Ulcer Index (1987) — RN SB performance-metrics cluster"},
            {"Framework": "Walk-Forward Validation", "Source": "RN SB — Trading System Design Checklist / Ten Performance Criteria for Judging a Backtest"},
            {"Framework": "Trading Psychology Bias Check", "Source": "Andrew Lo — Adaptive Markets; Malkiel — A Random Walk Down Wall Street; RN SB Efficient Markets vs Behavioral & Adaptive Finance"},
            {"Framework": "Black-Scholes-Merton", "Source": "Black, Scholes, Merton (1973); RN SB Python for Finance - Quantitative Analytics (Hilpisch)"},
            {"Framework": "Binomial (CRR) Option Pricing", "Source": "Cox, Ross, Rubinstein (1979); RN SB Python for Finance - Quantitative Analytics"},
            {"Framework": "Monte Carlo Option Pricing", "Source": "RN SB Python for Finance - Quantitative Analytics (antithetic variates)"},
            {"Framework": "Implied Volatility Solver", "Source": "Standard options-market inversion of BSM via Brent's method"},
            {"Framework": "Efficient Frontier (Markowitz)", "Source": "Markowitz (1952); RN SB Python for Finance - Quantitative Analytics"},
            {"Framework": "PCA Factor Decomposition", "Source": "RN SB Python for Finance - Quantitative Analytics"},
        ]
        st.dataframe(pd.DataFrame(_src_rows), width="stretch", hide_index=True)


# ─── Page: Glossary ────────────────────────────────────────────────────────────
elif page == "📖 Glossary":
    st.title("📖 Glossary")
    st.caption("Every term used across the dashboard, in plain language — search or browse by category.")

    _gloss_search = st.text_input("🔍 Search a term", "", key="_gloss_search",
                                   placeholder="e.g. sharpe, PEG, breakout, WACC…").strip().lower()

    # Section -> ordered list of keys into _TIP/_EXPLAIN (this file) and/or
    # mod_gloss.TIP (modules/glossary.py). Prefer the plain-language _EXPLAIN
    # text where one exists; otherwise fall back to _TIP's hover text; glossary
    # keys use mod_gloss.tip(). One page, one list, no more hunting for where
    # a term is or isn't explained.
    _GLOSS_SECTIONS: list[tuple[str, list[str]]] = [
        ("💰 Valuation", ["Price", "Market Cap", "P/S Ratio", "Forward P/E", "PEG Ratio",
                          "52W Range", "ev_ebitda", "dcf", "wacc", "terminal_value", "intrinsic_value"]),
        ("📈 Growth & Margins", ["Revenue Growth", "Earnings Growth", "Rule of 40", "Gross Margin",
                                 "FCF Yield", "FCF Margin", "R&D % Revenue", "Debt/Equity",
                                 "profit_margin", "roe", "fcf", "ocf_ni", "sbc", "dilution"]),
        ("📊 Technical", ["Trend (MA)", "RSI", "MACD", "Volume", "52W Position",
                          "ma200", "ma50", "atr", "bollinger", "golden_cross", "rs_line"]),
        ("🏦 Institutional & Flow", ["Short Interest", "Institutional Ownership", "Rate Sensitivity",
                                     "China Exposure", "13f", "mspr", "insider", "call_put_ratio"]),
        ("🎯 Composite Scores", ["Fundamental", "Technical", "Momentum", "Smart Money", "Macro", "Relative"]),
        ("🧑‍💼 Expert Panel & Trade Plan", ["Conviction", "Position Size", "Stop Loss", "Target Price",
                                          "r_multiple", "reward_risk", "position_sizing", "chandelier",
                                          "hedging", "leverage"]),
        ("🌡 Market Regime & Macro", ["VIX", "10Y Yield", "S&P 1M", "QQQ 1M", "vix", "yield_curve",
                                     "hy_spread", "dxy", "risk_on_off", "market_breadth"]),
        ("⚖ Risk & Portfolio", ["beta", "sharpe", "sortino", "max_drawdown", "var", "volatility",
                                "correlation", "risk_parity", "kelly", "drift", "rebalancing",
                                "monte_carlo", "stress_test"]),
        ("🔎 Weekly Picks & Screeners", ["RVOL", "Call/Put", "3M Ret", "PT Up", "Bulls", "Rev Gr",
                                        "GM", "Weekly Score", "Options", "Breakout", "Analyst", "Model",
                                        "rs", "momentum_dir", "weekly_score", "bull_pct",
                                        "breakout_score", "composite_health", "sector_rotation", "grade"]),
        ("🧠 Strategy & Trading", ["alpha", "momentum_factor", "value_factor", "quality_factor",
                                  "seasonality", "expectancy", "conviction", "time_horizon"]),
        ("📉 Backtesting", ["cagr", "win_rate", "profit_factor", "equity_curve", "benchmark", "backtest"]),
        ("🎓 Guru Methods", ["minervini_method", "turtle_method", "trend_following_method", "kelly_method",
                            "druckenmiller_method", "factor_method", "risk_parity_method", "panel_method",
                            "buffett_method", "munger_method", "lynch_method", "graham_method",
                            "greenblatt_method", "canslim_method", "bogle_method", "shiller_method",
                            "buffett_indicator", "fear_greed", "piotroski_method", "altman_method",
                            "templeton_method", "opportunity_lens", "reversal_signals", "falling_knife",
                            "analyst_grades", "congress_trading"]),
    ]

    def _gloss_lookup(key: str) -> tuple[str, str]:
        """Returns (display_term, definition) for a _TIP/_EXPLAIN key or a
        modules/glossary.py snake_case key."""
        if key in _TIP or key in _EXPLAIN:
            return key, (_EXPLAIN.get(key) or _TIP.get(key, ""))
        txt = mod_gloss.tip(key)
        if ":" in txt[:60]:
            term, definition = txt.split(":", 1)
            return term.strip(), definition.strip()
        return key.replace("_", " ").title(), txt

    _any_shown = False
    for _sec_name, _sec_keys in _GLOSS_SECTIONS:
        _sec_rows = []
        for _k in _sec_keys:
            _term, _def = _gloss_lookup(_k)
            if not _def:
                continue
            if _gloss_search and _gloss_search not in _term.lower() and _gloss_search not in _def.lower():
                continue
            _sec_rows.append((_term, _def))
        if not _sec_rows:
            continue
        _any_shown = True
        st.markdown(f"#### {_sec_name}")
        for _term, _def in _sec_rows:
            st.markdown(
                f'<div style="background:var(--panel);border:1px solid var(--border);border-radius:10px;'
                f'padding:10px 16px;margin-bottom:6px">'
                f'<b style="color:#e8edf8">{_html.escape(_term)}</b>'
                f'<div style="color:#8a9bc2;font-size:13px;margin-top:2px">{_html.escape(_def)}</div>'
                f'</div>', unsafe_allow_html=True,
            )
        st.markdown("")

    if not _any_shown:
        st.info(f"No terms match \"{_gloss_search}\" — try a different word.")
