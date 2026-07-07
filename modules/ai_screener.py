"""
AI-powered stock screener v2 — no fixed universe, full scoring, portfolio builder.
Claude suggests tickers freely → validate via yfinance → run full scoring model.
"""
import json
import anthropic
import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from config import ANTHROPIC_API_KEY
from utils.cache import get_ticker_info, get_price_history
from modules import fundamental, technical, momentum as mom_module, scoring

def _strip_json_markdown(raw: str) -> str:
    """Remove markdown code fences from a Claude response, return clean JSON string."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # skip opening fence line (```json or ```)
        lines = lines[1:]
        # strip closing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


def _extract_json(raw: str) -> str:
    """Like _strip_json_markdown, but also drops any leading/trailing prose
    Claude adds around the JSON (e.g. "Here's the portfolio:\n\n{...}")."""
    raw = _strip_json_markdown(raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start:end + 1]
    return raw


# Module-level client — created once
_client: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ── Full scoring (cached per ticker) ─────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def run_full_score(symbol: str) -> dict:
    try:
        f  = fundamental.analyze(symbol)
        t  = technical.analyze(symbol)
        mo = mom_module.analyze(symbol)
        s  = scoring.compute(
            fundamental=f["score"], technical=t["score"],
            momentum=mo["score"], smart_money=5, macro=5, relative=5,
        )
        return {
            "composite":   s["final"],
            "label":       s["label"],
            "color":       s["color"],
            "fundamental": f["score"],
            "technical":   t["score"],
            "momentum":    mo["score"],
        }
    except Exception:
        return {}


# ── Fetch all metrics for a ticker ───────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_data(symbol: str) -> dict | None:
    try:
        info = get_ticker_info(symbol)
        if not info or not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None

        price_df = get_price_history(symbol, period="1y")
        close    = price_df["Close"].squeeze() if not price_df.empty else pd.Series([])

        ma50  = float(close.rolling(50).mean().iloc[-1])  if len(close) >= 50  else None
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None
        r1m   = float(close.iloc[-1] / close.iloc[-21]  - 1) if len(close) >= 22  else None
        r3m   = float(close.iloc[-1] / close.iloc[-63]  - 1) if len(close) >= 64  else None
        r6m   = float(close.iloc[-1] / close.iloc[-126] - 1) if len(close) >= 127 else None

        rsi = None
        if len(close) >= 15:
            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean()
            loss  = (-delta.clip(upper=0)).rolling(14).mean()
            rs    = gain / loss.replace(0, np.nan)
            rsi   = float(100 - 100 / (1 + rs.iloc[-1]))

        price   = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        mkt_cap = info.get("marketCap")
        rev     = info.get("totalRevenue")
        ps      = (mkt_cap / rev) if mkt_cap and rev and rev > 0 else None

        return {
            "symbol":          symbol,
            "name":            info.get("shortName", symbol),
            "sector":          info.get("sector", ""),
            "industry":        info.get("industry", ""),
            "price":           price,
            "market_cap":      mkt_cap,
            "forward_pe":      info.get("forwardPE"),
            "peg":             info.get("pegRatio"),
            "ps_ratio":        ps,
            "revenue_growth":  info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "gross_margin":    info.get("grossMargins"),
            "fcf_margin":      (info.get("freeCashflow") / rev) if info.get("freeCashflow") and rev else None,
            "debt_equity":     info.get("debtToEquity", 0) / 100 if info.get("debtToEquity") else None,
            "short_pct":       info.get("shortPercentOfFloat"),
            "above_ma50":      (price > ma50)  if ma50  and price else None,
            "above_ma200":     (price > ma200) if ma200 and price else None,
            "pct_vs_ma200":    ((price / ma200 - 1) * 100) if ma200 and price else None,
            "r1m": r1m, "r3m": r3m, "r6m": r6m, "rsi": rsi,
        }
    except Exception:
        return None


# ── Claude: free-form query → tickers + filters ───────────────────────────────
def parse_query(user_query: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    prompt = f"""You are a professional equity analyst and stock screener.

User query: "{user_query}"

Your job:
1. Understand what the user is looking for — sector, style, metrics thresholds.
2. Suggest 20–30 specific, real US stock or ETF tickers that BEST match this query.
   - Go beyond the obvious mega-caps. Include mid-caps and high-conviction names.
   - Include sector ETFs if relevant (e.g., SOXX, WCLD, XBI).
   - Think about momentum leaders in the relevant theme.
3. Extract the numeric filters implied by the query.

IMPORTANT: Always respond in English regardless of the user's input language.

Respond ONLY with valid JSON (no markdown):
{{
  "explanation": "<2-3 sentences explaining what you're looking for and why these tickers>",
  "candidate_tickers": ["TICK1", "TICK2", ...],
  "filters": {{
    "forward_pe_max":       <float or null>,
    "forward_pe_min":       <float or null>,
    "revenue_growth_min":   <float 0-1 or null>,
    "earnings_growth_min":  <float 0-1 or null>,
    "gross_margin_min":     <float 0-1 or null>,
    "momentum_positive_3m": <true | false | null>,
    "above_ma200":          <true | false | null>,
    "market_cap_min_b":     <float billions or null>,
    "market_cap_max_b":     <float billions or null>,
    "ps_max":               <float or null>,
    "debt_equity_max":      <float or null>,
    "rsi_min":              <float or null>,
    "rsi_max":              <float or null>
  }}
}}"""

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-5", max_tokens=1500,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        raw = _extract_json(raw)
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


# ── Claude: portfolio builder ─────────────────────────────────────────────────
def build_portfolio(user_query: str) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}
    prompt = f"""You are building a real investment portfolio.

Request: "{user_query}"

Design an optimal, actionable portfolio (4–8 positions) that captures this investment thesis.
Rules:
- Weights must sum to exactly 100%.
- Be specific and opinionated — explain WHY each stock for THIS theme.
- Consider momentum leaders, not just the biggest names.
- Include concentration (higher weight = higher conviction).
- Consider risk: add a hedge or diversifier if the theme is concentrated.

IMPORTANT: Always respond in English regardless of the user's input language.

Respond ONLY with JSON:
{{
  "theme": "<portfolio name/theme — 3-6 words>",
  "thesis": "<2-3 sentences: the investment thesis and why now>",
  "time_horizon": "<short/medium/long-term>",
  "risk_level": "<Conservative|Moderate|Aggressive>",
  "positions": [
    {{
      "ticker":    "<exact ticker>",
      "weight":    <integer % — all must sum to 100>,
      "role":      "<Core|Satellite|Hedge|Growth|Value>",
      "rationale": "<1-2 sentences: why this specific stock for this theme>"
    }}
  ],
  "key_risks": ["<risk 1>", "<risk 2>"],
  "rebalance_trigger": "<what event/condition would cause you to change this portfolio>"
}}"""

    try:
        msg = _get_client().messages.create(
            model="claude-sonnet-5", max_tokens=2500,
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": prompt}]
        )
        raw = msg.content[0].text.strip()
        raw = _extract_json(raw)
        return json.loads(raw)
    except Exception as e:
        return {"error": str(e)}


# ── Claude: agentic portfolio builder (real tool use) ─────────────────────────
# Unlike build_portfolio() above, Claude does not just recall tickers from
# memory — it can call get_stock_metrics() mid-conversation to pull live
# fundamentals/technicals for any candidate before deciding to include it.
_PORTFOLIO_TOOLS = [
    {
        "name": "get_stock_metrics",
        "description": (
            "Fetch live fundamental, technical, and momentum metrics for a single "
            "US-listed stock or ETF ticker (price, forward P/E, revenue growth, "
            "gross margin, RSI, moving averages, etc). Use this to verify a "
            "candidate before including it in the portfolio — do not rely on "
            "memory for current prices or growth rates, they may be stale."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Exact ticker symbol, e.g. AAPL"},
            },
            "required": ["ticker"],
        },
    }
]

_AGENT_SYSTEM_PROMPT = """You are building a real investment portfolio using live tools, not memory alone.

Process:
1. Think of 6-12 candidate tickers that fit the user's request.
2. For EACH serious candidate, call get_stock_metrics to check its current price, valuation, growth, and momentum before deciding whether to include it. Prices and fundamentals from memory can be stale or wrong — always verify.
3. Once you've researched enough candidates, select 4-8 for the final portfolio.

Rules:
- Weights must sum to exactly 100%.
- Be specific and opinionated — explain WHY each stock for THIS theme, referencing the actual metrics you looked up.
- Consider momentum leaders, not just the biggest names.
- Consider risk: add a hedge or diversifier if the theme is concentrated.
- Always respond in English regardless of the user's input language.

When finished researching, respond with ONLY this JSON (no markdown, no more tool calls):
{
  "theme": "<portfolio name/theme - 3-6 words>",
  "thesis": "<2-3 sentences: the investment thesis and why now>",
  "time_horizon": "<short/medium/long-term>",
  "risk_level": "<Conservative|Moderate|Aggressive>",
  "positions": [
    {
      "ticker": "<exact ticker>",
      "weight": <integer % - all must sum to 100>,
      "role": "<Core|Satellite|Hedge|Growth|Value>",
      "rationale": "<1-2 sentences citing the actual metrics you looked up>"
    }
  ],
  "key_risks": ["<risk 1>", "<risk 2>"],
  "rebalance_trigger": "<what event/condition would cause you to change this portfolio>"
}"""


def build_portfolio_agentic(user_query: str, max_tool_rounds: int = 6) -> dict:
    """Same output shape as build_portfolio(), but Claude actively looks up live
    data via the get_stock_metrics tool before finalizing positions, instead of
    only recalling tickers from training data."""
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    client = _get_client()
    messages = [{
        "role": "user",
        "content": f'Request: "{user_query}"\n\nResearch candidates with the tool, then propose the portfolio.',
    }]
    researched: list[str] = []
    resp = None

    for _ in range(max_tool_rounds):
        try:
            resp = client.messages.create(
                model="claude-sonnet-5", max_tokens=8192,
                system=_AGENT_SYSTEM_PROMPT, tools=_PORTFOLIO_TOOLS, messages=messages,
            )
        except Exception as e:
            return {"error": str(e)}

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            break

        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "get_stock_metrics":
                ticker = str(block.input.get("ticker", "")).upper().strip()
                data = fetch_stock_data(ticker) if ticker else None
                researched.append(ticker)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(data) if data else json.dumps({"error": f"No data found for {ticker}"}),
                })
        messages.append({"role": "user", "content": tool_results})
    else:
        return {"error": "Agent exceeded max tool-call rounds without finishing."}

    def _text_of(response) -> str:
        return "".join(b.text for b in response.content if getattr(b, "type", None) == "text").strip()

    final_text = _text_of(resp)

    # Claude sometimes stops (e.g. hits its token budget mid-thought) without
    # emitting the final JSON. Nudge it once to just output the answer.
    if not final_text:
        messages.append({
            "role": "user",
            "content": "Output ONLY the final JSON now, no other text.",
        })
        try:
            resp = client.messages.create(
                model="claude-sonnet-5", max_tokens=8192,
                system=_AGENT_SYSTEM_PROMPT, tools=_PORTFOLIO_TOOLS, messages=messages,
            )
            final_text = _text_of(resp)
        except Exception as e:
            return {"error": str(e)}

    if not final_text:
        return {"error": f"Agent produced no final answer (stop_reason={resp.stop_reason})."}

    try:
        result = json.loads(_extract_json(final_text))
    except Exception as e:
        preview = final_text[:300]
        return {"error": f"Failed to parse final answer: {e} — response started with: {preview!r}", "raw": final_text}

    result["tickers_researched_live"] = researched
    return result


# ── Apply filters to fetched data ─────────────────────────────────────────────
def apply_filters(stocks: list[dict], filters: dict) -> list[dict]:
    results = []
    for s in stocks:
        if not s:
            continue
        fp = filters or {}

        def ok(val, lo=None, hi=None):
            if val is None: return True
            if lo is not None and val < lo: return False
            if hi is not None and val > hi: return False
            return True

        if not ok(s.get("forward_pe"),      fp.get("forward_pe_min"),     fp.get("forward_pe_max")):     continue
        if not ok(s.get("revenue_growth"),  fp.get("revenue_growth_min")):                               continue
        if not ok(s.get("earnings_growth"), fp.get("earnings_growth_min")):                              continue
        if not ok(s.get("gross_margin"),    fp.get("gross_margin_min")):                                 continue
        if not ok(s.get("ps_ratio"),        None,                          fp.get("ps_max")):             continue
        if not ok(s.get("debt_equity"),     None,                          fp.get("debt_equity_max")):    continue
        if not ok(s.get("rsi"),             fp.get("rsi_min"),             fp.get("rsi_max")):            continue
        if not ok(s.get("market_cap"),
                  (fp.get("market_cap_min_b") or 0) * 1e9,
                  (fp.get("market_cap_max_b") or 1e15)):                                                  continue
        if fp.get("above_ma200") is True  and s.get("above_ma200") is False: continue
        if fp.get("above_ma200") is False and s.get("above_ma200") is True:  continue
        if fp.get("momentum_positive_3m") is True and (s.get("r3m") or 0) <= 0: continue

        results.append(s)
    return results


# ── Signal-based score (used in display when full score not yet loaded) ───────
def signal_score(s: dict) -> float:
    base, signals = 45, [
        s.get("above_ma200"),
        s.get("above_ma50"),
        (s.get("r3m") or 0) > 0,
        40 <= (s.get("rsi") or 0) <= 65,
        (s.get("revenue_growth") or 0) > 0.15,
        (s.get("gross_margin") or 0) > 0.50,
        (s.get("forward_pe") or 99) < 40,
        (s.get("short_pct") or 1) < 0.08,
    ]
    weights = [8, 5, 7, 5, 8, 6, 5, 4]
    for hit, w in zip(signals, weights):
        if hit is True:   base += w
        elif hit is False: base -= w * 0.4
    return round(max(10, min(88, base)), 1)
