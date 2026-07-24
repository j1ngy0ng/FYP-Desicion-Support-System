# Human annotation protocol

## Purpose

Create an independently reviewed reference benchmark for the four bounded
marketing actions. AI suggestions must not be shown to reviewers or used to
fill any annotation field.

## Allowed intents

- **Survival**: cash preservation, cost control and reduced short-term risk.
- **Retention**: customer continuity, repeat value and relationship quality.
- **Growth**: acquisition and expansion where expected returns justify risk.

## Allowed actions

- **Increase**: controlled additional allocation is supported.
- **Maintain**: the present allocation remains appropriate.
- **Reduce**: reduced allocation is justified.
- **Investigate**: evidence is insufficient, ambiguous or contradictory.

## Pilot

1. Two reviewers independently label `data/pilot_reviewer_1.csv` and
   `data/pilot_reviewer_2.csv`. The case orders differ.
2. Reviewers must not see each other's entries.
3. Compare disagreements and refine this rubric before the full benchmark.
4. Pilot cases are relabelled under the final rubric if they are retained.

## Full benchmark

1. Two reviewers independently label `data/benchmark_reviewer_1.csv` and
   `data/benchmark_reviewer_2.csv`. Do not exchange the files.
2. Each reviewer records an intent, action and short evidence-based note.
3. Calculate Cohen's kappa separately for intent and action.
4. If action kappa is below 0.60, refine the rubric and repeat independent
   review; do not freeze the benchmark.
5. A third reviewer adjudicates disagreements.
6. Remove cases that remain unresolved.
7. Set `Annotation_Status` to `Audited` only after adjudication.
8. Save the final file as `data/benchmark_audited.csv`.

Merge the independent files after both reviewers finish:

```powershell
python scripts/audit_human_annotations.py merge `
  data/benchmark_reviewer_1.csv data/benchmark_reviewer_2.csv
```

After third-reviewer adjudication, validate and freeze the benchmark:

```powershell
python scripts/audit_human_annotations.py finalize `
  data/benchmark_adjudication.csv
```

## Review constraints

- Use only the campaign evidence visible in the row.
- Do not infer unavailable company information.
- Choose `Investigate` when evidence does not support a defensible decision.
- Do not use the system recommendation, an AI assistant or generated labels.
- Record conflicts or assumptions in the notes fields.
