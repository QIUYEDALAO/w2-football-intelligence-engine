# V2 corrected task roadmap

> Renumbering warning: old-plan Task 2 meant
> `V2-GATE1-CALIBRATION-RECOVERY-01`; this roadmap's Task 2 is
> `POINT-EV-LANDING-01` and requires separate explicit Owner deployment
> authorisation. Every future reference must use the full task ID, never bare
> “Task 2”.

Task IDs are workflow names. Gate numbers are independent programme decisions and
must not be inferred from task order.

## Ordered tasks

| Order | Task ID | Purpose | Gate relationship | Hard dependencies |
|---:|---|---|---|---|
| 1 | `V2-REENTRY-PROTOCOL-01` | freeze and accept this design | prepares all | Claude acceptance |
| 2 | `POINT-EV-LANDING-01` | integrate, release and accept fail-closed calibration authority | prerequisite to Gate 5 and any candidate influence | separate Owner deploy authority |
| 3 | `V2-INTEGRATION-BASELINE-01` | merge `6f2032cc` into `2b4751c6`, resolve semantic conflicts | revalidates Gate 0 foundation | `V2-REENTRY-PROTOCOL-01`; no deployment implied |
| 4 | `V2-GATE1-CALIBRATION-RECOVERY-01` | TRAIN-only development and freeze a new identity | candidate for future Gate 1 evidence, not a pass itself | `V2-REENTRY-PROTOCOL-01`, `V2-INTEGRATION-BASELINE-01` |
| 5 | `V2-FORWARD-PREREG-AMENDMENT-01` | preserve old prereg and freeze successor before first row | future confirmatory contract | `V2-INTEGRATION-BASELINE-01`, `V2-GATE1-CALIBRATION-RECOVERY-01`; verified zero rows |
| 6 | `V2-DUAL-TRACK-LEDGER-01` | variant-aware analysis-only schema and settlement | prepares Gate 2 | `V2-REENTRY-PROTOCOL-01`, `V2-INTEGRATION-BASELINE-01`; prereg amendment before any row |
| 7 | `V2-INDEPENDENT-WORKER-CANARY-01` | isolated worker/role and bounded forward canary | Gate 3 | `V2-FORWARD-PREREG-AMENDMENT-01`, `V2-DUAL-TRACK-LEDGER-01`; separate migration/deploy authority |
| 8 | `V2-DASHBOARD-01` | read-only funnel, identity, attrition and authority UI | Gate 4 | `V2-DUAL-TRACK-LEDGER-01`; deployed evidence separately authorised |
| 9 | `V2-LINEUP-FORWARD-01` | collect confirmed-lineup child variant | contributes to Gate 3/forward evidence | prereg, ledger and worker/canary tasks; V1 lineup authority |
| 10 | `V2-FORWARD-EVALUATION-01` | one-look prospective evaluation | closes or fails model evidence gates | prereg date and sample rule reached |
| 11 | `V2-GATE5-ADMISSION-01` | append evidence-bound approval and enable authority reconciliation | Gate 5 | `POINT-EV-LANDING-01`, worker/canary, Dashboard, forward evaluation and Owner approval |

The user-referenced former “task 6” is `V2-GATE5-ADMISSION-01`. POINT-EV is a hard
prerequisite for it. Renumbering the roadmap does not change that dependency.

## POINT-EV versus local integration ordering decision

The displayed safety priority remains `POINT-EV-LANDING-01` before the larger V2
integration. POINT-EV is a narrow, independently accepted fail-closed authority
change; making the unresolved V2 merge part of its deployment baseline would enlarge
the production change surface and delay the existing calibration safeguard.

This priority is not a dependency that blocks local work. While Owner deployment
authorisation for `POINT-EV-LANDING-01` is pending,
`V2-INTEGRATION-BASELINE-01` may proceed locally in parallel or finish first. No result
of that local merge authorises deployment, and the eventual V2 release still requires
the merged semantic-conflict and Alembic-head checks.

## Stop lines by phase

### POINT-EV, integration and calibration recovery

- POINT-EV deployment is separately authorised; V2 development does not inherit it.
- `V2-GATE1-CALIBRATION-RECOVERY-01` uses only the frozen 2024 TRAIN identities for
  outcome-visible development.
- No new result on 2025 VALIDATION or 2026 HOLDOUT may be shown to the developer.

### Task 5

- Freeze before the first row.
- Set cohort start to the later of freeze and actual activation.
- Preserve the old preregistration and never backfill the prospective gap.

### Tasks 6–9

- analysis-only, V2 tables only;
- Provider 0 unless separately authorised for a named collection action;
- no candidate, opportunity, outbox, Bark, formal recommendation or formal P&L;
- base/lineup variant is a schema dimension before migration;
- Gate 3 canary and Gate 4 Dashboard each require their own acceptance.

### Tasks 10–11

- no interim metric look;
- insufficient sample means no evaluation;
- a pass produces evidence, not automatic authority;
- Owner approval appends the authority decision; deployment/funds remain separate;
- revocation must create a blocked attempt and `CANDIDATE_WITHDRAWN` reconciliation.

## POINT-EV operational discontinuity

After `POINT-EV-LANDING-01` deployment, current V1 `BASELINE_PRIOR` is expected to
stop producing formal candidates while analysis forecasts and EV evidence remain.
`POINT-EV-LANDING-01` acceptance must prove both halves. Dual-track pairing uses V1
production forecast capture, never candidate delivery. Reports stratify pre/post
POINT-EV authority epochs.
