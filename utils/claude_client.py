"""
Shared Anthropic client + JSON extraction helpers.

Every module that talks to Claude should use:
  get_client()          — singleton Anthropic client (None if no API key)
  extract_json(raw)     — robust JSON extraction: strips markdown fences AND
                          surrounding prose; handles both objects and arrays
  ENGLISH_ENFORCEMENT   — standard instruction to append to every prompt
"""
import anthropic
from config import ANTHROPIC_API_KEY

ENGLISH_ENFORCEMENT = (
    "IMPORTANT: Always respond in English regardless of the user's input language."
)

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic | None:
    global _client
    if _client is None and ANTHROPIC_API_KEY:
        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def strip_json_markdown(raw: str) -> str:
    """Remove markdown code fences from a Claude response."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:]                      # drop ```json / ``` opening line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
    return raw


def extract_json(raw: str) -> str:
    """Strip fences AND any leading/trailing prose around the JSON payload.
    Works for both objects {...} and arrays [...]."""
    raw = strip_json_markdown(raw)
    obj_start, arr_start = raw.find("{"), raw.find("[")
    # Pick whichever JSON container starts first
    if obj_start == -1 and arr_start == -1:
        return raw
    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        start, end = arr_start, raw.rfind("]")
    else:
        start, end = obj_start, raw.rfind("}")
    if end > start:
        return raw[start:end + 1]
    return raw
