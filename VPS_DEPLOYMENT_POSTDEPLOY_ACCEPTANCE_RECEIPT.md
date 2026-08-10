# VPS Deployment and Postdeploy Acceptance Receipt

```text
AUTHORITY = VPS_DEPLOYMENT_AND_POSTDEPLOY_ACCEPTANCE_AUTHORIZATION.md
EXECUTION_STATUS = COMPLETE_TERMINAL
TERMINAL_CLASSIFICATION = VPS_DEPLOYMENT_ROLLED_BACK
ATTEMPTED_AT = 2026-08-09T06:38:19Z
TERMINATED_AT = 2026-08-09T06:53:10Z
EXACT_ORIGIN_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
EXACT_CONTEXT_BASE_SHA = efdc6f62eb6f0776f3c1a8d91cf95eea24011cc3
PREDEPLOY_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
FINAL_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
RELEASE_CANDIDATE_RUN = 31299328162
RELEASE_REQUIRED = PASS
IMMUTABLE_MANIFEST_SHA256 = e56bdef5c3bdcae04ae80f601a3fd845bb5ae407da9fdea56d8f474c6c5ae1e7
PREDEPLOY_BACKUP = PASS_CUSTOM_FORMAT_AND_RESTORE_LIST_VALIDATED
ROLLBACK_TARGET = PASS_LOCAL_IMMUTABLE_IMAGES_AND_RELEASE_ENV_VALIDATED
ROLLOUT_FAILURE = COLD_PULL_END_TO_END_304_SECONDS_EXCEEDED_300_SECOND_TARGET
ROLLBACK = PASS
ROLLBACK_DURATION_SECONDS = 33
ROLLBACK_TARGET_SECONDS = 120
POSTDEPLOY_ACCEPTANCE = NOT_RUN_ROLLOUT_GATE_FAILED
CONDITIONAL_TRACK_A_REFRESH = NOT_RUN_DEPLOYMENT_DID_NOT_PASS
PROVIDER_CALLS_CAUSED_BY_EXECUTION = 0
DB_BUSINESS_WRITES_CAUSED_BY_EXECUTION = 0
TRACKED_CODE_CHANGES = 0
ROUND_4 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

## Predeploy gates

Immediately before activation, `origin/main` and `origin/context/current` still
matched the exact SHAs above. The clean deployment worktree had the same tree as
the approved main. The exact-main Release Candidate passed Full CI, image smoke,
`RELEASE_REQUIRED`, immutable-manifest verification and the frozen zero-Provider /
Candidate-Formal-Lock-Production-off safety boundary.

The measured release was healthy on all six compose services. API and Web
reported the same predeploy release identity. A PostgreSQL custom-format backup
was created before switching, was non-empty, and passed `pg_restore --list`.
The measured Python and Web rollback images were locally available by immutable
digest, and the rollback release environment was independently preserved.

## Deployment terminal result

The existing deployment script pulled and verified the exact approved Python
and Web image digests, ran the existing migration step, and activated the four
application services. Its mandatory cold-pull end-to-end gate measured 304
seconds against the frozen 300-second target and failed closed.

No threshold was relaxed and no retry, tracked-code hotfix or alternate rollout
path was used. The script automatically restored the measured predeploy image
set. Rollback completed in 33 seconds against the 120-second target.

## Rollback acceptance

After rollback:

- API, worker, scheduler, Web, PostgreSQL and Redis were running and healthy;
- API health and readiness passed, including database, Redis, schema, mounts and
  artifact checks;
- API and Web again reported source/release identity
  `51ebbeabc5497ce48708b3587705e2922c4805da`;
- Candidate, Formal Recommendation and Production remained off;
- scheduler/cadence, Provider caps, active whitelist and model/threshold policy
  were not changed;
- the existing configured bridge policy remained `SHADOW_ONLY`; the recreated
  API container converged from an observed stale `OFF` process value to that
  already-declared configuration without changing the configuration source.

Provider request ledger, endpoint capture, checkpoint plan, fixture identity,
market observation and read-model checkpoint counts and maximum timestamps were
identical before and after the deployment window. No manual Provider probe was
made and no acceptance-generated business write occurred.

## Stop decision

This execution stops at `VPS_DEPLOYMENT_ROLLED_BACK`. The successful-deployment
postdeploy Dashboard/API/visual checks and the conditional source-bound Track A
refresh are inapplicable because the rollout gate did not pass. Track A remains
`WAIT_MORE_NATURAL_EVIDENCE`; Round4 and P6 remain unauthorized.

No VPS address, public URL, database identifier, sensitive value or unredacted
runtime log is stored in this receipt.

## Latest accepted deployment

The historical rollback above remains preserved. The current accepted release
is recorded separately in `DASHBOARD_OWNER_FIVE_FIXES_DEPLOYMENT_RECEIPT.md`:
PR #514, exact source `ea7ea01e049ef3110196b370ca06711ef7f849c6`,
warm-switch PASS in 43 seconds, postdeploy acceptance PASS, rollback not
required.
