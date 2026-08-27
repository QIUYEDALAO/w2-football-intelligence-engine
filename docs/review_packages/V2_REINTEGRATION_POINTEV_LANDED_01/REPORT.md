# V2-REINTEGRATION-POINTEV-LANDED-01 report

## Conclusion

Local reintegration is complete and ready for independent acceptance. The exact
non-fast-forward merge is `f3265ac0`: first parent deployed production `ea557bb8`,
second parent accepted V2 line `f0d201c5`. No deployment or runtime activation was
performed, and Task 6 has not started.

## POINT-EV equivalence and merge treatment

All four historical POINT-EV pairs have identical stable patch IDs; see
`PATCH_ID_MATRIX.md`. The deployed first-parent content is authoritative in the
resulting tree, so the duplicate history does not duplicate behavior. A final-tree
inspection found one `w2.domain.calibration_authority` implementation and no second
copy of the admission logic.

## Identity compatibility safety

`LEGACY_EVALUATION_IDENTITY_VERSION` remains present. Frozen payload validation
first rebuilds v2 identities and only rebuilds v1 after stored hashes mismatch.
The fallback test records and directly asserts that order. New-evaluation writes use
the public `classify_evaluation(value)` entry; it has no identity-version argument.
Legacy construction is private to frozen read/reproduction compatibility. The
write-v2-only assertion is direct and cannot pass on `None`.

## Generated package matrix and migrations

The package matrix represents the merged tree. Its complete row set was checked
against the contract's own `_graph()` and `_external_callers()` calculations; all
five matrix contracts passed. Alembic resolves to one head,
`0070_factor_shadow_v2_gate0`; no migration was applied.

## Preregistration integrity and documentation correction

The old and successor files remain byte-identical:

- old file: `cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1`;
- successor file: `5c6b13b50818587d381e361bafbce25f33bd7e7f52c3b090ccf02bd0def4c880`;
- successor semantic identity: `bf2b539d77a532b7c8bf9e81d2644f6f3f760ddf549719613ee2643c8aac4e98`.

The validator was run bare and returned PASS. The prior false `--check` wording was
changed to state that bare invocation is the check and that `--check` does not exist.

## Verification

- focused integration/identity/matrix set: 190 passed, 4 skipped;
- identity plus package-matrix set: 98 passed;
- full suite: 2975 passed, 5 failed, 9 skipped;
- deployed `ea557bb8` baseline: 2902 passed, 5 failed, 9 skipped;
- the five post-merge failure IDs are byte-for-byte the same set as baseline;
- Ruff lint: PASS;
- mypy `src apps`: 299 files, zero errors.

The five shared environment failures are the two Docker Compose CLI-unavailable
cases, SC18's missing `python` executable, and the two privileged ownership parity
checks. There are no new failures and no baseline failure disappeared.

## Boundaries and current gates

Provider 0; production reads/writes 0/0; GitHub/GHCR 0; deployment 0; migration
apply 0; collector/timer starts 0. Alpha/beta remain `NULL`. Gate 1 remains
`FAIL_PENDING_PROSPECTIVE_CONFIRMATION`; Gate 2 remains `CLOSED`.

`V2-DUAL-TRACK-LEDGER-01` remains blocked on independent acceptance of this package.
