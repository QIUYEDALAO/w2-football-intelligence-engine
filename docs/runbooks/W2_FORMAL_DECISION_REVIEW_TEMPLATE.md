# W2 FORMAL Decision Review Template

Status: template only. This document does not authorize FORMAL/CANDIDATE or
production release.

## Decision Summary

- Review date:
- Review owner:
- Candidate release SHA:
- Staging SHA:
- Validation window:
- Competitions included:
- Decision:
  - `KEEP_ANALYSIS_ONLY`
  - `CONTINUE_FORWARD_SHADOW`
  - `REQUEST_MORE_EVIDENCE`
  - `APPROVE_SEPARATE_FORMAL_UNLOCK_PR`

Default decision: `KEEP_ANALYSIS_ONLY`.

## Required Evidence

- Covered settled sample:
- Required minimum: `200`
- Devig market baseline method:
- Advantage over devig market distinguishable from noise: yes/no
- Time split passed: yes/no
- Holdout replication passed: yes/no
- Forward shadow passed: yes/no
- Runtime `beats_market`: must be `false` before any separate unlock PR
- FORMAL/CANDIDATE currently enabled: must be `false`

## Validation Summary

Paste the relevant `/v1/validation/summary` excerpt:

```json
{}
```

Paste the relevant walk-forward or dry-run report excerpt:

```json
{}
```

## Settlement Policy Confirmation

- Uses locked as-of market snapshot: yes/no
- Uses devig market baseline: yes/no
- AH supports `WIN / HALF_WIN / PUSH / HALF_LOSS / LOSS / VOID`: yes/no
- Push counted as win: must be no
- Void included in sample: must be no
- No post-match line substitution: yes/no
- No current line backfill into historical settlement: yes/no

## Risk Review

- Data leakage risk:
- Provider outage/quota risk:
- xG/statistics coverage risk:
- Lineups availability risk:
- Competition mapping risk:
- Public copy/user-misleading risk:
- Rollback path:

## Decision Rules

Do not approve FORMAL/CANDIDATE unless all S2 gate checks pass with reproducible
evidence. A separate implementation PR is required for any unlock. That PR must
still keep rollback available and must not combine unrelated feature work.

If evidence is incomplete, noisy, or only directionally promising, record
`KEEP_ANALYSIS_ONLY` or `CONTINUE_FORWARD_SHADOW`.
