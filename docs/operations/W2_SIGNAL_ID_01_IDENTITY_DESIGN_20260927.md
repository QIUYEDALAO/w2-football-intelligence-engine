# SIGNAL-ID-01 多策略身份与账本设计（离线设计，未实施）

状态：离线设计文档，只写设计不写生产。未执行 migration、未接 shadow 写入、未接通知。停点待 Owner 总验收。

来源：计划书 v3.2 第 8 节；对照现有代码 `src/w2/tracking/forward_evidence.py`、`src/w2/infrastructure/persistence/forward_evidence_models.py`、`src/w2/prematch/candidate_notifications.py`、`src/w2/api/repository.py`。

---

## 1. 问题陈述：现有唯一约束挡不住多策略共存

现有 fade 账本 `recommendation_review_ledger`：

- 主键 `review_event_id` = `canonical_sha256(payload)`（内容寻址，天然幂等）。
- **唯一约束 `uq_review_evaluation_event` = `evaluation_id × event_type`**。
- `event_type` ∈ {`EVALUATION_SNAPSHOT`, `DECISION_SNAPSHOT`, `SETTLEMENT_OBSERVED`}。
- 推送与结算均按 `evaluation_id` 匹配，且 `candidate_kind == "TRACK_D_FADE"` 才走 fade 结算（`settle_track_d_validation_signals_in_session`）。

DA-FADE-02 新 fade 与旧全量 fade 会对**同一个 UNDER 评估（evaluation_id）**各产生一条 OVER 反转信号。若仍写进 `recommendation_review_ledger`，`evaluation_id × event_type` 唯一约束会冲突。**因此不能只改 `candidate_kind` 或 `payload`**，必须引入独立的 `signal_identity` 作为新策略的幂等键。

---

## 2. signal_identity 设计

`signal_identity` 用**现有 canonical authority**（`canonical_sha256`，`HashDomain.PREMATCH_READ_MODEL_GENERIC`）对业务事实构建，禁止第二套序列化器。构建输入（与 v3.2 8.1 对齐）：

| 字段 | 来源 |
|---|---|
| `source_evaluation_id` | 来源评估（旧模型 UNDER 评估）的 evaluation_id |
| `forecast_capture_identity` | `model_forecast_capture_identity_hash` |
| `model_identity` / `parameter_identity` / `input_manifest_identity` | 冻结模型与参数、`model_input_manifest_hash` |
| `strategy_id` / `strategy_version` / `preregistration_sha256` / `cohort_id` | 新策略身份（DA-FADE-02） |
| `prediction_cutoff` / `quote_pair_identity` / `channel_quote_identity` | 预测截点、报价对身份、渠道报价身份 |
| `direction` / `exact_line` | OVER 反转、冻结半球线 |

规则：策略选择状态由预测时点事实固化；推送结果是后续独立事件，不进入 signal_identity。

---

## 3. 幂等规则

新策略信号采用**独立 append-only 合同**，幂等键为：

```text
signal_identity × event_type × revision
```

- `event_type` 沿用 `DECISION_SNAPSHOT` / `SETTLEMENT_OBSERVED`（或同义新枚举）。
- `revision` 处理同源追加/修正（晚到结果、重算），保留原稿不覆盖。
- 通过外键/端口关联原 `evaluation_id`，但**不受 `uq_review_evaluation_event` 约束**（旧 evaluation 与旧账本原样保留）。

落表形态（最小兼容设计二选一，实施前定）：
1. 扩展表（独立 signal 表 + `source_evaluation_id` 外键）；或
2. 现有表加 `signal_identity` 列并放宽唯一约束。
最终形态由「多策略共存、无双重推送/结算、旧读路径可用、重放一致」四项验证决定。

---

## 4. 现有路径逐项验证（不改，只验证）

| 路径 | 现状 | 兼容要求 |
|---|---|---|
| 唯一约束 | `uq_review_evaluation_event`（evaluation_id × event_type） | 新信号走独立 signal 表/键，不触碰该约束；旧行不动 |
| 旧读路径 | `api/repository.py:3271` 按 `candidate_kind=="TRACK_D_FADE"` 读取 | 旧 fade 读路径不变；新信号用 `strategy_id` 区分，不改变旧消费者 |
| 结算路径 | `settle_track_d_validation_signals_in_session` 按 `evaluation_id` 匹配 DECISION→SETTLEMENT | 新信号按 `signal_identity` 匹配结算，**不进入旧结算扫描**，避免对同一 evaluation 双重结算 |
| 推送路径 | `candidate_notifications.py:1047` `VALIDATION_SIGNAL_REQUIRES_TRACK_D_FADE` | 新信号推送资格独立判断（push_eligible / push_suppression_reason），不借用旧水印 |

关键：旧全量 fade 与新子集是嵌套比赛集合，不计为独立样本；未推送子集只是策略状态，不伪装成新模型。

---

## 5. 离线产物证明（实施 migration 前必须）

确认性研究初期只输出**冻结离线产物**，避免为了研究先改生产表。离线产物须证明四项：

1. **共存**：同一 evaluation 的旧 fade 信号与新 DA-FADE-02 信号同时存在，互不覆盖。
2. **重放**：同一输入重放产生相同 signal_identity 与相同事件，幂等。
3. **无双重结算**：同一 signal_identity 只结算一次；旧结算与新结算路径对同一业务事实不重复计。
4. **旧读路径可用**：旧消费者（dashboard/报表）读取旧账本不受影响。

---

## 6. 工程交付边界（另行授权，不随本设计推定）

以下均列为**单独工程交付**，本草案不推定已获生产写权限：

- migration（新表/列 + 唯一约束调整）。
- shadow 生产写入。
- 通知接入。
- 任何生产部署。

---

## 7. 过渡规则

- 新协议批准且登记生效前：旧 fade 参数、验证水印、正式推荐隔离、推送规则及密封规则按现行授权继续。
- 新 cohort 起点 = 协议冻结 + 实现身份固定 + 预测实际开始落盘（三者同时满足）；不能只写较早 T0 追认未固化预测。
- 跨协议数据移动列明来源与角色；已用于选规则或已查看的数据不能重新标为独立确认集。

## 停点

待 Owner 总验收。未实施任何代码/数据改动。
