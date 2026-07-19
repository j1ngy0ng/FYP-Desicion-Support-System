import os
import tempfile
import unittest

handle, database_path = tempfile.mkstemp(suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{database_path.replace(chr(92), '/')}"
os.environ["TOKEN_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from backend.app.main import app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()
        response = self.client.post("/api/auth/login", json={"email": "jingyong@example.com", "password": "prototype"})
        self.assertEqual(response.status_code, 200)
        self.headers = {"Authorization": f"Bearer {response.json()['token']}"}

    def tearDown(self):
        self.client.__exit__(None, None, None)

    @classmethod
    def tearDownClass(cls):
        from backend.app.database import engine
        engine.dispose()
        os.remove(database_path)

    def test_campaign_to_recommendation_flow(self):
        campaigns = self.client.get("/api/campaigns", headers=self.headers)
        self.assertEqual(campaigns.status_code, 200)
        campaign_id = campaigns.json()[0]["id"]
        generated = self.client.post("/api/recommendations", headers=self.headers, json={"campaign_id": campaign_id, "risk_tolerance": "Balanced"})
        self.assertEqual(generated.status_code, 201)
        body = generated.json()
        self.assertIn(body["action"], {"Increase", "Maintain", "Decrease", "Investigate"})
        decided = self.client.patch(f"/api/recommendations/{body['numeric_id']}/decision", headers=self.headers, json={"decision": "Accepted"})
        self.assertEqual(decided.json()["status"], "Accepted")

    def test_campaign_import_is_idempotent(self):
        csv_data = (
            "Campaign_ID,Campaign_Type,Channel_Used,Intent,Language,Customer_Segment,Date\n"
            "IMPORT-1,Email,Email,Growth,English,SME,2026-01-15\n"
            "IMPORT-1,Email,Email,Growth,English,SME,2026-01-15\n"
        )
        files = {"file": ("campaigns.csv", csv_data, "text/csv")}
        first = self.client.post("/api/campaigns/import", headers=self.headers, files=files)
        second = self.client.post("/api/campaigns/import", headers=self.headers, files=files)
        self.assertEqual(first.json(), {"imported": 1, "skipped": 1})
        self.assertEqual(second.json(), {"imported": 0, "skipped": 2})

    def test_evaluation_contains_full_framework_and_ablations(self):
        response = self.client.get("/api/evaluation/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["baselines"]), 4)
        self.assertTrue(body["baselines"][3]["Baseline"].startswith("Baseline D"))
        self.assertIn("Recommendation Accuracy", body["proposed"])
        self.assertEqual(len(body["ablations"]), 4)
        self.assertTrue(body["protocol"]["identical_holdout"])
        self.assertEqual(body["protocol"]["test_cases"], 26)
        self.assertIn("Recommendation Accuracy", body["proposed_ci"])
        self.assertIn("Actionability Proxy", body["proposed"])
        self.assertLess(
            body["proposed"]["Logical Conflict Rate"],
            body["ablations"]["Without Soft-Rule Reasoning"]["Logical Conflict Rate"],
        )
        self.assertLess(
            body["proposed"]["Expected Calibration Error (ECE)"],
            body["ablations"]["Without Trust Calibration"]["Expected Calibration Error (ECE)"],
        )
        self.assertGreater(
            body["proposed"]["Scenario-Fit Rate"],
            body["ablations"]["Without Intent Awareness"]["Scenario-Fit Rate"],
        )

    def test_admin_can_create_rule_without_equivalent_duplicate(self):
        payload = {
            "name": "Protect high-cost expansion", "metric": "cost_per_conversion",
            "operator": "gt", "threshold": 100, "action": "Increase", "intent": None,
            "weight": .8, "priority": 2, "active": True,
        }
        created = self.client.post("/api/rules", headers=self.headers, json=payload)
        duplicate = self.client.post("/api/rules", headers=self.headers, json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["definition"]["metric"], "cost_per_conversion")
        self.assertEqual(duplicate.status_code, 409)


if __name__ == "__main__":
    unittest.main()
