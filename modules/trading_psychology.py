"""
Trading Psychology — a pre/post-trade bias self-check, distilled from RN SB's
behavioral-finance notes (Adaptive Markets / A Random Walk Down Wall Street
book-notes cluster) into a Murphy-checklist-style yes/no format.

Every item is phrased so YES = disciplined behavior, matching the polarity
of modules.risk_tools.murphy_checklist — a "no" answer is the bias showing up.
All deterministic — no AI calls, this is a self-report checklist, not a
model that reads your trades.
"""

BIAS_CHECKLIST: list[dict] = [
    {
        "key": "stop_before_entry",
        "q": "I set a stop-loss / risk limit before entering, and I'm not averaging down on a loser to avoid realizing the loss.",
        "bias": "Loss aversion / doubling down (the 'rogue-trader' pattern)",
    },
    {
        "key": "own_thesis",
        "q": "I can state MY OWN reason for this trade, independent of what everyone else is buying right now.",
        "bias": "Herding / social proof",
    },
    {
        "key": "not_chasing_hot_streak",
        "q": "I'm not picking this stock/fund mainly because of its recent hot performance.",
        "bias": "Performance chasing (buying yesterday's winner)",
    },
    {
        "key": "no_urgency_pressure",
        "q": "This wasn't pitched to me with urgency pressure, 'don't miss out' framing, or suspiciously smooth/guaranteed returns.",
        "bias": "Hot-tip / IPO red flags",
    },
    {
        "key": "not_sizing_up_on_streak",
        "q": "A recent winning streak is not the reason I'm increasing my position size right now.",
        "bias": "Dopamine-driven overconfidence after wins",
    },
    {
        "key": "numbers_not_fear",
        "q": "I'm reacting to what the data actually says, not to how scary or exciting this feels in the moment.",
        "bias": "Fear/affect-driven panic decisions",
    },
    {
        "key": "week_delay_test",
        "q": "I'd still want to make this trade if I had to wait a week before acting on it.",
        "bias": "Hyperbolic discounting / impulsivity",
    },
    {
        "key": "committed_not_split",
        "q": "I'm committing to my highest-conviction idea, not splitting size across everything out of habit.",
        "bias": "Probability matching (hedging instead of committing)",
    },
    {
        "key": "not_revenge_trading",
        "q": "I'm not trading right now to 'get back' a recent loss.",
        "bias": "Revenge trading",
    },
    {
        "key": "skill_vs_luck",
        "q": "I'm crediting my last result to process, not just labeling a win 'skill' and a loss 'bad luck' (or vice versa).",
        "bias": "Self-attribution bias",
    },
]


def bias_checklist(answers: dict[str, bool]) -> dict:
    """Score against the bias self-check. `answers`: {key: bool}, YES=good.
    Missing keys are excluded from the denominator (not counted as failures)."""
    valid_keys = {item["key"] for item in BIAS_CHECKLIST}
    answered = {k: v for k, v in answers.items() if k in valid_keys}
    total = len(answered)
    passed = sum(1 for v in answered.values() if v)
    flags = [item["bias"] for item in BIAS_CHECKLIST
             if item["key"] in answered and not answered[item["key"]]]

    if total == 0:
        return {"passed": 0, "total": 0, "pct": None, "flags": [],
                "verdict": "Not yet answered", "items": BIAS_CHECKLIST}

    pct = passed / total * 100
    if pct >= 90:
        verdict = "CLEAR-HEADED — no active bias flags; the setup, not the mood, is driving this."
    elif pct >= 70:
        verdict = "MOSTLY CLEAR — a flag or two worth a second look before sizing up."
    elif pct >= 40:
        verdict = "BIAS PRESENT — several flags active; this is a good trade to slow down on, not speed up."
    else:
        verdict = "HIGH BIAS RISK — this decision looks driven by emotion/pattern more than by the setup."

    return {"passed": passed, "total": total, "pct": round(pct, 0),
            "flags": flags, "verdict": verdict, "items": BIAS_CHECKLIST}
