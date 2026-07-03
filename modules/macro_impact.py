"""
Macro Impact — per-indicator stock-specific impact analysis.
Uses Claude Haiku for fast, targeted analysis per stock's business model.
Cached per (symbol, indicators_summary) for 1 hour.
"""
import json
import streamlit as st
import anthropic
from config import ANTHROPIC_API_KEY

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


@st.cache_data(ttl=3600, show_spinner=False)
def analyze(symbol: str, name: str, sector: str, industry: str, indicators_summary: str) -> list[dict]:
    """
    indicators_summary: newline-separated "Label: value (status)" strings.
    Returns list of dicts: {indicator, impact, explanation}
    """
    if not ANTHROPIC_API_KEY:
        return []

    client = _get_client()
    if client is None:
        return []

    prompt = f"""Stock: {name} ({symbol})
Sector: {sector} / Industry: {industry}

Current macro indicators:
{indicators_summary}

For EACH indicator listed above, assess the specific impact on {symbol} given its actual business model.
Be concrete — cite the mechanism (e.g., "rate rise compresses 20x P/S multiple", "USD strength hurts 40% international revenue").
Do NOT write generic commentary that applies to all stocks.
IMPORTANT: Always respond in English regardless of any context language.

Respond ONLY with a raw JSON array (no markdown, no code fences):
[
  {{"indicator": "<indicator name exactly as shown above>", "impact": "POSITIVE|NEUTRAL|NEGATIVE", "explanation": "<1 specific sentence about {symbol}>"}}
]"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3].rstrip()
        return json.loads(raw)
    except Exception as e:
        return [{"indicator": "Error", "impact": "NEUTRAL", "explanation": str(e)}]
