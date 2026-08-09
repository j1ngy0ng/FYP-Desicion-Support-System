from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


FEATURES = (
    "Duration", "Impressions", "Clicks", "Leads", "Conversions", "Revenue",
    "Acquisition_Cost", "ROI", "Engagement_Score", "ctr", "conversion_rate",
    "lead_to_conversion", "cost_per_conversion",
)


def prepare_frame(path: Path, *, imputation_fit_fraction: float = .70) -> pd.DataFrame:
    """Prepare a chronological frame using training-only numeric medians."""
    if not 0 < imputation_fit_fraction <= 1:
        raise ValueError("imputation_fit_fraction must be in the interval (0, 1].")
    data = pd.read_csv(path).drop_duplicates().copy()
    forbidden = {
        "Intent",
        "Reference_Action",
        "Justification",
        "Reviewer_1_Label",
        "Reviewer_2_Label",
    }
    present = sorted(forbidden.intersection(data.columns))
    if present:
        raise ValueError(
            "AI-generated annotation columns are forbidden in the active campaign dataset: "
            + ", ".join(present)
        )
    date_values = data["Date"].astype(str).str.strip().str.replace("/", "-", regex=False)
    day_first = date_values.str.match(r"^\d{1,2}-\d{1,2}-\d{4}$")
    year_first = date_values.str.match(r"^\d{4}-\d{1,2}-\d{1,2}$")
    if day_first.all():
        data["Date"] = pd.to_datetime(date_values, errors="raise", format="%d-%m-%Y")
    elif year_first.all():
        data["Date"] = pd.to_datetime(date_values, errors="raise", format="%Y-%m-%d")
    else:
        raise ValueError("Date must consistently use D-M-YYYY or YYYY-M-D format.")
    data = data.sort_values(["Date", "Campaign_ID"]).reset_index(drop=True)

    derived = {"ctr", "conversion_rate", "lead_to_conversion", "cost_per_conversion"}
    numeric_fields = [field for field in FEATURES if field not in derived]
    for field in numeric_fields:
        data[field] = pd.to_numeric(data[field], errors="coerce")
    fit_end = max(1, int(len(data) * imputation_fit_fraction))
    medians = data.iloc[:fit_end][numeric_fields].median()
    missing_medians = medians[medians.isna()].index.tolist()
    if missing_medians:
        raise ValueError(
            "Training partition has no numeric values for: " + ", ".join(missing_medians)
        )
    data[numeric_fields] = data[numeric_fields].fillna(medians)
    data["ctr"] = np.where(data.Impressions > 0, data.Clicks / data.Impressions, 0)
    data["conversion_rate"] = np.where(data.Clicks > 0, data.Conversions / data.Clicks, 0)
    data["lead_to_conversion"] = np.where(data.Leads > 0, data.Conversions / data.Leads, 0)
    data["cost_per_conversion"] = np.where(data.Conversions > 0, data.Acquisition_Cost / data.Conversions, data.Acquisition_Cost)
    data.attrs["imputation_fit_rows"] = fit_end
    data.attrs["imputation_medians"] = medians.to_dict()
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
