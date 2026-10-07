export type User = { name: string; email: string; role: string; organisation: string }
export type Campaign = {
  id: string; name: string; type: string; intent: 'Growth' | 'Retention' | 'Survival'; channel: string;
  status: 'Active' | 'Review' | 'Completed'; roi: number; conversion: number; budget: number | null;
  target_audience: string; duration: number; impressions: number; clicks: number; leads: number;
  conversions: number; revenue: number; acquisition_cost: number; engagement_score: number;
}
export type Rule = { id: number; code: string; name: string; category: string; condition: string; definition?: Record<string, unknown>; weight: number; priority: number; active: boolean; constraint_type: 'Hard' | 'Soft' }
export type Explanation = { driver: string; implication: string; action: string; caveat: string; intent: string }
export type Recommendation = {
  id: string; numeric_id: number; campaign_id: string; campaign: string; intent: string; action: string;
  confidence: number; raw_confidence: number; performance_score: number; explanation: Explanation;
  evidence: { attribution: { feature: string; contribution: number }[]; channels: { channel: string; contribution: number }[]; confidence_level: string; action_evidence_status: string; decision_status: string; decision_reasons: string[]; feasible_actions: string[]; hard_rejected_actions: string[]; coverage_status: string; coverage_reasons: string[] };
  ranked_actions: { action: string; score: number }[]; latency_ms: number; status: string; date: string;
  rules?: { name: string; triggered: boolean; score: number }[];
  calibration_status: 'calibrated' | 'pending_human_annotations' | 'uncalibrated_ablation' | 'legacy_unknown';
  action_evidence_status: 'audited_actionnet' | 'development_actionnet' | 'campaignnet_only_fallback' | 'legacy_unknown';
  decision_status: 'RECOMMEND' | 'CHECK ADVISED' | 'HUMAN REVIEW REQUIRED' | 'NO SAFE RECOMMENDATION' | 'legacy_unknown';
  decision_reasons: string[];
  coverage_status: 'IN_SCOPE' | 'OUT_OF_BENCHMARK_COVERAGE' | 'legacy_unknown';
  coverage_reasons: string[];
}
export type Intervals = Record<string, [number, number]>
export type MetricRow = Record<string, string | number | Intervals>
export type RunStatus = { id: string; name: string; status: string; detail: string }
export type StudyStatistic = { mean: number | null; sd: number | null; ci95: [number, number] | null }
export type StudyMetrics = {
  responses: number; participants: number; actionability: StudyStatistic;
  specificity: StudyStatistic; feasibility: StudyStatistic;
  explanation_usefulness: StudyStatistic; trust_alignment: StudyStatistic;
  overtrust_rate: number | null; overtrust_cases: number;
  willingness_to_review: StudyStatistic; user_acceptance: StudyStatistic;
  decision_time_seconds: StudyStatistic;
}
export type ExperimentBlocks = {
  R001: { source_records: number; benchmark_cases: number; intent_kappa: number; action_kappa: number; provenance_complete: boolean };
  R003: { systems: MetricRow[]; participant_status: string; completed_participants: number; target_participants: number; conditions: Record<string, StudyMetrics> };
  R004: { systems: MetricRow[]; reversal_rate: number | null; active_rule_count: number };
  R005: { systems: MetricRow[]; participant_status: string };
  R006: { participant_status: string; completed_participants: number; target_participants: number; conditions: Record<string, StudyMetrics> };
  participant_count: number;
}
export type Summary = {
  status: string; message: string; dataset: string; source_records: number;
  processed_records: number; candidate_benchmark_records: number;
  candidate_benchmark_status: string;
  synthetic_development_records: number; human_provided_development_records: number;
  development_annotation_status: string; decision_cases: number;
  audited_benchmark_present: boolean; calibration_status: string;
  dataset_records: number; target_records: number; configuration: string;
  baselines: MetricRow[]; proposed: Record<string, number>; proposed_ci: Intervals;
  ablations: Record<string, Record<string, number>>; ablation_ci: Record<string, Intervals>;
  protocol: { seed: number | string; test_cases: number; label_source: string; identical_holdout: boolean; ruleset: string };
  benchmark: { ground_truth_conflict_rate: number };
  human_evaluation: Record<string, unknown>;
  runs: RunStatus[]; experiment_blocks: ExperimentBlocks;
}
