import csv
import json
import unittest
from pathlib import Path


class HumanProvidedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with Path("data/Dataset_human_provided_development.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle))
        with Path("data/raw/nykaa_campaign_data.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.raw = list(csv.DictReader(handle))
        cls.audit = json.loads(
            Path("data/human_annotation_dataset_audit.json").read_text(
                encoding="utf-8"
            )
        )

    def test_complete_canonical_source_coverage(self):
        self.assertEqual(len(self.rows), 55555)
        self.assertEqual(len({row["Campaign_ID"] for row in self.rows}), 55555)
        raw_fields = list(self.raw[0])
        for authentic, annotated in zip(self.raw, self.rows):
            self.assertEqual(
                [annotated[field] for field in raw_fields],
                [authentic[field] for field in raw_fields],
            )

    def test_annotations_are_complete_and_development_only(self):
        for row in self.rows:
            self.assertIn(row["Reviewer_Intent"], {"Growth", "Retention", "Survival"})
            self.assertIn(
                row["Reviewer_Action"],
                {"Increase", "Maintain", "Decrease", "Investigate"},
            )
            self.assertTrue(row["Reviewer_Notes"].strip())
            self.assertEqual(row["Annotation_Status"], "DevelopmentOnly")

    def test_audit_preserves_confirmatory_gate(self):
        self.assertFalse(self.audit["confirmatory_ready"])
        self.assertEqual(
            self.audit["action_distribution"],
            {"Decrease": 25941, "Investigate": 29614},
        )
        self.assertIn(
            "Action-class coverage is incomplete; missing: Increase, Maintain",
            self.audit["confirmatory_blockers"],
        )


if __name__ == "__main__":
    unittest.main()
