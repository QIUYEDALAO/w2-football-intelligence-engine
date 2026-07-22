# AH / OU / LMM 离线与影子证据 canary（2026-07-20）

## 范围与结论

本轮仅建设 AH、OU 与 LMM 的离线/影子验证证据。没有改动 Dashboard
组件、文案、CSS、布局、路由或信息架构；没有开启正式推荐、锁单、production
或任何 LMM 数值调整。

结论：**canary PASS（采集路径已上线，正式能力仍关闭）**。

当前没有可作为新 shadow 样本的完整赛前卡，因而尚未产生可用于门槛判断的
真实 AH/OU outcome；这不是失败，更不是建议开启能力。后续仅由正常 staging
刷新形成 shadow 记录和赛后结算。

## 交付的最小变更

- `e470c4d`：为同线、双边完整的 OU 盘口生成独立影子 pick，并令 shadow CLV
  能聚合 TOTALS；AH 与 OU 均带 `shadow=true`、`not_a_recommendation=true`、
  `not_displayed=true`。
- `01e641b`：修复 V3 `NO_EDGE`/`NOT_READY` 卡片没有 canonical pick 时跳过
  shadow 采集的缺口；任何标记为 shadow 的 pick 都优先归入 `SHADOW` scope，
  不会误进入验证或正式 scope。
- 同线约束不变：OU 必须有同一盘口线、双边价格均大于 1 且模型公平线与市场线
  存在差异；跨线 OU 继续拒绝采集。

没有改变因子、模型阈值、方向、canonical performance cohort 或 LMM 数值。

## 本地门禁

| 检查 | 结果 |
| --- | --- |
| 影子 ledger 定向单元测试 | 17 passed |
| 完整 pytest | 1266 passed，4 个既有环境 skip |
| Ruff | PASS |
| Mypy（243 source files） | PASS |
| Web typecheck / build | PASS |
| 既有 Playwright | 9 passed |
| `git diff 8deee24..01e641b -- apps/web` | 无输出（未改 UI） |

新增回归覆盖：V3 `NO_EDGE` 卡可生成独立 AH + OU `SHADOW` 记录，且即便页面
级别是 `ANALYSIS_PICK`，也绝不变为 `VALIDATION`/`OFFICIAL`；跨线 OU 继续
不产生记录。

## staging canary

- release / API / Web SHA：`01e641b5a2812b783e989b15144e668283a6a0fb`，一致。
- `/health`：PASS；`/ready`：READY；Alembic current/head：
  `0024_create_lineup_intelligence`。
- api、web、worker、scheduler、postgres、redis：均 healthy；restart count 均为
  0；`OOMKilled=false`。
- 容器日志在部署窗口未发现 error、exception、traceback、OOM 或 restart。
- 磁盘基线：97G / 118G（85%）；作为容量风险记录，未在本轮清理或变更。
- canonical cohort：eligible=16、excluded=7、recovered=4、pending=0，部署前后
  未变化。

### 只读采集演练

在 API 容器执行 `run_w2_forward_outcome_ledger.py --window all --dry-run --json`：

- `provider_calls=0`
- `db_writes=0`
- `lock_capture_write=false`
- `settlement_write=false`
- 当前可读记录 68，`shadow_count=0`，`formal_or_validation_count=0`

`shadow_count=0` 的原因是当时 68 个 future 卡均为盘口/模型不完整的 `BLOCKED`
状态，不能以不完整数据制造样本。代码路径由新增的 V3 回归测试覆盖；未来正常
刷新获得完整同线行情后才会产生 shadow 记录。

## 能力状态（保持关闭）

| 能力 | 状态 |
| --- | --- |
| AH 正式推荐 | 关闭 |
| OU 正式推荐 | 关闭（仍为 NOT_IMPLEMENTED） |
| AH / OU LMM 数值调整 | 关闭，数值仍为 0 |
| 锁单 | 关闭 |
| production 推荐 | 关闭 |

现有 LMM 离线评估仍因没有 versioned Transfermarkt 历史输入、球员 identity mapping
与可 as-of join 的估值而处于 `INSUFFICIENT_EVIDENCE`。本轮没有请求 provider，
也没有导入、回填或伪造历史数据。

## 后续门槛

不会因本次 canary 自动打开任何能力。需要先积累满足既有协议的、可赛后结算的
同线 AH/OU shadow 样本，并完成 LMM 离线数据的可追溯导入与评估；届时以协议中
既有门槛判断是否提出单独的开启建议。
