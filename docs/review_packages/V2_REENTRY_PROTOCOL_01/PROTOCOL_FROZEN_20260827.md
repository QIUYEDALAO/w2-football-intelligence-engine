# V2-REENTRY-PROTOCOL-01 — frozen review protocol

Status: `FROZEN_BEFORE_REVIEW_RESULTS`

Scope: local, read-only technical review and protocol design. This protocol does
not authorise model fitting, parameter selection, migration application, a
collector or timer, deployment, Provider traffic, production reads or writes,
candidate formation, notifications, formal recommendations, or real-money use.

## 1. Objective

Produce an independently reasoned re-entry design for Factor Model V2 that:

1. reconciles the deployed/local/POINT-EV code lines without pretending that a
   local acceptance is deployed;
2. establishes whether the frozen Gate 1 conclusion survives the corrected xG
   persistence semantics and the changed corpus;
3. assigns non-overlapping roles to development, validation and final evidence
   after both the former VALIDATION and HOLDOUT results have been observed;
4. defines an analysis-only V1/V2 pairing and settlement contract without
   opening Gate 2 or writing V1 authorities;
5. makes the base-model/confirmed-lineup decision an immutable input to later
   ledger identity and schema design;
6. defines how a future evidence-bound calibration decision becomes, and can
   cease to be, `APPROVED_VALIDATED` under the POINT-EV authority; and
7. restores the Owner-approved Gate 0 through Gate 5 programme, including the
   independent worker/forward canary and V2 Dashboard stages, while keeping task
   identifiers distinct from Gate identifiers.

## 2. Claims to verify, not assumptions to inherit

The review starts from the following supplied claims. Each must be reproduced
from local Git, files or frozen artifacts and classified `CONFIRMED`,
`CORRECTED`, `PARTIAL`, or `NOT_VERIFIABLE` in the report:

- production authority: `fc70b48e`;
- V2 forward line: `6f2032cc`;
- POINT-EV line: `2b4751c6`;
- production and V2 diverge at `ae5b4d88`, with 21 production-only and 17
  V2-only commits;
- the far-horizon odds checkpoint slack change exists independently on both
  sides;
- the V2 line lacks `5b926ee8` (null xG remains retryable) and `4733c76f`
  (`captured_at` first-write immutability);
- the frozen Gate 1 xG corpus is 18,696 rows / 9,348 fixtures, while the current
  production-derived count is 18,978 rows / 9,489 fixtures;
- no current code path produces `APPROVED_VALIDATED`; production calibration is
  a hard-coded `BASELINE_PRIOR`;
- both former VALIDATION and HOLDOUT metrics were observed;
- the existing forward preregistration is still amendable only because no first
  forward row has been written; and
- V1 T-30m evaluation completeness is 85%, so missing attempts are a material
  part of the pairing denominator.

No production connection may be used to refresh any of these claims. A value
that exists only in supplied or frozen evidence remains labelled as such.

## 3. Frozen evidence inputs

The review may read only local Git objects, the three local worktrees, repository
governance files, frozen artifacts and the W2 Vault:

- deployed line: `fc70b48e` and its local ancestors;
- V2 line: `6f2032cc` and its local ancestors;
- POINT-EV line: `2b4751c6` and its local ancestors;
- Gate 1 reports under `reports/factor_model_v2/`;
- `docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json`;
- V2 migration, persistence, collector, settlement and runner code;
- POINT-EV calibration authority, lifecycle, repository and notification code;
- local xG persistence commits and their tests; and
- `/Users/liudehua/Documents/Obsidian/W2/` as a navigation/decision layer, never
  as code or runtime authority.

GitHub, GHCR and remote refresh operations are forbidden.

## 4. Reproducible review methods

### 4.1 Commit topology and integration risk

- compute merge bases and `rev-list --left-right --count` for all three heads;
- list first-parent and full unique commit sets;
- compare candidate duplicate changes by patch content, not subject alone;
- inventory changed paths and migration revisions;
- identify semantic rather than only textual conflicts in xG persistence,
  checkpoint scheduling, migration heads, recommendation admission and audit
  identity; and
- evaluate merge, rebase and transplant/cherry-pick strategies. The report must
  select one and reject at least two with explicit trade-offs. This task does not
  execute the selected integration.

### 4.2 Gate 1 persistence and corpus audit

- trace every `captured_at` field used by the Gate 1 corpus, split manifest,
  feature construction and xG eligibility rule back to its persisted source;
- determine whether the old mutable-write behaviour could change historical
  first visibility or only later operational rows;
- compare the frozen 18,696/9,348 identity set with locally available later
  corpus artifacts by fixture and row identity where those artifacts exist;
- separate semantic invalidation from ordinary corpus expansion;
- never rerun model fitting or metrics; and
- decide whether the former Gate 1 result remains a valid historical result,
  must be reproduced unchanged, or requires a new experiment identity on the new
  baseline. A corpus change cannot be called the same experiment.

### 4.3 Calibration authority and downgrade audit

- locate every producer and consumer of `CALIBRATION_STATUS`,
  `PRODUCTION_VALIDATED`, `APPROVED_VALIDATED` and the POINT-EV authority;
- define the future promotion record, signer/actor, evidence-hash binding,
  immutability and revocation/downgrade event without implementing them;
- trace how a downgrade would cause the existing opportunity to become blocked
  and enqueue `CANDIDATE_WITHDRAWN`;
- identify any missing orchestration needed between an admission record and the
  existing attempt lifecycle; and
- make POINT-EV landing a separate task if it is a dependency. Local acceptance
  must never be represented as production enforcement.

### 4.4 Data-role isolation

- mark every fixture set ever used for fitting, preprocessing, model selection,
  threshold choice, debugging or metric inspection;
- treat former VALIDATION and HOLDOUT as equally observed;
- define the exact permissible development set for the next calibration task;
- prohibit claims of improvement on a set used to choose the change;
- preserve the existing forward preregistration byte-for-byte unless a formal
  pre-first-row amendment is selected and committed before any row exists; and
- if a different model identity needs an earlier evaluation, require a separate,
  non-overlapping prospective cohort, power justification, evaluation date and
  one-look rule frozen before results.

### 4.5 Base/lineup and paired-ledger design

- decide whether confirmed-lineup output is a second checkpoint version of one
  model, an explicit overlay on a base model, or an independent track;
- bind that decision into future forecast/attempt identity and schema
  requirements before table design;
- compare reuse of V1 `lineup_input_hash`, `LINEUP_CONFIRMED` and the post-lineup
  fresh-exact-quote gate with any proposed alternative;
- use the preregistered `fixtures_with_paired_v1_production_capture` as the strict
  paired-output numerator;
- keep the full eligible opportunity denominator, including V1/V2 misses,
  unscorable rows and exclusions, so neither-track output is required for a row
  to remain in denominator accounting; and
- define settlement as analysis-only and append-only, with the same authoritative
  result and market settlement rules but no V1 ledger, candidate, opportunity,
  outbox or formal-P&L writes.

## 5. Decisions that the report must make

The report must give a written technical judgement, alternatives and rejected
options for all eleven items in the revised scope:

1. integration base and code-line reconciliation;
2. effect of missing xG persistence fixes on the old Gate 1 conclusion;
3. treatment of the 18,696/9,348 to 18,978/9,489 corpus change;
4. `APPROVED_VALIDATED` production, binding, revocation and downgrade flow;
5. POINT-EV landing sequence and the V1 candidate-baseline discontinuity;
6. exact development/validation/final-evidence isolation;
7. disposition of the already preregistered failed-model forward cohort;
8. base/lineup decision as a hard ledger-schema input;
9. lineup timing and V1 lifecycle reuse;
10. strict paired-output numerator and the 85% T-30m denominator gap; and
11. restoration or explicit deferral of Gate 3 independent worker/canary and
    Gate 4 Dashboard work, with task IDs kept separate from Gate IDs.

## 6. Frozen decision constraints

- A failed old experiment remains failed; a new corpus/model/protocol receives a
  new identity rather than overwriting it.
- Both former VALIDATION and HOLDOUT are observed and unavailable for a new
  confirmatory claim after model selection.
- The old forward preregistration may not be relaxed after the first row. Any
  allowed amendment must precede that row, name the zero-row evidence, and retain
  the old file/history.
- POINT-EV is not deployed and may not be depended on implicitly.
- `APPROVED_VALIDATED` must be evidence-bound, auditable and reversible; a scalar
  environment flag or unversioned constant is insufficient.
- High EV is never calibration evidence.
- A lineup fact may affect only a version whose feature time is not before the
  lineup capture and whose exact quote is not before lineup confirmation.
- Task numbers and Gate numbers are independent namespaces.
- Gate 1 remains `FAIL` and Gate 2 remains `CLOSED` throughout this review.

## 7. Deliverables and acceptance

The result commit must add, without modifying this frozen protocol:

- `REPORT.md` with the eleven judgements, evidence, alternatives and rejected
  options;
- `STATUS_MATRIX.md` covering Gate 0 through Gate 5 and every deliverable;
- `COMMIT_LINEAGE_MATRIX.md` with topology, duplicate-change and conflict
  inventories;
- `FACTOR_DATA_ROLE_MATRIX.md` with exact data roles and contamination status;
- `DUAL_TRACK_CONTRACT.md` with pairing, denominator, settlement and lineup
  identity semantics; and
- a corrected task roadmap that includes POINT-EV landing separately and names
  Gate 3 and Gate 4 work.

Acceptance requires every factual number to identify whether it came from local
Git, a frozen artifact, supplied evidence or live state. Any unavailable evidence
must remain `NOT_VERIFIABLE`, not inferred.

## 8. Stop lines

- Provider calls: `0`.
- Production reads: `0`.
- Production writes: `0`.
- GitHub/GHCR access: `0`.
- Model fitting, tuning, scoring or new metric inspection: `0`.
- Migration apply, collector/timer start, deployment: `0`.
- Candidate, notification, V1/V2 ledger or formal-P&L writes: `0`.
- Match-result and current-65-pick access for model selection: `0`.
- EV-SE work and alpha/beta changes: `0`.
- Existing forward preregistration rewrite: `0` unless a separately proposed
  pre-first-row amendment is itself accepted after this protocol review.

