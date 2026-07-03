"""
Macro & Geopolitical analysis module.
Uses Claude AI to produce a qualitative score + narrative.
Results cached per (symbol, sector, industry) for 2 hours.
"""
import json
import streamlit as st
import anthropic

from config import ANTHROPIC_API_KEY
from utils.cache import get_ticker_info

# Module-level client — instantiated once
_client: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


@st.cache_data(ttl=7200, show_spinner=False)
def analyze(symbol: str, sector: str = "", industry: str = "") -> dict:
    if not ANTHROPIC_API_KEY:
        return {
            "score": 5,
            "narrative": "Add ANTHROPIC_API_KEY to enable macro analysis.",
            "tailwinds": [], "headwinds": [],
            "geopolitical": [], "tech_trends": [],
            "rate_sensitivity": "medium", "china_exposure": "none",
        }

    info     = get_ticker_info(symbol)
    sector   = sector   or info.get("sector",   "Unknown")
    industry = industry or info.get("industry", "Unknown")
    country  = info.get("country", "US")
    name     = info.get("longName", symbol)

    prompt = f"""You are a senior macro and geopolitical investment analyst.
Analyze the current macro and geopolitical environment for:
- Company: {name} ({symbol})
- Sector: {sector}
- Industry: {industry}
- Country: {country}

Focus on growth-oriented investors with a 1-year horizon.
IMPORTANT: Always respond in English regardless of any context language.

Respond ONLY with valid JSON (no markdown):
{{
  "score": <integer 1-10>,
  "narrative": "<2-3 sentence summary>",
  "tailwinds": ["<tailwind 1>", "<tailwind 2>"],
  "headwinds": ["<headwind 1>", "<headwind 2>"],
  "geopolitical_risks": ["<risk 1>"],
  "tech_trends": ["<trend 1>"],
  "rate_sensitivity": "<low|medium|high>",
  "china_exposure": "<none|low|medium|high>"
}}

Consider: interest rates, AI/tech cycle, China/US tensions, semiconductor supply chains, dollar strength, inflation, earnings cycle."""

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        return {
            "score":            data.get("score", 5),
            "narrative":        data.get("narrative", ""),
            "tailwinds":        data.get("tailwinds", []),
            "headwinds":        data.get("headwinds", []),
            "geopolitical":     data.get("geopolitical_risks", []),
            "tech_trends":      data.get("tech_trends", []),
            "rate_sensitivity": data.get("rate_sensitivity", "medium"),
            "china_exposure":   data.get("china_exposure", "none"),
        }
    except Exception as e:
        return {
            "score": 5, "narrative": f"Macro analysis unavailable: {e}",
            "tailwinds": [], "headwinds": [],
            "geopolitical": [], "tech_trends": [],
            "rate_sensitivity": "medium", "china_exposure": "none",
        }
