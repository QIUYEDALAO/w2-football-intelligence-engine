# V2-REENTRY-PROTOCOL-01 — technical judgement

Status: `CLAUDE_ACCEPTED / DOCUMENT_CORRECTIONS_APPLIED / NO_FOLLOW_ON_STARTED`

Frozen protocol: `1f080b26` (`PROTOCOL_FROZEN_20260827.md`)

This report is a design decision, not an implementation or release approval. Gate 1
remains `FAIL`; Gate 2 remains `CLOSED`. No model was fitted or scored and no
production, Provider, GitHub, migration, collector, notification or deployment path
was used.

## 1. Executive decision

The V2 programme may re-enter only through a new integration and experiment identity:

1. base the integration on POINT-EV head `2b4751c6`, which is a descendant of the
   deployed `fc70b48e`, then merge `6f2032cc` without rewriting either history;
2. preserve the old Gate 1 result as a valid failure of its frozen
   `SOURCE_KICKOFF_ONLY` experiment, but do not reuse it as evidence for the enlarged
   xG corpus or corrected production persistence line;
3. use only the frozen 2024 TRAIN identities as development data in calibration
   recovery; 2025 VALIDATION and 2026 HOLDOUT are equally observed and cannot support
   a new confirmation claim;
4. freeze a successor forward preregistration for the new model before the first V2
   row. The old file remains preserved as a never-started, superseded failed-model
   protocol;
5. represent base and confirmed-lineup predictions as two explicit checkpoint
   variants of one model family. This dimension must exist in the ledger schema and
   identities before migration design;
6. land POINT-EV as an independent production task before any V2 admission. It is not
   a prerequisite for offline development or analysis-only collection;
7. implement an append-only, evidence-bound calibration decision and a downgrade
   reconciler before any process can produce `APPROVED_VALIDATED`; and
8. restore the independent worker/forward canary and V2 Dashboard as explicit tasks.

High EV is not validation evidence. Until the future evidence and authority chain are
complete, V2 remains analysis-only and `APPROVED_VALIDATED` does not exist.

## 2. Evidence classifications

| Claim | Result | Authority |
|---|---|---|
| Production head is `fc70b48e` | `CONFIRMED_RECORD / NOT_LIVE_VERIFIED` | local Git and W2 Vault deployment record; production reads were 0 |
| V2 head is `6f2032cc` | `CONFIRMED` | local Git |
| POINT-EV head is `2b4751c6` | `CONFIRMED` | local Git |
| Production/V2 split at `ae5b4d88`, 21/17 | `CONFIRMED` | local `merge-base` and `rev-list` |
| POINT-EV is five commits above production | `CONFIRMED` | local Git, merge-base exactly `fc70b48e` |
| far-horizon change duplicated | `CONFIRMED` | stable patch-id `568c9554…` for both commits |
| V2 lacks `5b926ee8` and `4733c76f` | `CONFIRMED` | local ancestry and diffs |
| xG changed 18,696/9,348 to 18,978/9,489 | `CONFIRMED_LOCAL_ARTEFACTS` | two local CSV snapshots; not a live production query |
| current common xG rows changed values | `CORRECTED: NO` | all 18,696 `(fixture_id, team_id)` rows match on compared fields |
| code produces `APPROVED_VALIDATED` | `CONFIRMED: NO` | code search; value is accepted by consumers but has no producer |
| production calibration is `BASELINE_PRIOR` | `CONFIRMED_RECORD / NOT_LIVE_VERIFIED` | `src/w2/strategy/calibration.py` at the recorded production lineage; production reads were 0 |
| VALIDATION and HOLDOUT metrics were observed | `CONFIRMED` | frozen Gate 1 report and artifact |
| no forward V2 row exists | `SUPPLIED_AND_CODE_CONSISTENT / NOT_LIVE_REFRESHED` | revised scope, Vault and production migration absence |
| V1 T-30m evaluation is 85% | `SUPPLIED_FROZEN_OPERATIONAL_EVIDENCE` | W2 Vault record; no production query in this task |

## 3. Judgement 1 — integration base and reconciliation

### Decision

Create the future integration branch from `2b4751c6` and make a non-fast-forward
merge of `6f2032cc`. Preserve both parent histories and the old evidence commits.
Do not execute that merge in this protocol task.

Why this baseline:

- `2b4751c6` already contains the deployed production history and all five accepted
  POINT-EV commits;
- a merge keeps the Gate 1 and preregistration commit identities historically true;
- the patch-equivalent far-horizon commits remain visible in the DAG but apply one
  content change; and
- local `git merge-tree --write-tree 2b4751c6 6f2032cc` reports one textual conflict,
  in the architecture checklist, rather than a long sequential conflict chain.

The merge is still a semantic integration, not a mechanical green merge. The
auto-merged xG repository, scheduler, Compose and tests require explicit review.
Migration `0070_factor_shadow_v2_gate0` declares
`down_revision = 0070_notification_delivery_routing`, but that target revision does
not exist on branch `6f2032cc`. The chain can become complete only on the selected
merged baseline `2b4751c6 + 6f2032cc`, where the migration graph and single-head claim
must be checked again.

### Conflict inventory

- Text conflict: architecture convergence master checklist.
- xG semantic conflict: V2 `SOURCE_KICKOFF_ONLY` research semantics must coexist with
  production null-retry and first-write immutability.
- persistence semantic conflict: raw fixture scope membership and immutable
  `team_xg_match` evidence share `future_refresh_repository.py`.
- scheduler/Compose semantic conflict: current production services and the isolated
  V2 worker/timer definitions share entrypoints and environment surfaces.
- policy overlap: the far-horizon slack patch is identical and must not be applied
  twice.
- migration concern: two files use the numeric prefix `0070`, while Alembic authority
  is the revision/down-revision chain, not the filename number.
- admission semantic gap: V2's admission table has no evidence-bound producer and
  does not itself satisfy POINT-EV authority.

### Rejected options

- **Rebase all 17 V2 commits onto POINT-EV**: rewrites the exact historical chain,
  creates sequential conflict opportunities and makes frozen reports appear to have
  arisen on semantics they did not use.
- **Cherry-pick selected V2 commits**: risks omitting a guard or prereg binding and
  duplicates the patch-equivalent scheduler change unless hand-curated.
- **Use `6f2032cc` as the base and add production/POINT-EV later**: starts from the
  stale side of a 21-commit production divergence and makes safety fixes optional.

## 4. Judgement 2 — missing xG persistence fixes and old Gate 1

### Decision

The old Gate 1 failure remains an honest result for its frozen inputs and declared
method. It must not be rerun in place or relabelled. A current-baseline evaluation is
required and must have a new experiment identity.

`5b926ee8` changes future acquisition completeness: a null/one-sided Statistics
response no longer satisfies the cache, so it remains retryable. It does not prove
that any numeric row in the frozen Gate 1 CSV was wrong.

`4733c76f` makes `team_xg_match` first-write-wins. The old Gate 1 runner loaded
`captured_at`, but explicitly called `materialize_rolling_xg(...,
pit_semantics=SOURCE_KICKOFF_ONLY)`. Under that contract eligibility used source
kickoff, not `captured_at`. Therefore the first-write fix does not retroactively alter
the arithmetic of the frozen experiment.

This is a limited conclusion. The old result is not evidence for strict captured-at
PIT visibility. It is evidence under the separately frozen claim that this xG method
is an immutable post-match fact that may be indexed by source kickoff.

The local later snapshot also provides a direct guard against an overclaim: every
one of the 18,696 common `(fixture_id, team_id)` rows has the same kickoff,
`captured_at`, xG values and source system. No common row was removed. Thus no local
evidence shows that first-write immutability would change the old frozen rows.

That zero-difference evidence is bounded to the two local snapshots from
`2026-08-22T06:22Z` through `2026-08-26`. It is not evidence that the common rows had
never varied before the earlier snapshot.

### Rejected options

- **Declare the old result invalid solely because `4733c76f` was absent**: that
  ignores the runner's explicit source-kickoff-only rule and the unchanged common
  rows.
- **Declare the old result current**: it ignores the changed code baseline and the
  enlarged historical inputs.
- **Silently replace the CSV and reuse the old hashes**: that overwrites an experiment
  identity and is forbidden.

## 5. Judgement 3 — corpus expansion is a new experiment

The frozen Gate 1 CSV (`09d921ff…`) contains 18,696 rows / 9,348 fixtures. The later
local CSV (`84ef81e9…`) contains 18,978 rows / 9,489 fixtures.

Exact local comparison found:

- common rows: 18,696;
- added rows: 282 / 141 fixtures;
- removed rows: 0;
- common compared-field mismatches: 0;
- added rows before the old historical cutoff: 108 / 54 fixtures;
- added rows at or after the cutoff: 174 / 87 fixtures; and
- all 282 added rows were captured after the old Gate 1 corpus snapshot.

The +54 pre-cutoff fixtures can change historical rolling xG inputs and scorable
coverage. Even though the common rows are stable, the later corpus is not the same
experiment. `V2-GATE1-CALIBRATION-RECOVERY-01` must create new corpus,
split/preprocessing, feature, model, calibration, score-matrix and report hashes. The
old Gate 1 report remains byte-for-byte historical evidence and `FAIL`.

No model metrics were recomputed in this review.

Rejected: treat row-count growth as harmless sample accumulation while retaining the
old hashes; or use only the 18,696-row intersection and call that the current corpus,
which would deliberately discard now-known eligible evidence.

## 6. Judgement 4 — producing and revoking `APPROVED_VALIDATED`

### Decision

`APPROVED_VALIDATED` must be a derived status from an active append-only authority
decision, never an environment variable, mutable config constant or arbitrary field
on a forecast row.

The decision belongs in a new domain-owned append-only
`calibration_authority_decision` store consumed by
`w2.domain.calibration_authority`, not in a factor-only free-form table. The writer is
an Owner-authorised Gate finalizer operated under a separate release-governance RBAC
role; model training code, scheduler and collector have no write permission.

The future authority record must include at least:

- exact model family, model version, checkpoint variant, feature registry,
  preprocessing and calibration identities;
- protocol/preregistration hash, evaluation package manifest hash and component
  evidence hashes;
- cohort bounds, metric/gate verdicts and source release identity;
- decision type (`APPROVE`, `REVOKE`, `EXPIRE`), reason, predecessor decision hash,
  effective time and optional expiry;
- Owner decision identity and the separately authorised operator/RBAC identity; and
- canonical payload hash and authority schema version.

The Gate finalizer may append `APPROVE` only after Owner acceptance of the exact Gate
5 evidence package. Runtime obtains `APPROVED_VALIDATED` only when the latest valid
decision for the exact identity tuple is an unexpired approval. Existing
`factor_shadow_v2_admission` is not sufficient as designed: it has a free-form status
and payload but no enforced evidence binding, decision lineage or POINT-EV consumer.

Revocation is another append-only decision; no prior row is edited. A downgrade
reconciler must then re-evaluate all open opportunities for the affected identity
under the current authority. POINT-EV R1 places calibration status in attempt
identity, so the downgrade creates a distinct attempt. Its state becomes
`NOT_READY_MODEL_INPUT` / opportunity `BLOCKED_BY_GATE`; the existing notification
transition from a previous `EVALUATED_CANDIDATE` enqueues `CANDIDATE_WITHDRAWN`.

The final step is currently missing: changing an authority record alone does not
visit existing open opportunities. The reconciler and its idempotent sweep/withdrawal
tests are required before approval can influence production.

### Rejected options

- set `CALIBRATION_STATUS = "APPROVED_VALIDATED"` in code;
- carry a boolean `admissible=true` inside the calibration artifact;
- infer validation from EV size, successful simulation, `READY`, or a local test run;
- mutate or delete the original approval on downgrade.

## 7. Judgement 5 — POINT-EV sequencing and the V1 discontinuity

`POINT-EV-LANDING-01` is a separate production task and is a hard prerequisite for the
legacy Task 6 (`V2-GATE5-ADMISSION-01`) and for any V2 candidate influence. It is not
a prerequisite for `V2-GATE1-CALIBRATION-RECOVERY-01` development, schema work or
analysis-only shadow rows.

Its deployment must be independently authorised and accepted. Local head
`2b4751c6` is not production enforcement, and `POINT-EV-LANDING-01` requires separate
explicit Owner deployment authorisation.

With current `BASELINE_PRIOR`, POINT-EV landing makes V1 produce no formal candidates.
That is the intended fail-closed result, but it creates an operational epoch break:

- pre-POINT-EV V1 candidate deliveries were admitted without calibration authority;
- post-POINT-EV V1 prediction/EV evidence may continue, but formal candidate count is
  expected to be zero until a validated calibration exists; and
- candidate yield or P&L cannot be compared across that boundary as one homogeneous
  V1 control.

The V1/V2 scientific comparison therefore uses V1 production forecast captures and
the same quotes, not "V1 delivered candidate" as the pairing requirement. The
POINT-EV landing task must prove that analysis capture continues while candidate and
outbox production stop. Reports must stratify candidate-era operational metrics by
authority epoch.

Rejected: postponing POINT-EV until V2 is ready merely to preserve candidate volume;
and using pre-fix V1 candidates as the continuing live control.

## 8. Judgement 6 — exact data roles after both old test sets were observed

`V2-GATE1-CALIBRATION-RECOVERY-01` development is limited to target fixture identities
marked `TRAIN` in frozen split manifest `01a4f593…`: kickoff in
`[2024-01-01, 2025-01-01)`, exactly 3,118 targets. Under the old Gate 1 xG snapshot,
2,684 were scorable for coefficient fitting. Missing/unscorable members remain in the
development accounting.

`V2-GATE1-CALIBRATION-RECOVERY-01` may use their outcomes for fitting, calibration
choice, debugging and internal time-ordered/cross-fitted diagnostics. Once used this
way, every such diagnostic is development evidence only. It cannot be called a
validation or Gate pass.

The old 2025 VALIDATION set (4,520 targets) and 2026 HOLDOUT set (2,628 targets) are
both sealed as `OBSERVED_CONFIRMATORY_CONTAMINATED`. They may be used only for
byte-for-byte regression/reproduction checks that do not reveal or optimise new
metrics. They cannot choose a method, threshold, feature, coefficient or calibration,
and no "improvement" claim may be made on them.

There is no untouched historical confirmation set left in the frozen corpus. The
first confirmatory evidence for the new identity must be a prospective cohort that
starts after the new model and preregistration are frozen. Its one-look date, sample
rule, metrics, attrition and power basis must be frozen before collection.

Rejected: tune on 2025 and test on already observed 2026; tune on both and report
cross-validation; or call the 54 later-added pre-cutoff xG fixtures a new holdout,
because their addition changes inputs to already observed target outcomes.

## 9. Judgement 7 — amend the preregistration before the first row

Choice: **formal pre-first-row amendment**, not cancellation and not parallel use of
the old model protocol.

The current preregistration is bound by `frozen_gate1_inputs` to the failed model and
its old hashes. `V2-GATE1-CALIBRATION-RECOVERY-01` necessarily creates a new identity.
Running the old protocol
in parallel would spend capacity on a model already known to fail, while its
`production_capture_captured_at_not_before=2026-08-22T09:05:33Z` predates actual
activation and would create an irrecoverable prospective gap.

The amendment must:

- preserve the existing file and hash as `SUPERSEDED_BEFORE_FIRST_SAMPLE`, never
  edit it in place;
- include evidence that the forward row count was zero immediately before freeze;
- bind the complete new model/checkpoint/calibration/schema identities;
- set the new cohort start to the exact later of amendment freeze time and actual
  collector activation; no rows between the old and new start may be backfilled;
- bind the full eligible denominator and strict paired numerator contract;
- replace the old power/evaluation schedule only with a design fixed without
  inspecting prospective outcomes; and
- retain `relaxation_forbidden_after_first_sample=true`.

The window closes permanently when the first row for any amended cohort lands. Until
the amendment is accepted and frozen, collector/migration activation is forbidden.

Rejected: mark the old preregistration "close enough" for a new hash identity; or
start collection now and revise model/cohort fields later.

## 10. Judgement 8 — base/lineup is a hard schema input

Decision: one model family with **two explicit checkpoint variants**:

- `BASE_PRE_LINEUP`; and
- `LINEUP_CONFIRMED`.

The lineup variant is an immutable child of a specific base forecast, not a mutation
of it and not an unlabelled optional feature. It has its own feature/calibration
identity and must earn validation independently. This retains a coherent family while
preventing late facts from changing an earlier prediction.

Before table creation, forecast schema and identity must explicitly include:

- `checkpoint_variant` (non-null);
- `parent_forecast_identity_hash` (required for lineup, null for base);
- `lineup_input_hash` and `lineup_captured_at` (required for lineup, null for base);
- production capture/checkpoint identity and feature-as-of;
- model, feature, preprocessing and calibration versions; and
- a variant-aware admission identity.

Unique constraints and forecast hashes must include the variant and relevant lineup
identity. Encoding the distinction only inside `model_version` or JSON is rejected:
the current V2 tables cannot enforce the required invariant that way.

Rejected: one mutable row whose lineup columns are later filled; and two unrelated
models with no parent relation, which loses the incremental question.

## 11. Judgement 9 — lineup timing reuses V1 authority

V2 must reuse V1's authoritative `LINEUP_CONFIRMED` event,
`lineup_input_hash`, captured time and post-lineup fresh exact-quote gate. Creating a
second lineup truth or a second quote-freshness rule would make same-opportunity
pairing unverifiable.

For the lineup variant:

- `feature_as_of >= lineup_confirmed.captured_at`;
- the exact quote capture is at or after lineup confirmation;
- V1 and V2 use the same checkpoint, quote identity, market, line, selection and
  bookmaker observation;
- both bind the same canonical `lineup_input_hash`; and
- missing/incomplete identities produce an explicit miss, never fallback to the base
  variant under a lineup label.

The base and lineup variants may use different chronological quotes; therefore their
raw EV difference is not, by itself, a causal estimate of lineup value. The strict
same-quote requirement applies to V1 versus V2 within each checkpoint variant.

Rejected: recompute lineup prediction against a pre-lineup quote; hash an independently
normalised lineup; or pair V1 T-30 with V2 LINEUP_CONFIRMED.

## 12. Judgement 10 — strict pair and denominator

A metric pair requires **both** V1 and V2 to have a scorable output for the exact same
fixture, market, checkpoint variant and quote. The numerator name remains the
preregistered `fixtures_with_paired_v1_production_capture`; it is not replaced by an
informal join.

Both-output is not an eligibility requirement for the denominator. The funnel begins
with all eligible scheduled opportunities and must retain:

1. eligible fixtures/opportunities;
2. V1 checkpoint captured versus missed;
3. V1 production capture available;
4. V2 forecast available;
5. exact V1/V2 pair available;
6. result/settlement scorable; and
7. exclusion reason.

The supplied T-30m `34/40 = 85%` V1 evaluation rate means the 15% gap remains in the
full denominator as V1 missingness. It may reduce the strict paired numerator, but it
may not disappear from coverage, attrition or sensitivity reports. Primary paired
metrics are accompanied by the full-denominator funnel and prespecified missingness
strata; no inverse selection claim is made without a frozen method.

Rejected: inner-join the two tracks and report only survivors; count V2-only rows as
pairs; or define pairing by fixture/date without exact checkpoint and quote identity.

## 13. Judgement 11 — Gate 3, Gate 4 and task namespace

Gate 3 and Gate 4 are restored, not deferred:

- **Gate 3 — independent worker + forward canary**: isolated V2 service/role, Provider
  isolation, V1 read-only, V2-only append rights, release identity, fail-closed switch,
  first-row prereg lock, paired capture and zero candidate/outbox influence. This is a
  separately authorised deployment/canary task.
- **Gate 4 — V2 Dashboard**: read-only V1/V2 identity, funnel, attrition, variant,
  cohort and authority display. It must not expose interim locked metrics or create
  candidate authority. UI correctness and API read contracts receive their own local
  and deployed acceptance.

Task order and Gate order are separate namespaces. A task may prepare more than one
Gate, and a Gate may require multiple tasks. The corrected roadmap is in
`TASK_ROADMAP.md`.

Rejected: call the third task Gate 3, infer Gate 4 from a fourth task, or postpone the
Dashboard until after evaluation when it is needed to audit collection quality.

## 14. Stop-line receipt

| Boundary | Observed |
|---|---:|
| Provider calls | 0 |
| Production reads | 0 |
| Production writes | 0 |
| GitHub/GHCR access | 0 |
| Model fit/tune/score/new metrics | 0 |
| Migration/collector/timer/deployment | 0 |
| Candidate/outbox/formal-P&L writes | 0 |
| Match-result/current-65-pick use | 0 |
| Business-code changes | 0 |

The only repository changes are protocol documents and local Git commits. No Gate,
production authority or deployment status changes as a result of this package.
