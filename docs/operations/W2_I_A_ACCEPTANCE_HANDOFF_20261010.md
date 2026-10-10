# 指令书 I 任务 A —— 验收交付包（实施方 → 验收方）

```text
handoff_type = IMPLEMENTER_HANDOFF_PACKAGE
NOT_ACCEPTANCE = true
实施方不代签任何验收结论：VERIFIED_LOCAL_ONLY / CHANGES_REQUIRED / BLOCKED_NOT_VERIFIED
             一律由验收方独立判定。
```

> 验收方须按 `acceptance-rules` 11 条强约束执行。本文件只提供：被验对象、要求→证据映射、
> 亲跑命令、以及**未验证项与自认可能被判缺陷的点**。第 7 节必须逐条独立复判，不得采信本文结论。

---

## 1. 被验对象

```text
工作树   /Users/liudehua/Documents/Projects/W2-workspaces/w2-i-a-footystats-shadow-20261010
分支     无 —— 本仓 reference-transaction 钩子规定「只允许 codex/w2-authority-20260916
         被创建或更新」。git worktree add -b 的 ref 更新在 prepared 阶段被钩子拒绝，
         工作树停在 detached HEAD（该现象本身已复现两次，属仓库设计而非常规做法）。
锚点     tag w2-i-a-footystats-shadow-20261010 → 5efce359（防 GC 保险，验收方可直接 checkout 它）
实现     A 实现      08424113
         A 实施回执  5efce359
         A 整合      merge bc435032（parents = 99587224, 5efce359）
原基线   9958722465540eacbf91ec1d46cd8878e692a083
```

请求验收方**用 `5efce359`（或 tag）建独立工作树**，不要用线上权威分支 `codex/w2-authority-20260916`——
后者现已到 `1a774a6c`，其中 B-1/B-2 不在任务 A 的验收范围内，混验会把 B 的问题算到 A 头上。

```bash
git worktree add --detach /tmp/w2-a-verify w2-i-a-footystats-shadow-20261010
```

---

## 2. 合同要求 → 证据映射

| # | 指令书 I 任务 A 要求 | 状态 | 证据位置 |
|---|---|---|---|
| 1a | `todays-matches` 每日 2 次 | 已实现 | `footystats_shadow.py::sync_todays_matches`；实测 2 次调用 |
| 1b | 24 联赛 `league-matches` 分页，每日 1 次全量同步当季 | 已实现（实测覆盖 **27** 联赛，见 §4.3） | `sync_league_matches` + 分页推进守卫 `PAGINATION_NOT_ADVANCING` |
| 1c | due 场 `match` 详情 | 已实现 | `sync_match_details` |
| 1d | 原始 payload 落旁路表，fixture 级 sha256 去重 | 已实现 | `fs_raw_payload`（PK=payload_sha256） |
| 1e | 配额计账 1800/小时，留 20% 余量 | 已实现 | `footystats_client.py`，余量守卫 + `fs_request_log` |
| 2a | 三层映射 · league | 已实现 | `config/quant/footystats_league_map.v1.json`（27 条，每条带 `evidence`） |
| 2b | 三层映射 · team（归一化 + 同联赛消歧） | 已实现 | `footystats_identity.py` + `footystats_team_alias.v1.json`（29 条带判据） |
| 2c | 三层映射 · fixture（日期+主客队+比分交叉） | 已实现 | `match_fixture` by provider team id + 比分交叉校验 |
| 2d | 映射表 + 准确率报告（随机抽 100 场，≥99% 才过） | **达成：100/100** | `pilot_report.json:mapping_report` |
| 3 | xG 发布滞后 ≥10 场，p50/p90 | ❌ **未交付** | 见 §4.1 —— 本轮没有任何 p50/p90 可信值 |
| 4 | 覆盖实测（xG / odds_comparison / Pinnacle 非空率） | 已实现（27 联赛） | `pilot_report.json:coverage_report` |
| A+ | 白名单覆盖矩阵（24 启用 + 中超 + 瑞典超，逐联赛四指标） | 已实现，27/27 联赛 | 同上 |

### 验收方亲跑项对照

| 验收项 | 本轮可执行性 | 说明 |
|---|---|---|
| 映射抽 20 场复核一致 | ✅ 可执行 | 报告含 100 场抽检全字段，任取 20 |
| 旁路表字段完整性 | ✅ 可执行 | 迁移 `0094` + 报告字段 |
| 配额计账与实测一致 | ✅ 可执行 | 1800→1428，逐调用留档 |
| 零生产表写入证明 | ⚠️ **见 §4.2** | 本地侧成立；但生产库已被 `0094` 触及，原因见下 |

---

## 3. 实测数字（实施方本机亲跑，验收方须独立重算）

```text
映射
  league            27/27
  team 交叉表        488/488 = 1.0000（规则 459 + 人工复核 29）
  fixture           1292/1297 = 0.9961
  抽检准确率         100/100 = 1.0000   pass=True（阈值 0.99，固定种子可复现）
  比分交叉校验        69 一致 / 0 不一致 / 31 无可比比分
  映射碰撞           0
  未命中 5 场        全部 *_NO_FOOTYSTATS_COUNTERPART（3×NS + 2×PST）
                     TEAM_NOT_CROSSWALKED = 0 → 映射缺陷 0

覆盖（每联赛 5 场 match 详情抽样）
  xG 非空（限 status=complete）   27/27 联赛 = 1.000
  顶层 1X2 非空                   27/27 联赛 = 1.000
  顶层 O/U 2.5 非空               27/27 联赛 = 1.000
  odds_comparison 非空            25/27 = 1.000；argentina_primera = 0.000；mls = 0.200
                                  细节端点总体：139 场观测 130 场有该字段 = 0.935
  Pinnacle 在 comparison 内       与 odds_comparison 逐行一致（130/130）

配额
  调用 186 次，失败 0；Provider 头 remaining 1800 → 1428
  端点分布 league-list=2, league-matches=27, todays-matches=2, match=155

旁路库行数
  fs_request_log=186  fs_raw_payload=186  fs_league_season=27
  fs_team=638（crosswalked=488）  fs_fixture=8432（matched=1292,
  with_cmp=130, with_pin=130）  alembic_head=0094_footystats_shadow

证据产物哈希
  docs/operations/W2_I_A_FOOTYSTATS_SHADOW_PILOT_REPORT_20261010.json
      = .local/pilot/pilot_report.json 的副本（88KB，已随仓库提交）
      sha256 = 52fe6773a1a02612082be87c9b3721c149273e7fb86bfa79009d51749d4ec1d4
  .local/snapshot/fs_evidence.sql                  ac99c69b2c13b3b2f8b75c220b9660d911cacbf9e1e02483895b4e5ffc9f9a06
  .local/snapshot/matchday_fixture_identities.sql  2cff0006faf071b34e3f4f557fda5d484e5370036d856cdf87be45f99e76e581

  完整清单：docs/operations/W2_I_A_FOOTYSTATS_SHADOW_EVIDENCE_SHA256SUMS_20261010.txt
```

### 两个必须说清的口径（否则数字会被误读）

1. **映射准确率的分母是生产 fixture，不是 FootyStats 整季。** FootyStats `league-matches`
   返回整季（含数月前已完赛、生产从未采集的比赛），用它当分母量的是「生产覆盖了整季多少」。
   报告里两个口径都有，字段名分别 `sampled_accuracy` 与 `production_overlap_rate`。
2. **`odds_comparison` 只在 `match` 详情端点存在。** `league-matches` / `todays-matches`
   响应里连这个键都没有。原判断「中超/瑞典超 odds_comparison = 0」是在错误端点上量的。

---

## 4. 未验证项与已知限制（不回避）

### 4.1 xG 发布滞后分布 —— **未交付**（任务 A 第 3 项）

单次会话内观测不到「先未完赛、后完赛」的时间差：2906 场完赛比赛在同一轮里既完赛又有 xG，
时滞恒为 0.000s，这是**上界不是真实延迟**。产出真实 p50/p90 需至少两次相隔采集
（建议 T+1h / T+6h / T+24h 重复同一批 due 场次）。**这是未完成项，不是「已覆盖」。**

### 4.2 零生产表写入 —— 本地侧成立，但生产库已被触及

- 本地侧成立：迁移 `0094` 只创建 `fs_*` 表，不引用、不 ALTER 任何既有表；采集器只写 `fs_*`。
- ⚠️ **但生产库现已被 `0094` 触及**：2026-10-10T11:51:26Z 的 B 发布（提交 `1a774a6c`，含 A 的迁移）
  在生产库执行了 `alembic upgrade head`，创建了 5 张**空**的 `fs_*` 表。
  该发布由 Owner 批准（`--skip-window-check`），**不在任务 A 原授权范围内**，属实施方在
  「直接上线」指示下未先行澄清的执行偏差，实施方主动登记，请验收方按合同判定。
- 既有表零变化可由 `0094` 迁移源码证明（只有 `create_table`，无 `alter_table`）。

### 4.3 「24 联赛」与实测不符

部署库 `league_season` 实际启用 **25** 个（`chinese_super_league` / `allsvenskan` = false 已确认）。
本任务覆盖 **27** 个 = 25 启用 + 中超 + 瑞典超（后者即任务 E 待重开的两家）。

### 4.4 其他

- 抽检是**固定种子随机 100 场**，不是全量人工复核；`sampled_accuracy=1.0` 是抽样结论。
- 覆盖实测是**每联赛 5 场**小样本；阿根廷 0/5 与 MLS 1/5 是真实缺失，但 5 场不足以给出稳定覆盖率。
- 配额核对只到 Provider 响应头层面，未做逐请求差分对账。
- `fs_team=638` vs 交叉表 488：差的 150 行来自 `todays-matches` 带回的未映射赛季球队
  （无 `competition_id`，不参与交叉表），属设计内旁路留存。
- 人工复核别名 29 条中 1 条判据是**结构性**的（`Líšeň ↔ Artis`，两侧 16:16 残余 1:1 强制配对），
  命名上无佐证，建议单独人工复核。
- **未跑全量测试套件**。本轮只跑了：ruff（改动文件全绿）、canonical 序列化权威守卫
  （`unauthorized_serializer_writers=0`、`unversioned_hash_writers=0`）、相关单测，以及集成测试
  alembic head 钉死同步。集成测试需 `W2_TEST_POSTGRES_URL` 未执行。

---

## 5. 停止线合规

```text
REAL_PROVIDER_CALLS             = 49（首轮）+135（逐联赛详情）+2 次幂等重跑 = 186 次，全部登记
                                  作用域：仅 FootyStats 影子采集，未触 API-Football
LIVE_CAPTURE_ENABLED            = false（无调度器、无定时任务、无 collector 激活）
生产 DB 写入（本地侧）           = 0 —— 采集器只写 fs_*；生产访问仅只读导出
生产 DB 写入（实际，见 §4.2）     = 0094 迁移创建 5 张空表（随 B 发布带上去）
V4 / prematch / strategy        = 未触碰
Scheduler / Dashboard           = 未触碰
FootyStats key                   = 只从 env 读；未入库、未落盘、未入日志
部署                            = 任务 A 本身未部署
```

---

## 6. 复现步骤（验收方亲跑）

```bash
A=/Users/liudehua/Documents/Projects/W2-workspaces/w2-i-a-footystats-shadow-20261010
V=/Users/liudehua/Documents/Projects/W2-workspaces/w2-v11-system-remediation-20260930/.venv/bin

# ── 6.1 纯静态：零 Provider 调用 ────────────────────────────────────────────
cd $A
$V/ruff check src/w2/quant_research/footystats_*.py scripts/quant/footystats_*.py
PYTHONPATH=$A/src:$A $V/python $A/scripts/check_canonical_serialization_authority.py

# ── 6.2 重建研究库（本地 PG，非生产）──────────────────────────────────────
dropdb --if-exists w2_fs_verify && createdb -O $USER w2_fs_verify
export W2_DATABASE_URL="postgresql+psycopg://$USER@localhost:5432/w2_fs_verify"
PYTHONPATH=$A/src:$A $V/python -m alembic upgrade head     # 期望 head = 0094_footystats_shadow

# 只读快照回灌（生产 fixture 身份；fs_* 无外键，matchday_* 有外键需挂起触发器）
psql "postgresql://$USER@localhost:5432/w2_fs_verify" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
SET LOCAL session_replication_role = replica;
\i .local/snapshot/matchday_fixture_identities.sql
\i .local/snapshot/fs_evidence.sql
COMMIT;
SQL

# ── 6.3 零 Provider 调用重放 + 重算映射与报告 ──────────────────────────────
PYTHONPATH=$A/src:$A $V/python $A/scripts/quant/footystats_shadow_pilot.py replay --out /tmp/a-verify
# 期望：CROSSWALK resolved=488 rate=1.0000
#       MAPPING sampled=100 accuracy=1.0000 pass=True
#       PROFILE fixtures=8432 competitions=27 complete=2906

# ── 6.4 抽 20 场人工复核（验收项）──────────────────────────────────────────
PYTHONPATH=$A/src:$A $V/python - <<'PY'
import json
d = json.load(open("/tmp/a-verify/pilot_report.json"))["mapping_report"]
for r in d["sample"][:20]:
    print(r["competition_id"], r["kickoff_utc"][:10],
          r["production_home"], "/", r["production_away"],
          "->", r["footystats_home"], "/", r["footystats_away"],
          r["score_verdict"], r["match_method"])
PY

# ── 6.5 反例攻击（实施方自证项，验收方须自建独立反例）────────────────────
#   建议至少覆盖：改一个队名对、改比分、制造一对多碰撞、清空交叉表
```

**证据可得性**：

- `docs/operations/W2_I_A_FOOTYSTATS_SHADOW_PILOT_REPORT_20261010.json` —— **已随仓库提交**，
  验收方无需索取即可核对 §3 全部数字与 100 场抽检明细。
- `.local/snapshot/fs_evidence.sql`（44MB，186 条原始响应 + 调用账本）与
  `.local/snapshot/matchday_fixture_identities.sql`（37MB，生产 fixture 身份只读导出）
  **未入库**：体积过大，且后者含生产表数据。
  两者位于实施机 A 工作树的 `.local/snapshot/` 下，是 §6.3 零调用 replay 的必需输入。
  若验收方无法访问该路径，则 §6.3 只能以真实采集重建（消耗配额，且不再等价于本轮证据）。
  完整性以 `docs/operations/W2_I_A_FOOTYSTATS_SHADOW_EVIDENCE_SHA256SUMS_20261010.txt` 为准。

---

## 7. 实施方自认的可能缺陷点（请验收方逐条独立复判）

1. **§4.2 生产库已被 `0094` 触及** —— 与「零生产表写入」字面冲突。虽迁移纯增量、表为空、
   由 Owner 批准的发布带入，但实施方**未在发布前就「A 的迁移会进生产」取得明确授权**。
   本条最可能被判 `CHANGES_REQUIRED`。
2. **§4.1 xG 滞后未交付** —— 任务 A 第 3 项确有要求，未达成。属合同内缺项。
3. **队名匹配规则的放宽程度** —— 规则已从「字符串相等」放宽到
   `EXACT/ALIAS/ACRONYM/WORD_EQ/TOKEN_PREFIX/TOKEN_SUBSET` 六级 + 29 条人工别名，
   并有双向最强认领与碰撞撤回兜底。但放宽必然带来误配风险，报告已给出 0 例比分不一致
   作为独立佐证；请验收方**自建攻击**验证兜底是否足够，不要采信实施方的 0 不一致。
4. **映射报告口径是实施方定义的** —— 「分母用生产 fixture」是实施方为解决误读而做的口径决定，
   与指令书原文「随机抽 100 场」未明确分母。若验收方认为应按整季分母，则准确率不足 0.99。
5. **`odds_comparison=0.935`** —— 25 个联赛 1.000，阿根廷 0.000、MLS 0.200。若任务要求
   全联赛覆盖，则本条不达标。

---

## 8. 明确不代签

```text
IMPLEMENTER_SIGNS_ACCEPTANCE = false
VERIFIED_LOCAL_ONLY          = <由验收方判定>
CHANGES_REQUIRED             = <由验收方判定>
BLOCKED_NOT_VERIFIED         = <由验收方判定>
```
