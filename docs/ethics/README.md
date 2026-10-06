# Human-participant ethics gate

The human-study endpoints remain locked unless `ETHICS_APPROVAL_REFERENCE` identifies the formal TAR UMT ethics approval. The approved document for this study is the TAR UMT Ethics Committee Checklist supplied for Ng Jing Yong's project. The approval document is retained outside the public repository.

Before enabling the study:

1. Retain the formal approval evidence outside the public source repository.
2. Keep the participant information, consent statement, pseudonymous-code procedure and collected fields within the approved scope.
3. Start the approved local study deployment with `scripts\human_study.ps1`.
4. Use the participant-only URL opened by the launcher and sign in with `study@example.com` / `participant`. This dedicated role cannot display the administrator workspace or aggregate study results.
5. Export responses only through the administrator-only CSV endpoint and store the export securely.
6. Report participant results only after genuine responses have been collected and checked.

The approval permits the study to begin; it does not make pending participant outcomes complete results.
