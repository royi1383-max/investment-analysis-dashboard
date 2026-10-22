"""
Scoring engine — combines all module scores into a final weighted score.
"""
from config import SCORE_WEIGHTS, SCORE_LABELS

# Same strong/weak cutoffs the rest of the app already uses for per-pillar
# grades (score_color / the "✅ Very Strong" / "❌ Weak" tags in app.py) —
# kept in sync so a pillar the UI calls "weak" is the same one this
# classifier calls "weak".
_STRONG = 7.5
_WEAK   = 4.5


def compute(
    fundamental: float,
    technical: float,
    momentum: float,
    smart_money: float,
    macro: float,
    relative: float,
) -> dict:
    raw = {
        "fundamental": fundamental,
        "technical":   technical,
        "momentum":    momentum,
        "smart_money": smart_money,
        "macro":       macro,
        "relative":    relative,
    }

    final = sum(raw[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
    final = round(min(max(final, 1), 10), 2)

    label = "Hold"
    color = "#ffd600"
    for (lo, hi), (lbl, col) in SCORE_LABELS.items():
        if lo <= final <= hi:
            label = lbl
            color = col
            break

    return {
        "final":      final,
        "label":      label,
        "color":      color,
        "breakdown":  raw,
        "weights":    SCORE_WEIGHTS,
    }


def classify_pattern(breakdown: dict) -> dict:
    """
    The linear weighted average in compute() treats every combination of
    pillars the same way — a stock with strong fundamentals+macro but weak
    technical+momentum lands on the same final number as one that's
    genuinely mixed across the board, even though those are very different
    situations (a business the market hasn't priced in yet vs. real
    uncertainty). This doesn't change the final score — every existing
    consumer (Weekly Picks, AI Screener, Portfolio health, the Scanner
    Verdict itself) keeps ranking/filtering on the same number it always
    has. It adds a second, independent read of the SAME breakdown so a
    human looking at the number can tell which situation they're in.

    "Quality" = fundamental+macro (the business case + the environment it
    operates in). "Confirmation" = technical+momentum (has the market
    actually started agreeing with that case yet). Smart money and
    relative strength are deliberately left out of both — they're
    market-behavior signals like confirmation, but not required to name
    the pattern, and folding them in would blur the exact fundamentals-vs-
    price-action tension this is meant to surface.
    """
    fundamental = breakdown.get("fundamental", 5.0)
    macro       = breakdown.get("macro", 5.0)
    technical   = breakdown.get("technical", 5.0)
    momentum    = breakdown.get("momentum", 5.0)

    quality      = round((fundamental + macro) / 2, 2)
    confirmation = round((technical + momentum) / 2, 2)

    if quality >= _STRONG and confirmation <= _WEAK:
        pattern, icon, color, note = (
            "FUNDAMENTALLY-DRIVEN — AWAITING CONFIRMATION", "🌱", "#60a5fa",
            "Business quality and macro backdrop are strong, but price/momentum "
            "haven't confirmed it yet. Often a timing question, not a thesis "
            "problem — worth tracking for a technical trigger rather than "
            "dismissing on the headline score alone."
        )
    elif quality <= _WEAK and confirmation >= _STRONG:
        pattern, icon, color, note = (
            "MOMENTUM WITHOUT FUNDAMENTAL SUPPORT", "⚠️", "#f97316",
            "Price/momentum are strong but the underlying business/macro case "
            "is weak. A momentum trade with no fundamental cushion if the move "
            "stalls — size and exit plan matter more here than usual."
        )
    elif quality >= _STRONG and confirmation >= _STRONG:
        pattern, icon, color, note = (
            "BROAD ALIGNMENT — BULLISH", "🟢", "#16c784",
            "Business quality and price action agree — the clean case, no "
            "hidden tension between the two halves of the score."
        )
    elif quality <= _WEAK and confirmation <= _WEAK:
        pattern, icon, color, note = (
            "BROAD ALIGNMENT — BEARISH", "🔴", "#ea3a44",
            "Business quality and price action agree — the clean avoid, no "
            "hidden tension between the two halves of the score."
        )
    else:
        pattern, icon, color, note = (
            "MIXED — NO DOMINANT STORY", "⚪", "#8a9bc2",
            "No single factor dominates either way — genuinely uncertain "
            "rather than a hidden setup in either direction."
        )

    return {
        "pattern":      pattern,
        "icon":         icon,
        "color":        color,
        "note":         note,
        "quality":      quality,
        "confirmation": confirmation,
    }


def action_plan(score_label: str, quadrant: str, pattern: str,
                current_price: float | None = None,
                nearest_support: float | None = None,
                nearest_resistance: float | None = None,
                ma50: float | None = None) -> dict:
    """
    One decisive stance + concrete next steps, synthesized from pieces that
    already exist elsewhere on the page (the composite score's label, the
    Opportunity Lens quality-vs-condition quadrant, and this module's own
    quality-vs-confirmation pattern) plus, when available, the nearest
    support/resistance levels and MA50 (same swing-point detection used
    for the price-chart overlays) to make the steps concrete price levels
    rather than vague advice. Deterministic — no LLM call, so it's always
    available and reproducible from the same inputs.

    Priority-ordered rules (first match wins) rather than a full label x
    quadrant x pattern cross-product — the combinations below are the ones
    that actually change what you should DO; everything else falls through
    to a same "no dominant story" default rather than guessing.
    """
    def _pct(level):
        if current_price and level:
            return (level / current_price - 1) * 100
        return None

    sup_pct = _pct(nearest_support)
    res_pct = _pct(nearest_resistance)

    if quadrant == "FALLING KNIFE":
        action, color = "AVOID — DO NOT BUY THE DIP", "#ea3a44"
        steps = [
            "Business quality AND price action are both weak — the market is "
            "likely right about this one. Cheapness alone isn't a thesis.",
            "Needs a real fundamental turnaround (margin/growth inflection), "
            "not just a bounce, before this is investable again.",
        ]
        if nearest_support:
            steps.append(f"If already holding: a close below the nearest support "
                        f"(${nearest_support:.2f}, {sup_pct:+.1f}%) would confirm "
                        f"the downtrend is still in control.")

    elif quadrant == "LEADER" and score_label in ("Strong Buy", "Buy"):
        action, color = "HOLD / ADD ON WEAKNESS", "#16c784"
        steps = [
            "Business quality and price action both confirm — this is what "
            "a core position looks like. The risk here is valuation, not "
            "the business itself.",
        ]
        if nearest_support:
            steps.append(f"A pullback to the nearest support (${nearest_support:.2f}, "
                        f"{sup_pct:+.1f}%) is a place to consider adding, not a reason to sell.")

    elif pattern == "FUNDAMENTALLY-DRIVEN — AWAITING CONFIRMATION":
        action, color = "STARTER POSITION AT MOST — WAIT FOR CONFIRMATION", "#60a5fa"
        steps = [
            "Fundamentals and macro back the thesis, but price/momentum "
            "haven't turned yet. This is a timing question, not a broken thesis.",
        ]
        if ma50:
            steps.append(f"Entry/add trigger: a reclaim of the 50-day moving average "
                        f"(${ma50:.2f}) with RSI turning up — confirmation the market "
                        f"is starting to agree.")
        if nearest_support:
            steps.append(f"If starting a position now: size it small (⅓ normal) and "
                        f"set the stop under the nearest support (${nearest_support:.2f}, "
                        f"{sup_pct:+.1f}%) — that level breaking would say the market "
                        f"disagrees with the fundamental case, not just the timing.")

    elif quadrant == "MOMENTUM WITHOUT QUALITY" or pattern == "MOMENTUM WITHOUT FUNDAMENTAL SUPPORT":
        action, color = "TRADE WITH A STOP — NOT AN INVESTMENT", "#f97316"
        steps = [
            "Price/momentum are strong but the business/macro case isn't there "
            "to catch you if it stalls. This works until it doesn't, often violently.",
            "Never average down on this pattern — if the stop is hit, the trade "
            "thesis (momentum) is what failed, not just the price.",
        ]
        if nearest_resistance:
            steps.append(f"Nearest resistance (${nearest_resistance:.2f}, {res_pct:+.1f}%) "
                        f"is the natural first target — momentum trades are for taking "
                        f"profit at resistance, not holding through it.")

    elif quadrant == "QUALITY ON SALE":
        action, color = "WATCHLIST — LET IT PROVE ITSELF", "#4da3ff"
        steps = [
            "Business intact, stock out of favor — but not enough reversal "
            "signals yet to act. Watching beats guessing the bottom.",
        ]
        if nearest_support:
            steps.append(f"Watch for a higher low forming above the nearest support "
                        f"(${nearest_support:.2f}, {sup_pct:+.1f}%) as the first sign "
                        f"of a real base, not just a bounce.")

    else:
        action, color = "NO EDGE — WAIT FOR A CLEARER SIGNAL", "#8a9bc2"
        steps = [
            "Neither the business case nor the price action is decisive enough "
            "to act on right now. The best trades come from clearer setups than this.",
        ]

    return {"action": action, "color": color, "steps": steps}
