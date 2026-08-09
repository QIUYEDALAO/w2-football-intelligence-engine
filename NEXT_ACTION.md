# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_OWNER_MARKET_TRUTH_REMEDIATION
CURRENT_GATE = DASHBOARD_OWNER_MARKET_TRUTH_REMEDIATION_ACTIVE
AUTHORITY = DASHBOARD_OWNER_MARKET_EVIDENCE_CONSISTENCY_REMEDIATION.md
BASE_MAIN = 14a25727c77b5ede3a1731ec2487e08fa2be4eab
PR_504 = MERGED_DEPLOYED_BUT_OWNER_ACCEPTANCE_REVOKED
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
TERMINAL_TARGET = DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS
```

## Why this workstream is reopened

PR #504 passed technical CI and deployment, but real persisted market data exposed
movement-evidence and readiness-authority conflicts that were not covered by the
prior deterministic acceptance.

The previous `DASHBOARD_OWNER_CANONICAL_TRUTH_ACCEPTANCE_PASS` is not the final
Owner verdict. It is superseded by the current bounded remediation authority.

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. DASHBOARD_OWNER_MARKET_EVIDENCE_CONSISTENCY_REMEDIATION.md
5. DASHBOARD_DATA_CONTRACT.md
6. current origin/main market engine and unified workspace code
7. current persisted real-data payload for the reported fixture, read only
8. PR #504 evidence only as historical implementation evidence
```

## Execute continuously

Close D15-01 through D15-06 in one continuous task. Do not stop after merely
renaming the movement label.

First inspect the exact persisted payload and determine whether the reported
status is caused by a real side-price median delta or by an incorrect movement
classification. Then enforce the exact four-class movement contract and display
the evidence that supports it.

Create one canonical public market-evidence readiness status and use it in
Market Radar, selected-match Market View, Market Fact and Model Lab market
summary. A stale snapshot may remain visible as Market Memory but cannot be
publicly `就绪`. Label Model Lab relation separately as `模型比较状态`.

Then close quote-count terminology, Scoreline status layout and repeated-group
Attention aggregation. Preserve every accepted D13/D14 fix.

## Required negative assertions

```text
same line + same prices + bookmaker-count change != movement
PRICE_MOVEMENT primary label != 盘口变化
STALE + READY for same public market = forbidden
市场就绪 + 市场证据未就绪 for same market = forbidden
multiple snapshots alone != movement
observation_count primary label 次观测 = forbidden
unlabelled Scoreline status string = forbidden
6 Attention matches in 2 repeated groups -> 2 default group summaries
```

## Validation and delivery

Require focused Python/unit/contract tests, full Web E2E, exact-head Full CI,
`RELEASE_REQUIRED`, Repository Hygiene and deterministic screenshots at
1280x720, 1366x768, 1512x982 and 1536x1024.

After PASS, merge and deploy through `LOCAL_OCI_RELAY_PRIMARY`. Run real
postdeploy acceptance against the reported Market Memory case and verify Web/API
identity, health, ready, release sync, Provider calls 0 and business writes 0.

Do not ask the Owner to relay ordinary in-scope failures. Fix and revalidate
until a terminal classification is reached.

## Terminal classifications

```text
DASHBOARD_OWNER_MARKET_TRUTH_ACCEPTANCE_PASS
DASHBOARD_OWNER_MARKET_TRUTH_ROLLED_BACK
MARKET_TRUTH_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

Round4 remains `NOT_STARTED` after every terminal classification.

## Frozen stop lines

```text
PROVIDER_CALL_OR_MANUAL_PROBE = FORBIDDEN
DB_BUSINESS_WRITE_FROM_READ = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_CONNECTION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
SYNTHETIC_MARKET_POINT_OR_MOVEMENT = FORBIDDEN
DELETE_MARKET_MEMORY = FORBIDDEN
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
```
