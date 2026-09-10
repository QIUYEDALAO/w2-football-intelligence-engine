# F1P 前瞻 AH 因子数据合同

```text
TASK_ID        W2_AH_FACTOR_ACCURACY_F1P_FORWARD_CONTRACT_20260910
CONTRACT_ID    w2.forward_ah_factor_observation.v1
PARENT_COMMIT  71cffa8d4ab8e7a7d4a779cc91951c97f594a261
终态           FORWARD_CONTRACT_READY
```

## 0. 这是什么，不是什么

**是**：从今往后采集因子观测的离线数据合同与 append-only 参考实现。

**不是**：历史 148 场的补全。F1 已确认那 336 个单元 exact PIT 为 0，本合同
不改变、不触碰、也不试图绕过那个结论。

本合同**不产生任何模型权重、不产生任何推荐方向、不改变现役推荐链**。
即使终态为 `FORWARD_CONTRACT_READY`，也**不自动解锁** F2、F3、Provider 或 Shadow。

## 1. 逐场因子观测记录

一条记录 = 一个 `(evaluation_id, attempt_id, factor_id)` 的赛前事实。

```text
schema_version              w2.forward_ah_factor_observation.v1
evaluation_id / attempt_id / fixture_id
market                      恒为 ASIAN_HANDICAP
factor_id                   仅 F3_REST_FITNESS / F5_RECENT_AH_COVER / F6_H2H / F9_TRUE_XG
factor_version
factor_status               见 §5
signed_score                缺失时必须为 null，且状态必须是显式缺失状态
participated                布尔，必须与 status 一致
applied_weight              该次评估**实际采用**的权重
factor_inputs               赛前输入映射；出现任何赛果字段即拒绝
factor_input_hash / factor_verdict_hash / observation_id
source_capture_id / source_capture_sha256 / source_version
evidence_time_utc / evaluated_at_utc / created_at_utc
supersedes_observation_id   首版 null
revision_reason             首版 null；修订时必填
record_kind                 AS_OF_FACTOR_OBSERVATION
```

## 2. 严格 PIT

```text
evidence_time_utc < evaluated_at_utc        必须严格早于
```

- 一律 `datetime.fromisoformat()` 解析为 aware UTC 再比较，**禁止字符串比较**；
- **相等失败**：与评估同一瞬间才可得的事实，不是评估当时的知识；
- 晚于、缺失、空白、不可解析、**naive（无时区）** 全部 fail closed；
- **`created_at_utc` 不能证明 PIT**，它不在身份里（写入时间说明不了可知性）；
- 不得用 `result_available_at`、比赛结束时间或赛后页面代替 `evidence_time_utc`。

存储也按解析后的瞬间归一：同一瞬间的 `+09:00` 与 `Z` 两种写法存下来完全相同，
因此重复写入是真正的幂等，而不是"身份相同但字段不同"的假冲突。

## 3. 身份与哈希

**不新建第二套序列化器。** 复用 `src/w2/domain/canonical_serialization.py`
与 `w2.canonical-json.v2`；模块内不出现 `hashlib.sha256`（有测试断言）。

未新增 quant 专用 `HashDomain`——那要改生产模块。改为复用现有
`future_refresh.evidence`，并把 domain 字符串**显式写进 preimage**，
这样将来引入专用 domain 会是一次可见的身份变更，而不是静默变更。

```text
factor_input_hash   ← contract, hash_domain, serializer_version, evaluation_id,
                      attempt_id, fixture_id, market, factor_id, factor_version,
                      applied_weight, factor_inputs, evidence_time_utc,
                      source_capture_id, source_capture_sha256, source_version
factor_verdict_hash ← contract, hash_domain, factor_input_hash,
                      factor_status, participated, signed_score
observation_id      ← contract, hash_domain, factor_input_hash,
                      factor_verdict_hash, evaluated_at_utc,
                      supersedes_observation_id
```

数值一律以 canonical decimal 文本进入 preimage，不用浮点。
哈希必须是**小写 64 位十六进制**；大写、非十六进制、长度错误、
与 preimage 不一致，全部 fail closed。

**17 个受保护字段**任一变化都必须产生不同身份（逐字段参数化测试）。
`created_at_utc` **不在**受保护字段内，这是刻意的。

## 4. append-only 与版本链

- 已写入记录**不 UPDATE、不 DELETE**；
- 完全相同的重复写入是幂等 no-op，但必须**逐字段比较全部业务字段**后才认定；
- 同一 `observation_id` 而业务字段不一致 → `OBSERVATION_ID_BUSINESS_CONFLICT` 拒绝；
- 修订必须新建 `observation_id`，用 `supersedes_observation_id` 指向旧记录，
  且**必须给出 `revision_reason`**；
- supersedes 目标不存在 → 拒绝；**链上成环 → 拒绝**；
- 修订**不覆盖**旧行的 evidence_time、weight、score 或 source identity
  （测试断言修订后旧行仍逐字节在文件前缀里、且 readback 值不变）；
- readback 会**重新计算** canonical hash 并逐字段核对，磁盘被篡改即拒绝；
- 历史无因子身份的旧 payload 返回 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY`，
  且 `is_factor_admitted()` 对它恒为 `False`。

## 5. 因子状态与缺失

```text
PARTICIPATED                        参与计分，必须有 signed_score
INSUFFICIENT_DATA                   数据不足 —— 不是 signed_score = 0
SOURCE_UNAVAILABLE                  来源不可用 —— 不是中性因子
FACTOR_ADMISSION_FAILED             因子层拒绝
HISTORICAL_NO_FACTOR_VERDICT_IDENTITY  旧记录无裁决身份，永不视为通过
```

规则：

- 四种无分状态**携带任何 score（包括 0.0）即拒绝**；
- `PARTICIPATED` 而无 score 即拒绝；
- `participated` 布尔与 status 矛盾即拒绝；
- **缺 `applied_weight` 即拒绝，绝不回填当前注册表默认值**
  （模块源码内不出现任何默认权重常量，有测试扫描）；
- 缺因子身份的 AH 记录 fail closed；
- **TOTALS 报 `MARKET_OUT_OF_CONTRACT`，不是 AH 因子失败**——
  它只是不在本合同范围内。

## 6. AS-OF 与赛后隔离

```text
AS_OF_FACTOR_OBSERVATION   只放 evidence_time < evaluated_at 的赛前事实
POST_EVENT_ENRICHMENT      赛果、结算、赛后统计；独立文件、独立 kind
```

单向：赛后账本从不参与观测的构建。

- 赛果字段出现在 `factor_inputs` 里即拒绝（`POST_EVENT_FIELD_IN_FACTOR_INPUT`）；
- 赛后 enrichment 写入后，观测账本**逐字节不变**（测试实测）；
- AS-OF 视图不返回任何赛后字段；
- 无 PIT 证据的 snapshot 不能被当作正式观测——F1 里那种"早 68 小时、
  无绑定"的归档快照，在本合同下直接 `EVIDENCE_TIME_MISSING` 或 PIT 失败。

## 7. 迁移

本任务**不写生产库、不注册到现役迁移链**。若将来要落库，
建议的表形状与本合同一一对应（`observation_id` 主键、
`(evaluation_id, attempt_id, factor_id)` 上的唯一约束、
禁 UPDATE/DELETE 的 append-only 策略、`supersedes_observation_id` 自引用）。
该迁移的编写、评审与应用需要单独授权，不在 F1P 范围内。
