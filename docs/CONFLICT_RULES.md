# Logical Conflict Rule Catalogue

The Logical Conflict Rate (LCR) is the proportion of recommendations that violate at
least one predefined rule. Multiple violations on one recommendation still count as one
conflicting recommendation:

`LCR = recommendations with one or more conflicts / all recommendations`

The same rules and thresholds are applied to every baseline and the proposed system.
They are defined in `baseline_evaluation.py`, independently of model accuracy.

## Intent rules

- Growth campaigns must not receive `Reduce`.
- Survival campaigns must not receive `Increase`.
- Retention campaigns must not receive `Reduce`.

## Performance rules

An `Increase` conflicts with any clearly weak signal:

- ROI below `0`.
- Conversion rate below `8%`.
- Click-through rate below `3%`.
- Engagement score below `5`.

A `Reduce` conflicts when at least two strong signals are present:

- ROI above `2.0`.
- Conversion rate above `20%`.
- Click-through rate above `10%`.
- Engagement score above `20`.

A `Maintain` conflicts only when all exceptional-performance conditions hold:

- ROI above `4.0`.
- Conversion rate above `20%`.
- Click-through rate above `10%`.
- Engagement score above `20`.

## Evidence-sufficiency rule

`Increase` or `Reduce` conflicts when there are fewer than `500` clicks or fewer than
`50` conversions. A decisive recommendation is not considered adequately supported in
that case.

## Scope limitation

`Channel_Used` identifies multi-channel campaigns, but the dataset has no per-channel
ROI, cost, conversion, or engagement values. Consequently, cross-channel contradictions
cannot be measured reliably and are not included in LCR. Adding invented channel rules
would overstate the metric's coverage.
