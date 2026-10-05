# Next Meeting Questions and Evidence Based Answers

1. **What does the system recommend?** One operational campaign investment action: Increase, Maintain, Reduce or Investigate. Channel evidence supports the action but is not the recommendation unit.
2. **Why Survival, Retention and Growth?** They are the three project-defined strategic conditions. Their domain adequacy still requires independent confirmation.
3. **Who supplies intent?** The manager explicitly selects one primary intent. The model does not infer it.
4. **How are mixed intents handled?** The current study does not accept mixed intent. A case with unresolved mixed intent should be routed to human review.
5. **Where do the safeguards come from?** They are predefined project rules in `rule-catalogue-v1`. The register records their implementation basis, hard/soft classification and the completed independent marketing review.
6. **Which safeguards are hard?** Evidence sufficiency, the three declared-intent safeguards, explicit budget feasibility and conflicting evidence. They exclude affected candidates before final ranking.
7. **Which safeguards are soft?** Negative ROI, low conversion, low CTR, low engagement, strong signal, exceptional performance, acquisition cost and channel saturation. They adjust scores and remain overridable.
8. **Who created the reference actions?** The benchmark records Reviewer 1, Reviewer 2 and an adjudicated action. The available audit manifest does not identify the people or establish independence from development.
9. **How were they checked?** They were checked using the supervisor- and university-approved structured domain review protocol and independently reviewed by Sherlynn Poh, who holds a Bachelor's degree in Marketing.
10. **Can one case have multiple acceptable actions?** Yes. The structured review records acceptable, conditional and unacceptable sets while preserving the original primary label.
11. **How is safeguard-intervention correctness judged?** Set-based correctness is primary: the unconstrained action must be in the reviewed unacceptable set and the constrained outcome must be acceptable or conditional. A No Safe Recommendation is correct only when all executable actions are unacceptable and Investigate remains an acceptable manual fallback. Exact primary-label agreement is a secondary diagnostic.
12. **How many cases exist?** 125 unique audited cases.
13. **Are the cases real or synthetic?** The case features are drawn from the project campaign dataset and the intent/action labels are human-review fields. The evidence pack does not claim that they are live SME deployments.
14. **Can near-duplicate templates cross partitions?** The split is chronological, but no documented near-duplicate or template-similarity audit is currently available.
15. **Are deterministic baselines complete?** Yes. Intent-only and fixed weighted deterministic comparators are implemented and tested.
16. **What value does AI add over the weighted comparator?** On the 19-case held-out pilot, weighted deterministic Macro F1 is 0.5071, unconstrained AI is 0.8865, and the proposed method is 0.7836. The proposed method's observed value is lower logical conflict (0.0000 versus 0.1053), not superiority over unconstrained AI accuracy.
17. **What is the calibration target?** Agreement between the top action and the audited reference action on the validation distribution.
18. **Is confidence a probability of campaign success?** No. It is calibrated model confidence for action agreement.
19. **What happens when all executable actions are unsafe?** Hard exclusions are logged, the engine returns NO SAFE RECOMMENDATION and Investigate is displayed only as a manual-review fallback.
20. **How is over-reliance measured?** The human-study analysis compares participant reliance and acceptance with recommendation correctness and reports overtrust on incorrect recommendations.
21. **What if AI does not beat deterministic baselines?** The claim must shift to safeguard compliance, selective review, calibration and traceability. The thesis must not claim AI superiority.
