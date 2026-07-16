"""Compatibility facade for the Chapter 4 reasoning components."""

from system_components.data_management_layer.data_preprocessing import case_features, prepare_frame
from system_components.neuro_symbolic_reasoning_layer.candidate_action_generation import ACTIONS
from system_components.neuro_symbolic_reasoning_layer.engine import EngineResult, RecommendationEngine, ScoringParameters
from system_components.neuro_symbolic_reasoning_layer.weighted_soft_rule_reasoning import DEFAULT_RULES

__all__ = [
    "ACTIONS", "DEFAULT_RULES", "EngineResult", "RecommendationEngine",
    "ScoringParameters", "case_features", "prepare_frame",
]
