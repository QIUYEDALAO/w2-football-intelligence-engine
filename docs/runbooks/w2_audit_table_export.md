# W2 Audit Table Export

`scripts/export_w2_audit_tables.py` is a read-only exporter for the four W2 audit views:

- `prematch_recommendations`
- `market_timeline_snapshots`
- `locked_recommendation_snapshots`
- `settlement_history`

The default mode combines a `/v1/dashboard` payload with existing read-only model rows. It opens a database session only to read existing models and does not write rows, mutate schema, call providers, or change recommendation logic.

Use `--no-db` for pure payload mode. In that mode, exported rows come only from the provided dashboard payload.

Examples:

```bash
python scripts/export_w2_audit_tables.py \
  --input /tmp/dashboard.json \
  --output-dir /tmp/w2_audit_tables \
  --format csv \
  --no-db
```

```bash
python scripts/export_w2_audit_tables.py \
  --url "http://43.155.208.138/v1/dashboard?window=today&include_debug=true" \
  --output-dir /tmp/w2_audit_tables \
  --format both \
  --timeout 20
```

The manifest reports `provider_calls=0`, `db_writes=0`, and `read_only=true`.
