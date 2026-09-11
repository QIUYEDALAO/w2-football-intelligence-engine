# ALLSV-RESTORE-01 恢复 Gate

Status: `BLOCKED_BEFORE_DECISION_A`

Owner 只批准恢复 `allsvenskan` 的范围；这不是部署、Provider 回补或生产写入授权。`chinese_super_league` 必须保持 disabled。

## 尺度限定

5 场成熟样本中 `5/5` 返回两队 numeric xG，且 4 场由旧 null 恢复，只能证伪“旧 null 永久”这一机制命题。不得据此估计长期覆盖率。恢复后以滚动 30 日已完赛覆盖率实测；低于既有 `70%` 健康线立即进入回退决策，不继续推荐链验收。

## 严格顺序

1. **Decision A — 部署基础修复**：部署 null 可重试、首次可见证据不覆写，以及动态读取 `league_season.payload.enabled` 的 `w2-xg-refresh`。验收必须证明中超仍 disabled、刷新脚本无固定联赛名或数量。
2. **Decision B — 受控回补**：只对 `allsvenskan` 运行一次显式范围回补；记录 Provider 额度前后、调用数、写入数、失败项。回补完成后只读计算近 30 日覆盖和最新 xG。
3. **健康 Gate**：覆盖率 `>=70%`，最新 xG kickoff 距执行时 `<=7d`。当前生产为 `2/16=12.5%`，Gate 失败。
4. **容量 Gate**：SCHED-DEDUP-01 完成并给出恢复瑞超增量后的容量证据。`concurrency=2` 只是 11 联赛止血值，不能代替该证据。
5. **Decision C — 启用与精确重开**：启用瑞超，并在同一事务只重开审批时冻结的 1296 条“未过期、状态为 SKIPPED_POLICY、blockers 精确等于单元素禁用 blocker”的计划。计划数或集合哈希漂移即失败并重新提交决策；28 条已过期计划永不重开。
6. **上线验收**：验证动态启用集合、30 日覆盖、新鲜度、正式推荐链、计划吞吐、看板/赛后口径；用冻结的可复现语料重新计算恢复后的 EV 缺口，不默认继承 65 注结论，也不宣称盈亏改善。

## Decision C 的强制输入

- `production_decision_id`
- Decision A 部署证据 SHA256
- Decision B 回补证据 SHA256
- SCHED-DEDUP-01 容量证据 SHA256
- `expected_reopen_plan_count=1296`
- `expected_reopen_plan_set_sha256=8998f5e00892a178ff29e3bbc9926267a616a5adaea1d73ce38c22f210bfd7de`

执行器只接受 `allsvenskan`，会先确认中超仍 disabled，并把实际重开的 plan IDs 写入 append-only readiness audit。任一输入缺失、格式错误或集合漂移都 fail-closed。

## 回退

若恢复后 30 日覆盖低于 70%、中超状态变化或正式链异常：先停止新 claim，单独取得回退决策；将瑞超重新 disabled，再依据本次 readiness audit 中的 `reopened_plan_ids` 只处理尚未执行且仍未过期的计划。不得改写已 CAPTURED、已结算、已过期或其他 blocker 的行。回退后重新验证看板范围与推荐链，并保留所有历史数据。
