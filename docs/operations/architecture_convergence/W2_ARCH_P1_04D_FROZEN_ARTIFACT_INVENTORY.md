# ARCH-P1-04D 只读 frozen artifact 盘点证据

> 只读盘点，未修改 staging/生产任何数据。用于 04D 迁移设计的 M2 对账基线。
> **可达性未在本盘点评估**（见末节），历史 artifact 的删链前置仍锁在 M3 gate。

## 采集与校验方式

- staging host：`118.196.30.136`（只读 SSH）
- 表：`read_model_checkpoint`；frozen canary key 前缀：`analysis-card:frozen:v1:`
- captured_at（每条 artifact 的 DB `created_at`，UTC）：2026-07-22T02:19:04Z
- 采集：只读 SELECT 导出 8 条 `{checkpoint_key, source_hash(表列), payload}`，
  无写入、无 DDL。
- 校验：本地对每条 payload 运行**生产校验函数**
  `w2.prematch.read_model_projection.validate_frozen_analysis_payload`
  （纯函数，无 DB 写入），并用同模块的 `canonical_sha256` 计算对象 hash。

### 两个 hash 语义不同，分别验证（不要求互相相等）

- **artifact_hash**（payload 完整性）：`canonical_sha256(payload 去除
  artifact_hash 键)` 是否等于 payload 自带的 `artifact_hash`
  （对应 read_model_projection.py:512-515）。→ `ARTIFACT_HASH_VALID`
- **source_hash**（来源身份）：验证器由 payload 的 `input_manifest` /
  `source_event_hash` / `source_evaluation_hashes` 重算的 source_hash，是否等于
  **数据库行 `source_hash` 列**（对应 read 路径 `row.source_hash !=
  artifact.source_hash`；重算式见 :525-535）。→ `SOURCE_HASH_VALID`

两者哈希的是不同输入，**本就不应相等**；实测每条 artifact_hash 与 source_hash
取值不同（见下表前缀），故按两条独立断言分别记录 PASS，不写
`SOURCE_HASH == ARTIFACT_HASH`。

## 8 条 artifact 身份与字段检查

checkpoint_key = `analysis-card:frozen:v1:<fixture_id>`。hash 均 sha256（表内
截断展示）；sim_obj_hash 为 `canonical_sha256(simulation 对象)`。

| fixture_id | artifact_hash | db source_hash | card_top_tier | contract_tier | sim_jsonb_equal | top_sim_obj_hash | pshadow_sim_obj_hash |
|---|---|---|---|---|---|---|---|
| 1494217 | `d95c60662a1b…` | `2e96adb23ee0…` | WATCH | WATCH | true | `2092cfd327984bac…` | `2092cfd327984bac…` |
| 1494218 | `cca1e349cc44…` | `80323c04e1bd…` | WATCH | WATCH | true | `331759fb669d9ba8…` | `331759fb669d9ba8…` |
| 1494219 | `ed2b2f94c02e…` | `43d65caf40cc…` | NOT_READY | NOT_READY | true | `618ad78da45cb042…` | `618ad78da45cb042…` |
| 1494220 | `9140c6bc67e5…` | `505576a72a1b…` | WATCH | WATCH | true | `0db83774b8c38236…` | `0db83774b8c38236…` |
| 1494221 | `8488de31c8fa…` | `ce156ac5b03f…` | WATCH | WATCH | true | `1896ead8d61a9863…` | `1896ead8d61a9863…` |
| 1494222 | `4702ec33985d…` | `49d404612743…` | ANALYSIS_PICK | ANALYSIS_PICK | true | `e5aed5e386ec9755…` | `e5aed5e386ec9755…` |
| 1494223 | `d54c27a466f2…` | `909cc0108301…` | WATCH | WATCH | true | `5eaf0316dc79a1a3…` | `5eaf0316dc79a1a3…` |
| 1494224 | `10d5bf79c1e6…` | `42251db35539…` | WATCH | WATCH | true | `592970debe19de2a…` | `592970debe19de2a…` |

- `card_top_tier` = `analysis_card.decision_tier`；`contract_tier` =
  `analysis_card.decision_contract.decision_tier`；两者逐条相同。
- `sim_jsonb_equal` = 顶层 `analysis_card.simulation` 与
  `analysis_card.pricing_shadow.simulation` 的**全对象深度相等**（等价 JSONB
  全对象 equality）；两侧 `sim_obj_hash` 逐条相同，即完整对象 hash 一致。

**inventory 总指纹（md5，仅身份指纹，非任何相等/正确性证明）**：
`3a748382575ce8dd7f36184b7e15ebbd`（8 条 artifact_hash 有序拼接后的 md5）。

## 盘点结论

```text
FROZEN_ARTIFACTS_TOTAL            = 8
SCHEMA_ALL_CANONICAL             = 8/8  (w2.analysis-card.frozen.v1)
PRODUCTION_VALIDATE_OK           = 8/8  (validate_frozen_analysis_payload 无异常)
ARTIFACT_HASH_VALID              = PASS (8/8)
SOURCE_HASH_VALID                = PASS (8/8)
CARD_TOP_TIER_PRESENT            = 8/8  (WATCH×6, NOT_READY×1, ANALYSIS_PICK×1)
CONTRACT_TIER_PRESENT            = 8/8  (逐条与 card_top_tier 相同)
SIM_JSONB_EQUAL (full object)    = 8/8  true
TOP_SIM_OBJ_HASH == PSHADOW_OBJ  = 8/8  (canonical_sha256 全对象)
REACHABILITY_NOT_YET_EVALUATED   = M3_GATE
```

- 顶层 simulation 与 pricing_shadow simulation 在**全对象层面逐条相等**，为 M2
  对账（`top_level_simulation_hash == pricing_shadow_simulation_hash`）的基线。
- **可达性未评估**：本盘点未查证 public-reader / current-fixture 是否仍读取
  这些历史 artifact，故**不主张**任何 `UNREACHABLE` / `CANNOT_REMATERIALIZE`
  结论。可达性判定与三分支处置（不可达保留审计 / 可达重新物化 / 无法物化
  fail-closed）一并锁在 **M3 gate**，届时须补真实 public-reader /
  current-fixture 可达性查询后方可评估。
