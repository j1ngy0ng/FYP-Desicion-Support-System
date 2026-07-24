#!/usr/bin/env python3
"""Generate disclosed, deterministic development annotations for all source rows."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path


ANNOTATION_SOURCE = (
    "Synthetic rule-based development annotation; not independent human review"
)


def number(row: dict[str, str], field: str) -> float:
    return float(row[field])


def metrics(row: dict[str, str]) -> dict[str, float]:
    impressions = number(row, "Impressions")
    clicks = number(row, "Clicks")
    leads = number(row, "Leads")
    conversions = number(row, "Conversions")
    acquisition_cost = number(row, "Acquisition_Cost")
    return {
        "roi": number(row, "ROI"),
        "engagement": number(row, "Engagement_Score"),
        "ctr": clicks / impressions if impressions else 0.0,
        "conversion_rate": conversions / clicks if clicks else 0.0,
        "lead_to_conversion": conversions / leads if leads else 0.0,
        "cost_per_conversion": acquisition_cost / conversions if conversions else acquisition_cost,
        "clicks": clicks,
        "conversions": conversions,
        "acquisition_cost": acquisition_cost,
    }


def choose_intent(values: dict[str, float], thresholds: dict[str, float]) -> str:
    if (
        values["roi"] < .5
        or values["acquisition_cost"] >= thresholds["acquisition_cost_p75"]
        or values["engagement"] <= thresholds["engagement_p25"]
    ):
        return "Survival"
    if (
        values["roi"] >= 2
        and values["conversion_rate"] >= thresholds["conversion_rate_median"]
        and values["engagement"] >= thresholds["engagement_median"]
    ):
        return "Growth"
    return "Retention"


def choose_action(
    intent: str,
    values: dict[str, float],
    thresholds: dict[str, float],
) -> tuple[str, str]:
    weak = {
        "negative ROI": values["roi"] < 0,
        "low conversion": values["conversion_rate"] < .08,
        "low CTR": values["ctr"] < .03,
        "low engagement": values["engagement"] < 5,
        "high acquisition cost": values["acquisition_cost"] >= thresholds["acquisition_cost_p75"],
    }
    strong = {
        "high ROI": values["roi"] > 2,
        "strong conversion": values["conversion_rate"] > .20,
        "strong CTR": values["ctr"] > .10,
        "strong engagement": values["engagement"] > 20,
    }
    weak_names = [name for name, active in weak.items() if active]
    strong_names = [name for name, active in strong.items() if active]
    insufficient = values["clicks"] < 500 or values["conversions"] < 50

    if insufficient:
        action = "Investigate"
        reason = (
            f"Evidence is limited ({values['clicks']:.0f} clicks, "
            f"{values['conversions']:.0f} conversions)."
        )
    elif weak_names and strong_names:
        action = "Investigate"
        reason = (
            "Signals conflict: "
            + ", ".join(strong_names[:2])
            + " versus "
            + ", ".join(weak_names[:2])
            + "."
        )
    elif intent == "Growth":
        if len(strong_names) >= 2 and values["cost_per_conversion"] <= thresholds["cpc_p75"]:
            action = "Increase"
            reason = "Growth intent is supported by " + ", ".join(strong_names[:3]) + "."
        else:
            action = "Maintain"
            reason = "Growth evidence is positive but not strong enough for controlled expansion."
    elif intent == "Survival":
        if values["roi"] < 0 or len(weak_names) >= 2:
            action = "Decrease"
            reason = "Survival intent prioritises cost protection because of " + ", ".join(weak_names[:3]) + "."
        else:
            action = "Maintain"
            reason = "Survival intent supports holding allocation while monitoring cost and return."
    else:
        if len(strong_names) >= 3 and values["cost_per_conversion"] <= thresholds["cpc_p75"]:
            action = "Increase"
            reason = "Retention performance is exceptionally strong: " + ", ".join(strong_names[:3]) + "."
        elif len(weak_names) >= 2:
            action = "Investigate"
            reason = "Retention evidence requires review because of " + ", ".join(weak_names[:3]) + "."
        else:
            action = "Maintain"
            reason = "Retention intent supports continuity with acceptable campaign evidence."

    note = (
        f"{reason} ROI={values['roi']:.2f}; "
        f"conversion={values['conversion_rate']:.1%}; "
        f"CTR={values['ctr']:.1%}; engagement={values['engagement']:.2f}; "
        f"cost/conversion={values['cost_per_conversion']:.2f}."
    )
    return action, note


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/raw/nykaa_campaign_data.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/Dataset_synthetic_development.csv"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("data/synthetic_development_summary.json"),
    )
    args = parser.parse_args()

    with args.source.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Source dataset is empty.")

    calculated = [metrics(row) for row in rows]
    thresholds = {
        "acquisition_cost_p75": percentile(
            [values["acquisition_cost"] for values in calculated], .75
        ),
        "engagement_p25": percentile(
            [values["engagement"] for values in calculated], .25
        ),
        "engagement_median": statistics.median(
            values["engagement"] for values in calculated
        ),
        "conversion_rate_median": statistics.median(
            values["conversion_rate"] for values in calculated
        ),
        "cpc_p75": percentile(
            [values["cost_per_conversion"] for values in calculated], .75
        ),
    }

    output_rows = []
    for row, values in zip(rows, calculated):
        intent = choose_intent(values, thresholds)
        action, notes = choose_action(intent, values, thresholds)
        output_rows.append({
            **row,
            "Reviewer_Intent": intent,
            "Reviewer_Action": action,
            "Reviewer_Notes": notes,
            "Annotation_Source": ANNOTATION_SOURCE,
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) + [
        "Reviewer_Intent",
        "Reviewer_Action",
        "Reviewer_Notes",
        "Annotation_Source",
    ]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "records": len(output_rows),
        "source": str(args.source).replace("\\", "/"),
        "output": str(args.output).replace("\\", "/"),
        "annotation_source": ANNOTATION_SOURCE,
        "thresholds": {key: round(value, 6) for key, value in thresholds.items()},
        "intent_distribution": dict(Counter(row["Reviewer_Intent"] for row in output_rows)),
        "action_distribution": dict(Counter(row["Reviewer_Action"] for row in output_rows)),
        "confirmatory_use_allowed": False,
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
