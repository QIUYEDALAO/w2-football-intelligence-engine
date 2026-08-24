# XG-PROBE-01 reproduction

The live path is deliberately single-use. It selects the fixed 6/2/1/1 league sample in a repeatable-read, read-only production transaction, refuses to continue unless the source pool is 902, refuses any future-60-minute formal prematch plan, preserves the 1,500-call daily reserve, and dispatches exactly ten direct `fixtures/statistics` requests without the application Provider ledger or any database connection.

```bash
python3 scripts/run_xg_provider_retry_probe.py \
  --preflight \
  --ssh-key /Users/liudehua/.ssh/id_ed25519_w2_hk
```

The Owner-authorized execution command is identical except for `--execute`. It refuses to run if the frozen raw artifact already exists, preventing an accidental second ten-call probe.

```bash
python3 scripts/run_xg_provider_retry_probe.py \
  --execute \
  --ssh-key /Users/liudehua/.ssh/id_ed25519_w2_hk
```

Verification is fully offline: it reads the frozen sanitized raw result, rebuilds the evidence JSON and Markdown report, and compares both byte-for-byte.

```bash
python3 scripts/run_xg_provider_retry_probe.py --check
```

`--check` makes no SSH, Provider, database, deployment, model, EV-SE, or outcomes call. It fails on a changed source-pool count, sample quota, fixture binding, prematch gate, call count, HTTP result, quota header, xG value, derived recovery statistic, evidence field, or report field.
