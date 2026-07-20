# W2 GitHub Context Sync - 2026-07-21

Purpose: context-only synchronization for source review. This file records the latest operational and architectural context for reviewers on GitHub. It is not a code change, does not request deployment, and should not be treated as approval for recommendation, formal AH, lock, production, calibration, or provider canary.

## Current User Instruction

The user requires every working round to synchronize GitHub-visible context. Context sync should be plain text only: no PR is required, no CI intent is required, and no production action is implied.

## Current Date Context

- Local operational date: 2026-07-21, Tuesday, Asia/Shanghai.
- "Yesterday" in the current discussion means 2026-07-20.
- The immediate question was whether the next week has no matches, and whether the two Swedish Allsvenskan matches from 2026-07-20 were missing factors for recommendation.

## Corrected Match Availability Finding

The previous runtime observation of zero W2 fixtures must not be interpreted as "there are no real matches."

External public schedules indicate Swedish Allsvenskan has matches in the coming week, including:

- 2026-07-24: Vasteras SK vs Orgryte
- 2026-07-25: Degerfors vs Djurgarden
- 2026-07-25: Kalmar FF vs Mjallby
- 2026-07-26: Brommapojkarna vs Hammarby
- 2026-07-26: Sirius vs IFK Goteborg
- 2026-07-26: GAIS vs Halmstad
- 2026-07-26: Malmo FF vs Elfsborg
- 2026-07-27: Hacken vs AIK

Therefore the current truth is:

```text
Real-world fixtures exist
!=
W2 staging currently has fixtures visible
```

## W2 Runtime Observation

The current staging/provider evidence observed during this context round:

- Future fixture queries in W2 staging showed zero fixtures.
- Recent future refresh audit rows showed `fixture_count=0` and `market_snapshot_count=0`.
- The blocker observed was `LiveNetworkDisabledError`.
- `matchday_endpoint_captures` was empty.
- `matchday_market_observations` was empty.
- 2026-07-20 Swedish Allsvenskan fixtures were not present as canonical W2 fixtures.

This indicates a provider intake / live-gate / scheduler-worker wiring problem, not an absence of real football matches.

## Code-Level Gate Context

`src/w2/providers/api_football.py` still enforces live network gates:

- `ApiFootballClient.fetch()` raises `LiveNetworkDisabledError` unless live execution is explicitly approved.
- `ApiFootballClient.request_live()` checks `allow_live`, `W2_PROVIDER_CALLS_DISABLED`, endpoint allowlist, and provider credential visibility.
- `src/w2/providers/control.py` reads `W2_PROVIDER_CALLS_DISABLED` and provider endpoint allowlist from environment.

This is consistent with the observed runtime blocker.

## Why 2026-07-20 Swedish Allsvenskan Could Not Produce W2 Recommendations

The two Swedish Allsvenskan matches discussed for 2026-07-20 could not produce W2 canonical recommendations because the missing items are upstream evidence-chain blockers, not merely optional factors.

Missing hard requirements:

1. Canonical fixture identity
   - No W2 canonical fixture record.
   - No fixture id to bind league, kickoff, teams, market, evidence, and decision.

2. Provider endpoint captures
   - No fixtures endpoint capture.
   - No odds endpoint capture.
   - No lineup/injury capture if lineup policy is relevant.

3. Market observations
   - No AH, OU, or 1X2 `matchday_market_observations`.
   - No line, odds, bookmaker, captured_at, provider, or market observation hash.

4. Exact quote identity
   - No capture id.
   - No observation ids.
   - No executable quote hash.
   - No quote-level identity for V3 recommendation binding.

5. Team identity crosswalk
   - Swedish Allsvenskan teams need reviewed API-Football-to-W2 canonical team mapping.
   - Without this, F5, F8, form, ratings, xG, and historical data cannot be safely joined.

6. F5 binding
   - Historical AH evidence may exist as an asset, but the runtime fixture must bind to canonical team-history queries before kickoff.
   - Push handling and denominator semantics must remain canonical.

7. F8 binding
   - Team value must come from a reviewed as-of artifact with deterministic hash verification.
   - Static or unreviewed values must not bypass F8 authority.

8. Model-to-quote binding
   - Missing model probability.
   - Missing market probability.
   - Missing probability delta.
   - Missing EV.
   - Missing uncertainty.
   - Missing model version and calibration version.

9. Recommendation/formal gates
   - Recommendation, candidate, formal, and production gates remain closed.
   - Even with evidence fixed, the next legitimate state is analysis or no-edge, not automatic formal recommendation or lock.

## Current Root Problem

The root problem is universal Matchday intake visibility:

```text
Real fixtures exist
-> provider intake does not write endpoint captures
-> no canonical fixtures
-> no market observations
-> no exact quote identity
-> F5/F8/model evidence cannot bind
-> V3 recommendation cannot be generated
```

This is not a Swedish Allsvenskan-only problem. Swedish Allsvenskan is simply the first visible example because it has near-term fixtures.

## Recommended Next Actions

1. Fix provider intake live-gate behavior for controlled staging execution.
2. Confirm scheduler and worker use the same provider-call policy and endpoint allowlist.
3. Run a bounded controlled capture for near-term Swedish Allsvenskan fixtures.
4. Persist endpoint captures before any canonical transformation.
5. Persist canonical fixtures and market observations.
6. Review and register Allsvenskan team crosswalk.
7. Bind F5 historical AH evidence and F8 reviewed team value artifact.
8. Run V3 builder only after exact quote identity exists.
9. Keep output limited to `NOT_READY`, `NO_EDGE`, or `ANALYSIS_PICK` until manual approval opens formal gates.

## Recommendation Status

Current status remains:

```text
MANUAL_APPROVAL_REQUIRED
NO_FORMAL_RECOMMENDATION
NO_LOCK
NO_PRODUCTION
NO_CALIBRATION_TRAINING
PROVIDER_INTAKE_BLOCKER_OPEN
```

