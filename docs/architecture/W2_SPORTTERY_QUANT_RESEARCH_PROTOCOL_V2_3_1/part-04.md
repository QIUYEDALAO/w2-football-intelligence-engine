---

## 11. 本协议明确不做
```text
不建设 Portfolio Builder ｜ Phase A 不启用 2×1
不用 L4 数字判断策略优劣 ｜ 不用复利曲线判断信号
不修改现有 V4 推荐链 / Scheduler / Dashboard
不开启 Candidate/Formal/Lock/Production ｜ 不执行真实投注
不采信截图收益数字 ｜ 不以历史结果宣称 GO
不合并不同 version 样本 ｜ 不隐藏任何已注册版本
不给出固定的 PROVEN 时间承诺
```

## 12. 冻结身份清单
```text
原始 Excel SHA-256 ｜ 工作表名称与维度 ｜ 排除行 manifest SHA-256
Track 0 的 D/V split manifest SHA-256 ｜ 联赛制式归属表 SHA-256
竞彩↔API-Football 映射表 SHA-256 ｜ 球队别名表 SHA-256
解析代码 commit SHA ｜ 去水实现版本号 ｜ 序列化版本（须显式为 w2.canonical-json.v2）
本协议 SHA-256 ｜ bootstrap 随机种子 ｜ 运行环境锁文件 SHA-256
双源供应商条款存档 SHA-256
```

## 13. 签署

**Freeze A**
```text
项目方：______  GPT：______  Claude Code：______   日期：______
Q0 双源许可证据 SHA-256：______
Q14 成本确认（≈¥24/月 + 一次性 ¥90）：______
L1 上线时间（Forward 时钟起点，UTC）：______
```

**Freeze B**
```text
项目方：______  GPT：______  Claude Code：______   日期：______
Track 1 起止：______   映射表切换是否达标：______   Cycle 1 起点：______
```

---

# 14. ★ 工程边界与复用清单（新增，D4）

## 14.1 定位裁决

```text
重建独立项目            不采纳
直接改现有 V4 推荐链    不采纳
★ 同仓库 + 独立 bounded context + 旁路建设   采纳
```

**但"复用现有基础设施"的论证必须按实测重述**（依据 F31/F32，reality-checker 逐项验证）。

## 14.2 实测复用清单

| # | 能力 | 状态 | 关键证据 |
|---|---|---|---|
| 1 | Canonical serializer | **DEGRADED** | 至少 5 个独立实现，参数分歧（`ensure_ascii` True/False 不一）；实测同一输入产生不同 SHA-256。**注：v1 profile 的分歧是 SER-01 冻结的历史契约，非新缺陷** |
| 2 | SHA-256 身份 | ✅ **WIRED** | 身份列与唯一约束贯穿全库 |
| 3 | Raw payload store | **DEGRADED** | `RawPayloadStore` 是内存 dict 且无生产调用者；真正落库的 `RawPayloadModel` 读路径已接，**写路径只在未部署的 scheduler 下运行** |
| 4 | Fixture / team identity | ✅ **WIRED** | `canonical_teams` + `uq_canonical_team_identity_hash`（迁移 0033）；`matchday_fixture_identities`（0032） |
| 5 | PostgreSQL + Alembic | ✅ **WIRED** | 45 个迁移，CI 有 `upgrade → downgrade -1 → upgrade` |
| 6 | 幂等 / 冲突检测 | WIRED **但无调度器** | `outcome_ledger_repository` 按 `business_key` 比对 `payload_sha256`，冲突抛 `LEDGER_IMPORT_IDENTITY_CONFLICT` |
| 7 | 离线 replay | **PRESENT_UNWIRED** | src/apps 无调用者 |
| 8 | 结果账本与结算 | WIRED **但无调度器** | 读路径可达 |
| 9 | CI / 镜像 / 部署 / 回滚 | **DEGRADED** | CI 强（路径感知、digest 锁定、构建后 smoke、`trap rollback ERR`）；但**CI 无部署 job，部署是手工 systemd**；**两份 Dockerfile 分歧**（CI 推的是非 root + `--no-dev` + healthcheck，本地 compose 构建的是 root + 全量 dev 依赖 + 无 healthcheck） |
| 10 | API-Football 接入 | **DEGRADED** | `ApiFootballClient.fetch()` 无条件 raise；可用路径是 `request_live()`，但被 `W2_PROVIDER_CALLS_DISABLED: "true"` 在**所有已提交环境**里关掉 |
| 11 | xG / 比分矩阵 | **DEGRADED + UNWIRED** | `dixon_coles_rho = 0.0` 且 config 零供给 → τ 为恒等函数；`predict_score_matrix` / `one_x_two_from_matrix` 零生产调用者，生产用的是私有副本 `_poisson_score_matrix`；xG 读取包在 `except Exception: return []` 里，源表由已死的 backfill 写 |
| 12 | Secret 扫描 | **不在本协议范围** | 由项目方另行处置，本协议不涉及 |

**11 项工程能力中，真正 WIRED 且有活触发的：3 项（#2 / #4 / #5）。**

## 14.3 ★ 结构性事实：调度器从未部署

```text
infra/systemd/w2-staging.service:38   up -d --remove-orphans api worker web   ← 无 scheduler
deploy_stage7h_staging.sh:120         断言「scheduler 运行数 = 0」为部署成功条件
apps/worker/celery_app.py             无 beat_schedule / crontab
```

**worker 注册了任务但无派发器。整条 ingestion / refresh / ledger 写入链从无实时触发。**

## 14.4 新子系统必须自建的（不可复用）

```text
schema 隔离与角色权限   45 个迁移中 CREATE SCHEMA/GRANT/CREATE ROLE 零命中（F32）
                        一库一角色（w2_user 即 owner）→ 默认拿到全库 DDL/DML 权限
per-consumer 配额治理   provider control 是模块级 env 读取，无 consumer 作用域
                        两个进程各自独立执行 tick_hard_cap → 无共享上限，同烧上游配额
                        Redis 去重闸只按 task_key → 新消费者需手工设计不冲突前缀，
                        否则会静默压制现有 scheduler 的任务（DUPLICATE_TASK_KEY_SUPPRESSED）
竞彩市场身份            match_id / 场次编号 / HAD-HHAD / goal_line / SP / sellStatus
                        poolStatus / cbtSingle / cbtAllUp
Capture Schedule 与 entry/close 快照合同
供应商修订链
Append-only Signal Ledger
AS-OF / Post-event 视图级隔离
竞彩 ↔ API-Football 映射表（§5.2）
Track 1 数据质量报表
```

## 14.5 代码与数据组织（冻结）

```text
src/w2/quant_research/
    domain/ ｜ ingestion/ ｜ adapters/ ｜ ledger/ ｜ asof/ ｜ post_event/
    data_quality/ ｜ replay/ ｜ queries/ ｜ mapping/
scripts/quant/
    import_historical_excel.py ｜ bootstrap_mapping.py
    replay_capture.py ｜ build_data_quality_report.py

★ 禁止放入：src/w2/prematch/ ｜ src/w2/strategy/ ｜ RecommendationDecisionV4
             现有 future-refresh 业务链
```

**数据库：**
```text
同一 PostgreSQL 集群 + 独立 quant_research schema + 独立角色（★ 全部新建）
  quant_ingest_role        只能追加 capture 与 ledger
  quant_asof_reader_role   只能读 AS_OF_SIGNAL_VIEW
  quant_postevent_role     只能追加 close / 赛果 / 赛后指标
  现有 W2 生产服务          默认无权写 quant_research
```

**序列化：**
```text
★ 新子系统必须显式指定 w2.canonical-json.v2
  不得「import 那个 canonical serializer」——存在 5 个分歧实现（#1）
  竞彩数据全为中文队名，ensure_ascii 分歧必然触发哈希不一致
```

## 14.6 与现有系统的边界

```text
同仓库 ｜ 新模块 ｜ 新 schema ｜ 新角色 ｜ 新采集进程
旧推荐链零修改 ｜ 旧生产运行零影响
不得修改现有 Scheduler 的 Provider allowlist
新 collector 必须有自己的：开关 ｜ 额度 ｜ allowlist ｜ Capture Schedule ｜ 数据库角色
                          ★ 以及不与现有 scheduler 冲突的 Redis task_key 前缀
```

**页面**：Freeze A 阶段不建 Quant Dashboard，只出本地静态数据质量报告。未来分 `/dashboard`（现有）与 `/quant`（量化）两个入口。

## 14.7 ★ 新 collector 必须避开的既有陷阱

```text
静默失效的开关依赖链
   apps/scheduler/main.py:66  market_timeline_refresh_enabled() 需先满足
                              future_fixture_refresh_enabled()
   compose.staging.yml:208    W2_MARKET_TIMELINE_REFRESH_ENABLED = "true"
   compose.staging.yml:207    W2_FUTURE_FIXTURE_REFRESH_ENABLED  = "false"
   → 特意打开的开关静默无效；同一陷阱还卡住 xg_history_backfill_enabled()
   → staging-lite 的 scheduler healthcheck 断言的契约永远不可能通过
```

**对新子系统的约束（冻结）：**
```text
quant collector 的每个开关必须是独立布尔，不得依赖另一个开关为真
每个开关必须有对应的 EFFECTIVE_STATE 日志行，启动时打印实际生效值
healthcheck 断言的契约必须在开关关闭时也能通过（否则容器永远不健康）
```

## 14.8 运行依赖（可用性，非安全）

```text
API-Football 订阅有效期是 L1 的硬依赖：
    订阅失效 → Pinnacle 侧全部断供 → ③ 无法计算 → Phase A 停摆
Freeze A 须记录：订阅到期日 ｜ 续费责任人 ｜ 到期前告警提前量
Track 1 必须包含一条 SOURCE_AVAILABILITY 检查：每日确认两源均返回 200
```

---

**Freeze A 候选版 v2.3.1 结束。**
