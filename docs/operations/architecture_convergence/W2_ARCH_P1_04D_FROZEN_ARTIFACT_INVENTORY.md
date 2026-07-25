# ARCH-P1-04D 只读 frozen artifact 可达性盘点证据

> 只读盘点，未修改 staging/生产任何数据。用于 04D 裁决第 2 点（历史 frozen
> artifact 不原地修改，先做可达性盘点）与迁移设计的 M2/M3 对账基线。

## 采集环境

- staging host：`118.196.30.136`（只读 SSH）
- 表：`read_model_checkpoint`
- frozen canary key 前缀：`analysis-card:frozen:v1:`
- 采集时间：2026-07-25（UTC）
- 采集方式：只读 SQL，无写入、无 DDL

## 查询方式

字段检查（每条 artifact 的 schema / decision_tier / 顶层 simulation /
pricing_shadow / 两侧 simulations / created_at / payload md5 前 16 位）：

```sql
select
  substring(checkpoint_key from 'v1:(.*)') as fixture_id,
  coalesce(payload->>'schema_version','<none>') as schema_ver,
  case when payload->'analysis_card'->'decision_contract'->>'decision_tier' is not null
       or payload->'decision_contract'->>'decision_tier' is not null then 'Y' else 'N' end as tier,
  case when payload->'analysis_card'->'simulation' is not null
       or payload->'simulation' is not null then 'Y' else 'N' end as top_sim,
  case when payload->'analysis_card'->'pricing_shadow' is not null
       or payload->'pricing_shadow' is not null then 'Y' else 'N' end as pshadow,
  coalesce((payload->'analysis_card'->'simulation'->>'simulations'),
           payload->'simulation'->>'simulations','?') as top_sims,
  coalesce((payload->'analysis_card'->'pricing_shadow'->'simulation'->>'simulations'),
           payload->'pricing_shadow'->'simulation'->>'simulations','?') as psh_sims,
  to_char(created_at at time zone 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"') as captured_at,
  substr(md5(payload::text),1,16) as payload_hash16
from read_model_checkpoint
where checkpoint_key like 'analysis-card:frozen:v1:%'
order by fixture_id;
```

总摘要 hash（8 行 payload md5 有序拼接后再 md5）：

```sql
select md5(string_agg(md5(payload::text), '|' order by checkpoint_key))
from read_model_checkpoint
where checkpoint_key like 'analysis-card:frozen:v1:%';
```

## 8 条 artifact 身份与字段检查结果

| fixture_id | schema_version | decision_tier | 顶层 simulation | pricing_shadow | top sims | pshadow sims | captured_at (UTC) | payload_hash(16) |
|---|---|---|---|---|---|---|---|---|
| 1494217 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `1c2064aa4ac58d84` |
| 1494218 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `6caa2ba3cf0e0969` |
| 1494219 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `816823a44c20f763` |
| 1494220 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `9789fbcfaef578b9` |
| 1494221 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `46dec5f7b5248355` |
| 1494222 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `22b192d39b537068` |
| 1494223 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `5301487bbc02f975` |
| 1494224 | w2.analysis-card.frozen.v1 | Y | Y | Y | 10000 | 10000 | 2026-07-22T02:19:04Z | `bbd60fda1e3eaa96` |

**总摘要 hash**：`2f76dc8946b231aff4c821e77ecbb669`

## 盘点结论

```text
FROZEN_ARTIFACTS_TOTAL            = 8
SCHEMA_ALL_CANONICAL             = 8/8  (w2.analysis-card.frozen.v1)
HAS_DECISION_TIER                = 8/8
HAS_TOP_LEVEL_SIMULATION         = 8/8
HAS_PRICING_SHADOW               = 8/8
TOP_SIM == PSHADOW_SIM           = 8/8  (都 10000)
PRE_LMM_MISSING_FIELD_ARTIFACTS  = 0
UNREACHABLE_OLD_ARTIFACTS        = 0
CANNOT_REMATERIALIZE_FAIL_CLOSED = 0
BLOCKERS                         = 0
```

- staging 上**零个** pre-LMM 缺字段 artifact；裁决第 2 点三分支当前零
  fail-closed 触发。
- 8 条 artifact 顶层 simulation 与 pricing_shadow simulation **逐场一致**，
  为 M2 对账（`top_level_simulation_hash == pricing_shadow_simulation_hash`）
  的基线证据。
- 本盘点仅为读取核验；M3 读切换前须以同法重新采集并与本快照对账，确认
  可达性未变。
