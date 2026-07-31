# W2 资产唯一性审计报告

## 基线与证据纪律

```text
repository = QIUYEDALAO/w2-football-intelligence-engine
baseline = main@dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

本报告区分：

```text
存储层唯一性
计算层唯一性
```

存储、表、目录和配置清理完成，不自动证明同一事实只有一个算法实现。人工数量是已知起点；最终分母必须由 Issue #454 / #456 的 T00-R5 可重复扫描生成。

---

# 一、存储层：当前没有删除遗漏证据

独立资产清点报告：

| 项目 | 当前结论 |
|---|---|
| ORM `__tablename__` 重名 | 0 |
| 已 drop 表仍留 ORM model | 0 |
| upgrade 重复建表 | 未确认；早期命中为 downgrade 恢复语句 |
| git 资产 `runtime/` | 当前不存在 |
| git 资产 `reports/` | 当前不存在 |

据此，P1-01 僵尸表删除、P1-02 赔率收敛、P1-03 crosswalk 收敛和 04C legacy 合同删除，当前没有发现孤儿 model 或残留目录权威。

严谨边界：

```text
STORAGE_LAYER_RESIDUALS = NO_CURRENT_EVIDENCE
REPRODUCIBLE_STORAGE_INVENTORY = REQUIRED_BY_T00_R5
COMPUTATION_LAYER_UNIQUENESS = NOT_IMPLIED
```

---

# 二、Critical：canonical JSON / hash serialization 不是唯一权威

## 已直接核实的最小运行相关集合

| 文件 | ensure_ascii | allow_nan | 其他差异 |
|---|---:|---:|---|
| `src/w2/ingestion/future_refresh.py` | `True` | 默认 `True` | 返回 `str` |
| `src/w2/tracking/outcome_ledger_repository.py` | `True` | 默认 `True` | 返回 `str` |
| `src/w2/monitoring/stage7i_lifecycle.py` | `True` | 默认 `True` | 返回 `bytes` |
| `src/w2/monitoring/stage7i_supervision.py` | `True` | 默认 `True` | 自定义 datetime/string fallback |
| `src/w2/prematch/read_model_projection.py` | `False` | 默认 `True` | 自定义 date/Decimal/datetime，未知类型拒绝 |
| `src/w2/prematch/repository.py::_pair_sha256` | `False` | `False` | pair identity 专用 |

代码搜索还发现其他 canonical/hash helper。因此“6”是已经逐项核实的最小集合，不是最终仓库分母。

## Unicode 实证

输入：

```json
{"home_cn":"上海海港","away_cn":"北京国安"}
```

结果：

```text
ensure_ascii=True
97c6d410cc9167d2af458ff73d99cad125f1b534c6f4bd6d5bffddac33d5695d

ensure_ascii=False
3c6fe4e44f3ad08f4483d49d2ca33d9206c6e06a19d98504acedff86584aa46a
```

同一语义 payload 因序列化字节不同得到不同 SHA-256。

## EVAL-02B 合同缺口

当前冻结文本规定：

```text
PAIR_IDENTITY_SERIALIZATION = UTF8_CANONICAL_JSON_SORTED_KEYS_COMPACT
Canonical JSON 禁止 NaN/Infinity
```

但没有显式冻结：

```text
serializer version
ensure_ascii
Unicode escaping / normalization
float / Decimal / exponent / negative-zero policy
date / datetime policy
unsupported type behavior
```

全仓代码搜索只在 `_pair_sha256` 找到显式 `allow_nan=False`。已知其余实现继承 Python 默认 `allow_nan=True`，可能输出 `NaN` / `Infinity` token，而不是拒绝输入。

## 风险

1. 独立 reviewer 和跨语言实现可能无法复算 `pair_identity_hash`；
2. 相同 validation pair 集合可能产生不同 bootstrap seed；
3. ledger/projection/artifact 跨模块对账可能永久不匹配；
4. 直接切换参数会改变历史 hash，不能无版本、无迁移覆盖。

## 裁决

```text
R5_CANONICAL_SERIALIZATION = CRITICAL_GATE_A
REAL_CANARY = BLOCKED
```

在 Issue #456 的 R5-SER-01 至 R5-SER-06 完成前，不允许真实 canary。

---

# 三、Important：其他计算权威重复

以下重复已核实存在；实现数量由 T00-R5 最终确定。

## 1. fair odds / decimal odds

- `src/w2/markets/score_baseline.py::fair_decimal_odds`：返回 `float`，round 6；
- `src/w2/markets/value_engine.py::fair_decimal_odds`：返回 `Decimal`，ROUND_HALF_UP 到 4 位。

风险：同一分布的 fair odds、EV 和阈值边界可能因类型与舍入不同而分裂。

## 2. canonical market taxonomy

至少在以下核心路径有独立 canonicalization：

```text
src/w2/ingestion/future_refresh.py
src/w2/matchday/intake_v2.py
src/w2/markets/historical_dataset.py
src/w2/markets/asian_handicap_scope.py
```

代码搜索还发现其他同名或等价入口。风险是采集、历史、评估和正式范围对同一 Provider market 分类不同。

## 3. Brier / ECE

```text
src/w2/models/evaluation.py
src/w2/tracking/performance_scoring.py
```

两处独立实现 Brier、reliability 和 ECE，输入接口与聚合方式不同。必须判定：

- 是同一指标的重复实现；或
- 是两个不同业务定义，但当前命名和合同未区分。

## 4. odds parsing / decimal representation

代码中存在多个 `decimal_odds` / odds conversion / parse helper，返回 `str`、`float` 或 `Decimal`。不能凭同名搜索直接合并；须记录输入域、精度、舍入、持久化格式与调用方。

## 5. 同名 read-model 类

`ReadModelRepository` / `ReadModelService` 在 API 读侧和 prematch 计算侧存在同名类型。职责可能不同，但命名会误导 import、review 和运行排障。

## Gate 归属

```text
canonical serialization -> Gate A
其他公式/分类/命名 -> Gate C
```

如果 T00-R5 证明某一重复直接参与本次 pair/v2/five-state evidence chain，则提升到 Gate A。

---

# 四、Minor / 后续治理

## 历史 migration 动态反射 ORM

代码搜索确认 `migrations/versions/0002` 至 `0016` 共 15 个历史 migration 引用当前 `Base.metadata`，例如按 `Base.metadata.sorted_tables` 动态创建/删除表。

风险：修改当前 ORM 可能改变 fresh replay 的历史行为，migration 快照与 ORM 权威分裂。

处置：

- 不原地改写已应用历史 migration；
- 增加 fresh-replay schema golden manifest；
- 禁止新 migration 动态依赖当前 ORM metadata；
- Gate D / 恢复验收前证明 replay schema 一致。

## 状态与任务文档重复

`PROJECT_STATE.yaml`、主清单和 architecture_convergence 子文档仍有部分重复状态。保持为 bounded governance debt，不重开已完成架构任务；当前状态由 #450 上下文收敛。

---

# 五、新增审计视角 R5

```text
名称：计算权威唯一性
定义：同一业务事实、身份、分类或公式是否只有一个明确的算法权威；若存在不同业务定义，是否显式版本化和命名区分。
状态：IN_PROGRESS
当前发现：Critical >=1；Important 多项
执行权威：Issue #456
```

T00-R5 扫描至少覆盖：

```text
同名函数/类
同概念异名实现
canonical JSON / hash serializer
float/Decimal/rounding 差异
market taxonomy
metrics / EV / CLV / settlement formula
migration 与当前 ORM 的动态耦合
```

每项必须有文件/行号、调用者、输入输出合同、持久化/哈希域、分类、owner、测试、迁移与关闭 Gate。

---

# 六、最终停机线

本报告不授权：

```text
Provider
真实 canary authorization
persistent scheduler
Candidate
Formal
Lock
Production
auto merge
```

当前执行顺序以 Issue #454 v4 为准：

```text
GitHub local sync
-> T00-GOV
-> T00-SAFE R1-R5
-> canonical serialization authority/migration
-> trusted-main C9 rebuild
-> remaining Gate A blockers
-> fake-Provider rehearsal
-> independent second review
-> human canary authorization decision
```
