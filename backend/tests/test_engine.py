import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from backend.app.engine import DEFAULT_RULES, RecommendationEngine, case_features, prepare_frame
from system_components.neuro_symbolic_reasoning_layer.engine import RecommendationEngine as ComponentEngine


class RecommendationEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RecommendationEngine(Path("data/layers/02_processed_model_data.csv"))
        cls.rules = [
            {"id": index, "code": rule[0], "name": rule[1], "weight": rule[4], "priority": rule[5], "active": True}
            for index, rule in enumerate(DEFAULT_RULES, 1)
        ]

    def test_complete_recommendation_package(self):
        case = self.engine.test.iloc[0].to_dict()
        result = self.engine.recommend(case, self.rules, "Growth")
        self.assertIn(result.action, {"Increase", "Maintain", "Reduce", "Investigate"})
        self.assertAlmostEqual(sum(item["score"] for item in result.ranked_actions), 1, places=3)
        self.assertEqual(set(result.explanation), {"driver", "implication", "action", "caveat", "intent"})
        self.assertTrue(result.attribution)

    def test_backend_uses_architecture_component(self):
        self.assertIs(RecommendationEngine, ComponentEngine)

    def test_survival_penalises_increase(self):
        case = self.engine.test.iloc[0].to_dict()
        result = self.engine.recommend(case, self.rules, "Survival")
        safeguard = [item for item in result.rule_results if item["code"] == "survival_safeguard"]
        self.assertTrue(safeguard and safeguard[0]["triggered"])

    def test_chronological_holdout_is_used(self):
        self.assertLessEqual(self.engine.train.Date.max(), self.engine.validation.Date.min())
        self.assertLessEqual(self.engine.validation.Date.max(), self.engine.test.Date.min())

    def test_missing_values_use_training_partition_median_only(self):
        rows = []
        for index, roi in enumerate([1, 3, None, None], 1):
            rows.append({
                "Campaign_ID": f"C{index}", "Date": f"2026-01-0{index}",
                "Duration": 1, "Impressions": 100, "Clicks": 10, "Leads": 5,
                "Conversions": 2, "Revenue": 20, "Acquisition_Cost": 5,
                "ROI": roi, "Engagement_Score": 4,
            })
        with TemporaryDirectory() as directory:
            path = Path(directory) / "missing.csv"
            pd.DataFrame(rows).to_csv(path, index=False)
            frame = prepare_frame(path, imputation_fit_fraction=.50)
        self.assertEqual(frame.attrs["imputation_fit_rows"], 2)
        self.assertEqual(frame.attrs["imputation_medians"]["ROI"], 2)
        self.assertEqual(frame.iloc[2]["ROI"], 2)
        self.assertEqual(frame.iloc[3]["ROI"], 2)

    def test_active_dataset_contains_no_generated_annotations(self):
        forbidden = {
            "Intent", "Reference_Action", "Justification",
            "Reviewer_1_Label", "Reviewer_2_Label",
        }
        self.assertFalse(forbidden.intersection(self.engine.data.columns))

    def test_missing_budget_does_not_trigger_budget_rule(self):
        case = self.engine.test.iloc[0].to_dict()
        score = self.engine._rule_score(
            "budget_feasibility", "Increase", case_features(case), "Growth", None
        )
        self.assertIsNone(score)

    def test_custom_threshold_rule_is_executed(self):
        case = self.engine.test.iloc[0].to_dict()
        case["ROI"] = 3
        custom_rule = {
            "id": 99, "code": "custom_test", "name": "High ROI check", "weight": 1,
            "priority": 2, "active": True,
            "definition": {"kind": "threshold", "metric": "ROI", "operator": "gt", "threshold": 2, "action": "Increase", "intent": None},
        }
        result = self.engine.recommend(case, [custom_rule], "Growth")
        matches = [item for item in result.rule_results if item["code"] == "custom_test"]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["triggered"])

    def test_intent_specific_custom_rule_is_excluded_from_intent_ablation(self):
        case = self.engine.test.iloc[0].to_dict()
        custom_rule = {
            "id": 100, "code": "custom_intent", "name": "Growth ROI check", "weight": 1,
            "priority": 2, "active": True,
            "definition": {"kind": "threshold", "metric": "ROI", "operator": "gt", "threshold": -99, "action": "Increase", "intent": "Growth"},
        }
        result = self.engine.recommend(case, [custom_rule], "Growth", ablation="without_intent")
        self.assertFalse(any(item["code"] == "custom_intent" for item in result.rule_results))

    def test_backbone_ablation_really_disables_intent_and_rules(self):
        case = self.engine.test.iloc[0].to_dict()
        growth = self.engine.recommend(case, self.rules, "Growth", ablation="backbone")
        survival = self.engine.recommend(case, self.rules, "Survival", ablation="backbone")
        self.assertEqual(growth.action, survival.action)
        self.assertEqual(growth.ranked_actions, survival.ranked_actions)
        self.assertFalse(growth.rule_results)


if __name__ == "__main__":
    unittest.main()
