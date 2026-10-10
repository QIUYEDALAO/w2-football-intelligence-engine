# 指令书 I 任务 A 实施回执 —— FootyStats 影子试点

```text
receipt_type = IMPLEMENTATION_RECEIPT_NOT_ACCEPTANCE
implementer_revision = 08424113
worktree = /Users/liudehua/Documents/Projects/W2-workspaces/w2-i-a-footystats-shadow-20261010
branch = codex/w2-authority-20260916
base = 9958722465540eacbf91ec1d46cd8878e692a083
date = 2026-10-10
acceptance = NOT_SIGNED_BY_IMPLEMENTER（验收方为 Kimi，本文件不含任何验收结论）
```

**本文件是实施方回执，不是验收回执。** 下列数字全部来自实施方本机亲跑，验收方须独立复算。

## 1. 授权边界与停止线

| 项 | 实际 |
|---|---|
| 生产表写入 | 0（迁移只创建 `fs_*` 旁路表，不引用任何生产表） |
| 生产 DB 变更 | 0 |
| V4 / prematch / strategy / scheduler / dashboard | 未触碰 |
| FootyStats key | 只从 env 读；未入库、未落盘、未写日志 |
| 生产库访问 | 只读导出 `matchday_fixture_identities`（1297 行） |
| 部署 | 未执行 |

## 2. 交付物

```text
migrations/versions/0094_footystats_shadow.py          5 张 fs_* 旁路表
src/w2/quant_research/footystats_client.py             带配额计账的传输层
src/w2/quant_research/footystats_shadow_models.py      旁路表模型
src/w2/quant_research/footystats_identity.py           三层身份映射（league/team/fixture）
src/w2/quant_research/footystats_shadow.py             采集器 + 报表
config/quant/footystats_league_map.v1.json             联赛映射（27 条）
config/quant/footystats_team_alias.v1.json             球队人工复核别名（29 条）
scripts/quant/footystats_build_league_map.py           联赛映射构建/校正
scripts/quant/footystats_shadow_pilot.py               run / replay / remap / report
tests/integration/test_ah_ou_*_pg.py                   3 处 alembic head 钉死 0093→0094
```

迁移行为：`upgrade head` 在全新库建立 5 张表；`downgrade` 在旁路表已有采集证据时**拒绝执行**（避免销毁原始 payload）。

## 3. 实测结果

### 3.1 三层身份映射

```text
league   27/27 已映射（19 条精确三元组 + 8 条按实测校正，见 league_map 的 evidence 字段）
team     488/488 = 1.0000（规则 459 + 人工复核 29）
fixture  1292/1297 = 0.9961
抽检     100/100 = 1.0000，pass=True（阈值 0.99，固定种子可复现）
比分交叉校验  69 例一致 / 0 例不一致 / 31 例无可比比分（未开赛或不完整）
映射碰撞  0
未命中    5，全部为 *_NO_FOOTYSTATS_COUNTERPART（3 场 NS + 2 场 PST），
          TEAM_NOT_CROSSWALKED = 0 —— 即映射缺陷 0，残差来自对侧无此场
```

**分母口径（必须澄清，否则数字会被误读）**：抽检分母是「生产身份表中存在于已映射联赛的 fixture」，不是 FootyStats 整季。FootyStats 的 `league-matches` 返回整季（含数月前已完赛、生产从未采集的比赛），用它当分母算出的比率量的是「生产覆盖了整季多少」，不是「映射准不准」。两个口径都在报告里，字段名分别是 `sampled_accuracy` 与 `production_overlap_rate`，报告内显式标注区别。

### 3.2 覆盖实测（逐联赛 5 场详情抽样）

```text
xG 非空（限 status=complete）     27/27 联赛 = 1.000
顶层 1X2 非空                     27/27 联赛 = 1.000
顶层 O/U 2.5 非空                 27/27 联赛 = 1.000
odds_comparison 非空              25/27 联赛 = 1.000；argentina_primera = 0.000；mls = 0.200
Pinnacle 在 odds_comparison 内     与 odds_comparison 逐行一致（有则有，无则无）
```

`odds_comparison` 细节响应总体：139 场观测中 130 场（93.5%）存在该字段；存在的 130 场中 Pinnacle 覆盖 100%。

**指令书预判 vs 实测**：预判「中超/瑞典超 odds_comparison = 0」。实测该字段**存在**，只是**不在** `league-matches`/`todays-matches` 响应里——它只出现在 `match` 详情端点。此前「0/1130 全为 null」的结论是在错误端点上量的。逐联赛差异真实存在（阿根廷 5/5 缺失、MLS 4/5 缺失），所以「主源仍走 API-Football 逐场 Pinnacle」的口径决定是正确的，但要按「FootyStats 比较赔率覆盖不全」而不是「FootyStats 没有比较赔率」来记录。

### 3.3 配额

```text
调用 186 次，失败 0；Provider 头 remaining 1800→1428
端点分布 league-list=2, league-matches=27, todays-matches=2, match=155
```

计账依据是 Provider 响应头（`request_remaining` / 上限），每次调用入库。余量守卫在剩余低于 20% 时拒发。

## 4. 实测推翻或修正的既有假设

1. **FootyStats 结构上没有亚盘**：`odds_comparison` 的 13 个市场里没有任何 AH 项。与既有裁决一致，AH 主源必须留在 API-Football。
2. **未开赛比赛的 xG 是 `0.0` 而不是 null**：按「非空即有效」统计会把未开赛比赛算成 100% 覆盖。已强制 `status == 'complete'` 才计入 xG 覆盖率。
3. **状态词表有第三个值 `suspended`**：不是只有 complete/incomplete。
4. **跨年赛季用拼接标签 `20262027`**，不是 `2026`。按字面 `2026` 取 season_id 会取到空或错表。
5. **部署库是 25 个启用联赛，不是 24**（`chinese_super_league` / `allsvenskan` = false 已确认）。指令书正文的「24」与实测不符。
6. **CSL = 16789、Allsvenskan = 16576 正确**，已由 league-list 实测确认。
7. **两队名口径系统性不同**：api_football 用简称、FootyStats 用全称。字符串精确匹配只有约 8% 命中，必须走规则 + 球队交叉表。

## 5. 实现过程中发现并修复的缺陷

| # | 缺陷 | 后果 | 处置 |
|---|---|---|---|
| 1 | `league_season` 自然键漏 `fs_country` | Germany/Austria 同名 `Bundesliga` 撞唯一约束，采集中断 | 自然键改为 (country, name, season_year) |
| 2 | 队名归一化未转写 `ø/æ/å` | 北欧联赛大面积对不上（Tromsø/Tromso 等） | 增加转写表，在 casefold 之后替换 |
| 3 | 把 `AIK` 当俱乐部形式词剥掉 | `AIK Stockholm` 变 `stockholm`、`AIK` 变回退 `aik`，两边对不上 | 从形式词表移除 `aik` |
| 4 | 词首重合被当作同队 | `Plate`(River Plate) 与 `Platense` 互相认领，把双方正确命中一起拖进歧义 | token 比较收紧为「相等或仅差复数尾」 |
| 5 | 多候选不按强度/对齐位次裁决 | `Los Angeles FC` 的精确命中被 `Los Angeles Galaxy` 的弱命中拖成歧义 | 引入 `(级别, 对齐位次)` 排序 + 双向最强认领 |
| 6 | 赔率可观测性可被低保真端点覆盖 | 整季/当日同步把已抓到 `match` 详情的比赛打回「未观测」，实测 20 场受害 | 该组字段改为只升不降；并区分「端点可暴露」与「字段值」 |

第 6 条附攻击验证：先全量重放得 `via_match=139 / with_cmp=130`，再**只重放低保真端点**，结果不变（`139/130/130`），`MONOTONIC_OK = True`。

## 6. 未验证项 / 已知限制（不回避）

1. **xG 发布滞后分布（≥10 场，p50/p90）未测出。** 单次会话内观测不到「先未完赛、后完赛」的时间差：2906 场完赛比赛全部在同一轮里既完赛又有 xG，时滞恒为 0.000s，这是**上界**不是真实延迟。产出真实分布需要至少两次相隔的采集（建议 T+1h / T+6h / T+24h 重复同一批 due 场次）。**这是任务 A 第 3 项未完成的交付，不是「已覆盖」。**
2. **映射抽检是固定种子随机 100 场，不是全量人工复核。** 100/100 是抽样结论。
3. **`odds_comparison` 逐联赛覆盖是每联赛 5 场的小样本。** 阿根廷 0/5 与 MLS 1/5 是真实缺失，但 5 场不足以给出该联赛的稳定覆盖率。
4. **「零生产表写入」的本地证据是「迁移只建 fs_* 表 + 对生产库只做只读导出」**，不是对生产库的外部审计结论。
5. **配额的「计账与实测一致」只对到 Provider 响应头层面**，未做逐请求差分对账。
6. **`fs_team` 638 行 vs 生产球队 488 支**：差的 150 行来自 `todays-matches` 带回的、不在已映射赛季内的联赛球队（未映射赛季，故无 `competition_id`），不参与交叉表。这是设计内的旁路留存，不当作缺口。
7. **团队别名表 29 条中 1 条判据是结构性的**（`Líšeň ↔ Artis`，两侧 16:16 残余 1:1 强制配对），命名上无佐证，建议验收方单独人工复核。
8. **任务 B / C / D / E 全部未开始。**
9. **未跑全量测试套件。** 本轮只跑了 ruff（改动文件全绿）、canonical 序列化权威守卫（`unauthorized_serializer_writers=0`、`unversioned_hash_writers=0`）、相关单测 5 passed，以及集成测试的 head 钉死同步。集成测试需 `W2_TEST_POSTGRES_URL` 未执行。

## 7. 复现命令

```bash
# 旁路库（本地研究库，非生产）
dropdb --if-exists w2_fs_shadow && createdb -O "$USER" w2_fs_shadow
W2_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/w2_fs_shadow" \
  python -m alembic upgrade head

# 载入生产 fixture 身份快照（只读导出；fs_* 表无外键，可先挂起 FK 触发器）
# 注意 fs_* 之外的表由生产导出带 FK 约束，装载需 session_replication_role = replica

# 零 Provider 调用复算映射与报告
W2_DATABASE_URL=... python scripts/quant/footystats_shadow_pilot.py replay --out .local/pilot

# 真实采集（需 W2_FOOTYSTATS_API_KEY 且已解除代理）
W2_DATABASE_URL=... W2_FOOTYSTATS_API_KEY=... \
  python scripts/quant/footystats_shadow_pilot.py run --out .local/pilot \
  --skip-league-matches --details-per-competition 5
```

## 8. 证据哈希

```text
.local/pilot/pilot_report.json                          76ef1db9585cd39df6e27f6355b62532a6818315b5682f80a84aff685564ac75
.local/snapshot/matchday_fixture_identities.sql         2cff0006faf071b34e3f4f557fda5d484e5370036d856cdf87be45f99e76e581
.local/snapshot/fs_evidence.sql                         ac99c69b2c13b3b2f8b75c220b9660d911cacbf9e1e02483895b4e5ffc9f9a06
```

旁路库行数：`fs_request_log=186`、`fs_raw_payload=186`、`fs_league_season=27`、`fs_team=638`（其中 488 已对齐）、`fs_fixture=8432`（其中 1292 已映射）、`has_odds_comparison=130`、`has_pinnacle_comparison=130`、`alembic head = 0094_footystats_shadow`。

## 9. 结论

```text
IMPLEMENTATION_STATUS = COMPLETE_FOR_AUTHORISED_SCOPE
MAPPING_BAR_GE_0.99 = MET（抽检 100/100，分母=生产 fixture）
XG_LAG_DISTRIBUTION = NOT_DELIVERED（缺至少两次相隔采集）
PRODUCTION_TOUCHED = false
ACCEPTANCE = NOT_SIGNED_BY_IMPLEMENTER
```
