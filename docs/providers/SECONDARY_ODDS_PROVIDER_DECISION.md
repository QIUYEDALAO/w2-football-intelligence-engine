# Secondary Odds Provider Decision

Status:

```text
SECONDARY_ODDS_PROVIDER=UNDECIDED
```

Stage 4A creates only a generic `SecondaryOddsProviderPort` and a capability
comparison shape. It does not register accounts, pay for services, call a
provider, or hard-code provider keys.

| Capability | Required Later | Current Status |
| --- | --- | --- |
| Pre-match odds | Yes | Unknown |
| Live odds | Optional | Unknown |
| Bookmaker depth | Yes | Unknown |
| Historical snapshots | Preferred | Unknown |
| Commercial terms reviewed | Yes | Not reviewed |

Selection is deferred until a separate approval checkpoint.

## S13 Candidate Signal

Status:

```text
MLS_SECONDARY_ODDS_PROVIDER_CANDIDATE
```

S13 odds-window re-audit found no usable MLS 2026 odds payloads for the W2
AH/OU engine, while Brazil, China, Sweden, and Norway produced AH/OU lines with
sufficient bookmaker depth after the audit probe was fixed.

This does not select or integrate a secondary provider. It only records MLS as
the first league that needs either a later near-kickoff API-Football re-check or
a separate secondary odds provider decision before MLS can become a reliable W2
AH/OU staging candidate.
