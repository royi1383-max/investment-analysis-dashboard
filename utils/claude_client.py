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


def salvage_json_objects(raw: str, array_key: str) -> list[dict]:
    """
    Rescue parser for TRUNCATED Claude JSON: extracts every COMPLETE object
    from the `array_key` array, dropping only the object that got cut off
    at the max_tokens limit.

    Walks the text with brace-depth + string awareness (handles quotes and
    escapes inside values). Returns [] if the array isn't found.
    """
    import json as _json
    idx = raw.find(f'"{array_key}"')
    if idx == -1:
        return []
    arr_start = raw.find("[", idx)
    if arr_start == -1:
        return []

    objects, depth, obj_start = [], 0, None
    in_str, esc = False, False
    for i in range(arr_start + 1, len(raw)):
        ch = raw[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    objects.append(_json.loads(raw[obj_start:i + 1]))
                except Exception:
                    pass
                obj_start = None
        elif ch == "]" and depth == 0:
            break
    return objects


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
