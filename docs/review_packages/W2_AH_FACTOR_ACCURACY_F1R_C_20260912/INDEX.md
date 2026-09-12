# W2 AH Factor Accuracy — F1R-C successor

Closes the F5 source-observed-time blocker by constructing AH settlement facts
from real Provider captures, and serving F5 from them.

This package is a **successor**. The F1R-B package
(`W2_AH_FACTOR_ACCURACY_F1R_B_20260911`) is historical evidence and is **not
modified**; its module digests are still verified, against the F1R-B delivery
commit rather than against a working tree this task was authorised to change.

## Identity

| Item | Value |
|---|---|
| Parent commit | `b428688`… see `PORT_REVISIONS.md` for the exact task/parent pair |
| Policy | `canonical_bookmaker_mainline_majority_v1` |
| Line authority | `src/w2/markets/asian_handicap_mainline.py::select_canonical_ah_mainline` |
| Settlement authority | `src/w2/domain/odds.py::settle_asian_handicap` |
| Quote identity authority | `src/w2/markets/quote_identity.py::project_quote_identity` |
| Hash domain | `HashDomain.FUTURE_REFRESH_EVIDENCE`, `SerializerVersion.V2` |
| Schema | `w2.runtime_ah_settlement_fact.v1` |
| Hash contract | `w2.runtime_ah_settlement_fact_hash.v1` |

## What was built

* `src/w2/markets/ah_settlement_fact.py` — the only constructor of a runtime AH
  settlement fact. It chooses no line and settles nothing itself: it composes
  the three authorities above and refuses when any cannot answer.
* `runtime_ah_settlement_facts` + additive migration `0072` — immutable facts,
  no backfill, populated downgrade refused.
* The natural writer, wired into the Provider capture path
  (`FactorModelRemediationService.materialize_runtime_ah_settlement_facts`).
* `TeamMatchHistory` gained an independent `settlement_observed_at` and source
  identity. `observed_at` still returns `kickoff_at`, so F3 is unchanged.
* F5 consumes the maximum `settlement_observed_at` among the facts it read, and
  records the full quote/result provenance in `factor_inputs`.

## 340-fixture offline replay

Every fixture that has both a pre-kickoff AH quote bucket and a terminal
settlement capture, replayed through the real builder. Extracted read-only from
the production database; no synthetic row is used as evidence.

| Measure | Result |
|---|---|
| Input fixtures | **340** |
| READY | **340** |
| Refused | **0** |
| PIT violations (`quote_captured_at < kickoff < settlement_observed_at`) | **0** |
| Hash-shape violations | **0** |
| Non-deterministic replays | **0** |

Canonical line distribution (top): `0.25` 66, `-0.25` 63, `-0.5` 54, `-0.75` 45,
`-1` 16, `-1.25` 11, `-1.5` 11.

Bookmakers voting the selected line: 3→4, 4→12, 5→41, 6→75, **7→160**, 8→31,
9→3, 10→7, 11→7 fixtures.

Terminal status: `FT` 340 (no AET/PEN in the pairable set).

Line shape: quarter lines **211**, whole lines 129.

Settlement outcomes: `LOSS/WIN` 143, `WIN/LOSS` 126, `HALF_WIN/HALF_LOSS` 44,
`HALF_LOSS/HALF_WIN` 19, `PUSH/PUSH` 8.

Competitions: `mls` 52, `argentina_primera` 47, `brasileirao_serie_a` 39,
`eliteserien` 31, `la_liga` 30, `chinese_super_league` 25, `primeira_liga` 25,
`eredivisie` 24, `premier_league` 20, `serie_a` 20, `ligue_1` 18, `bundesliga` 9.

Per-fixture detail — quote capture, settlement capture, canonical line, both
payload hashes, both settlement outcomes and all three digests — is in
`F1R_C_AH_SETTLEMENT_REPLAY_DETAIL.jsonl`.

## Port revisions

Exactly two F1R-B modules were revised, both named in the task authorisation:
`f1r_b_production_ports.py` (F5 served from runtime facts instead of refusing)
and `f1r_b_production_recording_integration.py` (F5's consumed set and source
time checked against the builder's own report). See `PORT_REVISIONS.md`.

Four of the six F1R-B modules are byte-identical to the delivery; a test asserts
that the set of revised modules is exactly the two authorised ones.

## Migration and rollback

See `MIGRATION_AND_ROLLBACK.md`.

## Files

| File | Contents |
|---|---|
| `F1R_C_AH_SETTLEMENT_REPLAY_SUMMARY.json` | the distribution report above |
| `F1R_C_AH_SETTLEMENT_REPLAY_DETAIL.jsonl` | one line per fixture, full provenance |
| `F1R_C_SMALL_REGRESSION_SAMPLE.jsonl` | three real fixtures used as the unit regression fixture |
| `PORT_REVISIONS.md` | the two revised modules, their digests, and why |
| `MIGRATION_AND_ROLLBACK.md` | migration 0072, its constraints and its rollback discipline |
| `HASHES.sha256` | digests of this package's files |
