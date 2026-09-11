# SC21 xG Statistics Collection Owner Decision Packet

## Decision requested

No collection change is authorized by SC21. The Owner must decide separately whether the
currently policy-disabled Statistics endpoint should be enabled for the exact-13 competitions.

## Verified current evidence

- Audit grain: 36 persisted T+7 fixtures in the exact-13 scope.
- Four-field xG READY: 9 / 36.
- `PROVIDER_EMPTY_OR_UNAVAILABLE`: 20 fixtures.
- `INSUFFICIENT_HISTORY`: 3 fixtures.
- `PARTIAL_HISTORY`: 4 fixtures.
- Saved-raw dry-run: Provider calls 0, business writes 0.
- Saved-raw new `team_xg_match` rows: 0.
- Existing `team_xg_match` / rolling rows stayed 140 / 72 before and after dry-run.
- Existing saved raw can deterministically re-upsert 22 rolling snapshots, but does not improve
  bilateral four-field readiness for this T+7 set.

## Implementation boundary already corrected

The saved-raw path is now exact-13 allowlisted, competition/season scoped, and requires canonical
team crosswalk coverage. Its historical `world_cup_2026` default and `_world_cup_team_ids` binding
were removed. Conflicts, ambiguous identities, and fewer than three matches continue to fail
closed. No sample, as-of, or freshness threshold was reduced.

## Owner choices

1. Keep Statistics policy-disabled. Expected xG/Simulation coverage remains 9 / 36 for the current
   evidence set; natural existing-evidence accumulation can improve it later.
2. Authorize a separately budgeted, exact-13 Statistics collection plan. This requires its own
   Provider budget, per-competition availability audit, scheduler plan, and deployment approval.

Until the Owner chooses option 2, this packet records `OWNER_DECISION_REQUIRED`; it does not turn
on Statistics, change cadence, call Provider, or alter Candidate/Formal/Lock/Production authority.
