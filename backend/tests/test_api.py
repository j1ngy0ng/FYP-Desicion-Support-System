import os
import tempfile
import unittest
import base64
from types import SimpleNamespace

handle, database_path = tempfile.mkstemp(suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{database_path.replace(chr(92), '/')}"
os.environ["TOKEN_SECRET"] = "test-secret"

from fastapi.testclient import TestClient

from backend.app.main import app, human_study_statistics


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
        self.assertIn(body["action"], {"Increase", "Maintain", "Reduce", "Investigate"})
        details = self.client.get(
            f"/api/recommendations/{body['numeric_id']}", headers=self.headers
        )
        self.assertEqual(details.status_code, 200)
        self.assertIn("rules", details.json())
        feedback = self.client.post(
            f"/api/recommendations/{body['numeric_id']}/evaluations",
            headers=self.headers,
            json={
                "actionability": 4,
                "trust_alignment": 4,
                "explanation_usefulness": 5,
                "user_acceptance": 4,
                "comments": "Clear recommendation.",
            },
        )
        self.assertEqual(feedback.status_code, 201)
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

    def test_manager_registration_profile_and_password_flow(self):
        payload = {
            "name": "Test Manager",
            "email": "manager@example.com",
            "organisation": "Test SME",
            "password": "original-password",
        }
        registered = self.client.post("/api/auth/register", json=payload)
        self.assertEqual(registered.status_code, 201)
        manager_headers = {
            "Authorization": f"Bearer {registered.json()['token']}"
        }
        profile = self.client.get("/api/profile", headers=manager_headers)
        self.assertEqual(profile.json()["role"], "manager")
        forbidden_export = self.client.get(
            "/api/human-study/export.csv", headers=manager_headers
        )
        self.assertEqual(forbidden_export.status_code, 403)
        changed = self.client.patch(
            "/api/profile/password",
            headers=manager_headers,
            json={
                "current_password": "original-password",
                "new_password": "updated-password",
            },
        )
        self.assertEqual(changed.status_code, 204)
        old_login = self.client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "original-password"},
        )
        new_login = self.client.post(
            "/api/auth/login",
            json={"email": payload["email"], "password": "updated-password"},
        )
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)

    def test_campaign_create_update_delete_flow(self):
        payload = {
            "name": "Temporary Campaign", "campaign_type": "Email",
            "intent": "Growth", "channels": "Email", "duration": 14,
        }
        created = self.client.post(
            "/api/campaigns", headers=self.headers, json=payload
        )
        self.assertEqual(created.status_code, 201)
        campaign_id = created.json()["id"]
        payload["name"] = "Updated Temporary Campaign"
        updated = self.client.put(
            f"/api/campaigns/{campaign_id}", headers=self.headers, json=payload
        )
        self.assertEqual(updated.json()["name"], payload["name"])
        deleted = self.client.delete(
            f"/api/campaigns/{campaign_id}", headers=self.headers
        )
        missing = self.client.get(
            f"/api/campaigns/{campaign_id}", headers=self.headers
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(missing.status_code, 404)

    def test_evaluation_contains_full_framework_and_ablations(self):
        response = self.client.get("/api/evaluation/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "confirmatory_technical_complete")
        self.assertEqual(body["source_records"], 55555)
        self.assertEqual(body["processed_records"], 55555)
        self.assertEqual(body["candidate_benchmark_records"], 125)
        self.assertEqual(
            body["candidate_benchmark_status"],
            "frozen_human_audited",
        )
        self.assertEqual(body["decision_cases"], 125)
        self.assertEqual(body["dataset"], "audited_benchmark")
        self.assertEqual(body["target_records"], 125)
        self.assertEqual(body["human_provided_development_records"], 55555)
        self.assertEqual(body["development_annotation_status"], "audited_human_benchmark")
        self.assertEqual(len(body["baselines"]), 4)
        self.assertIn("Macro F1", body["proposed"])
        self.assertEqual(body["calibration_status"], "calibrated")
        self.assertEqual([run["id"] for run in body["runs"]], [
            "R001", "R002", "R003", "R004", "R005", "R006",
        ])
        self.assertEqual(
            set(body["experiment_blocks"]["R006"]["conditions"]),
            {"terse_calibrated", "structured_calibrated", "full_framework"},
        )
        self.assertEqual(
            len(body["experiment_blocks"]["R004"]["systems"]),
            3,
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

    def test_blinded_human_study_flow_and_duplicate_prevention(self):
        participant = "TEST-PARTICIPANT"
        study = self.client.get("/api/human-study/cases", headers=self.headers, params={"participant_code": participant})
        self.assertEqual(study.status_code, 200)
        body = study.json()
        self.assertEqual(body["total"], 9)
        self.assertEqual(len(body["cases"]), 9)
        self.assertEqual(
            {case["presentation"] for case in body["cases"]},
            {
                "raw", "confidence_only", "structured",
                "terse", "structured_no_caveat",
            },
        )
        case = body["cases"][0]
        self.assertNotIn("condition", case)
        decoded_token = base64.urlsafe_b64decode(
            case["study_token"].encode()
        ).decode()
        self.assertFalse(
            any(condition in decoded_token for condition in (
                "raw_uncalibrated",
                "calibrated_confidence",
                "structured_uncalibrated",
                "terse_calibrated",
                "structured_calibrated",
                "full_framework",
            ))
        )
        response_payload = {
            "participant_code": participant,
            "participant_group": "Marketing practitioner",
            "study_token": case["study_token"],
            "actionability": 4,
            "specificity": 4,
            "feasibility": 3,
            "explanation_usefulness": 4,
            "reliance": 3,
            "willingness_to_review": 5,
            "user_acceptance": 4,
            "decision": "Verify before accepting",
            "decision_time_ms": 12500,
            "consent": True,
            "comments": "",
        }
        recorded = self.client.post(
            "/api/human-study/responses",
            headers=self.headers,
            json=response_payload,
        )
        duplicate = self.client.post(
            "/api/human-study/responses",
            headers=self.headers,
            json=response_payload,
        )
        self.assertEqual(recorded.status_code, 201)
        self.assertEqual(recorded.json()["recorded"], True)
        self.assertNotIn("condition", recorded.json())
        self.assertEqual(duplicate.status_code, 409)
        exported = self.client.get(
            "/api/human-study/export.csv", headers=self.headers
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("Participant_Code", exported.text)
        self.assertIn(participant, exported.text)
        self.assertNotIn("comments", exported.text.lower())

    def test_human_study_statistics_detect_overtrust_and_alignment(self):
        rows = [
            SimpleNamespace(participant_code="P1", participant_group="Marketing practitioner", correct=False, low_confidence=False, reliance=5, decision="Accept without checking", actionability=3, specificity=4, feasibility=3, explanation_usefulness=4, willingness_to_review=5, user_acceptance=3, decision_time_ms=10000),
            SimpleNamespace(participant_code="P2", participant_group="Non-practitioner", correct=True, low_confidence=False, reliance=5, decision="Accept without checking", actionability=5, specificity=5, feasibility=4, explanation_usefulness=4, willingness_to_review=4, user_acceptance=5, decision_time_ms=20000),
        ]
        result = human_study_statistics(rows)
        self.assertEqual(result["participants"], 2)
        self.assertEqual(result["actionability"]["mean"], 4)
        self.assertEqual(result["trust_alignment"]["mean"], .5)
        self.assertEqual(result["overtrust_rate"], 1)
        self.assertEqual(result["decision_time_seconds"]["mean"], 15)


if __name__ == "__main__":
    unittest.main()
