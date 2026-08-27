# V2-REENTRY-PROTOCOL-01 — commit lineage matrix

All values below come from local Git objects. No remote was contacted.

## Topology

| Pair | Merge base | Left only | Right only | Meaning |
|---|---|---:|---:|---|
| `fc70b48e...6f2032cc` | `ae5b4d88` | 21 | 17 | production and V2 diverged |
| `fc70b48e...2b4751c6` | `fc70b48e` | 0 | 5 | POINT-EV is based on production |
| `6f2032cc...2b4751c6` | `ae5b4d88` | 17 | 26 | V2 versus production plus POINT-EV |

Selected future base: `2b4751c6`.

Selected integration: non-fast-forward merge of `6f2032cc` into a fresh branch from
`2b4751c6`, followed by semantic conflict review and the full local gate. This package
does not execute it.

## Duplicate patch

| Line | Commit | Subject | Stable patch-id | Disposition |
|---|---|---|---|---|
| production | `0c8b3006` | far-horizon odds checkpoint slack | `568c9554aff13d4ff4fbf65fd13c36575b604e31` | keep history |
| V2 | `d908250d` | far-horizon odds checkpoint slack | `568c9554aff13d4ff4fbf65fd13c36575b604e31` | do not replay content |

Both modify only `config/policies/matchday_intake.v2.json`, with the same 40
insertions/40 deletions. Same subject alone was not treated as proof; patch-id is the
proof.

## Production-only commits missing from V2

The 21-commit production side includes the two xG safety changes material to this
review:

- `5b926ee8` — incomplete/null Statistics remains retryable;
- `4733c76f` — `team_xg_match` first visible evidence is immutable.

It also includes scheduler, delivery routing, xG competition recovery, synchronized
release and read-scope changes. Therefore V2 cannot be promoted by deploying
`6f2032cc` directly.

## POINT-EV additions

| Commit | Role |
|---|---|
| `6fdecb95` | protocol frozen before tracing |
| `1f0a689f` | calibration blocks recommendation admission |
| `19c6bd2c` | calibration becomes attempt identity and audit record |
| `238d04b1` | persisted payload reconstructs calibration audit fields |
| `2b4751c6` | evidence SHA documentation correction |

POINT-EV has no deployment authority in this package.

## Merge simulation

Local `git merge-tree --write-tree 2b4751c6 6f2032cc` found one content conflict:

- `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`.

The following changed in both histories and auto-merged, so they require semantic
review even without text markers:

- `apps/scheduler/main.py`;
- `infra/compose/compose.staging.yml`;
- `src/w2/features/xg_materialization.py`;
- `src/w2/ingestion/future_refresh_repository.py`;
- `tests/integration/test_future_refresh_db_persistence.py`;
- `tests/unit/test_future_fixture_refresh.py`; and
- `tests/unit/test_runtime.py`.

Other overlapping changed paths include the checkpoint policy/readiness files. The
identical far-horizon patch explains their content overlap.

## Semantic resolution requirements

| Area | Required merged invariant |
|---|---|
| xG cache | null or one-sided xG never marks Statistics complete |
| xG persistence | first write preserves `captured_at`, values and raw evidence |
| V2 historical method | `SOURCE_KICKOFF_ONLY` stays explicitly research-scoped and hashed |
| raw fixture scope | V2 scope membership remains append-only and conflict checked |
| scheduler | current production checkpoint/claim fixes remain authoritative |
| worker | V2 uses independent role/service and cannot call Provider or write V1 |
| migrations | factor revision follows notification routing and has one Alembic head |
| POINT-EV | admission is fail-closed for all nonvalidated states |
| V2 authority | no free-form admission row may manufacture `APPROVED_VALIDATED` |
| documentation | old Gate 1 remains old-line evidence, not a merged-baseline result |

## Rejected integration strategies

| Strategy | Rejection |
|---|---|
| rebase the 17 V2 commits | rewrites the frozen evidence chain and serialises conflicts |
| cherry-pick a subset | omission risk and duplicate-patch risk |
| start from `6f2032cc` | omits 21 production commits and all POINT-EV commits |

