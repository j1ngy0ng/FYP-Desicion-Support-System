import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import numpy as np

from backend.app.engine import DEFAULT_RULES, RecommendationEngine, case_features, prepare_frame
from system_components.neuro_symbolic_reasoning_layer.engine import selective_decision_status
from system_components.neuro_symbolic_reasoning_layer.engine import RecommendationEngine as ComponentEngine


class RecommendationEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RecommendationEngine(
            Path("data/layers/02_processed_model_data.csv"),
            audited_benchmark=Path("data/benchmark_audited.csv"),
        )
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
        self.assertEqual(result.action_evidence_status, "audited_actionnet")
        self.assertIn(result.decision_status, {
            "RECOMMEND", "CHECK ADVISED", "HUMAN REVIEW REQUIRED", "NO SAFE RECOMMENDATION",
        })
        self.assertIn(result.coverage_status, {"IN_SCOPE", "OUT_OF_BENCHMARK_COVERAGE"})

    def test_selective_policy_exposes_all_four_states(self):
        ranked = [
            {"action": "Maintain", "score": .36},
            {"action": "Increase", "score": .33},
        ]
        self.assertEqual(
            selective_decision_status("Maintain", .36, ranked, [], 1000)[0],
            "RECOMMEND",
        )
        low_confidence = [
            {"action": "Maintain", "score": .34},
            {"action": "Increase", "score": .20},
        ]
        self.assertEqual(
            selective_decision_status("Maintain", .34, low_confidence, [], 1000)[0],
            "CHECK ADVISED",
        )
        low_margin = [
            {"action": "Maintain", "score": .36},
            {"action": "Increase", "score": .35},
        ]
        self.assertEqual(
            selective_decision_status("Maintain", .36, low_margin, [], 1000)[0],
            "CHECK ADVISED",
        )
        self.assertEqual(
            selective_decision_status("Investigate", .7, ranked, [], 1000)[0],
            "HUMAN REVIEW REQUIRED",
        )
        self.assertEqual(
            selective_decision_status(
                "Maintain", .8, ranked, [], 1000, no_safe_action=True
            )[0],
            "NO SAFE RECOMMENDATION",
        )
        self.assertEqual(
            selective_decision_status("Increase", .8, ranked, [], None)[0],
            "HUMAN REVIEW REQUIRED",
        )
        self.assertEqual(
            selective_decision_status(
                "Maintain", .8, ranked, [], 1000,
                coverage_reasons=["Outside the training benchmark range: ROI."],
            )[0],
            "HUMAN REVIEW REQUIRED",
        )

    def test_training_envelope_detector_routes_out_of_coverage_case_to_review(self):
        case = self.engine.test.iloc[0].to_dict()
        case["Duration"] = self.engine.coverage_bounds["Duration"][1] + 1
        result = self.engine.recommend(case, self.rules, "Growth")
        self.assertEqual(result.coverage_status, "OUT_OF_BENCHMARK_COVERAGE")
        self.assertIn("Duration", result.coverage_reasons[0])
        self.assertEqual(result.decision_status, "HUMAN REVIEW REQUIRED")

    def test_channel_evidence_accepts_csv_text_and_prepared_lists(self):
        text = self.engine.predictive.channels({"Channel_Used": "Email, Facebook"})
        prepared = self.engine.predictive.channels({"channels": ["Email", "Facebook"]})
        self.assertEqual(text, prepared)

    def test_explanation_and_review_gate_ablations_are_isolated(self):
        case = self.engine.test.iloc[0].to_dict()
        full = self.engine.recommend(case, self.rules, "Growth")
        without_explanation = self.engine.recommend(
            case, self.rules, "Growth", ablation="without_explanation"
        )
        self.assertEqual(without_explanation.action, full.action)
        self.assertEqual(without_explanation.ranked_actions, full.ranked_actions)
        self.assertEqual(without_explanation.explanation, {})
        for row in self.engine.validation.to_dict("records") + self.engine.test.to_dict("records"):
            gated = self.engine.recommend(row, self.rules, "Growth")
            if gated.decision_status == "CHECK ADVISED":
                ungated = self.engine.recommend(
                    row, self.rules, "Growth", ablation="without_review_gate"
                )
                self.assertEqual(ungated.action, gated.action)
                self.assertEqual(ungated.decision_status, "RECOMMEND")
                break
        else:
            self.fail("Expected at least one CHECK ADVISED case for the review-gate ablation")

    def test_backend_uses_architecture_component(self):
        self.assertIs(RecommendationEngine, ComponentEngine)

    def test_survival_penalises_increase(self):
        case = self.engine.test.iloc[0].to_dict()
        result = self.engine.recommend(case, self.rules, "Survival")
        safeguard = [item for item in result.rule_results if item["code"] == "survival_safeguard"]
        self.assertTrue(safeguard and safeguard[0]["triggered"])
        self.assertIn("Increase", result.hard_rejected_actions)

    def test_conflicting_evidence_reaches_no_safe_recommendation(self):
        case = self.engine.test.iloc[0].to_dict()
        case.update({"ROI": 3, "Clicks": 1000, "Conversions": 60, "Impressions": 100000, "Engagement_Score": 2})
        result = self.engine.recommend(case, self.rules, "Retention")
        self.assertEqual(result.decision_status, "NO SAFE RECOMMENDATION")
        self.assertEqual(set(result.hard_rejected_actions), {"Increase", "Maintain", "Reduce"})
        self.assertEqual(result.action, "Investigate")

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

    def test_explicit_zero_and_positive_budget_are_evaluated(self):
        case = self.engine.test.iloc[0].to_dict()
        features = case_features(case)
        zero = self.engine._rule_score(
            "budget_feasibility", "Increase", features, "Growth", 0
        )
        positive = self.engine._rule_score(
            "budget_feasibility", "Increase", features, "Growth", 1_000_000_000
        )
        self.assertEqual(zero[0], 0.0)
        self.assertEqual(positive[0], 1.0)

    def test_actionnet_fallback_is_explicit(self):
        with TemporaryDirectory() as directory:
            dataset = Path(directory) / "campaigns.csv"
            self.engine.data.to_csv(dataset, index=False)
            fallback_engine = ComponentEngine(dataset)
            result = fallback_engine.recommend(
                fallback_engine.test.iloc[0].to_dict(), self.rules, "Growth"
            )
        self.assertEqual(result.action_evidence_status, "campaignnet_only_fallback")
        self.assertIn("CampaignNet evidence only", result.explanation["caveat"])

    def test_audited_actionnet_status_is_explicit(self):
        result = self.engine.recommend(
            self.engine.test.iloc[0].to_dict(), self.rules, "Growth"
        )
        self.assertEqual(result.action_evidence_status, "audited_actionnet")
        self.assertNotIn("CampaignNet evidence only", result.explanation["caveat"])

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

    def test_branch_ablations_isolate_campaign_action_and_fused_evidence(self):
        case = self.engine.test.iloc[0].to_dict()
        campaign = self.engine._score(
            case, self.rules, "Growth", "campaignnet_only", self.engine.scoring
        )
        action = self.engine._score(
            case, self.rules, "Growth", "actionnet_only", self.engine.scoring
        )
        fused = self.engine._score(
            case, self.rules, "Growth", "fused_evidence", self.engine.scoring
        )
        self.assertTrue(all(not result for result in (campaign[1], action[1], fused[1])))
        np.testing.assert_allclose(
            fused[2], .25 * campaign[2] + .75 * action[2], rtol=1e-6, atol=1e-6
        )


if __name__ == "__main__":
    unittest.main()
