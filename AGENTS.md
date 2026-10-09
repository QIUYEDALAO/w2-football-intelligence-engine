# W2 Repository Agent Instructions

2026-09-25 Owner 后续授权已使 Candidate C R0 前向时钟启动：`2026-09-25T09:43:11.620864Z`，生产实现 `d4ef36edebe66e4e3c7f279adbf37c9b51d947a9`，只开放 R1 追加证据与 Dashboard 只读监测。下方 Freeze A0 限制保留为独立 quant 平台的历史边界；不得据此误判该已登记时钟为未启动，也不得推论 Freeze A1 Provider 实时采集已获授权。

## 🔴 验收铁律（每次验收/下结论前必读，硬性）

任何「验收 / 复验 / 回执 / 6ol / 总验收 / CHANGES_REQUIRED / VERIFIED_LOCAL_ONLY / BLOCKED_NOT_VERIFIED」出现时：

1. **必须先调用** `Skill: acceptance-rules`（`~/.workbuddy/skills/acceptance-rules/SKILL.md`），逐条走 11 条强约束。
2. **10 条硬条件全满足才签 `VERIFIED_LOCAL_ONLY`**；有实际缺陷 → `CHANGES_REQUIRED`；因环境/材料无法执行 → `BLOCKED_NOT_VERIFIED`（列明未验项）。
3. 🔴 三条最易踩的红线（禁止再犯）：①不得把未完成的核心要求改名为「边界」「覆盖不足」「历史债」；②不得用「安全通过」掩盖错误放行、用「覆盖恢复」掩盖正常重试失败；③「亲跑脚本重算一致」只证可复现、不证公式正确——必须独立核对脚本核心公式/口径，不得把实施方脚本当唯一 oracle。
4. 发现合同内缺陷直接交实施方整改并复验，全部硬条件满足后再交总验收；不得把未解决问题包装成已收口。

Before any W2 change, read:

- `NEXT_ACTION.md`
- `AI_PROJECT_CONTEXT.md`
- `PROJECT_STATE.yaml`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_PROJECT_STATE.yaml`
- `QUANT_AGENTS.md`
- `docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`
- `docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`
- `docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md`
- the historical architecture checklist and independent audit receipts.

## Current quant program

```text
TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
CURRENT_WORKSTREAM = W2_QUANT_CONTEXT_FREEZE_A0
CURRENT_PHASE = QUANT_CONTEXT_CLOSURE
CURRENT_MAIN_SHA = 75159bfd71bb7492eece86da29cdb32e6f25d9c6
DEPLOYED_SOURCE_SHA = b5fb9ece6aa4c45696442dd7c9dd3cad8067f370
FREEZE_A0 = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1 = DEFERRED_OWNER_API_AND_LICENSE
TRACK1_FORWARD_CLOCK = STARTED
LIVE_CAPTURE_ENABLED = false
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
```

该 context PR 合并时唯一授权的独立量化代码目标为 `W2_QUANT_L1_OFFLINE_FOUNDATION`；后续 Candidate C R0 的具体授权以文件顶部及 `NEXT_ACTION.md` 为准。

## Quant code boundary

New quant code must be isolated under:

```text
src/w2/quant_research/
scripts/quant/
```

It must not be placed in:

```text
src/w2/prematch/
src/w2/strategy/
RecommendationDecisionV4
existing future-refresh business paths
```

Required reuse:

- `src/w2/domain/canonical_serialization.py`;
- `w2.canonical-json.v2`;
- existing PostgreSQL/Alembic and canonical fixture/team identities through explicit ports.

Do not create a second canonical serializer, generic HTTP transport, database engine or fixture
identity.

Freeze A0 stop line:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Do not implement live adapters, collector activation, strategies, Shadow orders, Kelly,
bankroll/risk, portfolio, 2×1 or real-money workflows. Do not modify the existing Scheduler,
Provider allowlist, V4 or Dashboard.

## Source and branch rules

Local workspace layout:

- the only W2 repository allowed directly under `/Users/liudehua/Documents/Projects/` is
  `/Users/liudehua/Documents/Projects/w2-football-intelligence-engine`;
- every additional task, audit, baseline or detached worktree must be created under
  `/Users/liudehua/Documents/Projects/W2-workspaces/`;
- do not create new `/Users/liudehua/Documents/Projects/w2-*` or `_w2_*` sibling directories;
- use `git worktree move` for relocation, and never delete or reset a dirty worktree while
  consolidating directories.

```bash
git worktree list
git status --porcelain=v1
git rev-parse codex/w2-authority-20260916
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' codex/w2-authority-20260916
```

- the single source of truth is the local branch `codex/w2-authority-20260916`; start from its
  latest commit in a clean worktree;
- the GitHub remote is legacy and outside the workflow: it carries only this one branch and has
  never had a `main`, so `git rev-parse origin/main` fails by construction. Do not reintroduce a
  remote-based precondition that cannot be satisfied locally, and do not treat a stale
  `origin/*` ref as the authority;
- stop on source drift or a dirty workspace;
- do not use PR #453, `agent/eval-02b-c9-*`, `e875050f...` or automation-authored remediation
  (the prohibition is on the content and lineage, not on GitHub PR mechanics — the remote is legacy);
- one bounded task per commit and per worktree; integrate with a merge commit only, never squash,
  never rewrite history that is already recorded, and never auto-merge.

## Operational safety rules retained

1. Missing, illegal, stale, unknown or unverifiable authority fails closed.
2. After a possible external Provider side effect, failure is persisted, surfaced, stops later
   calls and forbids automatic retry.
3. Idempotency requires the expected constraint and all stored business fields to agree.
4. Required empty, swallowed failure, no lock or not executed is not success.
5. One business fact has one versioned computation authority.
6. Historical identity and hash are not overwritten without migration.
7. Do not delete, skip, xfail or weaken required event, five-state `1e-9`, package matrix,
   delta, lineage, migration, fault-injection or historical guards.
8. Workflows may not push business implementation into PR branches.
9. Same-source tests are not an independent oracle.
10. Completion reports must distinguish implementation from independent review.

## R5 canonical serialization

- production authority: `src/w2/domain/canonical_serialization.py`;
- current contract: `w2.canonical-json.v2`, UTF-8, sorted compact keys, `allow_nan=False`;
- historical v1 profiles remain explicit compatibility contracts;
- SER-05 oracle author differs from production implementer and does not import production
  serializer;
- CI rejects a second unauthorised serializer or hash writer.

## Historical operational compatibility record

The following is retained as completed operational history, not as the current quant action:

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
ACTIVE_CONTEXT_PR = NONE
CURRENT_WORKSTREAM = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
CURRENT_PHASE = PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
DEPLOYED_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
DASHBOARD_REAL_DATA_RECOVERY = PASS
PUBLIC_DASHBOARD_CARDS = 51
PRODUCTION_FUTURE_FIXTURES = 51
PROVIDER_REQUEST_DELTA = 58
ENDPOINT_CAPTURE_DELTA = 58
PROVIDER_ERRORS = 0
COLLECTION_READY_COMPETITIONS = brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien
PROVIDER = ON_CONTROLLED
REAL_PROVIDER = ON_CONTROLLED
PERSISTENT_SCHEDULER = ON_CONTROLLED
SCHEDULER_CONCURRENCY = 1
PROVIDER_ATTEMPTS = 1
DAILY_HARD_CAP = 120
TICK_HARD_CAP = 30
DYNAMIC_EVALUATION_V2 = 0
EXPLICIT_NOT_READY_CARDS = 51
DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING
EVAL-03 = NOT STARTED
COLD_PULL_SLO = NOT_PROVEN
NEXT_CODE_ACTION = NONE_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
```

Registered historical policy gaps remain recorded:

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

The operational V4 chain, Wave 1–4 receipts, real canary, independent oracle and real-fixture
replay remain historical evidence. Candidate, Formal, Lock and Production stay off.
