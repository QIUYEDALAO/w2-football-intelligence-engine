# W2 审计视角登记表与跨视角验收模板

> 本文件管理“哪些视角已经审过、哪些只是局部覆盖、哪些尚未形成独立证据”。
>
> 它不推翻已完成的架构收敛，也不把 Production 全量审计提前塞进第一次真实 canary。
>
> 当前执行权威：GitHub Issue #454 v4  
> workflow 治理事件：Issue #455  
> 计算权威唯一性：Issue #456

---

# 1. 方法：清单法与生成法并用

```text
清单法：已知问题 -> 实现 -> 验收 -> 关闭
生成法：风险规则 × 全仓路径/副作用点/失败时机/计算入口 -> 生成未知实例
```

严格验收可以证明“实现符合当前规格”，但不能自动证明“规格已经提出全部重要问题”。一个视角完成不能扩大成系统整体完成。

当前生成式任务：

- **T00-GOV**：workflow、run、commit、push 和分支来源；
- **T00-SAFE**：R1–R5 五个风险家族；
- **T00-R5 资产唯一性**：存储资产与计算权威的可重复 inventory。

本登记表必须由真实事故、异常、canary 失败和独立审计推动增长，不能成为第二份静态清单。

---

# 2. 已核实时间线：C1–C11 不是架构清单返工

以下结论基于 GitHub commit 与代码，不以状态自述为证据。

| 风险 | 最迟已存在/引入 | GitHub 证据 | 裁决 |
|---|---|---|---|
| C7 broad exception retry / uncertain delivery | 2026-06-23 | `8e467e657836641975294aeea12066cc125307f7` | 明确早于收敛 |
| C5 DB 模式绕过运行锁 | 2026-06-25 | `5e46a8bfa946fad018df2276e7dadf0d78ce2979` | 明确早于收敛 |
| C1 Provider 熔断缺失时允许 | 2026-07-03 | `97978194ba577efebc1d9f12c17d92e15cc5b4b2` | 明确早于收敛 |
| C6 request/quota ledger 分事务 | 2026-07-03 | 同 `97978194...` | 明确早于收敛 |
| C11-A request ledger 吞 `IntegrityError` | 2026-07-03 | 同 `97978194...` | 明确早于收敛 |
| C11-B quota evidence 缺失时静默不更新 | 2026-07-05 | `ac17e8753726d172a5c82a5356594f8019271821` | 与 C11-A 来源不同；早于收敛 |
| C9 raw 已保存但 lineup 后续链可缺失 | 2026-07-19 前后 | `d460055b48005fa58ec6f01e555db80a71fb966e` | 根问题早于收敛 |
| C2/C3/C4 | 至迟 2026-07-22 | `09ca14a969b835314c93c122b80c3cfa1bbf9c6c` 基线 | 启动清单时已存在 |
| C8 schema/异常空数据降级 | 至迟 2026-07-22 | 同一基线 | 启动清单时已存在 |
| C10 scheduler `restart: unless-stopped` | 至迟 2026-07-22 | 同一基线 Compose | 启动清单时已存在 |
| 架构收敛主清单建立 | 2026-07-22 | `09ca14a969b835314c93c122b80c3cfa1bbf9c6c` | 晚于上述出生点 |

准确裁决：

```text
ARCHITECTURE_CONVERGENCE_SCOPE_REMAINS_VALID
NO_EVIDENCE_C1_TO_C11_WERE_CREATED_BY_ARCHITECTURE_CONVERGENCE
```

禁止扩大成未经证明的全称命题“架构收敛没有引入任何其他缺陷”。

---

# 3. 风险家族

## R1 — Default allow / missing authority

缺失、非法、陈旧、未知或不可验证的安全输入却继续执行。

## R2 — Silent failure / failure downgrade

异常被 `pass`、broad catch、rollback-and-continue、diagnostic-only 或成功退出码隐藏。

## R3 — External side effect / local-state non-atomicity

Provider 可能已计费，但 ledger、quota、raw、capture 或业务阶段未形成可对账状态。

## R4 — Authority split / concurrency / identity drift

CLI/policy、task key/scope、check/lock、SELECT/INSERT 或多个 current authority 之间缺少原子约束。

## R5 — Computation authority split

同一个业务事实、身份哈希、市场分类、赔率或评分公式存在多个算法实现；或不同业务定义使用相同名称而没有明确版本和边界。

R5 已发现：

- canonical JSON/hash serialization 参数分裂；
- fair odds 的 float/Decimal 与舍入分裂；
- canonical market taxonomy 多实现；
- Brier/ECE 多实现；
- odds parsing/representation 多实现；
- read-model 同名类职责分裂；
- 历史 migration 依赖当前 ORM metadata。

详细证据：

- `docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`
- GitHub Issue #456

---

# 4. 当前审计视角登记

状态：

```text
COMPLETE              冻结范围已完成并独立验收
IN_PROGRESS           正在生成式清点
PARTIAL                有局部合同/测试，无全系统独立覆盖
NOT_AUDITED            尚无足够证据
DEFERRED_TO_GATE       已明确关闭门禁
SELF_REVIEWED_ONLY     只有实现同源测试/自查，不能算独立关闭
```

| 视角 | 状态 | 独立性/现有证据 | 未覆盖与关闭门禁 |
|---|---|---|---|
| 架构、存储权威、重复路径、读写边界 | COMPLETE（冻结范围） | P0/P1/P2、CI、staging 与最终架构验收；资产审计未发现已删除表/目录残留 | 不因 C1–C11 重开；T00-R5 复现存储 inventory |
| 动态失败、缺失输入、并发、计费一致性 | IN_PROGRESS | 独立终审、C1–C11、T00 R1–R4 | Gate A 关闭 `MUST_FIX_FOR_CANARY` |
| workflow、分支来源与供应链治理 | IN_PROGRESS | #455、PR #453 quarantine；历史 run/log 尚待归零 | 可信实现前关闭 |
| **计算权威唯一性** | **IN_PROGRESS** | 资产唯一性首审；#456；canonical serializer Critical | canonical serialization 在 Gate A；其余公式/分类在 Gate C |
| 数据与数学正确性 | PARTIAL / SELF_REVIEWED_ONLY | 五态、settlement、CLV、EVAL-01 测试多与实现同源 | Gate C 独立 oracle/recalculation |
| 时间与时序语义 | PARTIAL | `capture_at`、部分 timezone/checkpoint/idempotency | Gate A 目标链最小证明；Gate B 全路径审计 |
| 安全、权限、密钥、日志暴露 | PARTIAL / NOT FULLY AUDITED | 局部 secret scan、脱敏与容器配置 | Gate D；canary 使用隔离最小权限 |
| 恢复、备份和灾备 | NOT_AUDITED / UNVERIFIED | 历史文档不证明真实恢复 | Gate D 真实恢复演练 |
| 可观测性与告警 | PARTIAL | 基础 readiness；已发现 collection 假绿 | Gate B progress/freshness/ledger health |
| 性能与资源耗尽 | PARTIAL | 个别 OOM/cold-pull 工作 | Gate B/D 容量与背压 |
| 产品输出与推荐正确性 | DEFERRED_TO_GATE | Candidate/Formal/Lock 全关闭 | Gate C 独立产品验收 |

### 计算权威首审的边界

当前可接受表述：

```text
STORAGE_ASSET_RESIDUALS = NO_CURRENT_EVIDENCE
KNOWN_RUNTIME_CANONICAL_SERIALIZERS >= 6
DEFINITIVE_R5_IMPLEMENTATION_COUNTS = PENDING_T00_R5
```

人工报告中的“6、4、2”等是已知起点，不是最终分母。

---

# 5. 登记表自扩展与 reviewer 轮换

## 5.1 现实事件驱动增长

每个事故、异常、canary 失败、staging/production 偏差或新 finding 必须回答：

```text
哪个登记视角本应抓到它？
```

规则：

1. 已有视角可覆盖：更新证据、覆盖边界、遗漏原因和关闭门禁；
2. 无视角可覆盖：同一整改中新增视角；
3. 新视角必须有生成规则、owner、独立 reviewer、关闭门禁和最小证据；
4. 未完成映射不得关闭任务/事故；
5. 禁止以“其他/综合风险”掩盖新视角。

最低输出：

```text
INCIDENT_PERSPECTIVE_MAPPED = true
MAPPED_PERSPECTIVE = <registry row>
NEW_PERSPECTIVE_REQUIRED = true|false
REGISTRY_UPDATED = true
UNMAPPED_PERSPECTIVE = 0
```

R5 正是由资产唯一性审计新增的视角实例。

## 5.2 reviewer 轮换

- 实现作者不能是独立关闭的唯一 reviewer；
- T00-GOV、T00 R1–R5、Gate A/B/C/D 均记录独立 reviewer；
- 重大审计尽量更换 reviewer 或问题框架；
- 无独立 reviewer 只能标 `SELF_REVIEWED_ONLY` / `PARTIAL`。

最低记录：

```text
IMPLEMENTER
PRIMARY_REVIEWER
REVIEWER_INDEPENDENT_OF_IMPLEMENTATION
PERSPECTIVE_USED
NEW_PERSPECTIVE_ADDED
```

---

# 6. 事故型紧急修复的事后跨视角复查

事故/hotfix 可以先止血，但正常路径恢复后只能标：

```text
CONTAINED_PENDING_POST_INCIDENT_REVIEW
```

最终关闭前至少复查 R1–R4；如果触及 hash、公式、分类、精度或 identity，同时复查 R5；若触及数据、时间、安全、恢复或可观测性，再加入对应视角。

最终要求：

```text
POST_INCIDENT_R1_REVIEW = PASS
POST_INCIDENT_R2_REVIEW = PASS
POST_INCIDENT_R3_REVIEW = PASS
POST_INCIDENT_R4_REVIEW = PASS
POST_INCIDENT_R5_REVIEW = PASS|NOT_APPLICABLE_WITH_REASON
UNCLASSIFIED_POST_INCIDENT_FINDINGS = 0
REGRESSION_GUARDS_ADDED = true
PERSPECTIVE_REGISTRY_UPDATED = true
INDEPENDENT_REVIEW_COMPLETE = true
```

`97978194...` 同时引入 C1、C6、C11-A，是紧急修复需要事后复查的仓库内证据。

---

# 7. Gate 映射

## Gate A — 一次人工前台、单执行者 canary

必须覆盖：

- T00-GOV；
- T00 R1–R5 中所有 `MUST_FIX_FOR_CANARY`；
- #456 canonical serialization authority、版本化合同、迁移兼容；
- Provider→ledger→raw→capture→lineup→v2→五态→pair 正增量和 lineage；
- 目标 fixture/window 最小时序证明；
- 本次五态与 pair 的冻结数学合同；
- 失败停机、留痕、禁止自动重试；
- foreground direct path，不使用 persistent scheduler/Celery。

Gate A 不等价于：

```text
完整数学正确性签字
持续 scheduler 就绪
多联赛并发就绪
Candidate/Formal/Lock/Production 就绪
完整灾备或生产安全签字
```

## Gate B — 持续 scheduler / 多联赛

增加：全路径时序、progress/freshness/queue/worker、Celery、长 lease/fencing、多 run quota、资源/背压和自动恢复。

## Gate C — Candidate / Formal / Lock

增加：

- fair odds / decimal odds 唯一权威；
- canonical market taxonomy；
- Brier/ECE 和其他评分公式的唯一权威或明确版本；
- EV、五态、结算、CLV、校准的独立 oracle；
- 数据集、样本选择和时间切分；
- 产品阈值、guardrail、回滚和独立授权。

## Gate D — Production

增加：密钥/日志/权限/供应链、migration replay、备份恢复/灾备、长期 soak、容量和独立安全运营签字。

---

# 8. 所有新任务/PR 的跨视角验收模板

`不适用` 必须写理由。

## A. 权威与资产

1. 触及哪些事实来源、表、文件、配置、writer、reader 或 fallback？
2. 是否新增第二套状态/存储权威？
3. 是否新增第二套**计算权威**、hash serializer、taxonomy 或公式入口？
4. 同概念现有实现数、目标 authority 和迁移计划是什么？

## B. 失败与空数据

5. 每个外部调用、花钱点和业务写入，失败前/失败后分别怎样？
6. 缺失、空、非法、陈旧、未知输入返回什么？
7. broad catch、`pass`、rollback-and-continue、`return []/0/None` 是否存在？为何安全？

## C. 幂等、重放与并发

8. exact replay 如何证明？冲突 replay 如何拒绝？
9. 两个执行者、无锁、锁过期、旧 owner 晚到时怎样？

## D. 计算、数据与时间

10. 业务计算不变量是什么？权威实现在哪里？
11. 是否有与生产 helper 分离的 oracle/golden vector？
12. 类型、精度、舍入、NaN/Infinity、Unicode 和版本策略是什么？
13. `capture_at`、as-of、kickoff、football day、timezone、freshness 如何约束？
14. 是否可能“链路通了但值算错/时间配错/hash 复算不一致”？

## E. 安全、可观测性与恢复

15. 凭据、日志、错误和 DB 权限是否最小化/脱敏？
16. 失败如何被机器发现，是否健康检查假绿？
17. 回滚、迁移、部分成功、证据保留和恢复策略是什么？

## F. 视角与 reviewer

18. 哪个登记视角本应抓到本任务/事故？是否新增视角？
19. 实现者和独立 reviewer 是谁？
20. 完成声明覆盖哪些视角，明确不覆盖哪些视角？
21. 若为事故型修复，R1–R5 事后复查如何处理？

---

# 9. 健康度指标

不使用“发现问题数量少”衡量健康度。使用：

```text
严重度
发现阶段
同类问题复发率
未分类 finding 数
未映射视角数
计算 authority 数与未版本化 writer 数
风险视角覆盖状态
失败检测延迟
生产前发现率
```

---

# 10. 当前执行顺序

```text
GitHub local trusted sync
-> T00-GOV
-> T00-SAFE R1-R5 + asset inventory
-> canonical serialization authority/versioned migration
-> trusted-main C9 rebuild
-> remaining Gate A canary blockers
-> fake-Provider offline rehearsal
-> independent second review
-> human canary authorization decision
```

本登记表不授权真实 Provider、scheduler、Candidate、Formal、Lock 或 Production。
