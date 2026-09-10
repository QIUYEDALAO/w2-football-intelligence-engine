# F1R-B migration and rollback

`W2_AH_FACTOR_ACCURACY_F1R_B_PRODUCTION_RECORDING_INTEGRATION_20260911`
Parent commit `71daa3f5ec17ac3c5484e75a87d6bcac990d4bae`.

**Nothing here has been applied to the production database.**
`PRODUCTION_DB_READS = 0`, `PRODUCTION_DB_WRITES = 0`, `DEPLOYMENT_EXECUTED = false`.
The migration was generated and validated against an isolated database this run
created and destroyed.

## The migration

```text
migrations/versions/0071_forward_ah_factor_observation.py
revision      0071_forward_ah_factor_observation
down_revision 0070_notification_delivery_routing
```

It creates one table, `forward_ah_factor_observations`, and three indexes plus
one partial unique index. It is additive: every `op.*` call in `upgrade` is
`create_table` or `create_index`, and every one names that single table. There
is no `alter_column`, no `drop_column`, and no reference to any existing table.
`test_17_the_migration_is_additive_only`, `test_18_the_migration_touches_no_existing_table`.

Historical prematch attempt payloads are untouched, so their identity, their
hashes and their `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY` semantics are exactly
what they were.

## Fail closed, not backfilled

Every column that carries meaning is `NOT NULL`. The only nullable columns are
`signed_score`, `supersedes_observation_id` and `revision_reason`, each of which
has a real absent case. `test_17_every_meaningful_column_is_not_null`.

An observation missing its version, capture identity, source version or
evidence time is not a partially-complete row to be filled in later — it is a
row that must never have been written. Nothing is backfilled and no default is
invented.

Constraints carried in the DDL:

| Constraint | What it refuses |
|---|---|
| `ck_…_factor_id` | any factor outside the four AH scoring factors |
| `ck_…_market` | any market but `ASIAN_HANDICAP` |
| `ck_…_pit` | `evidence_time_utc >= evaluated_at_utc` |
| `ck_…_score_presence` | a participating row with no score, or a scoreless row carrying one |
| `ck_…_status_agrees` | `participated` disagreeing with `factor_status` |
| `ck_…_zero_weight_when_absent` | a non-participating row carrying weight |
| `ck_…_revision_pairing` | a supersession with no reason, or a reason with no target |
| `ck_…_no_self_supersession` | a row superseding itself |
| `uq_…_original_per_attempt` | the same factor twice on one evaluated attempt |

### Why the uniqueness is partial

`uq_…_original_per_attempt` is unique on
`(evaluation_id, attempt_id, fixture_id, market, factor_id, evaluated_at_utc)`
**where `supersedes_observation_id is null`**.

A plain unique constraint was the first version and it was wrong: a correction
is an append that supersedes an earlier row rather than editing it, so the same
factor legitimately appears again on the same attempt. The plain constraint
forbade exactly the revision the contract requires, and
`test_15_a_revision_chain_appends_and_leaves_the_old_rows` caught it. Making
the index partial keeps the guarantee that matters — one *original* per factor
per attempt — without outlawing the revision chain.

### Four-factor batch consistency

A check constraint cannot count rows, so the all-or-nothing guarantee is where
it can be enforced: the store validates all four, resolves conflicts, and
stages every row inside one `session.begin()`. A refusal or a failure part way
through commits nothing. `batch_key` indexes the four rows of one attempt so a
batch is addressable as a unit.

## Isolated validation

`ISOLATED_REPLAY_RESULT.json` is the machine-readable record. The sequence:

1. create the pre-migration state (every table except the new one) in a fresh
   database in a temporary directory;
2. `alembic stamp 0070_notification_delivery_routing`;
3. `alembic upgrade head` — creates the table and its indexes;
4. `alembic upgrade head` again — no-op, exit 0;
5. append the four-factor batch — 4 rows;
6. append the identical batch again — 0 appended, 4 idempotent no-ops;
7. read every row back and compare all business fields against the contract's
   own serialisation of the record;
8. `alembic downgrade 0070…` **with rows present** — refuses, non-zero exit,
   rows still 4;
9. delete the rows, `alembic downgrade 0070…` — succeeds, table gone;
10. `alembic downgrade 0070…` again — no-op, exit 0;
11. confirm the unrelated table count is unchanged from before the upgrade.

### PostgreSQL was not available

PostgreSQL is not installed in this environment (`pg_ctl`, `initdb`,
`postgres` and `psql` are all absent from `PATH`), and reaching the production
PostgreSQL is forbidden by this task. The isolated database is therefore a
file-backed SQLite created in a temporary directory and deleted at the end —
real DDL, real constraints, real transactions, real Alembic, and not the
production database. This is recorded verbatim in
`ISOLATED_REPLAY_RESULT.json` under `database_kind` and `database_note` rather
than presented as a PostgreSQL result.

The partial unique index is written with both `postgresql_where` and
`sqlite_where`, so the same predicate applies on either dialect. What a
PostgreSQL run would still add is dialect-specific behaviour of the check
constraints and the self-referencing foreign key; that is the residual gap and
it is stated here rather than glossed.

## Rollback

**Rollback never destroys an append-only business fact.** `downgrade` counts
the rows first:

* **empty** — drop the indexes and the table. This is the state the migration
  ships in: `LIVE_CAPTURE_ENABLED` is false, so nothing has been captured.
* **not empty** — raise
  `FORWARD_AH_FACTOR_OBSERVATION_DOWNGRADE_WOULD_DESTROY_FACTS:rows=<n>` and
  change nothing.
* **table already absent** — return quietly, so a repeated downgrade is a
  no-op rather than a failure.

### The forward-compatible path for a populated table

If observations exist and the application has to be rolled back, do **not**
force the schema down. Instead:

1. disable the writer — `PRODUCTION_CAPTURE_ENABLED = False` in
   `scripts/quant/f1r_b_production_ports.py`, which is already the shipped
   state;
2. leave `forward_ah_factor_observations` and its rows in place. The prior
   application revision does not read the table, so an extra table is inert to
   it;
3. roll the application back without moving the Alembic revision;
4. when the schema must genuinely be retired, export the rows to an
   append-only archive first, verify the export by re-deriving every
   `observation_id`, and only then run the empty-table downgrade.

This is why `downgrade` refuses rather than cascading: a rollback that silently
deleted observations would destroy the only record of what a factor contributed
to an evaluation, which is the entire point of capturing them.

The pattern is the repository's own, not a new invention. Migration 0052 does
the same thing for `checkpoint_plan`, and
`tests/integration/test_migrations.py::test_0052_refuses_nonempty_retired_checkpoint_plan`
is the existing test that pins it.

`tests/integration/test_migrations.py::test_alembic_upgrade_and_downgrade_smoke`
already exercises 0071 inside the full history — `upgrade head`,
`downgrade base`, `upgrade head` — and passes, so the new revision round-trips
in the chain as well as in isolation.

### Failure recovery

| Failure | State afterwards | Recovery |
|---|---|---|
| `upgrade` fails mid-DDL | Alembic revision not advanced | fix, re-run `upgrade`; `create_table` is not partially applied |
| `upgrade` run twice | second is a no-op, exit 0 | none needed |
| batch write fails part way | zero rows added, transaction rolled back | re-run the batch; identical rows are idempotent no-ops |
| batch replayed after success | 0 appended, 4 idempotent no-ops | none needed |
| same id, different content | `OBSERVATION_ID_BUSINESS_CONFLICT`, zero rows added | investigate the source change; append a revision, never an edit |
| `downgrade` refused (rows present) | table and rows intact | use the forward-compatible path above |
| `downgrade` run twice | second is a no-op, exit 0 | none needed |
