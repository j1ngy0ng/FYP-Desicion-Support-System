import os
import tempfile
import unittest
import base64
from types import SimpleNamespace

handle, database_path = tempfile.mkstemp(suffix=".db")
os.close(handle)
os.environ["DATABASE_URL"] = f"sqlite:///{database_path.replace(chr(92), '/')}"
os.environ["TOKEN_SECRET"] = "test-secret"
os.environ["ETHICS_APPROVAL_REFERENCE"] = "TEST-APPROVAL-NOT-FOR-RESEARCH"

from fastapi.testclient import TestClient
from unittest.mock import patch

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
        self.assertEqual(body["action_evidence_status"], "audited_actionnet")
        self.assertEqual(body["evidence"]["action_evidence_status"], "audited_actionnet")
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
        imported = self.client.get(
            "/api/campaigns/IMPORT-1", headers=self.headers
        )
        self.assertIsNone(imported.json()["budget"])

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
        rule = self.client.get("/api/rules", headers=manager_headers).json()[0]
        forbidden_create = self.client.post(
            "/api/rules",
            headers=manager_headers,
            json={
                "name": "Manager must not create this rule",
                "metric": "ROI",
                "operator": "lt",
                "threshold": 0,
                "action": "Increase",
                "intent": None,
                "weight": .8,
                "priority": 2,
                "active": True,
            },
        )
        forbidden_update = self.client.patch(
            f"/api/rules/{rule['id']}",
            headers=manager_headers,
            json={
                "name": rule["name"],
                "weight": rule["weight"],
                "priority": rule["priority"],
                "active": rule["active"],
            },
        )
        self.assertEqual(forbidden_create.status_code, 403)
        self.assertEqual(forbidden_update.status_code, 403)
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
            "intent": "Growth", "channels": " google, EMAIL, Google ", "duration": 14,
        }
        created = self.client.post(
            "/api/campaigns", headers=self.headers, json=payload
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["channel"], "Email, Google")
        self.assertIsNone(created.json()["budget"])
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

    def test_budget_null_zero_and_positive_are_distinct(self):
        base = {
            "name": "Budget Semantics", "campaign_type": "Email",
            "intent": "Growth", "channels": "Email", "duration": 14,
        }
        omitted = self.client.post(
            "/api/campaigns", headers=self.headers, json=base
        )
        explicit_zero = self.client.post(
            "/api/campaigns", headers=self.headers, json={**base, "budget": 0}
        )
        positive = self.client.post(
            "/api/campaigns", headers=self.headers, json={**base, "budget": 5000}
        )
        self.assertEqual(omitted.status_code, 201)
        self.assertIsNone(omitted.json()["budget"])
        self.assertEqual(explicit_zero.json()["budget"], 0)
        self.assertEqual(positive.json()["budget"], 5000)

    def test_campaign_rejects_unsupported_channel(self):
        response = self.client.post(
            "/api/campaigns",
            headers=self.headers,
            json={
                "name": "Invalid Channel Campaign",
                "campaign_type": "Paid Ads",
                "intent": "Growth",
                "channels": "Google Ads",
            },
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("Unsupported channel", response.text)

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

    def test_audited_benchmark_cases_are_active_campaigns(self):
        response = self.client.get("/api/campaigns", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        campaigns = response.json()
        audited = [item for item in campaigns if item["id"].startswith("NY-CMP-")]
        self.assertEqual(len(audited), 125)
        self.assertTrue(all(item["status"] == "Active" for item in audited))
        self.assertTrue(all(item["budget"] is None for item in audited))
        self.assertEqual(sum(item["status"] == "Active" for item in campaigns), 127)

    def test_seeded_admin_can_login_create_and_update_rule(self):
        login = self.client.post(
            "/api/auth/login",
            json={"email": "jingyong@example.com", "password": "prototype"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "admin")
        admin_headers = {
            "Authorization": f"Bearer {login.json()['token']}"
        }
        payload = {
            "name": "Protect high-cost expansion", "metric": "cost_per_conversion",
            "operator": "gt", "threshold": 100, "action": "Increase", "intent": None,
            "weight": .8, "priority": 2, "active": True,
        }
        created = self.client.post("/api/rules", headers=admin_headers, json=payload)
        duplicate = self.client.post("/api/rules", headers=admin_headers, json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["definition"]["metric"], "cost_per_conversion")
        self.assertEqual(duplicate.status_code, 409)
        updated = self.client.patch(
            f"/api/rules/{created.json()['id']}",
            headers=admin_headers,
            json={
                "name": "Protect costly expansion",
                "weight": .9,
                "priority": 3,
                "active": False,
            },
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["name"], "Protect costly expansion")
        self.assertEqual(updated.json()["weight"], .9)
        self.assertEqual(updated.json()["priority"], 3)
        self.assertFalse(updated.json()["active"])

    def test_human_study_is_locked_without_ethics_reference(self):
        with patch("backend.app.main.ETHICS_APPROVAL_REFERENCE", ""):
            response = self.client.get(
                "/api/human-study/cases?participant_code=LOCKED-TEST",
                headers=self.headers,
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn("ethics approval or exemption", response.text)

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
