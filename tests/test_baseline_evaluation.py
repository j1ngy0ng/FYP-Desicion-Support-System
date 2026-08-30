import unittest

from baseline_evaluation import (
    ACTION_ORDER,
    assert_canonical_action_order,
    conflict_reasons,
    filter_conflicting_actions,
    fit_centroid_model,
    rank_actions,
    row_has_conflict,
)


def sample_row(**overrides):
    row = {
        "ROI": 1.0,
        "conversion_rate": 0.15,
        "ctr": 0.07,
        "Engagement_Score": 12.0,
        "Intent": "Retention",
        "Clicks": 2_000,
        "Conversions": 300,
    }
    row.update(overrides)
    return row


class ConflictRuleTests(unittest.TestCase):
    def test_every_baseline_uses_the_canonical_action_index_order(self):
        self.assertEqual(ACTION_ORDER, ("Increase", "Maintain", "Reduce", "Investigate"))
        rows = []
        for action in reversed(ACTION_ORDER):
            row = sample_row()
            row.update(
                {
                    "label": action,
                    "Duration": 1.0,
                    "Impressions": 1_000.0,
                    "Leads": 100.0,
                    "Revenue": 1_000.0,
                    "Acquisition_Cost": 100.0,
                    "lead_to_conversion": 0.5,
                    "cost_per_conversion": 1.0,
                }
            )
            rows.append(row)
        labels, _, _, _ = fit_centroid_model(rows)
        self.assertEqual(tuple(labels), ACTION_ORDER)
        self.assertEqual(
            rank_actions({action: 0.25 for action in reversed(ACTION_ORDER)}),
            list(ACTION_ORDER),
        )
        with self.assertRaises(ValueError):
            assert_canonical_action_order(ACTION_ORDER[:-1])

    def test_safe_recommendation_has_no_conflict(self):
        self.assertFalse(row_has_conflict(sample_row(), "Maintain"))

    def test_intent_conflict_is_detected(self):
        reasons = conflict_reasons(sample_row(Intent="Survival"), "Increase")
        self.assertIn("intent:survival_recommended_increase", reasons)

    def test_each_weak_signal_can_conflict_with_increase(self):
        cases = [
            {"ROI": -0.1},
            {"conversion_rate": 0.07},
            {"ctr": 0.02},
            {"Engagement_Score": 4.0},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertTrue(row_has_conflict(sample_row(**values), "Increase"))

    def test_reduce_requires_two_strong_signals(self):
        one_signal = sample_row(ROI=3.0)
        two_signals = sample_row(ROI=3.0, conversion_rate=0.25)
        self.assertNotIn(
            "performance:reduce_despite_multiple_strong_signals",
            conflict_reasons(one_signal, "Reduce"),
        )
        self.assertIn(
            "performance:reduce_despite_multiple_strong_signals",
            conflict_reasons(two_signals, "Reduce"),
        )

    def test_low_evidence_conflicts_with_decisive_action(self):
        reasons = conflict_reasons(sample_row(Clicks=499), "Reduce")
        self.assertIn("evidence:decisive_action_with_insufficient_sample", reasons)

    def test_post_hoc_overlay_filters_conflicting_actions_and_renormalises(self):
        row = sample_row(Intent="Survival")
        action, confidence, rejected = filter_conflicting_actions(
            row, {"Increase": 0.7, "Maintain": 0.2, "Reduce": 0.05, "Investigate": 0.05}
        )
        self.assertIn("Increase", rejected)
        self.assertEqual(action, "Maintain")
        self.assertAlmostEqual(confidence, 2 / 3)


if __name__ == "__main__":
    unittest.main()
