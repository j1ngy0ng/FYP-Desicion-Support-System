from typing import Any


def explain(action: str, confidence: float, intent: str, attribution: list[dict[str, Any]], channels: list[dict[str, Any]], activated: list[dict[str, Any]]) -> dict[str, str]:
    feature = str(attribution[0]["feature"]).replace("_", " ") if attribution else "campaign performance"
    channel = str(channels[0]["channel"]) if channels else "reported channels"
    implications = {
        "Increase": "The campaign shows enough upside to support controlled expansion.",
        "Maintain": "Current performance is balanced enough to preserve the present allocation.",
        "Decrease": "Reducing exposure can protect budget from weak or misaligned performance.",
        "Investigate": "The evidence is uncertain or contradictory, so committing budget now would add avoidable risk.",
    }
    actions = {
        "Increase": "Increase allocation gradually and review ROI and acquisition cost after seven days.",
        "Maintain": "Maintain the current plan and continue monitoring conversion and engagement.",
        "Decrease": "Decrease allocation and redirect spend only after managerial review.",
        "Investigate": "Validate the data and review channel-level performance before changing allocation.",
    }
    if activated:
        caveat = "Review required: " + "; ".join(item["detail"] for item in activated[:2]) + "."
    elif confidence < .5:
        caveat = "Low calibrated confidence; obtain more observations before relying on this recommendation."
    else:
        caveat = "Confidence is calibrated on final validation-set reasoning scores; channel attribution remains campaign-level."
    return {
        "driver": f"{feature.title()} is the strongest model driver; {channel} has the strongest historical channel evidence.",
        "implication": implications[action], "action": actions[action], "caveat": caveat,
        "intent": f"The ranking is conditioned on {intent} intent.",
    }
