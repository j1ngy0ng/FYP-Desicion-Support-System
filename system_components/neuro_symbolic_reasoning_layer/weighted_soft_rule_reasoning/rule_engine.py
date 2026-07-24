import operator
from typing import Any

from ..candidate_action_generation import ACTIONS


DEFAULT_RULES = (
    ("negative_roi", "Negative ROI protection", "Performance", "Penalise Increase when ROI is negative", .95, 3),
    ("low_conversion", "Low conversion protection", "Performance", "Penalise Increase when conversion rate is below 8%", .80, 2),
    ("low_ctr", "Low CTR protection", "Performance", "Penalise Increase when CTR is below 3%", .75, 2),
    ("low_engagement", "Low engagement protection", "Performance", "Penalise Increase when engagement is below 5", .70, 2),
    ("evidence_sufficiency", "Evidence sufficiency", "Evidence", "Penalise decisive action below 500 clicks or 50 conversions", .85, 3),
    ("strong_signal", "Strong signal protection", "Performance", "Penalise Reduce when at least two performance signals are strong", .85, 2),
    ("exceptional_performance", "Exceptional performance", "Performance", "Penalise Maintain when all core signals are exceptional", .70, 1),
    ("growth_safeguard", "Growth intent safeguard", "Intent", "Penalise Reduce under Growth intent", .90, 3),
    ("survival_safeguard", "Survival intent safeguard", "Intent", "Penalise Increase under Survival intent", .90, 3),
    ("retention_safeguard", "Retention intent safeguard", "Intent", "Penalise Reduce under Retention intent", .75, 2),
    ("high_cpa", "Acquisition cost protection", "Cost", "Penalise Increase when acquisition cost exceeds revenue per conversion", .80, 2),
    ("channel_saturation", "Channel saturation", "Channel", "Penalise Increase when exposure is high but CTR is weak", .70, 2),
    ("budget_feasibility", "Budget feasibility", "Budget", "Penalise Increase when budget cannot support 50 additional acquisitions", .80, 2),
    ("conflicting_evidence", "Conflicting evidence", "Risk", "Favour Investigate when strong and weak signals conflict", .75, 2),
)

INTENT_RULES = {"growth_safeguard", "retention_safeguard", "survival_safeguard"}
COMPARISONS = {"lt": operator.lt, "lte": operator.le, "gt": operator.gt, "gte": operator.ge, "eq": operator.eq}


def evaluate_rule(code: str, action: str, features: dict[str, float], intent: str, budget: float | None, definition: dict[str, Any] | None = None) -> tuple[float, str] | None:
    if definition:
        if action != definition.get("action") or definition.get("intent") not in {None, intent}:
            return None
        metric = definition.get("metric")
        actual = budget if metric == "budget" else features.get(metric)
        comparison = COMPARISONS.get(definition.get("operator"))
        if actual is None or comparison is None:
            return None
        violated = comparison(float(actual), float(definition["threshold"]))
        return (0.0 if violated else 1.0, f"{metric} is {float(actual):g}")

    roi, conversion, ctr, engagement = features["ROI"], features["conversion_rate"], features["ctr"], features["Engagement_Score"]
    strong = sum((roi > 2, conversion > .20, ctr > .10, engagement > 20))
    weak = sum((roi < 0, conversion < .08, ctr < .03, engagement < 5))
    if code == "budget_feasibility" and budget is None:
        return None
    checks = {
        "negative_roi": (action == "Increase", roi >= 0, f"ROI is {roi:.2f}"),
        "low_conversion": (action == "Increase", conversion >= .08, f"Conversion rate is {conversion:.1%}"),
        "low_ctr": (action == "Increase", ctr >= .03, f"CTR is {ctr:.1%}"),
        "low_engagement": (action == "Increase", engagement >= 5, f"Engagement score is {engagement:.1f}"),
        "evidence_sufficiency": (action in {"Increase", "Reduce"}, features["Clicks"] >= 500 and features["Conversions"] >= 50, f"Evidence contains {features['Clicks']:.0f} clicks and {features['Conversions']:.0f} conversions"),
        "strong_signal": (action == "Reduce", strong < 2, f"{strong} strong performance signals detected"),
        "exceptional_performance": (action == "Maintain", not (roi > 4 and conversion > .20 and ctr > .10 and engagement > 20), "All core performance signals are exceptional"),
        "growth_safeguard": (action == "Reduce" and intent == "Growth", False, "Reduce conflicts with Growth intent"),
        "survival_safeguard": (action == "Increase" and intent == "Survival", False, "Increase conflicts with Survival intent"),
        "retention_safeguard": (action == "Reduce" and intent == "Retention", False, "Reduce conflicts with Retention intent"),
        "high_cpa": (action == "Increase", features["cost_per_conversion"] <= (features["Revenue"] / features["Conversions"] if features["Conversions"] else 0), f"Cost per conversion is {features['cost_per_conversion']:.2f}"),
        "channel_saturation": (action == "Increase", not (features["Impressions"] > 50000 and ctr < .05), "High exposure is paired with weak CTR"),
        "budget_feasibility": (action == "Increase", float(budget or 0) >= features["cost_per_conversion"] * 50, "Budget should support at least 50 additional conversions"),
        "conflicting_evidence": (action != "Investigate" and strong > 0 and weak > 0, False, "Strong and weak signals conflict"),
    }
    check = checks.get(code)
    if not check:
        return None
    applies, satisfied, detail = check
    return (1.0 if satisfied else 0.0, detail) if applies else None


def apply_rules(scores: dict[str, float], rules: list[dict[str, Any]], features: dict[str, float], intent: str, budget: float | None, penalty: float, investigate_boost: float, without_intent: bool = False) -> list[dict[str, Any]]:
    results = []
    for rule in rules:
        definition = rule.get("definition") or {}
        if not rule.get("active", True) or without_intent and (rule["code"] in INTENT_RULES or definition.get("intent")):
            continue
        for action in ACTIONS:
            result = evaluate_rule(rule["code"], action, features, intent, budget, definition or None)
            if result is None:
                continue
            satisfaction, detail = result
            weight = float(rule["weight"])
            if not satisfaction:
                scores[action] -= weight * max(1, int(rule.get("priority", 1))) * penalty
                if action != "Investigate":
                    scores["Investigate"] += weight * investigate_boost
            results.append({"id": rule.get("id"), "code": rule["code"], "name": rule["name"], "action": action, "score": satisfaction, "triggered": not bool(satisfaction), "detail": detail})
    return results
