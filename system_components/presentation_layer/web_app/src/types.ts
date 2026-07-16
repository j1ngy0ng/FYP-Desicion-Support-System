export type User = { name: string; email: string; role: string; organisation: string }
export type Campaign = {
  id: string; name: string; type: string; intent: 'Growth' | 'Retention' | 'Survival'; channel: string;
  status: 'Active' | 'Review' | 'Completed'; roi: number; conversion: number; budget: number;
  target_audience: string; duration: number; impressions: number; clicks: number; leads: number;
  conversions: number; revenue: number; acquisition_cost: number; engagement_score: number;
}
export type Rule = { id: number; code: string; name: string; category: string; condition: string; weight: number; priority: number; active: boolean }
export type Explanation = { driver: string; implication: string; action: string; caveat: string; intent: string }
export type Recommendation = {
  id: string; numeric_id: number; campaign_id: string; campaign: string; intent: string; action: string;
  confidence: number; raw_confidence: number; performance_score: number; explanation: Explanation;
  evidence: { attribution: { feature: string; contribution: number }[]; channels: { channel: string; contribution: number }[]; confidence_level: string };
  ranked_actions: { action: string; score: number }[]; latency_ms: number; status: string; date: string;
}
export type Intervals = Record<string, [number, number]>
export type MetricRow = Record<string, string | number | Intervals>
export type Summary = {
  dataset: string; dataset_records: number; target_records: number; configuration: string;
  baselines: MetricRow[]; proposed: Record<string, number>; proposed_ci: Intervals;
  ablations: Record<string, Record<string, number>>;
  protocol: { seed: number; test_cases: number; label_source: string; identical_holdout: boolean };
  benchmark: { ground_truth_conflict_rate: number };
  human_evaluation: { responses: number; actionability: number | null };
}
