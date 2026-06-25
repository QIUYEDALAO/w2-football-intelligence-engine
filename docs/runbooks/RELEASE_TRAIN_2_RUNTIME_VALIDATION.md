# Release Train 2 Runtime Validation

Release Train 2 runtime validation uses installed W2 module entrypoints. Do not
run `/app/scripts/*.py` inside containers.

Required runtime probes:

```bash
w2-shadow-cycle --execution-kind FORWARD --dry-run --database-url-from-env --json
w2-gate5-preflight --dry-run --database-url-from-env --json
w2-stage7i-observer --expected-revision "$EXPECTED_REVISION" --once --json
```

W1/W2 comparison on the server may only import sanitized artifacts:

```bash
w2-shadow-comparison-import \
  --artifact runtime/comparison/sanitized.json \
  --manifest runtime/comparison/manifest.json \
  --artifact-root runtime/comparison \
  --dry-run \
  --json
```

If no sanitized artifact is needed for the deployment, run:

```bash
w2-shadow-comparison-import --dry-run --json
```

Expected Gate5 result while Gate4 is pending:

```text
PROVISIONAL_BLOCKED_GATE4
```

The runtime validation must not print credentials, read W1 `.env`, create
candidate/recommendation states, modify production, or解除 deployment freeze.
