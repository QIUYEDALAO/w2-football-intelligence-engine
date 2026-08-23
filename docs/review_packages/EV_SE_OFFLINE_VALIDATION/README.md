# EV-SE offline preregistration reproduction

This package reproduces the preregistration baseline, the Owner-approved Contract 1 semantic specification, the frozen GH-3 counterfactual, its `price_source`-stratified impact, and the item-2 denominator-authority feasibility evidence. It makes no Provider calls, production database writes, or outcome reads. The audit uses repeatable-read PostgreSQL `BEGIN ... READ ONLY` transactions, reads the frozen evaluation cohort and xG source separately, and rolls both back.

Contract 1 approval is semantic only: `lambda_sigma` means a true standard deviation. The package does not authorize a coefficient, an SE formula, a production implementation, or a release. Formula-family item 3 remains frozen pending the Owner's item-2 denominator decision.

## 1. Checkout and self-check

```bash
git switch codex/ev-se-offline-validation
python3 scripts/audit_ev_se_offline_preregistration.py --self-check
```

The expected result is `{"self_check": "PASS"}`.

## 2. Acquire and verify the frozen corpus

The already materialized local artifact is:

```text
/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/reports/factor_model_v2/gate1_history_backfill_20260822T055041929427Z/factor_history_corpus.json
```

It is intentionally not committed. Its byte-level SHA-256 must be:

```text
80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2
```

Its W2 canonical corpus fingerprint must be:

```text
d19b217afe159c87dbf8d0dea87c260374ac9d18ffd8bb97581cfffe858cedc5
```

The audit script checks both fingerprints, the `38,706` row count, and snapshot `2026-08-22T05:50:41.929427Z`; any mismatch is fatal.

If the artifact is unavailable, reproduce it from persisted saved raw at materializer commit `0c77c086` (no GitHub access is required):

```bash
git worktree add --detach /tmp/w2-factor-corpus-source 0c77c086
mkdir -p /tmp/w2-factor-corpus-output
cd /tmp/w2-factor-corpus-source

ssh -i /Users/liudehua/.ssh/id_ed25519_w2_hk \
  -o StrictHostKeyChecking=yes root@45.207.194.97 \
  "docker exec -i w2-staging-postgres-1 psql -X -qAt \
  -v ON_ERROR_STOP=1 -U w2_user -d w2" <<'SQL' | \
PYTHONPATH=src uv run --frozen python scripts/materialize_factor_history_dry_run.py \
  --as-of 2026-08-22T05:50:41.929427Z \
  --kickoff-from 2022-01-01T00:00:00Z \
  --kickoff-to 2026-08-21T19:18:10.674088Z \
  --seasons 2022,2023,2024,2025,2026 \
  --output-dir /tmp/w2-factor-corpus-output
BEGIN READ ONLY;
COPY (
  SELECT json_build_object(
    'sha256', sha256,
    'captured_at', captured_at,
    'payload', payload
  )::text
  FROM raw_payload
  WHERE endpoint = 'fixtures'
    AND captured_at <= timestamptz '2026-08-22T05:50:41.929427Z'
  ORDER BY captured_at, sha256
) TO STDOUT;
ROLLBACK;
SQL

shasum -a 256 /tmp/w2-factor-corpus-output/factor_history_corpus.json
```

The materializer output must report `provider_calls=0`, `database_writes=0`, `eligible_finished_fixture_count=19353`, and `history_row_count=38706`. The byte SHA must be the value above. The main audit then independently verifies the W2 canonical fingerprint.

## 3. Reproduce and diff the preregistration

From `codex/ev-se-offline-validation`:

```bash
python3 scripts/audit_ev_se_offline_preregistration.py \
  --corpus /absolute/path/to/factor_history_corpus.json \
  --ssh-key /Users/liudehua/.ssh/id_ed25519_w2_hk \
  --check
```

The expected result is `{"reproduction": "PASS"}`. `--check` regenerates both artifacts in memory and compares them exactly with:

- `EV_SE_OFFLINE_PREREGISTRATION_EVIDENCE_20260823.json`
- `EV_SE_OFFLINE_PREREGISTRATION_BASELINE_20260823.md`

Exact rendered equality is stronger than the preregistered floating tolerance of `0.000001`. To inspect a proposed regeneration without overwriting the package, pass temporary `--output-json` and `--output-markdown` paths without `--check`, then use `diff -u`.

`--check` is intentionally mutation-sensitive. To prove the failure path without touching the committed evidence, copy both expected artifacts to a temporary directory, change one numeric byte in either copy, and pass the copies through `--output-json` and `--output-markdown`; the command must exit non-zero with `EV_SE_EVIDENCE_JSON_DIFF` or `EV_SE_BASELINE_MARKDOWN_DIFF`.

## Frozen cohort predicate

The script contains the authoritative SQL. In compact form, `usable` requires:

```text
current_ev IS NOT NULL
AND current_ev_minus_se IS NOT NULL
AND current_ev - current_ev_minus_se >= 0
AND COALESCE(recorded_at, evaluated_at) <= 2026-08-23T12:00:50Z
AND api_football fixture identity resolves
AND kickoff_at < evaluated_at
AND captured_at <= evaluated_at
AND latest visible rows per side are capped at 20
AND home_n >= 3 AND away_n >= 3
AND age, sigma_home, sigma_away are non-null
```

Coverage-denominator reconstruction additionally requires `evaluated_at < target kickoff` and both expected same-league denominators `>=3`. Its competition scope is read from `league_season.payload.enabled`; the script has no fixed league count or league-name list. The evidence reports every league separately and deliberately computes no overall coverage average.

For the Contract 1 comparison, both AH and TOTALS must exist for a model-input group so the point lambdas can be identified from the frozen five-state distributions. A whole group enters the old-versus-GH-3 comparison only when the reconstructed old `ev_se` matches the persisted value within `0.000001`. The JSON records every excluded group and row. The script never back-solves a missing historical sigma from persisted `ev_se`.

The accepted Contract 1 cohort is then partitioned by the exact `price_source` value. Each source gets `n/min/p05/p25/median/mean/p75/p95/max/max_absolute` for all four required deltas. The script also records attempted, accepted, and excluded counts per source, so excluded-to-accepted ratio is not mislabeled as attempted-row failure rate. The pooled `ev_se` delta is compared with a forward reconstruction of `old_ev_se * (sqrt(2) - 1)`; no historical sigma is inferred.

The reporting-only materiality rule is fixed in the script: source distributions differ materially when either the absolute mean gap or the largest absolute `p05/p25/median/p75/p95` gap reaches `0.20` pooled within-source SD. This criterion controls whether a pooled number may stand as the only reporting granularity. It is not a model gate, coefficient, SE formula, or outcome-derived threshold.

The evidence JSON records the definitions and relationships of `2,564`, `2,528`, `2,603`, and `2,653`, plus the exact provenance of the minimum change.
