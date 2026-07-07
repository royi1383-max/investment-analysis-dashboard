"""
Portfolio Health Check — scores each position and uses Claude
to give actionable recommendations: trim, add, exit, add exposure.
"""
import json
import anthropic
import pandas as pd
import streamlit as st
from config import ANTHROPIC_API_KEY
from utils.cache import get_ticker_info, get_price_history
from modules import fundamental, technical, momentum as mom_module, scoring

# Module-level client
_client: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SCORE_COLORS = {
    "STRONG ADD":  "#16c784",
    "ADD":         "#a3e635",
    "HOLD":        "#f0b90b",
    "TRIM":        "#f97316",
    "EXIT":        "#ea3a44",
    "NO DATA":     "#556070",
}


@st.cache_data(ttl=3600, show_spinner=False)
def score_position(ticker: str) -> dict:
    """Run full scoring on a single US ticker."""
    try:
        f  = fundamental.analyze(ticker)
        t  = technical.analyze(ticker)
        mo = mom_module.analyze(ticker)
        s  = scoring.compute(
            fundamental=f["score"],
            technical=t["score"],
            momentum=mo["score"],
            smart_money=5, macro=5, relative=5,
        )
        info = get_ticker_info(ticker)
        ph   = get_price_history(ticker, period="6mo")
        close = ph["Close"].squeeze() if not ph.empty else pd.Series([])
        r3m   = float(close.iloc[-1] / close.iloc[-63] - 1) * 100 if len(close) >= 64 else None
        r1m   = float(close.iloc[-1] / close.iloc[-21] - 1) * 100 if len(close) >= 22 else None

        return {
            "ticker":          ticker,
            "name":            info.get("shortName", ticker),
            "sector":          info.get("sector", "Unknown"),
            "score":           s["final"],
            "label":           s["label"],
            "fundamental":     f["score"],
            "technical":       t["score"],
            "momentum":        mo["score"],
            "revenue_growth":  info.get("revenueGrowth"),
            "forward_pe":      info.get("forwardPE"),
            "gross_margin":    info.get("grossMargins"),
            "r3m":             r3m,
            "r1m":             r1m,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "score": None}


_IL_KEYWORDS = {
    "nikkei": "Japan Equities",    "s&p": "US Equities",
    "health": "Healthcare",        "tech": "Technology",
    "ai":     "AI / Technology",   "eusto": "European Equities",
    "europe": "European Equities", "ta-12": "Israeli Large Cap",
    "ta-90":  "Israeli Mid Cap",   "ta-35": "Israeli Blue Chip",
    "bond":   "Bonds",             "שקל":  "NIS Bonds",
    "govern": "Government Bonds",  "world": "Global Equities",
    "nasdaq": "US Tech (Nasdaq)",  "russell": "US Small Cap",
    "emerg":  "Emerging Markets",  "china": "China Equities",
    "energy": "Energy",            "real":  "Real Estate",
    "smallc": "Small Cap",         "indust": "Industrials",
    "financ": "Financials",        "75%":   "Israeli Bonds (75%)",
    "תא":     "Israeli Equities",  "מניות": "Israeli Equities",
}


def classify_israeli(name: str) -> str:
    """Infer asset class from Israeli security name."""
    n = name.lower()
    for kw, label in _IL_KEYWORDS.items():
        if kw in n:
            return label
    return "Israeli Security"


def _fmt_pct(v):
    if v is None: return "N/A"
    try:
        return f"{float(v):+.1f}%"
    except Exception:
        return str(v)


def run_health_check(positions: list[dict]) -> dict:
    """
    positions: list of dicts — US stocks have score_data, Israeli have asset_class.
    Returns full health check result from Claude.
    """
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    us_lines = []
    il_lines = []

    for p in positions:
        sd = p.get("score_data", {})
        pos_type = p.get("pos_type", "US")

        if pos_type == "US":
            line = (
                f"- {p['ticker']} ({p.get('name','')}) | "
                f"Weight: {p.get('weight_pct',0):.1f}% | "
                f"P&L: {p.get('pnl_pct',0):+.1f}% | "
                f"Sector: {p.get('sector','?')} | "
                f"Score: {sd.get('score','N/A')} | "
                f"Fundamental: {sd.get('fundamental','?')} | "
                f"Technical: {sd.get('technical','?')} | "
                f"Momentum: {sd.get('momentum','?')} | "
                f"3M Return: {(str(round(sd['r3m'],1))+'%') if sd.get('r3m') is not None else 'N/A'} | "
                f"Rev Growth: {_fmt_pct(sd.get('revenue_growth'))} | "
                f"Fwd P/E: {sd.get('forward_pe','N/A')}"
            )
            us_lines.append(line)
        else:
            line = (
                f"- {p.get('name', p.get('ticker','?'))} | "
                f"Weight: {p.get('weight_pct',0):.1f}% | "
                f"P&L: {p.get('pnl_pct',0):+.1f}% | "
                f"Asset Class: {p.get('asset_class','Israeli Security')} | "
                f"Type: Israeli Fund/Certificate | No live scoring available"
            )
            il_lines.append(line)

    us_str = "\n".join(us_lines)   if us_lines else "None"
    il_str = "\n".join(il_lines)   if il_lines else "None"

    # Sector/asset-class concentrations
    sector_weights = {}
    for p in positions:
        s = p.get("asset_class") or p.get("sector", "Unknown")
        sector_weights[s] = sector_weights.get(s, 0) + p.get("weight_pct", 0)
    sector_str = ", ".join(f"{k}: {v:.0f}%" for k, v in
                           sorted(sector_weights.items(), key=lambda x: -x[1]))

    # Use name as ticker key for Israeli positions
    all_ids = (
        [p["ticker"] for p in positions if p.get("pos_type") == "US"] +
        [p.get("name", "")[:20] for p in positions if p.get("pos_type") == "IL"]
    )

    prompt = f"""You are a senior portfolio manager reviewing a mixed portfolio of US stocks and Israeli funds/certificates.

US STOCK POSITIONS (with full scoring):
{us_str}

ISRAELI FUNDS / CERTIFICATES (limited data — name, weight, P&L, asset class):
{il_str}

ASSET CLASS CONCENTRATION:
{sector_str}

Notes:
- US positions have scores 1-10 (Fundamental, Technical, Momentum). P&L and weight are from broker data.
- Israeli positions: no live scoring available. Analyze based on asset class, P&L trend, and portfolio weight.
- For Israeli positions, the "ticker" field in your response should be the first word of the name.
- Consider both the US and Israeli sides when assessing diversification and risk.
- IMPORTANT: Always respond in English regardless of any Hebrew fund names or context.

Respond ONLY with valid JSON (no markdown):
{{
  "health_score": <integer 1-10>,
  "health_label": "<Excellent|Good|Fair|Needs Attention|Critical>",
  "health_summary": "<2-3 sentences: overall assessment covering both US stocks and Israeli funds>",
  "positions": [
    {{
      "ticker": "<US ticker OR first word of Israeli fund name>",
      "action": "<STRONG ADD|ADD|HOLD|TRIM|EXIT>",
      "conviction": <1-5>,
      "reason": "<1-2 sentences specific to this position — cite metric or P&L>",
      "risk": "<main risk>"
    }}
  ],
  "missing_exposures": [
    {{"theme": "<sector/asset class>", "why": "<why this adds value to this specific portfolio>"}}
  ],
  "top_changes": [
    "<specific actionable change #1 — mention the position name>",
    "<specific actionable change #2>",
    "<specific actionable change #3>"
  ],
  "concentration_risks": ["<risk 1>", "<risk 2>"],
  "thesis_alignment": "<2 sentences: implied investment thesis and whether US + Israeli sides are coherent>"
}}"""

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-5",
            max_tokens=2000,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if raw.endswith("```"):
                raw = raw[:-3]
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}
