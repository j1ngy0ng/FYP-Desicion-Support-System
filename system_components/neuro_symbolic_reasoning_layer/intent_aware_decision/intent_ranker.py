INTENT_ADJUSTMENTS = {
    "Growth": {"Increase": 1, "Maintain": .2, "Decrease": -1, "Investigate": -.1},
    "Retention": {"Increase": .2, "Maintain": 1, "Decrease": -.5, "Investigate": .1},
    "Survival": {"Increase": -1, "Maintain": .4, "Decrease": 1, "Investigate": .3},
}

ALLOWED_ACTIONS = {
    "Growth": {"Increase", "Maintain"},
    "Retention": {"Increase", "Maintain", "Investigate"},
    "Survival": {"Decrease", "Maintain", "Investigate"},
}


def apply_intent(scores: dict[str, float], intent: str, strength: float) -> None:
    for action, adjustment in INTENT_ADJUSTMENTS.get(intent, {}).items():
        scores[action] += strength * adjustment
