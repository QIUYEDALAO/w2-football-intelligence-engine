# W2 审计视角登记表与跨视角验收模板

> 本文件用于管理“系统已经从哪些视角审过、哪些只做了局部覆盖、哪些尚未形成独立证据”。
>
> 它不推翻已经完成的架构收敛，也不把所有未来审计视角提前塞进第一次真实 canary。
> 当前执行权威仍是 GitHub Issue #454；自修改 workflow 治理事件权威是 Issue #455。

## 1. 为什么需要视角登记

清单只能穷尽清单已经提出的问题。严格验收可以证明“实现符合当前规格”，但无法自动证明“规格已经覆盖所有风险类别”。

W2 采用两类互补方法：

```text
清单法：已知问题 -> 实现 -> 验收 -> 关闭
生成法：风险规则 × 全仓路径/外部副作用点/失败时机 -> 生成未知实例
```

T00-GOV 与 T00-SAFE 是当前第一次系统化生成式清点：

- T00-GOV：workflow、run、commit、push、分支来源；
- T00-SAFE：R1–R4 四个运行安全家族。

本登记表负责更高一层的问题：记录尚未使用或只覆盖一部分的审计视角，避免把“一个视角完成”误写成“系统整体完成”。

## 2. 已核实时间线：当前 Critical 不是架构清单返工

以下结论基于 GitHub 提交和对应代码，不依据状态自述。

| 风险 | 最迟已存在/引入时间 | GitHub 证据 | 结论 |
|---|---|---|---|
| C5 DB 模式绕过运行锁 | 2026-06-25 | `5e46a8bfa946fad018df2276e7dadf0d78ce2979`，`Package A core: future-refresh DB persistence`；该版本 DB persistence 直接 `lock_acquired = True` | 明确早于架构收敛 |
| C1 Provider 总熔断缺失时允许 | 2026-07-03 | `97978194ba577efebc1d9f12c17d92e15cc5b4b2`，`A-QUOTA-INCIDENT-002 Provider quota hard-stop`；新增 `provider_calls_disabled(... default=False)` | 明确早于架构收敛 |
| C6 request ledger 与 quota ledger 分事务 | 2026-07-03 | 同一提交新增 `DbProviderRequestLedger`，request log commit 与 quota usage commit 分离 | 明确早于架构收敛 |
| C11-A request ledger 吞 `IntegrityError` | 2026-07-03 | 同一提交新增 `except IntegrityError: session.rollback()` 后继续 | 明确早于架构收敛 |
| C7 广义异常重试/不确定送达风险 | 2026-07-04 前后已存在 | `f4d221bf0d121044b94db52ad3fc09dd10a91eaf` 中 `_request()` 对 broad exception 按可配置 attempts 重试 | 明确早于架构收敛 |
| C9 的根问题：lineup 写入失败降级、raw 已保存但后续链可缺失 | 2026-07-19 前后已存在 | `d460055b48005fa58ec6f01e555db80a71fb966e` 已将 lineup snapshot 写入置于 broad catch/错误降级路径 | 根问题早于架构收敛；后续具体代码形态仍由 T00/来源矩阵核实 |
| C2/C3/C4 | 至迟 2026-07-22 已存在 | `09ca14a969b835314c93c122b80c3cfa1bbf9c6c` 基线中的 `scripts/run_prematch_refresh.py` 已存在无 runtime authorization、CLI season 只参与 task key、persistence 未显式时下层默认 DB 的行为 | 已确认在架构清单启动时存在；精确首次引入 commit 可由 T00 补充 |
| C8 schema/异常空数据降级 | 至迟 2026-07-22 已存在 | 同一基线中 `_future_fixtures()` 对非 list 返回 `[]`，required empty 主要表现为 diagnostic | 已确认在架构清单启动时存在 |
| C10 scheduler `restart: unless-stopped` | 至迟 2026-07-22 已存在 | 同一基线 `infra/compose/compose.staging.yml` | 已确认在架构清单启动时存在 |
| 架构收敛总清单建立 | 2026-07-22 | `09ca14a969b835314c93c122b80c3cfa1bbf9c6c` | 晚于上述明确出生点 |

### 裁决

1. 架构收敛清单没有因为当前 C1–C11 而失效；其已完成任务继续保持完成。
2. 当前证据足以证明上述风险不是“清单完成后新发现所以清单白做了”，而是过去未从动态失败、计费一致性、并发或治理视角发现的既有风险。
3. 不能仅凭上述样本宣称“架构收敛绝对没有引入任何其他缺陷”。该绝对命题必须由 T00、提交来源矩阵及对应视角复核支持；当前更准确的表述是：

```text
NO_EVIDENCE_C1_TO_C11_WERE_CREATED_BY_ARCHITECTURE_CONVERGENCE
ARCHITECTURE_CONVERGENCE_SCOPE_REMAINS_VALID
```

## 3. 当前审计视角登记

状态定义：

```text
COMPLETE              已完成该视角的冻结范围和独立验收
IN_PROGRESS           当前正在用生成式方法清点
PARTIAL                有局部合同/测试，但没有全系统独立覆盖
NOT_AUDITED            尚无足够证据
DEFERRED_TO_GATE       已明确在哪个门禁前完成
```

| 视角 | 当前状态 | 已有证据 | 未覆盖/下一门禁 |
|---|---|---|---|
| 架构、权威、重复路径、读写边界 | COMPLETE（冻结范围） | P0/P1/P2 与最终架构验收 | 不因 C1–C11 重开；后续变更按模板检查 |
| 动态失败、缺失输入、并发、计费一致性 | IN_PROGRESS | 独立终审、C1–C11、T00-SAFE R1–R4 | 一次监督 canary 前关闭 `MUST_FIX_FOR_CANARY` |
| 治理、分支来源、workflow 供应链 | IN_PROGRESS | #455、PR #453 quarantine、T00-GOV | 可信 C9 重建前未分类项必须为 0 |
| 数据与数学正确性（EV、五态、结算、CLV、校准） | PARTIAL | 五态合同、settlement/calibration 单项实现与测试、EVAL-01 系列 | Candidate/Formal 前做独立 oracle/recalculation；canary 只要求其直接产物满足冻结数学合同 |
| 时间与时序语义（football day、kickoff window、freshness、as-of、时区） | PARTIAL | `capture_at` 配对合同、部分 timezone/idempotency/checkpoint 测试 | canary 前完成目标链的最小时序证明；持续 scheduler 前完成全路径审计 |
| 安全、权限、密钥和日志暴露 | PARTIAL / NOT FULLY AUDITED | 部分 secret scan、脱敏和容器配置 | Production 安全签字前完成；真实 canary 使用最小权限、隔离凭据 |
| 恢复、备份和灾备 | NOT_AUDITED / UNVERIFIED | 文档或历史报告不能单独证明恢复可用 | Production 前真实恢复演练；持续运行前至少定义失败恢复边界 |
| 可观测性与告警 | PARTIAL | 基础 readiness、已发现 collection 假绿 | 持续 scheduler 前完成 progress/freshness/ledger 健康证明 |
| 性能与资源耗尽 | PARTIAL | 个别 OOM/cold-pull 工作 | 持续 scheduler/Production 前完成资源与背压测试 |
| 产品输出与推荐正确性 | DEFERRED_TO_GATE | Candidate/Formal/Lock 当前全部关闭 | EVAL-02B 证据链通过后另行产品决策，不由 canary 自动解锁 |

## 4. 门禁映射：不把所有视角提前到第一次 canary

### Gate A：一次人工前台、单执行者真实 canary

必须覆盖：

- T00-GOV、T00-SAFE 中所有 `MUST_FIX_FOR_CANARY`；
- Provider 调用、ledger、raw、capture、lineup event、v2、五态、pair 的正增量和 lineage；
- 目标 fixture/window 的最小时序证明；
- 五态、exact pair 等本次产物的冻结数学合同；
- 失败立即停止、留痕、禁止自动重试；
- 前台直连，不使用 persistent scheduler/Celery。

Gate A 不等价于：

```text
完整模型数学正确性签字
持续 scheduler 就绪
多联赛并发就绪
Candidate/Formal/Lock/Production 就绪
完整灾备或生产安全签字
```

### Gate B：持续 scheduler / 多联赛

增加：

- 全路径时序语义；
- progress/freshness/queue/worker 可观测性；
- Celery 交付语义；
- 长任务 lease/fencing；
- 多 run/multi-competition quota；
- cold-pull、资源、背压和自动恢复。

### Gate C：Candidate / Formal / Lock

增加：

- EV、五态、结算、CLV、校准的独立 oracle/recalculation；
- 数据集、样本选择和时间切分正确性；
- 产品阈值、guardrail 和回滚；
- 每个能力独立授权。

### Gate D：Production

增加：

- 密钥、日志、权限、供应链；
- 备份恢复与灾备演练；
- 长期 soak、资源容量和告警；
- 独立安全与运营签字。

## 5. 所有新任务/PR 的跨视角验收模板

每个任务必须在 PR 描述和验收证据中回答；`不适用` 必须写理由。

### A. 权威与边界

1. 本任务触及哪些事实来源、读写权威、fallback 或重复路径？
2. 是否新增第二套状态、表、配置、writer 或计算权威？
3. 身份、task key、policy scope、DB scope 是否一致？

### B. 失败与空数据

4. 每个外部调用、花钱点和业务写入点，失败前/失败后分别会怎样？
5. 缺失、空、非法、陈旧、未知输入返回什么？是否可能被当作成功？
6. 是否存在 broad catch、`pass`、rollback-and-continue、`return []/0/None` 或 diagnostic-only？为什么安全？

### C. 幂等、重放和并发

7. 重复执行如何证明 exact replay？
8. 冲突重放如何显式拒绝？
9. 两个并发执行者、锁缺失、锁过期、旧 owner 晚到时会怎样？

### D. 数据与时间正确性

10. 业务计算不变量是什么？是否有独立 oracle、golden vector 或反向计算？
11. `capture_at`、as-of、kickoff、football day、timezone、freshness 如何约束？
12. 该变更是否可能让“链路通了但值算错/时间配错”？

### E. 安全、可观测性与恢复

13. 凭据、日志、错误信息和 DB 权限是否最小化且脱敏？
14. 失败如何被机器检测，是否可能健康检查假绿？
15. 回滚、恢复、部分成功和证据保留策略是什么？

## 6. 指标

不得再用“发现问题数量少”作为健康指标。使用：

```text
严重度
发现阶段（设计/代码审查/CI/离线演练/canary/staging/production）
同类问题复发率
未分类 finding 数
风险视角覆盖状态
失败被检测到的时间
生产前发现率
```

正向目标是把 Critical 尽量提前到设计、代码审查、T00 或离线演练，而不是为了数字好看而减少报告。

## 7. 当前执行顺序不变

```text
GitHub local sync
-> T00-GOV
-> T00-SAFE R1-R4
-> trusted-main C9 rebuild
-> Gate A canary blockers
-> fake-Provider offline rehearsal
-> independent second review
-> human canary authorization decision
```

本登记表是治理和未来门禁地图，不授权真实 Provider、scheduler、Candidate、Formal、Lock 或 Production。
