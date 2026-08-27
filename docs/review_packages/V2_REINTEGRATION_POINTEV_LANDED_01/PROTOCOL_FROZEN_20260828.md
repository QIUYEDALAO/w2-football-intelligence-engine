# V2-REINTEGRATION-POINTEV-LANDED-01 frozen protocol

Base: `ea557bb8ff64e06add91bbe32814fe073ec64642`

Merge source: `f0d201c5e0abf38107a7bbe8611fa5b9c73c1b8b`

## Objective

Create one local non-fast-forward merge whose first parent is the deployed POINT-EV
release and whose second parent is the accepted V2 successor-preregistration line.
Preserve deployed identity-v1 read compatibility, keep POINT-EV code effective once,
recompute generated package metadata from the merged graph, and retain a single
Alembic head.

## Frozen decisions

1. The merge must retain both exact parents; rebasing, squashing and replaying the V2
   line are forbidden.
2. The four POINT-EV pairs must have equal `git patch-id --stable` values. Duplicate
   changes are resolved to the deployed first-parent content unless a later explicit
   compatibility change requires otherwise; no functional POINT-EV patch may appear
   twice in the resulting tree.
3. `LEGACY_EVALUATION_IDENTITY_VERSION` and the deployed v2-first/v1-on-mismatch read
   fallback are safety requirements. Every production write path must remain v2-only.
   Direct tests must exercise both fallback and write-side rejection without nullable
   or vacuous assertions.
4. `tests/contract/test_src_w2_package_matrix.py` is regenerated using its own
   `_graph()` and `_external_callers()` output after the merge; choosing either parent
   wholesale is forbidden.
5. The merged migration graph must resolve to exactly one head without applying any
   migration.
6. The old and successor preregistrations remain byte-identical with file hashes
   `cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1` and
   `5c6b13b50818587d381e361bafbce25f33bd7e7f52c3b090ccf02bd0def4c880`;
   the successor semantic identity remains
   `bf2b539d77a532b7c8bf9e81d2644f6f3f760ddf549719613ee2643c8aac4e98`.
7. The preregistration report must describe its validator accurately: a bare run is
   the check; there is no `--check` option.

## Verification

- capture the exact `ea557bb8` full-suite failure IDs before merging;
- run focused identity/read-write/fallback tests and direct non-vacuity assertions;
- run package/canonical/migration contract tests;
- run Ruff, `mypy src apps`, and the full suite after the merge;
- compare post-merge failures by exact test ID with the captured baseline; and
- prove merge topology and patch-id equivalence in frozen evidence.

## Stop lines

Provider `0`; production reads/writes `0/0`; GitHub/GHCR `0`; deployment `0`;
migration apply `0`; collector/timer start `0`; alpha/beta remain `NULL`; Gate 1
remains `FAIL_PENDING_PROSPECTIVE_CONFIRMATION`; Gate 2 remains `CLOSED`.

This task does not start `V2-DUAL-TRACK-LEDGER-01`.
