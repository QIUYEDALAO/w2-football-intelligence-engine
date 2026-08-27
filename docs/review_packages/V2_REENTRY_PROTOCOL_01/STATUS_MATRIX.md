# V2-REENTRY-PROTOCOL-01 — Gate and delivery matrix

## Gate state

Gate numbers are programme gates. They are not task ordinals.

| Gate | Current state | Evidence/condition | Next permitted work |
|---|---|---|---|
| Gate 0 — foundation/contracts | `CONDITIONAL_PASS_HISTORICAL` | old V2 local chain only | merge onto `2b4751c6`, re-run contracts |
| Gate 1 — offline model/calibration | `FAIL` | ECE worse on observed VALIDATION and HOLDOUT | TRAIN-only recovery; no confirmation claim |
| Gate 2 — analysis ledger readiness | `CLOSED` | Gate 1 failed; schema lacks hard variant dimension | design/implement analysis-only ledger after protocol acceptance |
| Gate 3 — independent worker/canary | `NOT_STARTED` | local old worker preparation is not current-baseline canary | separate authorised worker/canary task |
| Gate 4 — V2 Dashboard | `NOT_STARTED` | no accepted current V2 read model/UI | separate read-only Dashboard task |
| Gate 5 — calibration admission | `CLOSED` | POINT-EV not deployed; no producer for `APPROVED_VALIDATED`; no prospective pass | future evidence-bound Owner decision only |

No row in this table authorises migration, collection or deployment.

## Eleven required judgements

| # | Requirement | Decision | Location |
|---:|---|---|---|
| 1 | three-line integration | merge V2 into POINT-EV production descendant | REPORT §3; lineage matrix |
| 2 | xG fixes versus old Gate 1 | old frozen failure retained; new baseline gets new identity | REPORT §4 |
| 3 | corpus expansion | exact subset +282 rows; new experiment | REPORT §5; data matrix |
| 4 | `APPROVED_VALIDATED` mechanism | append-only evidence decision + downgrade reconciler | REPORT §6 |
| 5 | POINT-EV schedule/dependency | separate; hard prerequisite for admission/candidate influence | REPORT §7 |
| 6 | VALIDATION/HOLDOUT isolation | only frozen 2024 TRAIN IDs are development | REPORT §8; data matrix |
| 7 | old forward cohort | successor amendment before first row; preserve old file | REPORT §9 |
| 8 | base/lineup hard schema input | one family, two explicit variants | REPORT §10; dual-track contract |
| 9 | lineup timing | reuse V1 event/hash/post-lineup quote authority | REPORT §11 |
| 10 | paired criterion/85% gap | both outputs for metric pair; full denominator retains misses | REPORT §12 |
| 11 | Gate 3/4 restoration | separate worker/canary and Dashboard tasks | REPORT §13; roadmap |

## Deliverables

| Deliverable | Status |
|---|---|
| frozen protocol before results | `PASS` — commit `1f080b26` |
| technical report with 11 decisions | `PASS_LOCAL` |
| Gate 0–5 matrix | `PASS_LOCAL` |
| commit topology/conflict matrix | `PASS_LOCAL` |
| factor/data-role matrix | `PASS_LOCAL` |
| dual-track/lineup contract | `PASS_LOCAL` |
| corrected roadmap | `PASS_LOCAL` |
| Claude Code independent acceptance | `PENDING` |
| task 2 entry | `BLOCKED_PENDING_PROTOCOL_ACCEPTANCE` |

## Factual-source labels

| Label | Meaning |
|---|---|
| `LOCAL_GIT` | verified from existing local objects only |
| `FROZEN_ARTEFACT` | verified from hash-addressed local report/input |
| `LOCAL_LATER_ARTEFACT` | later local extract, not refreshed production truth |
| `SUPPLIED` | stated in revised scope and not independently refreshed live |
| `VAULT` | navigation/deployment record; subordinate to code/live evidence |
| `NOT_LIVE_REFRESHED` | production connection deliberately not used |

Material numbers:

| Fact | Value | Source label |
|---|---:|---|
| production/V2 unique commits | 21 / 17 | `LOCAL_GIT` |
| POINT-EV commits over production | 5 | `LOCAL_GIT` |
| old xG rows/fixtures | 18,696 / 9,348 | `FROZEN_ARTEFACT` |
| later xG rows/fixtures | 18,978 / 9,489 | `LOCAL_LATER_ARTEFACT` |
| added pre-cutoff rows/fixtures | 108 / 54 | local exact comparison |
| TRAIN/VALIDATION/HOLDOUT targets | 3,118 / 4,520 / 2,628 | `FROZEN_ARTEFACT` |
| old TRAIN fitted/scorable | 2,684 | `FROZEN_ARTEFACT` |
| V1 T-30m evaluation | 34/40 = 85% | `SUPPLIED` + `VAULT`, not live refreshed |

## Boundary receipt

| Action | Count/status |
|---|---|
| Provider | 0 |
| production read/write | 0 / 0 |
| GitHub/GHCR | 0 |
| model fit/tune/score | 0 |
| migration/collector/timer/deploy | 0 / 0 / 0 / 0 |
| business code changed | 0 |
| Gate 1 / Gate 2 changed | no (`FAIL` / `CLOSED`) |

