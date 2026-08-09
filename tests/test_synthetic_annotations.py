import csv
import unittest
from pathlib import Path


class SyntheticDevelopmentDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with Path("data/Dataset_synthetic_development.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_complete_source_coverage_and_provenance(self):
        self.assertEqual(len(self.rows), 55_555)
        self.assertEqual(len({row["Campaign_ID"] for row in self.rows}), 55_555)
        self.assertTrue(
            all(
                row["Annotation_Source"]
                == "Synthetic rule-based development annotation; not independent human review"
                for row in self.rows
            )
        )

    def test_annotations_are_complete_and_use_controlled_values(self):
        self.assertTrue(
            all(
                row["Reviewer_Intent"] in {"Survival", "Retention", "Growth"}
                and row["Reviewer_Action"]
                in {"Increase", "Maintain", "Reduce", "Investigate"}
                and row["Reviewer_Notes"].strip()
                for row in self.rows
            )
        )

    def test_synthetic_actions_respect_intent_compatibility(self):
        forbidden = {
            ("Growth", "Reduce"),
            ("Survival", "Increase"),
            ("Retention", "Reduce"),
        }
        self.assertFalse(
            any(
                (row["Reviewer_Intent"], row["Reviewer_Action"]) in forbidden
                for row in self.rows
            )
        )


if __name__ == "__main__":
    unittest.main()
