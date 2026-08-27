# POINT-EV-LANDING-01 deployment report

Status: `DEPLOYED_AND_POSTDEPLOY_ACCEPTED`

Release: `ea557bb8ff64e06add91bbe32814fe073ec64642`

Authority epoch: `2026-08-27T14:59:21Z`

## 1. Outcome

The calibration authority is live. Under the current `BASELINE_PRIOR` status,
the production chain continues to calculate and retain analytical probability,
five-state settlement distributions, EV and EV-SE, but it cannot promote an
evaluation into a formal candidate or notification.

This is the requested fail-closed behavior. It does not make the probability or
EV accurate; it prevents an unvalidated probability from being presented as a
recommendation.

## 2. Release identity

| Item | Observed value |
|---|---|
| source/release | `ea557bb8ff64e06add91bbe32814fe073ec64642` |
| Python digest | `sha256:b8d491db...a5440` |
| Web digest | `sha256:fa4ee355...d65c` |
| schema | `0070_notification_delivery_routing` |
| API / worker / scheduler / Web revision | exact match |
| business containers | all healthy |
| Postgres / Redis | healthy |
| `/v1/version` and `/ready` | PASS |
| workspace | HTTP 200 |
| workspace read contract | Provider 0 / DB writes 0 / no-call-on-read true |

The release files and image labels independently report the same commit and
digests. The release-sync preflight is line 22 of both deployment scripts and
runs before backup/release mutation.

## 3. Deployment incident and recovery

The first release attempt used an acceptance URL without the required `/v1`
prefix. It returned 404 and the deployment script automatically rolled back to
`fc70b48e`. Health and workspace checks recovered. This was an operator-script
acceptance-path error, not a POINT-EV code failure.

The corrected `deploy-retry1.sh` retained the preflight and changed the URL to
`/v1/dashboard/intelligence-workspace`. It then completed successfully.

Backups:

| Attempt | Backup | Dump bytes | Schema |
|---|---|---:|---|
| automatic rollback attempt | `20260827T145616Z` | 184,830,379 | `0070_notification_delivery_routing` |
| successful retry | `20260827T145846Z` | 184,830,384 | `0070_notification_delivery_routing` |

`W2_BACKUP_KEEP=1000000`; no old backup was deleted.

## 4. Analysis half continues

From the release epoch through the frozen observation:

- 18 new dynamic evaluations were written;
- all 18 retained complete five-state distributions summing to one;
- all 18 retained EV and EV-minus-SE, with derived EV-SE;
- EV range was `-0.056129` to `0.311380`;
- EV-SE range was `0.048317` to `0.063831`; and
- all 18 recorded calibration authority fields.

Example: fixture `1570336`, AH away `+0.5`, T3:

```text
EV = 0.178263
EV_SE = 0.049679
EV-SE = 0.128584
WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS
= 0.6438593441 / 0 / 0 / 0 / 0.3561406559
```

No new `model_forecast_capture` row naturally landed after the release epoch.
Therefore this report does not claim that a new forecast capture was observed.
The 18 post-release evaluations demonstrate that the deployed analysis path
continues to consume the retained model-capture authority and produce complete
analytical records.

## 5. Candidate half stops

All 18 post-release evaluations were:

```text
calibration_status = BASELINE_PRIOR
calibration_recommendation_admissible = false
state = NOT_READY_MODEL_INPUT
first failed gate = CALIBRATION_VALIDATED
blocker = MODEL_CALIBRATION_NOT_VALIDATED
```

Two opportunity rows were materialized for audit/lifecycle continuity, but both
ended `BLOCKED_BY_GATE`; promoted opportunities were zero. Candidate count,
outbox count and candidate/Bark log count were all zero.

This distinction matters: the deployment does not delete analytical attempts or
their opportunity identity. It blocks promotion and delivery.

## 6. Lineage deviation and rationale

The deployment release was cut by replaying the reviewed POINT-EV commits onto
the live `fc70b48e` production line, producing `ea557bb8`. It was not built from
the entire `cb8f5d22` V2 integration merge.

That is an intentional scope correction: deploying `cb8f5d22` would also deploy
the unapproved V2 forward line and migration. The POINT-EV code is already
present in the separate local integration baseline, while this production
release contains only POINT-EV plus its compatibility fix. V2 was not deployed.

## 7. Verification and boundaries

Predeployment verification retained the POINT-EV result set: 2,895 passed with
the six known environmental failures unchanged, Ruff clean, and mypy `src apps`
clean across 289 files. Postdeployment verification confirmed synchronized
revision/digests, schema, health, workspace and the two behavioral halves above.

Provider 0; GitHub/GHCR 0; no V1 probability parameter or five-state formula
change; no historical recommendation/settlement rewrite; alpha/beta remain
`NULL`; Contract 1 and V2 were not deployed.

## 8. Forward-design consequence

Candidate volume and performance must be stratified by authority epoch. The
pre-POINT-EV period allowed `BASELINE_PRIOR` recommendations; the post-POINT-EV
period correctly produces zero formal V1 candidates until a separately approved
validated calibration status exists. These periods are not a homogeneous V1
baseline for V2 paired validation.
