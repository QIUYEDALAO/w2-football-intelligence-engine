# W2 AI Project Context

> **用途：** 任何 AI 或人接手 W2 时先读本文件。它是“已完成 + 核心规则 + 当前待办”的 AI 汇总，不替代代码、DB 约束、Git history、Actions logs 和独立审查。
>
> 机器状态：[`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)  
> 当前动作：[`NEXT_ACTION.md`](NEXT_ACTION.md)  
> 独立终审：[`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)  
> 资产唯一性审计：[`docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`](docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md)  
> 审计视角登记：[`docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)  
> 执行总单：GitHub Issue **#454 v4**  
> workflow 治理事件：Issue **#455**  
> 计算权威唯一性：Issue **#456**

---

# 1. 当前可信基线

```text
repository = QIUYEDALAO/w2-football-intelligence-engine
trusted_main = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
compare(trusted_main, main) = identical
```

- PR #449 已包含在该 main 基线；
- `e875050f6bc0286aed389aadfce1e17b2063635a` 不是 main 的祖先；
- 当前已知 workflow 污染限于 Draft agent 分支；main 不需要回滚或历史重写；
- PR #453 已隔离：`QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE`。

---

# 2. 已完成

- P0/P1/P2 架构收敛完成，冻结范围继续有效；
- 阶段 A 已合并任务完成；
- EVAL-01A/B/C、EVAL-02A 在冻结实现范围内完成；
- OPS-01 Runbook 文档完成，runtime enablement 未完成；
- EVAL-02B 预注册合同、Legacy 35 永久排除决策、写侧 Implementation 01–04 完成；
- exact-pair 核心合同已实现：`capture_at` 边界、同 provider/bookmaker/market/selection/exact line、五态概率合法、歧义 fail-closed；
- `2/2.5 -> 2.25` 是明确实现和测试合同，不是已证实缺陷；
- `readiness.py` 是状态计算器，不是 Provider live-call 入口。

### 架构收敛与当前整改的关系

当前 GitHub 证据确认：

- C7 最迟于 2026-06-23 的 `8e467e65...` 存在；
- C5 最迟于 2026-06-25 的 `5e46a8b...` 存在；
- C1、C6、C11-A 由 2026-07-03 的 `97978194...` 引入；
- C11-B 当前形态来自 2026-07-05 的 `ac17e875...`；
- C9 根问题最迟于 2026-07-19 的 `d460055b...` 存在；
- C2/C3/C4、C8、C10 在 2026-07-22 架构主清单建立时已经存在。

准确裁决：

```text
ARCHITECTURE_CONVERGENCE_SCOPE_REMAINS_VALID
NO_EVIDENCE_C1_TO_C11_WERE_CREATED_BY_ARCHITECTURE_CONVERGENCE
```

禁止扩大成未经证明的“架构收敛没有引入任何其他缺陷”。

---

# 3. 当前状态

```text
CURRENT_TASK = EVAL-02B-T00
EVAL-02B_END_TO_END = BLOCKED / NOT_VALIDATED
EVAL-03 = NOT_STARTED
PROVIDER = OFF
REAL_CANARY = NOT_AUTHORIZED
PERSISTENT_SCHEDULER = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

A148 只能定义为：

```text
FAIL_CLOSED_BARRIER = PASS
PROVIDER_EXECUTION = NOT_EXECUTED
END_TO_END_CHAIN = NOT_VALIDATED
RUNTIME_COLLECTION_READINESS = NOT_PROVEN
```

A148 证明挡板有效，不证明链路可用。

---

# 4. workflow 治理事件

已核实：

```text
e875050f6bc0286aed389aadfce1e17b2063635a
Author: OpenAI Agent
```

它修改 C9 生产代码/测试并删除触发它的 workflow。多个相关 workflow 具有 `contents: write` 并能向业务 PR 分支 push。

裁决：

- PR #453 只作证据；
- C9 必须从可信 main 的本地 clean worktree 正常重写；
- 禁止 cherry-pick bot/workflow 整改提交；
- T00-GOV 必须把 workflow/run/commit/push 未解释项全部归零；
- 禁止任何自修改业务 workflow。

---

# 5. 风险家族 R1–R5

```text
R1 Default allow / missing authority
R2 Silent failure / failure downgrade
R3 External side effect / local-state non-atomicity
R4 Authority split / concurrency / identity drift
R5 Computation authority split
```

R5 由本次资产唯一性审计新增：

> 同一业务事实、identity/hash、market taxonomy、odds 或 metric 存在多个算法实现；或不同业务定义使用相同名称而没有版本和边界。

---

# 6. 资产唯一性新结论

## 6.1 存储层

当前独立清点未发现：

- ORM `__tablename__` 重名；
- 已 drop 表仍留 ORM model；
- upgrade 重复建表；
- git 中 `runtime/` / `reports/` 残留权威。

严谨表述：

```text
STORAGE_ASSET_RESIDUALS = NO_CURRENT_EVIDENCE
REPRODUCIBLE_STORAGE_INVENTORY = REQUIRED_BY_T00_R5
```

## 6.2 Critical：canonical serialization 分裂

至少六个运行相关 serializer 已逐项核实：

```text
future_refresh                ensure_ascii=True,  allow_nan default True
outcome_ledger_repository     ensure_ascii=True,  allow_nan default True
stage7i_lifecycle             ensure_ascii=True,  allow_nan default True
stage7i_supervision           ensure_ascii=True,  allow_nan default True
read_model_projection         ensure_ascii=False, allow_nan default True
prematch.repository pair hash ensure_ascii=False, allow_nan=False
```

代码搜索还有其他 helper；“6”是最小已核实集合，不是最终分母。

中文 payload 实证：

```text
ensure_ascii=True  -> 97c6d410cc9167d2...
ensure_ascii=False -> 3c6fe4e44f3ad08f...
```

EVAL-02B 合同虽规定 sorted keys、compact separators、UTF-8 和禁止 NaN/Infinity，但没有冻结：

```text
serializer version
ensure_ascii
Unicode policy
number/Decimal/date/datetime policy
```

所以：

```text
R5_CANONICAL_SERIALIZATION = CRITICAL_GATE_A
```

在 #456 R5-SER 完成前，真实 canary 继续禁止。

## 6.3 Important：其他计算权威

已核实：

- `fair_decimal_odds`：float/round 6 与 Decimal/4 位 HALF_UP 两套；
- canonical market：采集、matchday、历史、AH scope 等多实现；
- Brier/ECE：`models/evaluation.py` 与 `tracking/performance_scoring.py` 两套；
- odds parse/representation：str/float/Decimal 多路径；
- `ReadModelRepository` / `ReadModelService` 同名但职责不同；
- migrations 0002–0016 动态读取当前 `Base.metadata`。

最终数量由 T00-R5 生成，不以人工 grep 计数为验收分母。

---

# 7. 审计视角状态

| 视角 | 状态 | 关闭门禁 |
|---|---|---|
| 架构、存储权威、重复路径 | COMPLETE（冻结范围） | 已完成；T00-R5 复现资产 inventory |
| 动态失败、缺失、并发、计费 | IN_PROGRESS | Gate A |
| workflow/供应链治理 | IN_PROGRESS | 可信实现前 |
| **计算权威唯一性** | **IN_PROGRESS** | canonical serializer Gate A；其余 Gate C |
| 数据与数学正确性 | PARTIAL / SELF_REVIEWED_ONLY | Gate C 独立 oracle |
| 时间与时序 | PARTIAL | Gate A 最小链；Gate B 全路径 |
| 安全/权限/密钥/日志 | PARTIAL | Gate D |
| 恢复/灾备 | NOT_AUDITED | Gate D |
| 可观测性 | PARTIAL | Gate B |
| 性能/资源 | PARTIAL | Gate B/D |

同源实现测试不等于独立数学或业务 oracle。

---

# 8. 核心工程规则

1. **Default deny.** 缺失、非法、陈旧或不可验证意味着 `BLOCKED`。
2. **Explicit failure after side effect.** Provider 可能送达后，后续失败必须持久化、冒泡、停后续调用并禁止自动重试。
3. **Idempotency must be proven.** 只有预期约束 + 回读全部业务字段一致才是 no-op。
4. **No silent success.** Required empty、吞异常、无锁、陈旧 quota、未执行都不是成功。
5. **Canary is evidence-chain acceptance.** 不是进程存活或 HTTP 200。
6. **No self-modifying workflow.** 业务代码只允许本地正常 edit/commit/push/Draft PR。
7. **Context follows evidence.** 文档和状态不能领先于代码/GitHub 事实。
8. **Perspective coverage is explicit.** 完成声明列明覆盖和未覆盖视角。
9. **Perspective registry self-expands.** 无法映射的新发现必须新增视角。
10. **Emergency fix needs post-incident review.** 至少 R1–R4；触及计算/hash 时含 R5。
11. **One computation authority.** 同一事实只有一个明确算法权威；不同业务定义必须显式命名/版本化。
12. **Historical hashes are immutable without migration.** 不得无版本覆盖既有 identity/hash。

---

# 9. 真实 canary 硬合同

全部增量必须为正：

```text
actual_provider_calls_delta      > 0
provider_request_ledger_delta    > 0
raw_payload_delta                > 0
endpoint_capture_delta           > 0
lineup_event_delta               > 0
dynamic_evaluation_v2_delta      > 0
five_state_snapshot_delta        > 0
exact_pair_delta                 > 0
```

同一 lineage 至少对账：

```text
run_id
authorization_id
competition_id
season
fixture_id
provider
bookmaker
market
selection
exact_line
capture_at
raw_payload_sha256
endpoint_capture_id
lineup_input_hash
evaluation_id
pair_hash
exact_git_sha
serializer_version
```

任一 required delta 为 0、lineage 断裂或 independent hash recomputation 不匹配：

```text
CANARY_FAILED
EVAL_02B_BLOCKED
AUTO_RETRY_FORBIDDEN
```

调用前无法合理预期完整链路时，以 Provider calls=0 / business writes=0 停止；“这次没数据”不能 PASS。

---

# 10. 当前唯一执行顺序

```text
1. GitHub -> local trusted sync
2. T00-GOV (#455)
3. T00-SAFE R1-R5 + storage/computation asset inventory (#454/#456)
4. R5-SER canonical serialization authority + versioned migration/compatibility (#456)
5. trusted-main C9 rebuild in new Draft PR
6. remaining Gate A one-shot-canary blockers
7. fake-Provider offline rehearsal
8. context/evidence sync
9. independent second review
10. human canary authorization decision
```

Codex 必须在真实授权/调用前停止。

---

# 11. Gate 分层

## Gate A：一次人工前台 canary

除 C1–C11 外新增：

- T00-R5；
- canonical serializer 单一权威；
- serialization version 与历史 hash migration；
- EVAL-02B pair identity 合同补全；
- 中文/NaN/Decimal/datetime/pair/seed golden vectors；
- independent hash oracle。

## Gate B：持续 scheduler / 多联赛

完整 saga、全路径时序、progress health、Celery、长 lease、多 run quota、资源/背压和自动恢复。

## Gate C：Candidate / Formal / Lock

- fair odds / decimal odds authority；
- canonical market taxonomy；
- Brier/ECE 与其他 metrics authority；
- EV、五态、结算、CLV、校准 independent oracle；
- 数据集/时间切分/产品阈值；
- 独立产品授权。

## Gate D：Production

migration replay、备份恢复/灾备、密钥/日志/权限/供应链、长期 soak、容量和安全运营签字。

---

# 12. 接手检查清单

1. 读本文件、`PROJECT_STATE.yaml`、`NEXT_ACTION.md`、两份审计、#454/#455/#456。
2. 从 GitHub 同步并验证 main SHA；不依赖聊天记忆。
3. 保留污染 refs；不在 PR #453 原地修。
4. 先 T00-GOV，再 T00 R1–R5，再 canonical serializer，再重建 C9。
5. 不直接裁决 `ensure_ascii=True|False`；先完成持久化 hash inventory 和迁移方案。
6. 不创建可向业务分支 push 的 workflow。
7. 不调用 Provider、不创建真实授权、不启动 scheduler、不合并 PR。
8. 所有结论带 exact SHA、CI、故障注入、golden vectors 和可复现输出。
9. 每项完成声明列出覆盖/未覆盖视角、implementer 和独立 reviewer。
10. 每次事故/异常完成视角映射；触及计算权威时更新 R5。
