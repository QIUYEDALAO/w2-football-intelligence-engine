# W2 League Expansion Runbook

## 1. 目的、范围与权威

本流程用于把一个新联赛或新赛季加入 W2 数据采集范围。完成本流程不等于开放
Recommendation、Candidate、Formal、Lock 或 Production，也不改变模型数学、EV、CLV、
阈值或联赛分层规则。任何安全开关均由其既有独立流程控制。

运行时权威及用途：

| 权威 | 用途 |
|---|---|
| `league_profile` | 联赛身份、时区、市场范围和 readiness requirements |
| `league_season` | provider/season 映射、环境、生命周期和 `enabled` |
| `league_readiness_audit` | seed、enable/disable 和 readiness 决策的 append-only 审计链 |
| `quota_usage` | provider 配额窗口的事实来源 |
| `provider_request_logs` | 已发生 provider 请求的事实来源 |
| canonical identity DB | canonical team/player 及 reviewed provider crosswalk 权威 |

`config/competitions/**/*.json`、future refresh policy 和 matchday policy 只是 reviewed seed
input；seed 后由 DB 的 `league_profile` / `league_season` 承担运行时权威。Provider ID
只作 provenance，canonical team identity 才是比赛和模型主身份。

以下材料只可作历史设计参考，不是通用生产 readiness 权威：

- `scripts/run_stage14a_league_audit.py`
- `scripts/check_w2_stage14a.py`
- `docs/leagues/W2_LEAGUE_ONBOARDING_V1.md`
- `docs/leagues/W2_SEASON_ROLLOVER_V1.md`
- `docs/leagues/W2_LEAGUE_MODEL_SCOPE_V1.md`

Stage14A 本地 contract fixtures、生成型 reports 和 top-five 专用 audit 不得作为新联赛
的事实来源。当前仓库没有可用于任意联赛、覆盖本 Runbook 全部门禁的通用 DB readiness
producer；OPS-01 不新增第二套 producer。没有符合第 7 节字段的现存 DB audit 时，
`READINESS_GATE_BLOCKED`，不得启用。

## 2. 输入申请模板

复制并完整填写；核心字段缺失、空值、未知或互相冲突时输出
`BLOCKED_REQUEST_INPUT_INCOMPLETE`，不得自动补值。

```yaml
competition_id: <canonical slug>
league_name: <reviewed name>
country: <country>
timezone: <IANA timezone>
provider: <provider authority>
provider_league_id: <provider league id>
provider_season: <provider season>
season_start: <YYYY-MM-DD>
season_end: <YYYY-MM-DD>
expected_team_count: <integer>
market_scope: [<canonical markets>]
lineup_observability: <reviewed observation>
results_source: <DB-backed source>
odds_source: <DB-backed source>
operator: <operator identity>
change_reason: <reason>
rollback_owner: <owner identity>
```

申请不得用名称相似度推导 `competition_id`、provider mapping 或 team identity。

## 3. Phase 0：只读预检

任何写入前，以只读事务生成一份预检输出。逐项核对：

1. `competition_id` 在 `league_profile`、`league_season` 和 tracked seed inputs 中的状态；
2. `provider + provider_league_id + provider_season` 是否与其他联赛/赛季冲突；
3. season 起止日期、当前赛季和既有 season 是否冲突；
4. `timezone` 是否为有效 IANA 时区；
5. competition profile、future refresh policy、matchday policy 的 ID、provider ID 和 season
   是否一致；
6. reviewed provider team crosswalk 是否存在 unresolved、一个 provider ID 对多个 canonical
   team、或一个 canonical team 对多个 provider ID；
7. `provider_request_logs` 当前 count/hash；
8. `quota_usage` 当前窗口、used、limit 和剩余量；
9. `W2_PROVIDER_CALLS_DISABLED`、`W2_PROVIDER_SCHEDULER_ENABLED`、
   `W2_RECOMMENDATION_ENABLED`、`W2_CANDIDATE_ENABLED`、
   `W2_FORMAL_RECOMMENDATION_ENABLED`、Formal、Lock 和 Production 状态；
10. scheduler running count。

固定输出只能是：

```text
READY_FOR_SEED
BLOCKED_<REASON>
```

`MISSING`、`UNKNOWN`、`CONFLICT`、`UNRESOLVED`、DB 读取失败或权威缺失都必须进入
`BLOCKED_<REASON>`。预检不得自动修复数据。

建议记录以下只读基线：

```text
PROFILE_ROW_COUNT
SEASON_ROW_COUNT
PROVIDER_MAPPING_CONFLICT_COUNT
PROVIDER_REQUEST_COUNT
PROVIDER_LEDGER_HASH
QUOTA_WINDOW_START
QUOTA_WINDOW_END
QUOTA_USED
QUOTA_LIMIT
SCHEDULER_RUNNING_COUNT
SAFETY_SWITCH_HASH
```

## 4. Phase 1：Profile / Season seed

先在隔离测试数据库 rehearsal，禁止 provider 请求：

```bash
W2_PROVIDER_CALLS_DISABLED=true \
python scripts/seed_competition_runtime_authority.py \
  --environment <environment> \
  --config-root config \
  --updated-by <operator>
```

入口复用 `src/w2/competitions/seed.py`，写入或核对：

- `league_profile`；
- `league_season`；
- provider、provider league ID、provider season、environment、enabled；
- profile/season config hash；
- `league_readiness_audit` 中的 seed audit。

必须保存并比较：

```text
inserted_profiles
updated_profiles
inserted_seasons
updated_seasons
unchanged
audits_written
conflicts
provider_calls=0
```

`conflicts` 非空或命令非零退出时立即停止。

真实 seed 前备份以下最小数据，并记录备份位置与 SHA-256：

- 目标 `league_profile` 行（不存在也记录 `ABSENT`）；
- 目标 `league_season` 行（不存在也记录 `ABSENT`）；
- 目标联赛最新 `league_readiness_audit`；
- competition seed、future refresh policy、matchday policy 的 source hash。

对完全相同输入再运行一次，验收：

```text
SEED_RERUN_STATUS = PASS
UNEXPECTED_PROFILE_UPDATES = 0
UNEXPECTED_SEASON_UPDATES = 0
CONFIG_HASH_PARITY = PASS
IDENTITY_CONFLICT_COUNT = 0
provider_calls=0
```

## 5. Phase 2：Canonical identity gate

对目标 season 的每支球队逐一核对：

```text
provider team ID
→ reviewed provider_team_identity_crosswalks
→ canonical_teams.w2_team_id
```

只接受 REVIEWED/APPROVED provenance 以及有效期覆盖目标时间的映射。不得使用 name-only、
fuzzy、first-row 或未经 review 的自动映射。Provider ID 仅作 provenance，不得直接成为
模型或 fixture 的 canonical identity。

记录：

```text
EXPECTED_TEAM_COUNT
MAPPED_TEAM_COUNT
UNRESOLVED_IDENTITY_COUNT
DUPLICATE_PROVIDER_MAPPING_COUNT
DUPLICATE_CANONICAL_MAPPING_COUNT
REVIEW_PROVENANCE
CANONICAL_IDENTITY_HASH
```

硬门禁：

```text
UNRESOLVED_IDENTITY_COUNT = 0
DUPLICATE_PROVIDER_MAPPING_COUNT = 0
DUPLICATE_CANONICAL_MAPPING_COUNT = 0
```

任一不为零即 `IDENTITY_GATE_BLOCKED`。新赛季升降级或新增球队必须重新 review，不得沿用
名称相似度确认。

## 6. Phase 3：Provider quota gate

配额事实只来自当前 `quota_usage` 和 `provider_request_logs`；endpoint allowlist 与 tick
hard cap 只来自当前运行配置。不得自行发明 provider 套餐上限或安全余量。

对目标联赛未来七天的真实 fixture 列表逐日运行 dry-run。命令只允许 dry-run，不得 enqueue：

```bash
python scripts/run_w2_matchday_refresh_plan.py \
  --dry-run \
  --json \
  --env <environment> \
  --date <YYYY-MM-DD> \
  --competition-id <competition_id> \
  --fixture-id <fixture_id> \
  --kickoff-utc <kickoff_utc> \
  --as-of <as_of_utc>
```

多个 fixture 分别重复 `--fixture-id` 和 `--kickoff-utc`。每次输出必须核对：

```text
projected_calls_by_tick
endpoint_allowlist
hard_cap
blocked_ticks
would_enqueue=false
provider_calls=0
db_writes=0
```

计算方法：

```text
CURRENT_USAGE
  = quota_usage 当前有效窗口内、目标 provider/endpoint 的 used 总和

CURRENT_REMAINING_BUDGET
  = quota_usage 当前有效窗口 limit 总和 - CURRENT_USAGE

PROJECTED_CALLS_PER_TICK
  = dry-run projected_calls_by_tick 的逐 tick 值

PROJECTED_DAILY_CALLS
  = 同一自然日所有非 blocked tick 的 projected calls 总和

PROJECTED_7_DAY_CALLS
  = 七个实际自然日 dry-run 结果之和；不得用虚构平均值外推

SAFETY_HEADROOM
  = 当前 quota/config authority 已明确保留的安全余量

POST_ENABLE_PROJECTED_USAGE
  = CURRENT_USAGE + PROJECTED_7_DAY_CALLS
```

固定裁决：

- 预算内且保留既有安全余量：`QUOTA_GATE_PASS`；
- 超出预算：`QUOTA_GATE_BLOCKED`；
- quota authority、安全余量或窗口无法确定：`QUOTA_GATE_UNKNOWN`，按 BLOCKED 处理。

超预算联赛进入队列，禁止启用：

```yaml
competition_id: <id>
requested_at: <UTC timestamp>
projected_calls: <7-day calls>
current_remaining: <authority value>
blocking_reason: <reason>
reconsider_after: <UTC date/time or authority event>
owner: <operator>
```

## 7. Phase 4：Readiness audit

读取目标联赛最新 `league_readiness_audit`，并验证其 hash 与 payload。合格 audit 必须覆盖：

- profile identity；
- season identity；
- provider mapping；
- canonical team coverage；
- fixture coverage；
- result coverage；
- 1X2、AH、OU coverage；
- timeline coverage；
- lineup observability；
- duplicate fixtures；
- malformed rows；
- quota gate；
- rollback readiness。

盘点结论：当前通用生产入口仅有
`scripts/seed_competition_runtime_authority.py` 的 config/enable audit；Stage14A 和
`scripts/check_w2_league_remediation_readiness.py` 不构成任意联赛的完整 DB readiness
producer。本 Runbook 不把这些历史/离线工具升级为权威，也不新增第二套 readiness schema。

因此：

```text
LATEST_AUDIT_PRESENT = false  → READINESS_GATE_BLOCKED
AUDIT_HASH_INVALID = true     → READINESS_GATE_BLOCKED
REQUIRED_FIELD_MISSING = true → READINESS_GATE_BLOCKED
ANY_GATE_NOT_PASS = true      → READINESS_GATE_BLOCKED
```

只有现有 DB 中已存在、来源受审、字段完整且与当前 profile/season/identity/quota hash 对齐的
audit 才能得到 `READINESS_GATE_PASS`。缺失 producer 时必须由后续明确授权补齐，不得通过
direct SQL、Stage14A fixtures、runtime 文件或 reports 文件伪造 audit。

## 8. Phase 5：Enable

仅当下列全部为 PASS：

```text
PROFILE_GATE_PASS
SEASON_GATE_PASS
IDENTITY_GATE_PASS
QUOTA_GATE_PASS
READINESS_GATE_PASS
BACKUP_READY
ROLLBACK_OWNER_ASSIGNED
```

执行现有 audited 入口：

```bash
python scripts/seed_competition_runtime_authority.py \
  --set-enabled <competition_id> \
  --enabled true \
  --updated-by <operator>
```

核对：

- `league_season.payload.enabled = true`；
- `league_season.lifecycle = ACTIVE`；
- 最新 audit 为 `SET_ENABLED`；
- audit `before=false`、`after=true` 且 `audit_sha256` 已记录；
- 其他联赛 profile/season/config hash 不变；
- Provider scheduler 和所有 recommendation/product 安全开关不变。

`--set-enabled` 只改变目标联赛 runtime scope，不得与 Formal、Lock、Production 或
Provider scheduler 开关绑定。

## 9. Phase 6：七天观察

启用后观察七个完整自然日。每日从 DB/runtime authority 记录：

```text
FIXTURE_EXPECTED_COUNT
FIXTURE_CAPTURED_COUNT
RAW_FIXTURE_PAYLOAD_COUNT
ODDS_OBSERVATION_COUNT
MARKET_1X2_COVERAGE
MARKET_AH_COVERAGE
MARKET_OU_COVERAGE
LINEUP_OBSERVED_COUNT
RESULT_TERMINAL_COUNT
UNRESOLVED_TEAM_IDENTITY_COUNT
MALFORMED_PAYLOAD_COUNT
DUPLICATE_FIXTURE_COUNT
PROVIDER_REQUEST_DELTA
QUOTA_USAGE_DELTA
BLOCKED_REFRESH_TICK_COUNT
WORKER_FAILURE_COUNT
READ_MODEL_PROJECTION_COVERAGE
RUNTIME_FALLBACK_COUNT
PROVIDER_FALLBACK_COUNT
```

阈值只从目标 `league_profile.payload.competition_profile.readiness_requirements`、coverage
policy 和运行时安全约束读取，不在执行时临时发明。任何关键来源为
`MISSING`、`UNKNOWN`、`CONFLICT` 或 `UNRESOLVED` 时，不得判为 STRICT。

## 10. Phase 7：ADVISORY / STRICT 分类

分类必须由当前 profile、lineup observability、七日 observation 和 readiness audit 推导：

**STRICT**

- canonical identity 完整；
- results、odds、timeline 满足现有 readiness requirements；
- 赛前 lineup 可观测；
- 无关键 unresolved；
- 七日观察没有 authority 或 fallback 冲突。

**ADVISORY**

- canonical identity、results、odds 和核心 provenance 完整；
- 赛前 lineup 无法稳定观测；
- 后续必须进入 EVAL-02A 的盲区防护链。

**BLOCKED**

- identity、result、odds、quota 或 provenance 任一核心门禁未通过。

核心数据缺失时不得降级成 ADVISORY 后继续运行。分类必须追加一条受审
`league_readiness_audit`，字段至少包含：

```text
evidence_window
readiness_audit_hash
quota_evidence
canonical_identity_hash
operator
decision
reason
```

若当前没有授权的通用 audit producer，则分类写入也是 `READINESS_GATE_BLOCKED`，不得用
direct SQL 绕过。

## 11. Rollback

固定命令：

```bash
python scripts/seed_competition_runtime_authority.py \
  --set-enabled <competition_id> \
  --enabled false \
  --updated-by <operator>
```

核对：

```text
league_season.payload.enabled = false
league_season.lifecycle = CONFIGURED
SET_ENABLED.before = true
SET_ENABLED.after = false
ROLLBACK_AUDIT_SHA256 = <actual hash>
```

Rollback 只停止后续运行范围。不得删除历史数据、raw payload、canonical identity、
`league_readiness_audit`、`provider_request_logs` 或 `quota_usage`。回滚后再次核对所有安全
开关和 scheduler 状态。

## 12. 执行记录模板

每次真实联赛执行完成后，将以下精简记录追加到 v3 master checklist 的 OPS-01 执行记录区。
本 OPS-01 PR 不执行真实联赛，所有占位符必须保留，禁止伪造记录。

```yaml
competition_id: <id>
season: <season>
operator: <operator>
execution_date: <UTC date>
profile_config_hash: <hash>
provider_mapping: <provider/id/season>
canonical_identity_hash: <hash>
team_count: <count>
unresolved_count: <count>
quota_baseline: <used/limit/window>
projected_seven_day_calls: <count>
quota_gate: <PASS|BLOCKED|UNKNOWN>
readiness_audit_hash: <hash>
enable_audit_hash: <hash>
observation_start: <UTC date>
observation_end: <UTC date>
seven_day_coverage_summary: <summary>
tier_decision: <STRICT|ADVISORY|BLOCKED>
decision_reason: <reason>
rollback_command: >-
  python scripts/seed_competition_runtime_authority.py
  --set-enabled <competition_id> --enabled false --updated-by <operator>
rollback_status: <NOT_RUN|PASS|FAIL>
provider_call_delta: <count>
safety_switch_verification: <hash/status>
```

### Operator completion receipt

```text
PROFILE_GATE
SEASON_GATE
IDENTITY_GATE
QUOTA_GATE
READINESS_GATE
BACKUP_READY
ROLLBACK_OWNER_ASSIGNED
SEED_RERUN_STATUS
ENABLE_AUDIT_SHA256
SEVEN_DAY_OBSERVATION_STATUS
TIER_DECISION
ROLLBACK_READY
PROVIDER_CALL_DELTA
SAFETY_SWITCH_HASH_BEFORE
SAFETY_SWITCH_HASH_AFTER
```

本 Runbook 的 rehearsal 必须保持 `provider_calls=0`、`db_writes=0`（seed 隔离测试数据库
除外）。真实执行的每次 DB 写入必须来自上述现有 audited 入口，不得创建竞争性权威。
