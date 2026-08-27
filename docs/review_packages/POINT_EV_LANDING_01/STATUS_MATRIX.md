# POINT-EV-LANDING-01 status matrix

| Requirement | Status | Evidence |
|---|---|---|
| reviewed POINT-EV authority landed | PASS | release `ea557bb8` |
| Python/Web exact release | PASS | exact OCI revision and release labels |
| schema unchanged | PASS | `0070_notification_delivery_routing` |
| release-sync preflight before switch | PASS | line 22 in both deployment scripts |
| successful-release backup | PASS | `20260827T145846Z`, 184,830,384 bytes |
| automatic rollback exercised | PASS | bad acceptance URL returned 404; `fc70b48e` restored healthy |
| retry used corrected `/v1` URL | PASS | `deploy-retry1.sh` |
| API/worker/scheduler/Web healthy | PASS | all exact `ea557bb8` |
| Postgres/Redis healthy | PASS | observed healthy |
| analysis distribution continues | PASS | 18/18 five-state distributions present and sum to one |
| EV and EV-SE continue | PASS | 18/18 present; ranges frozen in evidence |
| new model forecast capture observed | NOT OBSERVED | post-epoch count 0; no claim made |
| unvalidated evaluations blocked | PASS | 18/18 `NOT_READY_MODEL_INPUT` |
| opportunity promotion blocked | PASS | 2 audit rows, both `BLOCKED_BY_GATE`; promoted 0 |
| candidate output | PASS | 0 |
| outbox / Bark | PASS | 0 / 0 |
| workspace read contract | PASS | Provider 0 / writes 0 / no-call-on-read true |
| V2 deployed | NO | deliberately excluded from release |
| historical rows rewritten | NO | none |
| V1 parameters/formula changed | NO | none |
| alpha / beta | PASS | `NULL / NULL` |
| Contract 1 | NOT IMPLEMENTED | out of scope |

Terminal status: `DEPLOYED_AND_POSTDEPLOY_ACCEPTED`.
