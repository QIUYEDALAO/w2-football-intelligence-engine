# XG-INGEST-01 reproduction

This package is frozen at `2026-08-23T15:40:00Z`. The audit opens a
`REPEATABLE READ READ ONLY` transaction against persisted production evidence.
It performs no Provider calls, production writes, or outcome reads.

```bash
uv run --frozen python scripts/audit_xg_ingest_saved_raw.py \
  --ssh-key "$W2_XG_AUDIT_SSH_KEY" \
  --check
```

The command must print `{"reproduction": "PASS"}`. Without `--check`, it
regenerates both frozen artifacts. `--self-check` validates the local source
contracts without connecting to production.

The check compares the generated JSON and Markdown byte for byte. Mutation
acceptance is therefore strict: changing any single numeric field, including a
coverage value by `0.000001`, must exit non-zero with
`XG_INGEST_EVIDENCE_JSON_DIFF`.

The Provider-0 replay result is intentionally zero. The 529 historical fixtures
contain xG keys whose values are JSON null, so they cannot be rematerialized
from saved raw. A bounded Provider retry and any production write require a
separate Owner decision.
