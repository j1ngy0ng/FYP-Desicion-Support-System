from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from baseline_evaluation import canonical_action


FEATURES = (
    "Duration", "Impressions", "Clicks", "Leads", "Conversions", "Revenue",
    "Acquisition_Cost", "ROI", "Engagement_Score", "ctr", "conversion_rate",
    "lead_to_conversion", "cost_per_conversion",
)


def benchmark_label(row: pd.Series) -> str:
    reviewer_1 = canonical_action(str(row.get("Reviewer_1_Label", "")))
    reviewer_2 = canonical_action(str(row.get("Reviewer_2_Label", "")))
    reference = canonical_action(str(row.get("Reference_Action", "")))
    return (reviewer_1 if reviewer_1 and reviewer_1 == reviewer_2 else reference).replace("Reduce", "Decrease")


def prepare_frame(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path).drop_duplicates().copy()
    derived = {"ctr", "conversion_rate", "lead_to_conversion", "cost_per_conversion"}
    for field in (field for field in FEATURES if field not in derived):
        data[field] = pd.to_numeric(data[field], errors="coerce").fillna(data[field].median())
    data["ctr"] = np.where(data.Impressions > 0, data.Clicks / data.Impressions, 0)
    data["conversion_rate"] = np.where(data.Clicks > 0, data.Conversions / data.Clicks, 0)
    data["lead_to_conversion"] = np.where(data.Leads > 0, data.Conversions / data.Leads, 0)
    data["cost_per_conversion"] = np.where(data.Conversions > 0, data.Acquisition_Cost / data.Conversions, data.Acquisition_Cost)
    data["model_label"] = data.apply(benchmark_label, axis=1)
    data["label"] = data.model_label
    data["Intent"] = data.Intent.astype(str).str.title()
    return data


def case_features(case: dict[str, Any]) -> dict[str, float]:
    def number(name: str) -> float:
        return float(case.get(name, case.get(name.lower(), 0)) or 0)

    impressions, clicks, leads, conversions = (number(name) for name in ("Impressions", "Clicks", "Leads", "Conversions"))
    acquisition_cost = number("Acquisition_Cost")
    return {
        "Duration": number("Duration"), "Impressions": impressions, "Clicks": clicks,
        "Leads": leads, "Conversions": conversions, "Revenue": number("Revenue"),
        "Acquisition_Cost": acquisition_cost, "ROI": number("ROI"),
        "Engagement_Score": number("Engagement_Score"),
        "ctr": clicks / impressions if impressions else 0,
        "conversion_rate": conversions / clicks if clicks else 0,
        "lead_to_conversion": conversions / leads if leads else 0,
        "cost_per_conversion": acquisition_cost / conversions if conversions else acquisition_cost,
    }
