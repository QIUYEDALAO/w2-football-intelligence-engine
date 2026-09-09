# 因子否决绕过：确认与修复（整改后）

## 1. 数据层证据（比代码推断更强）

```sql
select count(*) from dynamic_prematch_evaluations where payload::text ilike '%factor%'
→ 0
```

整张生产表、全部 payload，**没有一行**含 "factor" 字样。因子裁决**从未被写入过**动态评估——
不只是 `lifecycle.py` 不读，是数据层根本没有。

分析卡不持久化（库中无对应表，系读时投影），因此这 148 条的历史因子方向**不可重建**：

```text
FACTOR_DISPOSITION = UNKNOWN_NOT_RECONSTRUCTIBLE     148 / 148
```

## 2. 绕过链路

```text
analysis_calculator.py:5891-5897   因子冲突 → card 的 decision/analysis_decision = WATCH
read_model_projection.py:1481      _dynamic_evaluations(card, ...) 构造 DynamicEvaluationInput
                                   ——从不读 card 的 factor 字段
lifecycle.py:526                   state 纯由 economic_admission_pass 决定
lifecycle.py:311                   official_funnel_eligible=True（对所有状态无条件）
api/repository.py:499              正式漏斗筛 official_funnel_eligible + state==ANALYSIS_PICK_ACTIVE
```

`official_funnel_eligible` 无条件为 true，故该双条件实为**单条件**，唯一闸门是纯经济状态。
`_factor_veto` 的 docstring 本身写明候选链"never consults a factor"——
这是**已声明意图的实现缺口**，不是设计分歧。

## 3. 修复：进入写入契约，而非 read layer 过滤

- `DynamicEvaluationInput` 增 7 个字段：`factor_decision_status` / `factor_direction` /
  `ev_direction` / `factor_veto_code` / `factor_input_identity` /
  `factor_input_identity_hash` / `factor_evidence_digest`；
- 新增状态 `DynamicEvaluationState.BLOCKED_BY_FACTOR`，不在
  `{ANALYSIS_PICK_ACTIVE, NO_EDGE_CURRENT}` 内，故经 `lifecycle.py:297-303` 自然映射为
  `OpportunityState.BLOCKED_BY_GATE`；
- `factor_blocker()` 在**经济准入之前**判定，三种码任一命中即阻断并把具体码写入 blockers；
- **fail-closed**：AH 无因子裁决身份即 `FACTOR_SCORE_UNAVAILABLE`；
- 历史 payload 读回为 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY`，**显式不视为通过**；
- TOTALS 完全不受影响（`factor_blocker` 对非 AH 直接返回 None）；
- `official_funnel_eligible` **不改**，被阻断的 AH 仍计入正式漏斗分母（符合 B3）；
- `read_model_projection._factor_verdict()` 把 `card["markets"]` 的 `factor_veto` 与
  `card["market_candidates"]` join 起来——两者本就在同一张卡上，只是从未连过。

## 4. R1–R3：裁决真正被持久化，并进入身份

前一轮只把字段加进了 `DynamicEvaluationInput`。`DynamicEvaluationVersion` 没有对应字段，
而 `as_dict()` 走 `asdict(self)`，所以裁决**写不进 payload**，也就无法验收、无法回溯。本轮：

- `DynamicEvaluationVersion` 增同名字段 + `factor_verdict_schema =
  "w2.dynamic_quote_evaluation.factor_verdict.v1"`，裁决随 `as_dict()` 落入 payload；
- `factor_input_identity_hash` 由**完整规范化 factor payload**
  （direction / admitted / margin / strength / weight_sum_used / participant_count /
  participants / absent / admission_blockers / veto）经仓库唯一权威
  `canonical_sha256(..., domain=HashDomain.PREMATCH_READ_MODEL_GENERIC)` 计算。
  **不使用** `analysis_decision`、`WATCH`、`ANALYSIS_PICK` 等展示字符串，
  也不使用裸 `json.dumps` / `hashlib`；
- **身份绑定**：`identity_payload` 仅在 `factor_input_identity_hash or factor_veto_code`
  存在时并入因子字段，`attempt` 身份再绑定 `evaluation_identity_hash`。
  于是同一报价 + 同一模型输入 + 不同因子裁决 → 不同 evaluation 身份、不同 attempt 身份，
  append-only 不会把第二个结论吞掉；而历史与无裁决记录的身份**原样不变**，不改写历史；
- 反向测试：5 个受保护字段（status / direction / ev_direction / veto_code /
  identity_hash）逐个变更，断言 evaluation 与 attempt 两个身份都必须改变，
  共 10 条参数化，全部通过。

`ALEMBIC_MIGRATION_REQUIRED = false`：payload 是 JSON 列，版本化持久化不需要新增列，
因此**不添加空 migration**。

## 4b. 读回、严格门与身份兼容（本轮窄整改）

**读回**：`repository._version_from_payload` 之前不重建这 7 个字段，重复 append 走
existing-row 分支时裁决会整片丢成 None——调用方无法区分「被否决」和「从未判过」。
现已逐字段重建；旧 AH payload 无字段时显式返回 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY`
（不是 None，也不是通过），旧 TOTALS 仍返回 None 且不需要裁决。

**严格 fail-closed**：AH 只有全部满足才放行——
`factor_decision_status == "ADMITTED"`；`factor_veto_code` 为空；
`factor_input_identity` 与 `factor_input_identity_hash` 同时存在、均为 64 位小写十六进制、
且两者相等；`factor_direction` 可解析为 HOME/AWAY；该方向与 EV 侧一致。

阻断码映射（新增 `FACTOR_VERDICT_MALFORMED`，用来把「没有裁决」和「有裁决但不可用」分开）：

```text
FACTOR_SCORE_UNAVAILABLE       完全无裁决，或历史标记
FACTOR_ADMISSION_FAILED        明确的拒绝：NOT_ADMITTED / VETOED
FACTOR_VERDICT_MALFORMED       有裁决但不可用：身份缺失/非法/不一致、状态无法识别、
                               方向缺失或非法、veto 码无法识别
FACTOR_EV_DIRECTION_CONFLICT   裁决可用但指向另一侧
```

已识别的 veto 码原样透传以保留分析层给出的具体理由；无法识别的码不透传，按
`FACTOR_VERDICT_MALFORMED` 阻断，避免信任一个未知字符串。

**身份兼容**：上一轮把 `evaluation_identity_hash` 无条件塞进 attempt preimage，
等于给每一条无裁决的 TOTALS 与历史 attempt 换了身份，append-only 不允许。现已分版：

```text
attempt_identity.v2   无裁决 —— preimage 与整改前逐字相同
attempt_identity.v3   有裁决 —— 额外绑 evaluation_identity_hash 与五个裁决字段
```

基线 `3ac86c14` 与本工作树各跑一次全量并逐次记录 attempt preimage：54/54 条 v2 哈希
与基线一致，v2 preimage 中出现 factor 或 evaluation 键 0 次，v3 与基线哈希碰撞 0 次。

## 5. 已知受 fail-closed 影响的其他写入点

```text
src/w2/operations/gate_a_staged.py:71   staged canary 市场自举，无分析卡因子分
```

该路径构造 AH 评估时没有因子裁决，按 fail-closed 现在会得到 `BLOCKED_BY_FACTOR`。
这是**预期行为**：它是 staged 金丝雀自举，不是正式推荐通道；无裁决就不该形成候选。
在此记录，避免被当成回归。

## 6. 消费端已被真实断言覆盖

`scripts/quant/tests/test_factor_gate_consumers.py` 经生产写入器落库后，直接调用
`w2.api.repository._official_funnel_recommendations` 与候选通知 outbox：被否决的
AH 既不在正式推荐列表，也无任何 outbox 事件，也不贡献任何 `profit_units` 行。
对照组（同构造、裁决一致）三项全部出现，因此这不是"状态枚举不等于候选"的替身断言。

## 7. 证据自包含

正式重放不再需要 Git 外文件：committed `OFFICIAL_148_SOURCE_BUNDLE.jsonl`（148 行，
`sha256 = da9edb11…`）只含 `build_rows` 消费的字段，无凭据、无连接串、无 Provider 原始
响应体。`official_candidate_manifest.py` 默认只读该 bundle；`--raw` 仅用于从受限原件
重建 bundle，验收不需要它。桌面原件保留为受限原本，登记在 `SOURCE_IDENTITY.json`。

## 8. 覆盖情况

测试矩阵 1–20 现已全部有断言：1–5、9–14、19 见 `test_factor_gate.py`
与 `test_independent_oracle.py`；6/7/8 见 `test_factor_gate_consumers.py`（真实消费端）；
15–18、20 见 `test_offline_evidence_contracts.py`（离线夹具与内存库）。
