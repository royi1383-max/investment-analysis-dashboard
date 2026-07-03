"""
Scoring engine — combines all module scores into a final weighted score.
"""
from config import SCORE_WEIGHTS, SCORE_LABELS


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
