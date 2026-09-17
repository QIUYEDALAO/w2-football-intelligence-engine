# W2 联赛扩容后「从零重建数据库」处置方案（LEAGUE-01R 遗留风险）

- 日期：2026-09-16
- 触发：`migrations/versions/0051_apply_seven_day_collection_policy.py` 是已合并迁移（禁删清单⑤），
  其 `upgrade()` 内 `apply_collection_policy_update(...)` 读**磁盘当前 config** 且断言
  `len(updated) != 14`。新增 14 个联赛后 config/ 有 28 个联赛，从零重放迁移链会在 0051 断链。
- 本方案只出处置步骤，不执行（纯只读交付）。

---

## 1. 风险本质（事实）

`0051` 的 `upgrade()` 依赖两个「当时恰好成立、现在已不成立」的条件：

1. `apply_collection_policy_update` 读磁盘 `config/`，把当时所有非 world_cup 联赛（13 个）
   应用 collection policy，返回 `updated`（当时 13 + world_cup 退役 = 14 条）；
2. `len(updated) != 14` 断言。

新增 14 个联赛后：
- `apply_collection_policy_update` 已放宽（commit `a985cde2`），`active_ids` 收窄为
  「非 world_cup 且有 future/matchday policy」的联赛 = 13 个，`updated` 仍 = 14（13 联赛 +
  world_cup 退役）。**seed.py 放宽后 0051 不再炸。**
- 但 `0051` 里那句 `len(updated) != 14` **是迁移文件内的硬编码**，禁删清单⑤禁止改已合并迁移。

**结论**：seed.py 放宽后，`apply_collection_policy_update` 在「有 policy 的 13 联赛」口径下
仍返回 14，0051 的 `len(updated) != 14` 依然成立——**从零重建不会断在 0051**。

> 需要强调：这是放宽 seed.py 之后的附带结果。若未来 Owner 再给新联赛加 future/matchday
> policy（使 `active_ids` 超过 13），0051 的 `14` 断言才可能再次失效。因此本方案仍保留
> 「跨过已知不可重放迁移」的通用处置，作为兜底。

---

## 2. 处置方案（分两种情形）

### 情形 A：当前口径（有 policy 联赛仍 = 13，seed.py 已放宽）

从零重建时，迁移链 **可直接重放到底，无需 stamp 跳过**：

```bash
alembic upgrade head
```

0051 的 `apply_collection_policy_update` 返回 `updated == 14`（13 联赛 + world_cup 退役），
`len(updated) != 14` 为假，迁移通过。无需任何补做。

### 情形 B：未来「有 policy 联赛数 ≠ 13」时（通用兜底）

若 Owner 再给新联赛授予 collection policy（使 `active_ids` 变为 14+），0051 的 `14` 断言
会失效。此时从零重建必须用 `alembic stamp` 跳过 0051 的**数据写入副作用**（表结构已由
0033/0051 之前的迁移建立，0051 只做数据填充）：

```bash
# 1) 重放到 0051 之前
alembic upgrade 0050_gate_a_runtime_selection

# 2) 把版本指针直接 stamp 到 0051（跳过其 upgrade() 的数据填充）
alembic stamp 0051_apply_seven_day_collection_policy

# 3) 继续重放剩余迁移
alembic upgrade head
```

> `alembic stamp` 只改 `alembic_version` 指针，不执行 0051 的 `upgrade()` 数据写入。
> 0051 没有 `downgrade()`（pass），且它的唯一副作用是「给 13 个联赛写 APPLY_COLLECTION_POLICY
> audit + 设置 enabled」，这些在 seed 后本就会被 `seed_competition_runtime_authority`
> （FIRST_INSTALL_SEED）与 Phase 5 `--set-enabled`（SET_ENABLED）重新建立。

---

## 3. 被跳过迁移（0051）原本做的事如何补做

0051 `upgrade()` 做的事 = 调 `apply_collection_policy_update`，即：

```text
对「非 world_cup 且有 future/matchday policy」的每个联赛：
  - league_season.payload.enabled = true
  - refresh_switches = {fixtures:true, odds:true, lineups:true}
  - future_refresh_policy / matchday_policy = 对应 policy 条目
  - 写入一条 action=APPLY_COLLECTION_POLICY 的 league_readiness_audit
```

补做方式（按丙方案，等价且是现役标准路径）：

```bash
# 1) 先 seed（FIRST_INSTALL_SEED，重建 league_profile/league_season 基线）
python scripts/seed_competition_runtime_authority.py \
  --environment <environment> --config-root config --updated-by <operator>

# 2) 逐联赛 enable（SET_ENABLED，等价于 0051 的 enabled=true + audit 写入）
python scripts/seed_competition_runtime_authority.py \
  --set-enabled <competition_id> --enabled true --updated-by <operator>
```

> 注意：0051 的 `APPLY_COLLECTION_POLICY` audit action 与 `--set-enabled` 的 `SET_ENABLED`
> action **不是同一 audit 类型**。若需保留历史 audit 语义完全一致，需 Owner 裁定是否补写
> `APPLY_COLLECTION_POLICY` audit；否则按现役「seed + set-enabled」口径即可，历史 0051 的
> 那次 APPLY_COLLECTION_POLICY 属于一次性历史事件，重建后不要求逐字节复刻。

---

## 4. 该方案写入哪份运维文档

建议落（三选一或全部，需 Owner 确认）：
1. `docs/operations/W2_DAILY_OPERATIONS_V1.md`（日常运维入口，加「从零重建数据库」小节）；
2. `docs/operations/W2_RELEASE_AND_ROLLBACK_V1.md`（发布/回滚契约，加「重建库跨过 0051」小节）；
3. `docs/runbooks/W2_LEAGUE_EXPANSION_RUNBOOK.md` 第 11 节 Rollback 附近，作为联赛扩容的
   连带运维说明。

推荐主落点：**`docs/operations/W2_DAILY_OPERATIONS_V1.md`**（当前内容最短、是运维事实源），
并在 `docs/runbooks/W2_LEAGUE_EXPANSION_RUNBOOK.md` 补一句交叉引用。

---

## 5. 遗留登记

```text
DEBT-05：0051 迁移的 len(updated)!=14 硬编码是「有 policy 联赛数=13」的历史假设。
        禁删清单⑤禁止改已合并迁移，该断言无法通过改代码消除；若未来给新联赛加
        collection policy，从零重建需按本方案情形 B 用 alembic stamp 跳过 0051。
状态：OPEN，本轮不处理。
```

---

**执行方：Codex；验收方：独立验证者；最终授权：Owner。**
