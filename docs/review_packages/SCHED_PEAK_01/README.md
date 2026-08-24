# SCHED-PEAK-01 reproduction

The collector performs only SSH, Docker metadata/log reads, and a PostgreSQL
`REPEATABLE READ READ ONLY` transaction. It does not call Provider, write the
production database, or deploy anything.

```bash
python3 scripts/audit_sched_peak_01.py \
  --collect \
  --ssh-key /Users/liudehua/.ssh/id_ed25519_w2_hk
```

Offline verification rebuilds the evidence JSON and report from the frozen raw
artifact and compares both byte-for-byte:

```bash
python3 scripts/audit_sched_peak_01.py --check
```

`--check` validates the exact 18:30Z plan set, claim count and 900-second lease,
worker concurrency, task timing/order, bound endpoint captures, Provider error
and latency counts, terminal statuses, the two-slot replay, and all safety
fields. A one-field mutation in raw, evidence, or report must fail.
