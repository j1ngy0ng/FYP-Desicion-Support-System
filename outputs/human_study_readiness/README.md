# Human-study readiness evidence

The participant-study deployment is approved and technically ready for genuine data collection. The controlled launcher starts an isolated SQLite response database, a dedicated backend on port 8010 and a participant-only frontend on port 5180.

The smoke test used a pseudonymous QA code only to load the assigned cases. It did not submit a response. Participant accounts cannot view aggregate study summaries or export response data; those operations remain administrator-only.

Start and stop the study deployment from the repository root:

```powershell
.\scripts\human_study.ps1
.\scripts\human_study.ps1 -Stop
```

The approval document itself remains outside the public repository. Its SHA-256 digest is recorded in `READINESS_MANIFEST.json` so the retained document can be matched without publishing its contents.
