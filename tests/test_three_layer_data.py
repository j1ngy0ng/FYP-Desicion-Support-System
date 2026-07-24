import csv
import json
import unittest
from pathlib import Path


RAW_FIELDS = [
    "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration",
    "Channel_Used", "Impressions", "Clicks", "Leads", "Conversions",
    "Revenue", "Acquisition_Cost", "ROI", "Language", "Engagement_Score",
    "Customer_Segment", "Date",
]
AUDIT_FIELDS = [
    "Reviewer_1_Intent", "Reviewer_1_Action", "Reviewer_1_Notes",
    "Reviewer_2_Intent", "Reviewer_2_Action", "Reviewer_2_Notes",
    "Adjudicated_Intent", "Adjudicated_Action", "Adjudicated_Notes",
    "Annotation_Status",
]


def load(path: str):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class ThreeLayerDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = load("data/layers/01_raw_dataset_55555x16.csv")
        cls.processed = load("data/layers/02_processed_model_data.csv")
        cls.candidate = load("data/benchmark_candidate_125.csv")
        cls.audit = json.loads(
            Path("data/layers/IMPORT_AUDIT.json").read_text(encoding="utf-8")
        )

    def test_raw_and_processed_layers_align(self):
        self.assertEqual(len(self.raw), 55555)
        self.assertEqual(len(self.processed), 55555)
        self.assertEqual(len({row["Campaign_ID"] for row in self.raw}), 55555)
        for raw, processed in zip(self.raw, self.processed):
            self.assertEqual(
                [raw[field] for field in RAW_FIELDS],
                [processed[field] for field in RAW_FIELDS],
            )

    def test_candidate_benchmark_is_authentic_and_blank(self):
        self.assertEqual(len(self.candidate), 125)
        self.assertEqual(len({row["Campaign_ID"] for row in self.candidate}), 125)
        raw_by_id = {row["Campaign_ID"]: row for row in self.raw}
        for row in self.candidate:
            self.assertEqual(
                [row[field] for field in RAW_FIELDS],
                [raw_by_id[row["Campaign_ID"]][field] for field in RAW_FIELDS],
            )
            self.assertTrue(all(not row[field].strip() for field in AUDIT_FIELDS))

    def test_human_audited_labels_unlock_gold_gate(self):
        self.assertTrue(self.audit["gold_promoted_to_audited_benchmark"])
        self.assertTrue(self.audit["confirmatory_ready"])
        self.assertTrue(self.audit["human_provenance_attested"])
        audited = load("data/benchmark_audited.csv")
        self.assertEqual(len(audited), 125)
        self.assertTrue(all(row["Annotation_Status"] == "Audited" for row in audited))


if __name__ == "__main__":
    unittest.main()
