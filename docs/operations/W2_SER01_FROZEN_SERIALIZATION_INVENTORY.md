# W2 SER-01 frozen serialization inventory

## Boundary

This refinement is bound to Wave 1 T00-R5 at trusted base
`dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6` and accepted PR #458 head
`4079e663247148f2671f574ab8ba128ebd7ca5e3`.

```text
R5_COMPUTATION_SYMBOLS = 287
FROZEN_COMPUTATION_CONCEPT_HASH_DOMAINS = 76
UNCLASSIFIED_COMPUTATION_AUTHORITIES = 0
T00_DENOMINATOR_RERUN = false
T00_DENOMINATOR_EXPANDED = false
```

The original 55 entries in
`config/canonical_serialization_legacy_exceptions.v1.json` are an exact
SER-06 projection of already-frozen JSON-to-hash sites. They are not a new T00
denominator. Each site has a distinct semantic domain and an explicit legacy
profile; none is silently merged with the new authority. The bounded SER-06
remediation adds 19 existing operational/runtime sites exposed by the required
production-root scan. This guard coverage change does not rerun or expand the
frozen T00 denominator.

## Critical runtime writers frozen by Issue #456

| exact-base site | callers / persisted surface | possible values | legacy bytes | Wave 2 disposition |
|---|---|---|---|---|
| `src/w2/ingestion/future_refresh.py:160` | refresh raw payload, endpoint capture, observation, fixture identity and evidence writers; DB/files | Unicode, float, nested provider JSON | sorted, compact, `ensure_ascii=True`, implicit `allow_nan=True` | authority call with seven named domains; v1 compatibility write |
| `src/w2/tracking/outcome_ledger_repository.py:86` | ledger payload and business-key writers; `outcome_ledger` DB/import artifacts | Unicode, float, timestamps already represented as strings | sorted, compact, `ensure_ascii=True`, implicit `allow_nan=True` | authority call with payload/business-key domains; v1 compatibility write |
| `src/w2/monitoring/stage7i_lifecycle.py:80` | lifecycle payload/event IDs; JSONL/files | Unicode, float, timestamp strings | sorted, compact, `ensure_ascii=True`, implicit `allow_nan=True` | authority call with payload/event domains; v1 compatibility write |
| `src/w2/monitoring/stage7i_supervision.py:57` | run, heartbeat and watchdog IDs; DB | Unicode, datetime and fallback objects | sorted, compact, `ensure_ascii=True`, implicit `allow_nan=True`, `default=str/UTC` | authority call with supervision-event domain; v1 compatibility write |
| `src/w2/prematch/read_model_projection.py:242` | frozen artifact, manifest, projection, read-time and evaluation identities; checkpoints/DB | Unicode, float, `Decimal`, date, aware datetime | sorted, compact, `ensure_ascii=False`, implicit `allow_nan=True`, typed default hook | authority call with explicit read-model subdomains; v1 compatibility write/read |
| `src/w2/prematch/repository.py:924` | EVAL-02B exact pair projection; currently ephemeral projection | Unicode, finite binary64 exact line | sorted, compact, `ensure_ascii=False`, `allow_nan=False` | new v2 pair identity with emitted serializer metadata and projector schema v2 |

The EVAL-02B bootstrap seed had a frozen prose contract but no production
serializer entry point. Wave 2 adds only that interface and names it
`eval_02b.bootstrap_seed`; it does not create an oracle or expected output.

## Domain disposition

- `HashDomain` in `src/w2/domain/canonical_serialization.py` is the current
  named runtime authority for the critical writers and EVAL-02B pair/seed.
- Missing serializer version is interpreted as legacy v1 only. It is never
  guessed to be v2.
- The 74 frozen/guard-expanded sites remain compatibility-only exceptions with exact
  path, symbol, semantic domain, owner, reason and guard test. Their migrations
  are deferred to their owning Gate C/D work; new exceptions fail CI.
- Raw byte/file digests and delimiter-based aggregate digests are not JSON
  canonical serializers and remain separate hash domains.
