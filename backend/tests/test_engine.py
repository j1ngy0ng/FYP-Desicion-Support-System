import unittest
from pathlib import Path

from baseline_evaluation import load_dataset, stratified_split
from backend.app.engine import DEFAULT_RULES, RecommendationEngine, case_features
from system_components.neuro_symbolic_reasoning_layer.engine import RecommendationEngine as ComponentEngine


class RecommendationEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = RecommendationEngine(Path("data/Dataset.csv"))
        cls.rules = [
            {"id": index, "code": rule[0], "name": rule[1], "weight": rule[4], "priority": rule[5], "active": True}
            for index, rule in enumerate(DEFAULT_RULES, 1)
        ]

    def test_complete_recommendation_package(self):
        case = self.engine.test.iloc[0].to_dict()
        result = self.engine.recommend(case, self.rules, case["Intent"])
        self.assertIn(result.action, {"Increase", "Maintain", "Decrease", "Investigate"})
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

    def test_engine_and_baselines_use_identical_holdout(self):
        _, baseline_test = stratified_split(load_dataset(Path("data/Dataset.csv")), .2, 42)
        self.assertEqual(
            {row["Campaign_ID"] for row in baseline_test},
            set(self.engine.test.Campaign_ID),
        )

    def test_missing_budget_does_not_trigger_budget_rule(self):
        case = self.engine.test.iloc[0].to_dict()
        score = self.engine._rule_score(
            "budget_feasibility", "Increase", case_features(case), case["Intent"], None
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
        result = self.engine.recommend(case, [custom_rule], case["Intent"])
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
