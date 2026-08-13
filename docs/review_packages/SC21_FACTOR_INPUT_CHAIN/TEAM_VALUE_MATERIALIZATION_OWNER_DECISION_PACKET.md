# SC21 TeamValueAsOf Materialization Owner Decision Packet

## Decision required

TeamValueAsOf remains fail-closed. No database write is authorized by this packet.

## Read-only evidence

- Provider calls: `0`
- Business writes: `0`
- Player valuation observations: `31,507`
- Reviewed Transfermarkt team crosswalks: `16`
- Player identity mappings: `110`
- Registered roster rows: `0`
- Player-club membership observations: `0`
- Existing TeamValueAsOf artifacts: `0`
- Dry-run `EXPECTED_ARTIFACT_COUNT`: `0`
- Dry-run `EXPECTED_ARTIFACT_SET_SHA256`: `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`

The valuation rows alone do not prove which players belonged to a team at a fixture's
pre-match as-of time. The existing materializer requires reviewed team identity,
registered roster membership, reviewed player mapping, valuation time, currency and
conflict checks. With no roster or membership evidence, temporary aggregation would
invent squad membership and violate the canonical `TeamValueAsOf` contract.

## Owner options

1. Keep Team Value unavailable. This is the current safe state.
2. Separately authorize import/review of as-of roster membership evidence. After that,
   rerun dry-run and approve only the exact count and artifact-set hash.

This packet does not authorize Provider calls, scraping, identity auto-approval,
threshold changes, Formal, Lock, Production or Round 4.
