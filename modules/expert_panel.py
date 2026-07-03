"""
Expert Panel — AI investor personas, ONE Claude call.

All experts are sent in a single batch prompt and respond together.
Results are cached per (symbol, rounded_price) for 2 hours.
"""
import re
import json
import streamlit as st
import anthropic

from config import ANTHROPIC_API_KEY, EXPERTS


# Module-level client — instantiated once
_client: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _empty_result(name: str, profile: dict, price: float, reason: str) -> dict:
    return {
        "name": name, "profile": profile,
        "decision": "HOLD", "conviction": 3,
        "time_horizon": "",
        "entry_price": price, "position_size_pct": 5,
        "stop_loss_pct": 15, "target_price": None,
        "rationale": reason, "key_risks": [],
    }


@st.cache_data(ttl=7200, show_spinner=False)
def analyze(symbol: str, price_rounded: float, summary_json: str) -> list[dict]:
    """
    price_rounded: price rounded to 2 dp — used as cache key.
    summary_json: JSON string of metrics/scores — hashable for cache.
    Returns list of expert dicts.
    """
    if not ANTHROPIC_API_KEY:
        return [_empty_result(n, p, price_rounded,
                              "Add ANTHROPIC_API_KEY to enable AI expert panel.")
                for n, p in EXPERTS.items()]

    client = _get_client()

    expert_names = list(EXPERTS.keys())
    expert_lines = "\n".join(
        f"{i+1}. {name}: {profile['style']}"
        for i, (name, profile) in enumerate(EXPERTS.items())
    )
    n_experts = len(expert_names)

    prompt = f"""You are acting as {n_experts} distinct investor personas giving independent verdicts on the same stock.

STOCK: {symbol} @ ${price_rounded:.2f}

FINANCIAL DATA:
{summary_json}

THE {n_experts} PERSONAS (use the exact name key shown before the colon):
{expert_lines}

Rules:
- Each persona MUST speak in their OWN voice — use your specific investment lens, not generic analysis.
- Each rationale MUST cite at least 2 SPECIFIC numbers from the FINANCIAL DATA (e.g. revenue growth %, P/S ratio, gross margin, RSI, 3M return).
- target_price must be non-zero. entry_price should reflect your timing view (at market = buy now; below market = wait for pullback).
- Be DECISIVE. Avoid hedging language. No "it depends" without a clear conclusion.
- Michael and Charlie: lean toward SELL or WATCH unless data is truly exceptional — your job is to find the bear case the bulls ignore.
- The panel MUST show genuine disagreement. If 6 or more experts give the same decision, you have failed at this task.
- time_horizon: when does your thesis play out — "3M", "6M", "12M", or "2Y+".
- IMPORTANT: Always respond in English regardless of the stock or any context language.

Respond ONLY with a raw JSON object (no markdown, no code fences):
{{
  "experts": [
    {{
      "name": "<one of: {', '.join(expert_names)}>",
      "decision": "<BUY|SELL|HOLD|WATCH>",
      "conviction": <1-5>,
      "time_horizon": "<3M|6M|12M|2Y+>",
      "entry_price": <float>,
      "position_size_pct": <float 1-20>,
      "stop_loss_pct": <float>,
      "target_price": <float>,
      "rationale": "<3-4 sentences in this persona's voice, cite at least 2 specific metrics>",
      "key_risks": ["<risk 1>", "<risk 2>"]
    }}
  ]
}}"""

    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3].rstrip()
        # Strip any leading prose before the JSON object/array
        json_start = re.search(r'[{\[]', raw)
        if json_start:
            raw = raw[json_start.start():]

        parsed = json.loads(raw)

        # Support both {"experts": [...]} and bare [...] responses
        experts_list = parsed.get("experts", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(experts_list, list):
            experts_list = list(experts_list.values()) if isinstance(experts_list, dict) else []

        # Robust name lookup — handles numbered, hyphenated, full-name, lowercase variants
        def _name_variants(s: str) -> list[str]:
            s = s.strip()
            variants = [s, s.lower()]
            # strip leading digits/punctuation ("1. Cathie" → "Cathie")
            cleaned = re.sub(r'^[\d\s.]+', '', s).strip()
            variants += [cleaned, cleaned.lower()]
            # first word of each variant
            for v in list(variants):
                first = re.split(r'[\s\-—:.(]', v)[0].strip()
                if first:
                    variants += [first, first.lower()]
            return [v for v in variants if v]

        by_name: dict = {}
        for e in experts_list:
            if not isinstance(e, dict):
                continue
            for variant in _name_variants(str(e.get("name", ""))):
                by_name.setdefault(variant, e)

        results = []
        for name, profile in EXPERTS.items():
            e = None
            # 1. exact / lowercase / first-word lookup
            for key in _name_variants(name):
                e = by_name.get(key)
                if e:
                    break
            # 2. substring fallback — find any returned name that contains our key
            if not e:
                for ex_item in experts_list:
                    if isinstance(ex_item, dict):
                        returned = str(ex_item.get("name", "")).lower()
                        if name.lower() in returned:
                            e = ex_item
                            break
            if e:
                results.append({"name": name, "profile": profile, **e})
            else:
                results.append(_empty_result(name, profile, price_rounded,
                                             "No response from this expert."))

        # Don't cache a total failure — let the next call retry fresh
        all_failed = all(
            "No response" in str(r.get("rationale", "")) for r in results
        )
        if all_failed:
            analyze.clear()

        return results

    except Exception as ex:
        return [_empty_result(n, p, price_rounded, f"Error: {ex}")
                for n, p in EXPERTS.items()]
