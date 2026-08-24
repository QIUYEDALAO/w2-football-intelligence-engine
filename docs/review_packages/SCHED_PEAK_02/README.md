# SCHED-PEAK-02 reproducibility

## Files

- `SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json`: six source events, frozen event/projected clocks, source release/image.
- `SCHED_PEAK_02_PROFILE_PLAIN_20260824.json`: full read-only projection rehearsal without coverage.
- `SCHED_PEAK_02_PROFILE_COVERAGE_20260824.json`: same rehearsal under the production coverage rcfile.
- `SCHED_PEAK_02_EVIDENCE_20260824.json`: derived comparison bound to all input digests.
- `SCHED_PEAK_02_REPORT_20260824.md`: findings, abnormality decision, optimization and post-window retest.

## Profile contract

Run against an isolated clone of the authority database. The profile command refuses to start unless `W2_DATABASE_URL` is set and `PGOPTIONS` contains `default_transaction_read_only=on`. Do not point it at a writable production database.

```bash
export PGOPTIONS='-c default_transaction_read_only=on'
export W2_DATABASE_URL='postgresql+psycopg://USER:CREDENTIAL@HOST:5432/ISOLATED_CLONE'

python scripts/audit_sched_peak_02.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --profile plain \
  --output /tmp/SCHED_PEAK_02_PROFILE_PLAIN.json

python -m coverage run \
  --rcfile=config/coverage/production.coveragerc \
  scripts/audit_sched_peak_02.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --profile coverage \
  --output /tmp/SCHED_PEAK_02_PROFILE_COVERAGE.json
```

The two arms must use the same restored clone, code/image, environment and frozen manifest. They execute `build → validate → rebuild → validate`; clone writes are not needed.

## Rebuild and check

```bash
python scripts/audit_sched_peak_02.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --plain docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_PLAIN_20260824.json \
  --covered docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_COVERAGE_20260824.json \
  --assemble \
  --output /tmp/SCHED_PEAK_02_EVIDENCE.json

diff -u \
  docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_EVIDENCE_20260824.json \
  /tmp/SCHED_PEAK_02_EVIDENCE.json

python scripts/audit_sched_peak_02.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --plain docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_PLAIN_20260824.json \
  --covered docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_COVERAGE_20260824.json \
  --check docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_EVIDENCE_20260824.json
```

## Mutation proof

```bash
jq '.coverage_ab.coverage_multiplier += 0.000001' \
  docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_EVIDENCE_20260824.json \
  > /tmp/SCHED_PEAK_02_EVIDENCE_MUTATED.json

! python scripts/audit_sched_peak_02.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --plain docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_PLAIN_20260824.json \
  --covered docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_PROFILE_COVERAGE_20260824.json \
  --check /tmp/SCHED_PEAK_02_EVIDENCE_MUTATED.json
```

The final command must fail with `EVIDENCE_DIGEST_MISMATCH`.
