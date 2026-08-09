# Dashboard Owner Market Evidence Consistency Remediation

```text
AUTHORITY = W2_DASHBOARD_OWNER_MARKET_EVIDENCE_CONSISTENCY_REMEDIATION_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = CHANGES_REQUIRED_BOUNDED
BASE_MAIN = 14a25727c77b5ede3a1731ec2487e08fa2be4eab
PR_504_TECHNICAL_RESULT = PASS_MERGED_DEPLOYED
PR_504_OWNER_ACCEPTANCE = REVOKED_BY_REAL_DATA_MARKET_REVIEW
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_TARGET = DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS
```

## Independent review conclusion

The D14 remediation correctly closed canonical competition aggregation,
collection-assessment, canonical naming, tournament separation, PRIOR_ONLY,
football-day and record-only semantics. Those fixes must remain.

The deployed real-data view exposed a new bounded class of market-truth defects.
The current movement engine and the public UI do not use the same vocabulary or
show the same evidence. Separately, the market radar, market fact and Model Lab
surfaces expose different meanings under the shared word “就绪”. This authority
reopens only the unified Dashboard/read-model market-evidence boundary and the
small associated presentation defects below.

This is not Round4 authority and does not authorize Provider, Scheduler,
whitelist, model, threshold, production or migration changes.

## Confirmed code evidence

1. `src/w2/markets/round3_intelligence.py::_movement` classifies movement from
   canonical-line delta and median side-price deltas. Bookmaker count is not an
   input to movement classification.
2. The public UI currently translates `PRICE_MOVEMENT` as `盘口变化`, while the
   visible timeline shows line values but not the price deltas that caused the
   status. Therefore a legitimate price movement can look like a fabricated
   line movement.
3. The exact deployed runtime price deltas for the reported fixture are not
   proven by repository code alone. They must be read from the existing
   persisted payload with zero Provider calls and zero business writes before
   the root cause is classified.
4. Round3 market radar currently reports source `status=READY` whenever a
   current snapshot exists, even when its `freshness.status=STALE`.
5. Model Lab separately returns `MARKET_NOT_READY` when the same current
   snapshot is not fresh. The workspace then exposes both statuses on the same
   page, creating conflicting public authority.
6. Public `observation_count` equals the number of single-side quote rows. Each
   paired bookmaker contributes two rows, so the label “次观测” is ambiguous.
7. Scoreline context is rendered as adjacent unlabelled spans.
8. Attention aggregation only activates when the whole day is homogeneous by
   state and blocker. A day containing two repeated blocker groups still renders
   one Attention row per match.

## Findings and required closure

### P0 — D15-01 Movement classification must be evidence-visible and exact

First inspect the exact persisted payload for the deployed real fixture that
shows the two 2026-08-03 snapshots. Record sanitized evidence for:

```text
movement.status
movement.line_delta
movement.price_delta by side
movement.probability_delta by side
timeline point canonical_line
timeline point side-price medians
bookmaker_count
captured_at
```

No Provider call, checkpoint write or business-data write is allowed.

Required public and engine semantics:

```text
STABLE                  = line_delta == 0 and all price_delta == 0
PRICE_MOVEMENT          = line_delta == 0 and at least one price_delta != 0
LINE_MOVEMENT           = line_delta != 0 and all price_delta == 0
LINE_AND_PRICE_MOVEMENT = line_delta != 0 and at least one price_delta != 0
```

Bookmaker-count change, snapshot-count change and quote-row-count change are
coverage changes, not market movement.

Public labels must be exact:

```text
STABLE                  -> 盘口与赔率均未变化
PRICE_MOVEMENT          -> 赔率变化
LINE_MOVEMENT           -> 盘口变化
LINE_AND_PRICE_MOVEMENT -> 盘口及赔率变化
INSUFFICIENT            -> 证据不足，无法判断变化
```

When movement is reported, show the evidence that supports it: from/to time,
line from/to or delta, and the relevant side-price median from/to or delta.
Do not show a movement label supported only by hidden technical detail.

If the deployed payload has all-zero line and price deltas but a non-STABLE
status, fix the authoritative movement calculation. If price delta is nonzero,
retain the classification but correct the public label/evidence. Do not assume
which branch applies before inspecting the payload.

Deterministic tests must include:

```text
same line + same prices + bookmaker 4->5 = STABLE
same line + changed side price median = PRICE_MOVEMENT
changed line + same prices = LINE_MOVEMENT
changed line + changed prices = LINE_AND_PRICE_MOVEMENT
multiple snapshots alone never imply movement
```

### P0 — D15-02 One canonical public market-evidence readiness authority

Define one source-bound public market-evidence status per AH/OU market and use it
consistently in Market Radar, selected-match Market View, market fact and Model
Lab market summary.

Minimum semantics:

```text
READY        = current snapshot exists and freshness is current
STALE        = persisted snapshot exists but freshness is stale
INSUFFICIENT = no usable current snapshot/evidence
```

The existing raw/source status may remain in technical details, but it cannot be
shown as a second competing public readiness status.

The lower Model Lab relation is not a second market-readiness authority. Label
it explicitly as `模型比较状态`, with values such as comparable, model not ready,
market evidence not ready or insufficient bookmaker depth.

For one market, the following must never coexist in primary copy:

```text
市场就绪 + 市场证据未就绪
就绪 + 新鲜度已过期
```

### P0 — D15-03 Stale evidence must fail closed without hiding Market Memory

A stale historical snapshot remains valuable Market Memory and must remain
visible with its capture time, line, price and lineage. It must be labelled:

```text
历史快照（已过期，不可用于当前模型比较）
```

Stale evidence must not produce `就绪` in Market Radar, Market View, Market Fact
or Model Lab summary. Model comparison should remain blocked until a fresh
source-bound snapshot exists. Do not delete or overwrite the historical points.

### P1 — D15-04 Replace ambiguous observation terminology

Do not present `observation_count` as “次观测”. Preserve the canonical field for
compatibility/technical detail, and expose or derive clear public counts:

```text
snapshot_count
bookmaker_pair_count = sum of bookmaker pairs across snapshots
quote_row_count      = single-side quote rows (current observation_count)
```

Preferred public copy:

```text
2 个快照 · 9 组机构双边报价（18 条单边报价）
```

### P1 — D15-05 Scoreline context must be structurally labelled

Replace the inline status string with separate labelled fields/chips:

```text
模型状态
比赛就绪
阻塞原因
```

The unavailable state must not render as an unparseable sequence such as
`模型 不可用 就绪 阻塞 身份映射未就绪`.

### P1 — D15-06 Attention must aggregate repeated groups, not only a fully homogeneous day

Group repeated Attention rows by at least:

```text
intelligence_state
normalized primary blocker/reason family
affected-domain set
```

Repeated groups of two or more default to one summary row and remain expandable.
Unique high-severity items remain individual. Do not merge COLLECTION_INCIDENT
and DATA_INCOMPLETE into one group.

Required deterministic case:

```text
6 matches
2 COLLECTION_INCIDENT with same collection blocker
4 DATA_INCOMPLETE with same data blocker
=> default Attention shows 2 grouped summaries, not 6 match rows
=> expand exposes all 6 real fixtures
```

The feed must remain ordered by frozen state precedence and kickoff evidence.

## Contract and implementation boundaries

Authorized:

- Round3 movement bug fix only if exact persisted evidence proves it;
- additive unified workspace schema/read-model fields;
- derivation of public evidence readiness from existing persisted market and
  freshness data;
- frontend labels, evidence display, grouping and layout;
- focused source-bound fixture inspection with zero calls/writes;
- tests, screenshots, CI, merge and deployment.

Forbidden:

- Provider calls or manual Provider probes;
- Scheduler/cadence changes;
- 13-competition whitelist changes;
- model/factor/threshold/retraining changes;
- Phase 0.5 rerun;
- Round4 start;
- Candidate/Formal/Lock/Production or real-money enablement;
- synthetic market points or inferred movement;
- deleting historical Market Memory;
- migration unless proven unavoidable and Owner approval is obtained.

## Required tests and evidence

At minimum:

1. Unit tests for all four movement classes and bookmaker-count-only change.
2. Contract tests locking market public readiness and source-status separation.
3. Negative tests forbidding `READY + STALE` and conflicting market readiness
   copy for the same market.
4. E2E tests for price-only movement with visible price evidence, stale Market
   Memory, quote-count terminology, Scoreline labels and grouped Attention.
5. Exact real-data payload evidence for the reported fixture, sanitized.
6. 1280x720, 1366x768, 1512x982 and 1536x1024 screenshots with no overlap or
   horizontal overflow.
7. Full exact-head CI, `RELEASE_REQUIRED` and Repository Hygiene PASS.
8. Post-merge deployment through `LOCAL_OCI_RELAY_PRIMARY` only.
9. Postdeploy Web/API exact identity, health, ready, release sync, no-call and
   no-write acceptance.
10. Postdeploy real-page evidence proving no contradictory statuses and no
    unsupported movement statement.

## Continuous execution and terminal behavior

Execute D15-01 through D15-06 continuously. Ordinary implementation, test,
layout, schema, exact-payload-inspection and deployment failures inside this
scope must be fixed and revalidated without intermediate Owner relay.

After exact-head PASS, merge and deploy through the existing local OCI relay.
Stop only at:

```text
DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS
DASHBOARD_OWNER_MARKET_TRUTH_ROLLED_BACK
MARKET_TRUTH_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

Even after PASS, Round4 remains `NOT_STARTED`.

## Required sanitized outputs

- implementation PR and exact SHAs;
- exact persisted movement-evidence report;
- movement/readiness contract tests;
- viewport screenshots;
- Full CI and promotion run IDs;
- deployment receipt;
- updated `CODEX_EXECUTION_RECEIPT.md`;
- updated `CURRENT_STATE.yaml`;
- updated `NEXT_ACTION.md`.

Do not commit public URL/IP, SSH identity path, credentials, database identifiers,
API keys or unredacted production logs.
