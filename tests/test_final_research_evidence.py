import copy
import unittest

from scripts.finalize_research_evidence import result_signature
from system_components.neuro_symbolic_reasoning_layer.engine import EngineResult


class FinalResearchEvidenceTests(unittest.TestCase):
    def test_result_signature_ignores_latency_but_not_decision_evidence(self):
        base = dict(
            action="Maintain", confidence=.6, raw_confidence=.55,
            performance_score=.5, confidence_level="Medium",
            ranked_actions=[{"action": "Maintain", "score": .6}],
            attribution=[], channel_attribution=[], rule_results=[],
            explanation={"driver": "ROI", "implication": "Stable", "action": "Maintain", "caveat": "Review", "intent": "Retention"},
            calibration_status="calibrated", action_evidence_status="audited_actionnet",
            decision_status="RECOMMEND", decision_reasons=[], feasible_actions=["Maintain"],
            hard_rejected_actions=[],
        )
        first = EngineResult(latency_ms=1.0, **copy.deepcopy(base))
        second = EngineResult(latency_ms=99.0, **copy.deepcopy(base))
        self.assertEqual(result_signature(first), result_signature(second))
        second.explanation["driver"] = "CTR"
        self.assertNotEqual(result_signature(first), result_signature(second))


if __name__ == "__main__":
    unittest.main()
