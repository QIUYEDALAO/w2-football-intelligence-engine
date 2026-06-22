# W2 Stage6B Result

## Status

STAGE_6B=LOCAL_ENGINE_COMPLETE

No server deployment, current release switch, systemd restart, container restart, or existing snapshot
mutation was performed.

## Implemented

- Decimal/Hong Kong odds conversion.
- AH whole, half, and quarter-line settlement distribution.
- OU whole, half, and quarter-line settlement distribution.
- Push-aware and half-result-aware EV and fair odds.
- Bookmaker pair validation.
- Cross-market value engine for 1X2, AH, OU, and BTTS.
- Research grades with Gate4 pending publication cap.
- Dashboard read-model fields for primary direction, AH ladder, OU ladder, and all-market ranking.

## Pending Runtime Step

Append-only valuation supersession events and corrected Argentina/Austria runtime cards are pending
explicit approval to run against `/opt/w2/shared/runtime/matchday/argentina-austria-20260622/`.

## Validation

- `make verify`: PASS
- `uv run pytest -q`: PASS
- `uv run python scripts/check_w2_stage6b.py`: PASS
- `uv run python scripts/check_w2_stage10b.py`: PASS
- `npm --prefix apps/web run typecheck`: PASS
- `npm --prefix apps/web run build`: PASS
- `git diff --check`: PASS
- `uv run python tests/secret_scan.py`: PASS

## Dependency Note

`npm --prefix apps/web ci` reported one moderate and one high vulnerability. The available automatic
fix requires `npm audit fix --force`, so no breaking dependency upgrade was applied in this stage.
