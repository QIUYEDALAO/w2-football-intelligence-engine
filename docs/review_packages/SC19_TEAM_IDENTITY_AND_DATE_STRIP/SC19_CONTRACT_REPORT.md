# SC19 Team Identity and Persisted Date Strip

## Team identity P0

The five persisted `2026-08-10` football-day fixtures were traced without Provider calls or database writes. Four Allsvenskan sides already had canonical teams, exact approved crosswalks and existing public Chinese product labels; the missing authority was the backend reviewed-label projection. Those labels now live in `config/identity/public_team_labels.zh-CN.v1.json` and require the reviewed crosswalk before they can render as `CHINESE_LABEL_READY`.

The six Primeira Liga and Argentina sides have no persisted provider-team crosswalk or canonical identity. They remain explicit `IDENTITY_UNRESOLVED` gaps. The read model does not invent canonical IDs, guess Chinese names, or treat raw English as localized success.

## Persisted date strip

- Contract: 15 consecutive Asia/Shanghai football days, `T-7..T+7`.
- Boundary: local `12:00` through next-day `12:00` exclusive.
- Source: persisted fixture identities, checkpoint plans and market observations only.
- Future state derives from the first persisted odds checkpoint: future checkpoint means `PERSISTED_FIXTURE_OUTSIDE_MARKET_COLLECTION_WINDOW`; due/past checkpoint without usable evidence means `MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY`.
- Coverage is shown as persisted competition count out of the unchanged 13-league whitelist; it never claims complete future inventory.
- Empty-day `next_available_date` is the first later persisted football day with fixtures inside the returned range.
- Dashboard reads remain `provider_calls=0`, `db_writes=0`, `no_call_on_read=true`.

## Stop lines

Scheduler/cadence, whitelist, model/thresholds, Formal, Lock, Production, real money, Round4 and P6 are unchanged.
