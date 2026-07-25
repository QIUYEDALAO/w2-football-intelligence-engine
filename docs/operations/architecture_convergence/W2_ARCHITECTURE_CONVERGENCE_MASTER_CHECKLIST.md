# W2 架构收敛与 EVAL 能力建设总清单（v3，唯一权威）

> 本文件是 W2 全部任务状态的**唯一权威**。旧版清单（v2 及更早）已整体废止，
> 其完整内容保留在本文件之前的 git 历史中，审计坐标见第二节台账。
> 老板 2026-07-24 决定：任务清单只保留本版本，不再维护旧清单文本。
>
> 维护规则：
> - 只有完整 CI 通过、必要的 staging 验收完成并合并后，才允许把 `[ ]` 改为 `[x]`。
> - 每个任务状态流转与 PR 强制说明格式见第七节。
> - 本文件的任何结构性修改（增删任务、改顺序、改红线）必须走 docs PR 并由老板合并。

---

## 一、基线（2026-07-24 核验）

- `github-w2/main` 顶端：`75e4993`（PR #388，ARCH-P1-04B 收尾）
- migration head：`0041_converge_odds_history_and_projection`
- 生产读取权威：`read_model_checkpoint`（API 纯投影读取，fail-closed）
- 赔率权威：`matchday_market_observations`（唯一历史）+ 当前盘口投影视图
- 竞赛配置权威：`league_profile` / `league_season`（DB 热切换）
- 安全开关：Formal / Lock / Production 关闭；`W2_PROVIDER_CALLS_DISABLED=true` 等熔断保持

---

## 二、已完成任务台账（审计坐标；实施细节见各 Merge SHA 的 git 历史与 PR）

| 任务 | PR | Merge SHA | 一句话结论 |
|---|---|---|---|
| ARCH-00 总清单建立 | #371 | `09ca14a9` | 清单与功能冻结红线入库 |
| ARCH-01 PR#370 收口 | #374 | `160a6750` | 已验证基线并入 main，PR #370 关闭 |
| ARCH-P0-01 报表读取删除 | #375 | `1e9e811d` | 生产 API 报表文件读取 = 0，静态守卫落地 |
| ARCH-P0-02 赔率读取收敛 | #376 | `dae21e59` | 唯一读取入口 `matchday_market_observations` |
| ARCH-P0-03 联赛白名单入库 | #377 | `7bd5088b` | DB 竞赛权威 + 热切换，JSON/env 业务覆盖删除 |
| ARCH-P0-04 P0 总验收 | #378 | `d62e3351` | P0_ARCHITECTURE_CONVERGENCE_PASS |
| ARCH-P1-01 僵尸表删除 | #379 | `76201af8` | 144→66 表，78 张僵尸表证据化删除（0038–0040） |
| P1-01 收口 + 清单修订 | #380 | `8af05ddb` | P1 顺序调整获批（04 拆分、03 后移、新增 07） |
| ARCH-P1-02 赔率表收敛 | #381 | `f53b073f` | 唯一 append-only 历史 + 投影视图（0041，断言式 drop） |
| HYGIENE 清单顺序修正 | #382 | `db3fd12f` | 清单序列一致性修正 |
| ARCH-HYGIENE-01 | #383 | `748b50e5` | 生成审计产物退出 Git |
| ARCH-HYGIENE-02 | #384 | `1e252d73` | Scripts 权威盘点与证据化删除（取代 P2-01） |
| ARCH-P1-04A 评估持久化 | #385 | `aa59b61d` | 事件驱动写侧投影管线（收口 #386 `46aa8d36`） |
| ARCH-P1-04B Dashboard 读切换 | #387 | `7ffdc0fe` | API 降为 988 行纯投影读取，生产 fallback = 0（收口 #388 `75e49930`） |
| ARCH-GOVERNANCE-01 双门禁 | #393 | `35fcac0d99573556c5e9f7a41822e153783efa73` | 可信 PRE/POST 门禁落地；独立 closure 收口 |
| ARCH-P1-04C 死代码清理+依赖守卫 | #395 | `6eeb411747a1cef624ff4780dbad87d4cec4b26d` | `_is_decision_tier`+F10 删除，INFRASTRUCTURE 依赖守卫；合同层三活跃链移交 04D |
| ARCH-P1-04D | #398 | `e6e447293365ca29686b21876cab5e103829b1ed` | canonical card 权威统一，五项兼容代码删除，`LEGACY_DECISION_CONTRACT_CODE=0` |

---

## 三、执行红线

### 永久红线（不随任何阶段解除）

1. 每个 PR 只解决一个清单任务，必须可独立回滚；不得自行并行化或跨任务顺手重构。
2. 不新增竞争性的事实表、配置文件或 fallback；每类事实只有一个权威。
3. 删除或 drop 前必须证明零读、零写、零任务、零报表、零外键阻塞；历史业务数据不删除。
4. drop migration 的 upgrade 必须先断言（count / 覆盖检查）再删除（0041 模式）。
5. Formal、Lock、Production 开关保持关闭；开放它们是独立的产品决定，不在本清单任何授权范围内。
6. Provider 熔断等安全环境变量不动。
7. 模型数学只允许在 EVAL-02B 门禁通过的解冻点上变化，其余一律不动。
8. 不以本地测试或 Markdown 报告代替 GitHub CI 和 staging 证据；不用 `[skip ci]` 作最终验收提交。
9. 状态只更新本文件；不再创建重复的日期型上下文文档。
10. 修改 decision contract 结构时，必须同步 `src/w2/domain/decision_contract.py` 校验器、
    `tests/contract/test_api_projection_read_authority.py` 守卫及全部合同测试。
11. 每个任务必须附**资产账本**：新增了哪些表/文件/配置（目标 0），删除了哪些。

### 冻结解除边界（老板 2026-07-24 全权授权，固化执行）

ARCH-P1-08 通过后，功能冻结部分解除：**仅允许本清单阶段 B 的任务（B1~B7、OPS-01）**，
逐字按各任务"范围/不做"执行。清单外的任何功能想法记入本文件末尾"待议区"，不实施。

### 已授权决策基准（到点直接执行，判定过程写入本文件，无需请示）

**（a）EVAL-01A 建表判定**：复用优先。先逐一核对 `results`、`settlements` 及 P1-08 裁决后的
`shadow_strategy_*`；只有（一）现有表无法承载 append-only 语义、（二）复用造成列语义扭曲、
（三）文件记录无法无损映射——三条**全部**成立时，才新建唯一一张 `outcome_ledger`。
建表须同 PR 完成迁移对账并删除文件路径，migration 带 downgrade，三条判定证据写入本文件。

**（b）EVAL-02 预注册参数（初值固化；修改只能通过新的预注册条目，禁止回溯调整）**：
- 分歧成因分类器：`movement_ev_share > 0.5` → `MOVEMENT_CREATED_DIVERGENCE`；
  `divergence_age_ratio ≥ 0.6` 且非 MOVED → `STABLE_DIVERGENCE`；其余 → `INDETERMINATE`（按 MOVED 保守处理）。
- δ 溢价：初始 0（只标注不拦截）。ADVISORY 层 canonical 已结算样本 ≥50 场后自动标定：
  δ = max(0, STRICT 与 ADVISORY 层 CLV 均值差的 80% bootstrap 置信下界)，加到 ADVISORY 的
  EV 准入门槛；每新增 50 场或每 90 天重标定。扣除 δ 后滚动 CLV ≤ 0 → 该层自动降为只出 WATCH。
- 首发增量门禁：每联赛×每市场配对样本 ≥120 场；门禁 = 配对 log loss 改善的
  95% bootstrap（10,000 次重采样）置信下界 > 0；严格时间顺序切分。通过即解冻，
  报告写入本文件生效；每 90 天或每新增 60 场滚动复验，置信区间包含 0 即自动回冻为 0。

---

## 四、执行顺序与任务规格（唯一有效任务列表）

任务必须严格按此顺序执行。每任务开工：`git fetch github-w2 main` 拉新分支，
本文件写 `Status: IN_PROGRESS`；完成 = 完整 CI + staging 验收 + 合并 + 状态翻 DONE。

### 执行与验收节奏

1. 子步骤只跑 focused tests；同一 exact head 的完整 CI 不重复执行。
2. 最终 exact head 一次性完成范围项、业务 delta=0、静态守卫、临时/生成资产清理、
   资产账本，并满足 untracked=0、未引用新文件=0、worktree clean。
3. 最终完整 CI 固定为 `verify`、`staging-parity`、`predeploy-e2e` 全部 PASS；
   exact head 变化才重跑。
4. 外部验收 PASS 后才能进入合并；合并前任务不得 DONE，后续任务不得启动。
5. 数据库 drop、数据迁移、部署、兼容链物理删除、安全开关和模型数学变更继续执行
   各自逐项高风险门禁。

### 阶段 A：架构收尾

---

#### A1. ARCH-GOVERNANCE-01：合并前就绪 + 合并后清单一致性双门禁

```text
Status: DONE
Branch: codex/arch-governance-01-closure
PR: #393
Merge SHA: 35fcac0d99573556c5e9f7a41822e153783efa73
Closure PR: #394
Closure exact head: GITHUB_PR_EXACT_HEAD
Base SHA: 91c7921574fcca249a9f1a9cf29c8c782e774930
Started at: 2026-07-24T17:12:33Z
Owner: Codex
Bootstrap required checks: verify + staging-parity
Final A1 required checks: verify + staging-parity + PRE_MERGE_READINESS_GATE +
  POST_MERGE_CHECKLIST_CONSISTENCY_GATE
Trusted execution: workflow + checker from main/base; PR head checklist is API-read data only
Protocol read: GITHUB_SECONDARY_REVIEW_PROTOCOL_V1
Task scope contract read: TASK_SCOPE_AND_REVIEW_BOUNDARY_V1
Implementation SHA: GITHUB_PR_EXACT_HEAD
Validated remediation head: 6bb10237bfa3d60f138cf76450b25c659f7e697a
Final receipt head: GitHub PR exact head
Stage 2 CI: 30116539839
Main bootstrap POST run: 30123415474 /
  FAIL_EXPECTED_MERGED_TASK_NOT_CLOSED:ARCH-GOVERNANCE-01:#393
Branch protection before API: {"strict":true,"contexts":["verify","staging-parity"],
  "checks":[{"context":"verify","app_id":15368},{"context":"staging-parity","app_id":15368}]}
Branch protection after API: {"strict":true,"contexts":["verify","staging-parity",
  "PRE_MERGE_READINESS_GATE","POST_MERGE_CHECKLIST_CONSISTENCY_GATE"],
  "checks":[{"context":"verify","app_id":15368},{"context":"staging-parity","app_id":15368},
  {"context":"PRE_MERGE_READINESS_GATE","app_id":15368},
  {"context":"POST_MERGE_CHECKLIST_CONSISTENCY_GATE","app_id":15368}]}
Branch protection rollback: `gh api --method PATCH
  repos/QIUYEDALAO/w2-football-intelligence-engine/branches/main/protection/required_status_checks
  -F strict=true -f 'contexts[]=verify' -f 'contexts[]=staging-parity'`
Staging SHA: NOT_APPLICABLE_GOVERNANCE_ONLY
Evidence: local 1609 passed / 4 skipped; governance matrix 58 passed; Stage 2 CI
  verify + staging-parity + predeploy-e2e PASS; bootstrap required contexts =
  verify + staging-parity; predeploy-e2e remains mandatory full CI but is not a
  branch-protection required context; branch protection strict = true;
  workflow contents-write/self-commit/push count = 0
Rollback: `git revert "$(gh pr view 393 --repo QIUYEDALAO/w2-football-intelligence-engine
  --json mergeCommit --jq .mergeCommit.oid)"`; then `gh api --method PATCH
  repos/QIUYEDALAO/w2-football-intelligence-engine/branches/main/protection/required_status_checks
  -F strict=true -f 'contexts[]=verify' -f 'contexts[]=staging-parity'`
One-time bootstrap:
  1. #393 仅在原 required checks（verify + staging-parity）与外部验收下合并。
  2. #393 合并后，workflow/checker 才成为 main 可信代码。
  3. 随即将 required contexts 更新为 verify + staging-parity +
     PRE_MERGE_READINESS_GATE + POST_MERGE_CHECKLIST_CONSISTENCY_GATE。
  4. 从最新 main 创建独立 `W2_PR_KIND: CLOSURE` 的 A1 closure PR，写入
     `Status: DONE`、台账 `#393` 与 GitHub 返回的完整 40 位 Merge SHA。
  5. closure PR 必须真实跑通 PRE 与 POST 两个新门禁。
  6. closure PR 合并且 main POST PASS 前，A1 不得 DONE，A2 不得启动。
```

独立治理 PR。前者阻止未获外部验收结论的 PR 提前合并；后者核验已合并 PR 与本清单
DONE/merge 坐标一致。两个 required check 缺一不可。

- [x] 双门禁落地为 required checks。
- [x] 完整 CI 通过并合并。

---

#### A2. ARCH-P1-04C：合同层与死代码清理

```text
Status: DONE
Branch: codex/arch-p1-04c-contract-dead-code-cleanup
PR: #395
Base SHA: c09c7d9130f709d488f87e5369735a8bde0584b4
Merge SHA: 6eeb411747a1cef624ff4780dbad87d4cec4b26d
Started at: 2026-07-24T21:00:00Z
Owner: Codex
Scope outcome: 范围经生产 trace 收敛（老板 2026-07-24 裁决）。合同层删除的
  三处目标经证明是活跃兼容链，本轮不删，移交新任务 ARCH-P1-04D；仅交付
  两处真死代码 + 依赖守卫。三条 scope correction 见下方。
```

**目标**：删除全部新旧合同并存代码与 04B 后确认的死代码；每处删除附零引用证据。

**执行结果（老板裁决后）**：`legacy_decision_shim.py`、`decision_adapter.py`
legacy→V3、`pricing_shadow` 兼容读、`_public_market_is_legacy_pick`/pre-LMM
分支——经生产 trace 证明**均为活跃兼容链**，非死代码，本轮**不删**，移交
`ARCH-P1-04D`。本任务实际交付：`_is_decision_tier`（死函数）+ F10_LINEUPS
死子图删除 + INFRASTRUCTURE 层依赖守卫。

**范围（逐项处理，允许 ≤3 个提交但同一 PR）**：
- [ ] ~~`legacy_decision_shim.py` 整文件删除~~ → 移交 ARCH-P1-04D（活跃兼容链，见 correction 3）。
- [ ] ~~`decision_adapter.py` legacy→V3 转换删除~~ → 移交 ARCH-P1-04D（同 correction 3）。
- [ ] ~~`analysis_calculator` pre-LMM 分支 + `_public_market_is_legacy_pick`~~ → 保留（活跃，见 correction 2）。
- [x] `day_view.py` 死函数 `_is_decision_tier` 删除（commit 1）。~~`pricing_shadow` 兼容读~~ → 保留（活跃源，见 correction 1）。
- [x] F10_LINEUPS 死子图删除 + LMM 登记为唯一 lineup 来源（commit 1）。
- [x] 全库死代码复核完成：三处原定删除项经生产 trace 证明为活跃兼容链，记录如下。
- [x] INFRASTRUCTURE 层依赖守卫（commit 2，DEPENDENCY_CONTRACT_V1）。

**三条范围纠偏（生产 trace 结论，老板 2026-07-24 裁决保留 + 移交）**：

```text
A2_SCOPE_CORRECTION_1:
  item: DAY_VIEW_PRICING_SHADOW_COMPAT_READ
  original_assumption: COMPATIBILITY_FALLBACK_WITH_SIMULATION_PRIMARY_PATH
  audit_result: ACTIVE_PRODUCTION_SOURCE
  evidence:
    - canonical top-level writer already existed:
      payload["simulation"] = simulation_output.as_dict()
    - 04C-era live Dashboard projection omitted that top-level field
    - public/formal/scoreline paths therefore still consumed pricing_shadow.simulation
    - retain until ARCH-P1-04D projection, reconciliation and read-authority migration complete
  decision: RETAIN
  production_behavior_changed: false
  follow_up: ARCH-P1-04D

A2_SCOPE_CORRECTION_2:
  item: PUBLIC_MARKET_LEGACY_PICK_CHAIN
  original_assumption: PRE_LMM_DEAD_CODE
  audit_result: ACTIVE_PICK_PATH_FOR_ANALYSIS_PICK_WITHOUT_MARKET_CANDIDATE
  evidence:
    - market_candidate write is conditional (analysis_calculator:5286)
    - _public_market_is_primary_pick requires market_candidate
    - test_dashboard_validates_analysis_pick_without_promoting_to_candidate depends on it
  decision: RETAIN
  production_behavior_changed: false
  follow_up: ARCH-P1-04D

A2_SCOPE_CORRECTION_3:
  item: LEGACY_DECISION_SHIM_AND_ADAPTER_LEGACY_TO_V3
  original_assumption: DEAD_CONTRACT_CONVERSION_1100_LINES
  audit_result: ACTIVE_PRE_LMM_COMPATIBILITY_CHAIN
  evidence:
    - recommendations.derive_recommendation_tier calls legacy_decision_view when
      _decision_tier_from_payload returns None (card without decision_tier)
    - reached from write side via build_recommendation (analysis_calculator:6193/6556)
    - card["decision_tier"] written on conditional/multi paths (may be absent)
    - same test as correction 2 depends on the legacy tier inference
    - same active chain as correction 2 (retaining zone 2 implies retaining shim)
  decision: RETAIN
  production_behavior_changed: false
  follow_up: ARCH-P1-04D
```

**不做**：不动 analysis_calculator 计算语义；不动 API；不动表。
**验收（本轮实际口径）**：`_is_decision_tier` 零引用；`F10_LINEUPS` 全库零引用；
INFRASTRUCTURE→{API,DASHBOARD,APPS} 守卫绿；全量测试与 04B 守卫绿。原
`LEGACY_DECISION_CONTRACT_CODE = 0` 与 `NET_DELETION ≥ 1100` **不适用本轮**——
合同层证明为活跃链，其删除是 ARCH-P1-04D 在 pre-LMM 契约迁移完成后的验收项。
**资产账本**：新增 0；删除 227 行（`_is_decision_tier` + F10 子图）。
- [x] PR 合并（#395，merge SHA `6eeb411747a1cef624ff4780dbad87d4cec4b26d`；
      closure #396，main POST run `30143083350` PASS）。

---

#### A9. ARCH-P1-04D：pre-LMM 契约迁移与兼容链删除（A2/04C 的后续拆分任务）

```text
Status: DONE
Branch: codex/arch-p1-04d-pre-lmm-contract-migration
PR: #398
Merge SHA: e6e447293365ca29686b21876cab5e103829b1ed
Base SHA: 9b2dc44bed22f237868d1471cbb8d9950917edcb
Implementation SHA: d9748a24b2359e8a642006af53e713baad236cb9
Started at: 2026-07-25T04:30:00Z
Owner: Codex
M1: DONE (Dashboard simulation projection, status-driven pass-through)
M2: DONE (frozen 8 MATCH; live LEGACY_ONLY=4 blocker found, MISMATCH=0)
M2_REMEDIATION: DONE (live _dashboard_card_from_matchday passes through canonical
  top-level simulation; live LIVE_MATCH=4, LEGACY_ONLY=0, MISMATCH=0)
M3: DONE (canonical simulation read authority implemented;
  LEGACY_PICK_RUNTIME_REACHABLE=0; LEGACY_SHIM_RUNTIME_REACHABLE=0;
  LEGACY_ADAPTER_RUNTIME_REACHABLE=0)
M4: DONE (five retained compatibility components
  physically deleted; LEGACY_DECISION_CONTRACT_CODE=0)
04D 整体为 DONE。
```

**由来**：A2（04C）经生产 trace 发现三处原定"死代码"实为活跃 pre-LMM 兼容链
（见 A2 的三条 scope correction）。它们服务于**缺少完整 decision_contract 的
card 形状**（无 `decision_tier` / `market_candidate` / 顶层 `simulation`）。删除
这些兼容链的前置是先让写侧所有 card 带完整契约，这是数据迁移，超出 04C
"不改生产行为"范围，故独立成任务。

**目标**：淘汰 pre-LMM card 形状，之后删除三条兼容链。

##### 写侧 trace 与只读盘点结论（2026-07-25，未改任何数据）

生产 card 写入路径全量 trace：

```text
canonical 生成器 build_decision_contract_fields
  （orchestrator:245 / analysis_calculator:6243）
  → 显式含 decision_tier / data_status / pick / non_pick        → 合规
手写降级卡 analysis_calculator:2166（frozen 不可用）
  → decision_tier=NOT_READY 全字段完整                          → 合规
frozen artifact writer read_model_projection.write_frozen_...
  → 走注入的 canonical 计算器                                    → 04B 后合规
真 simulation 计算 run_simulation（analysis_calculator:2720）一次，其输出
  直接写入 card 顶层：payload["simulation"] = simulation_output.as_dict()
  （analysis_calculator:2833）。**顶层 simulation 有真源，非反向重建。**
  （更正：设计初稿曾误记"顶层 simulation 全库无写入点"，因 grep 漏读 2833；
   实为 day_view 主路径已读 card["simulation"]，仅当其空时才 fallback 到
   pricing_shadow.simulation —— 后者是 04C correction 1 的兜底活链。）
run_simulation_from_shadow（:405, :6144）仅用于 build_formal_recommendation
  的反序列化重建，**不写顶层 simulation**；裁决禁止的"反向重建→顶层"本就
  不存在。
market 级 analysis_decision / market_candidate 条件写入
  （analysis_calculator:5296）→ legacy pick 兜底无 candidate 的
    ANALYSIS_PICK market（= 04C correction 2 的活链）
```

staging 只读盘点（read_model_checkpoint，8 个 frozen canary artifact）：

```text
FROZEN_ARTIFACTS_TOTAL            = 8
SCHEMA_ALL_CANONICAL             = 8/8  (w2.analysis-card.frozen.v1)
PRODUCTION_VALIDATE_OK           = 8/8  (validate_frozen_analysis_payload 无异常)
ARTIFACT_HASH_VALID              = PASS (8/8)   （payload 完整性）
SOURCE_HASH_VALID                = PASS (8/8)   （来源身份；与 artifact_hash 语义不同）
CARD_TOP_TIER_PRESENT            = 8/8  (WATCH×6, NOT_READY×1, ANALYSIS_PICK×1)
CONTRACT_TIER_PRESENT            = 8/8  (逐条与 card_top_tier 相同)
SIM_JSONB_EQUAL (full object)    = 8/8  true
TOP_SIM_OBJ_HASH == PSHADOW_OBJ  = 8/8  (canonical_sha256 全对象)
REACHABILITY_NOT_YET_EVALUATED   = M3_GATE
```

（artifact_hash 与 source_hash 语义不同，分别验证，不要求相等。可达性未评估：
未查证 public-reader/current-fixture 是否仍读取历史 artifact，故不主张
UNREACHABLE / CANNOT_REMATERIALIZE，判定锁 M3 gate。inventory fingerprint =
3a748382575ce8dd7f36184b7e15ebbd，仅身份指纹。完整证据见
W2_ARCH_P1_04D_FROZEN_ARTIFACT_INVENTORY.md。）

**关键结论**：8 条 frozen artifact 均为 canonical schema，顶层与嵌套 tier
逐条一致；顶层 simulation 与 pricing_shadow simulation **全对象 JSONB 逐条
相等**（md5 全对象 hash 相同，非仅计数）；simulation 为**单次计算**（上游
`run_simulation`
一次，`run_simulation_from_shadow` 仅反序列化重建，非独立计算），满足
`simulation_compute_count = 1` / `independent_simulation_writers = 0`。

##### 迁移设计（双写 → 对账 → 读切换 → 删旧读）

- M1 Dashboard projection 直接透传（不删旧，裁决第 1 点）：Dashboard/DayView
  projection 直接透传 `card["simulation"]`（其真源为 analysis_calculator:2833
  的 `simulation_output.as_dict()`，即 run_simulation 的一次计算）。
  **禁止** `run_simulation_from_shadow → 顶层 simulation` 的反向重建（该反向
  重建本就不存在，M1 以静态守卫固化"不得引入"）。simulation 必带明确状态
  （READY / UNAVAILABLE），无有效 simulation 时透传 UNAVAILABLE 而非回退
  pricing_shadow。不新增计算、不新增表、不新增运行权威。
- M2 对账：live + frozen 两层证明
  `top_level_simulation_hash == pricing_shadow_simulation_hash`；Dashboard/DayView
  逐场 hash 一致（`scoreline_simulations`、`recommendation.decision_tier`、
  ANALYSIS_PICK 不提升）。
- M3 读切换：`day_view._scoreline_simulations` 从 pricing_shadow 切到读顶层
  `simulation`；证明三条兼容链**零可达**。历史 frozen artifact 按裁决第 2 点：
  不可达→保留审计；可达且缺字段→用原始输入重新物化 canonical artifact 后
  切读取指针；无法物化→fail-closed 并阻止删链。可达性统一为
  `REACHABILITY_NOT_YET_EVALUATED = M3_GATE`，M3 须先补真实 public-reader /
  current-fixture 可达性查询后再据结果走三分支，不得预设任何触发数。
- M4 删旧读（仅当 M2/M3 全绿且零可达）：删 pricing_shadow 兼容读、
  `legacy_decision_shim.py`、adapter legacy→V3、`_public_market_is_legacy_pick`/
  pre-LMM 分支。

##### card contract version + validator（裁决第 4 点）

新增独立的 `analysis_card_contract_version`（如
`w2.analysis-card.contract.v1`），**与 frozen artifact 的 `schema_version`
`w2.analysis-card.frozen.v1` 正交，不改后者原语义**。frozen.v1 继续由
`validate_frozen_analysis_payload` 按原规则校验；新 contract version 是 card
读取契约层，validator 至少保证：显式 `decision_tier`；显式 public-market
selection **或**明确无选择状态（`market_candidate` 仍为可选证据，禁止伪造）；
顶层 `simulation` 字典含 READY/UNAVAILABLE 等明确状态。新 validator 作为 M1
的对账守卫接入 projection 透传路径，不追溯改写已固化的 frozen.v1 payload。

**范围**：
- [x] canonical card 契约（写/投影侧 card 无条件具备三项，validator 强制）：
      1. 显式 `decision_tier`；
      2. 显式 public-market selection **或**明确 `NONE` 状态；
      3. 顶层 `simulation` 字典含明确 `READY` / `UNAVAILABLE` 状态。
      `market_candidate` **仍为可选证据，禁止写成必需字段、禁止伪造**。
- [x] 对账：迁移前后 Dashboard/DayView 语义逐场 hash 一致（含
      `scoreline_simulations`、`recommendation.decision_tier`、ANALYSIS_PICK
      不提升语义）。
- [x] 读切换：确认 pre-LMM 兼容链不再可达（无 card 走 legacy 分支）。
- [x] 删除三条兼容链：`legacy_decision_shim.py` 整删；`decision_adapter.py`
      legacy→V3 转换删；`_public_market_is_legacy_pick`/pre-LMM 分支删；
      `day_view` `pricing_shadow` 兼容读删。
- [x] 更新依赖该三链的测试为现代契约形状。
- [x] 静态守卫：`LEGACY_DECISION_CONTRACT_CODE = 0`。

**不做**：不改模型数学；不改 EV/门槛/安全开关。
**验收**：`LEGACY_DECISION_CONTRACT_CODE = 0`；pre-LMM 兼容链全库零可达；
迁移前后语义 hash 一致；全量测试与守卫绿。
- [x] PR 合并（#398，merge SHA `e6e447293365ca29686b21876cab5e103829b1ed`）。

---

#### A3. ARCH-P1-03：球队身份 Crosswalk 收敛

```text
Status: NOT_STARTED
```

待收敛组：`football_data_team_crosswalks`、`team_identity_crosswalks`、
`provider_team_identity_crosswalks`、`player_identity_crosswalks`、`player_identity_mappings`。

- [ ] 盘点全部球队/球员身份与 provider crosswalk 表。
- [ ] canonical team / player 体系为唯一权威；迁移有效映射及 review provenance。
- [ ] 其余表停止写入，零引用证明后同 PR 断言式 drop；证据不足的保持原状继续调查。
- [ ] provider IDs 仅作 provenance，不再作为模型主身份。
- [ ] fixture、history、rating、lineup 读取对账。
- [ ] **追加**：用 3 场真实比赛演示 canonical player ↔ provider lineup 球员唯一联接查询
      （EVAL-02B"缺阵分钟占比"的前置能力）。
- [ ] PR 合并。
**验收**：`CANONICAL_TEAM_IDENTITY_AUTHORITY_COUNT = 1`。
**资产账本**：目标净减 ≥3 张表。

---

#### A4. ARCH-P1-05：部署改为 CI 构建镜像、服务器 pull-only

```text
Status: NOT_STARTED
```

- [ ] 4 个 Python Dockerfile 合并为 1 个多 target/多 command；Web 独立镜像保留。
- [ ] CI：测试 → BuildKit cache 构建 → 推 GHCR → 记录 SHA tag 与 digest → 镜像 smoke test。
- [ ] staging Compose 从 `build:` 改为不可变 digest `image:`。
- [ ] 服务器部署只执行 pull → migration job → restart → health → release record。
- [ ] 删除服务器上传源码、安装依赖、构建镜像的正式流程；回滚用上一 digest。
- [ ] 部署时间验证：Web-only ≤3 分钟；Python ≤5 分钟；rollback ≤2 分钟。
- [ ] PR 合并。

**验收**：`CI_IMAGE_BUILD_AUTHORITY = PASS`；`SERVER_BUILD_COUNT = 0`。

---

#### A5. ARCH-P1-06：Compose 环境变量去重

```text
Status: NOT_STARTED
```

- [ ] api/worker/scheduler 重复环境变量提取为 `x-common-env` anchor；服务级差异保留。
- [ ] 展开后环境变量对账；安全开关值不得变化。
- [ ] Compose config、CI、staging smoke 通过；PR 合并。

---

#### A6. ARCH-P1-07：竞赛域读路径修正

```text
Status: NOT_STARTED
```

- [ ] `src/w2/competitions/league_whitelist_scope.py` 模块级常量（`TOP_FIVE_COMPETITIONS` 等）
      改为函数调用，消除 import 时查库与热切换失效。
- [ ] 核查 audit/backtest 导入链上的其他 import-time 副作用。
- [ ] PR 合并。

---

#### A7. ARCH-P1-08：P1 总验收 + 终态重复盘点

```text
Status: NOT_STARTED
```

- [ ] 一套赔率历史 + 一套当前盘口投影 + 一套 canonical identity + Dashboard 单一 read model。
- [ ] CI 镜像发布；服务器 pull-only；无生产 fallback。
- [ ] **追加三条**：API 层无特征/定价/模拟 import（守卫常绿）；读路径 fail-closed
      （无隐式空数据 fallback）；legacy 决策合同代码为零。
- [ ] **终态盘点**：按 P1-01 矩阵方法对全部剩余表、runtime 目录、配置、账本终态盘点，
      每类事实指认唯一权威，矩阵写入本文件；发现双权威 = 不通过。
- [ ] **`shadow_strategy_*` 裁决**：零读零写零任务则按证据法独立 PR drop；
      EVAL-01A 要复用则明确登记。
- [ ] P1 完整 CI 与 staging 验收；人工验收；PR 合并。

**完成标准**：`P1_ARCHITECTURE_CONVERGENCE_PASS`

---

#### A8. 阶段 P2：卫生治理（可与阶段 B 穿插，不得抢占 EVAL-01 序列）

**ARCH-P2-02 Docs 整理**
- [ ] 日期型一次性证据移入 `docs/archive/`；同一审计只留最新权威版；旧文档标 `SUPERSEDED_BY`。
- [ ] PR 合并。

**ARCH-P2-03 本地垃圾清理**（只清开发机，不进业务 PR）
- [ ] `.worktrees/`、过期 `.local/`、废弃 `runtime/` stage 目录、无用本地分支；记录释放空间。

**ARCH-P2-04 项目状态记录收敛**
- [ ] `PROJECT_STATE.yaml` 唯一机器可读状态；`PROJECT_LEDGER.md` 只记人工决定。
- [ ] `NEXT_ACTION.md` 改为链接本清单或删除；SHA/CI 不再多文档重复维护。
- [ ] 本清单任务回执压缩为 CI run 号 + merge SHA + 一行结论。
- [ ] PR 合并。

**ARCH-P2-06 `src/w2` 一级包角色与依赖矩阵**
- [ ] 逐包矩阵（package/callers/依赖/循环/镜像包含/role/decision/evidence），全包覆盖不抽样。
- [ ] `replay`、`data_assets`、`migration`、`audit_export` 先标 `OFFLINE_TOOL` 候选，不得直接判 DEAD。
- [ ] 只有证据充分的 `DEAD` 可删；PR 合并。

**ARCH-P2-05 最终架构收敛验收**
- [ ] P0/P1/P2 全部完成；无竞争权威；无生产 fallback；无服务器源码构建；
      所有 drop 有直接证据；完整 CI 与 staging 验收；老板最终验收。

**最终状态**：`W2_ARCHITECTURE_CONVERGENCE_COMPLETE`

---

### 阶段 B：EVAL 能力建设（ARCH-P1-08 通过后启动）

> 总目标：闭合"赛果→表现→反馈"回边，每场比赛（而非每次推荐）都产生可信度量；
> 首发因子两面处理：有首发的联赛验增量，无首发的联赛防逆向选择。

---

#### B1. EVAL-01A：赛果与结算账本数据库化

```text
Status: NOT_STARTED
```

**目标**：赛果获得 DB 唯一权威；runtime 文件账本（最后一块文件飞地）迁入 DB 并删除。

- [ ] **赛果权威 = 现有 `results` 表**（不新建）。新增 worker 任务：FINISHED 后从**已采集**的
      provider fixture 数据（`raw_payload` / matchday 采集链的 FT 状态与比分）提取
      `MatchResult` 写入 `results`。**不新增任何 provider 调用**；缺比分场次记
      `RESULT_SOURCE_MISSING`，不补采。
- [ ] **runtime 账本迁移**：`runtime/forward_outcome_ledger/*` 与
      `src/w2/tracking/formal_results.py` 的文件读写（11、26 处）迁入 DB；
      建表与否按第三节授权基准 (a) 执行，判定证据写入本文件。
      迁移行数+hash 对账后**同一 PR** 删除文件读写路径，`runtime/` 不再有账本目录。
- [ ] `src/w2/settlement/settle.py` 消费 DB `results`；`forward_ledger_performance`
      记录来源改为 DB 查询（调用方 `analysis_calculator.py` 语义不动）。

**不做**：不改 CLV/命中率计算逻辑；不动 canonical 样本定义；不做 Dashboard。
**验收**：`RESULTS_DB_AUTHORITY_COUNT = 1`；`RUNTIME_LEDGER_FILE_IO = 0`（静态守卫，
模式同 `test_production_report_reads.py`）；迁移对账一致；老板可见的历史表现数字不漂移。
**资产账本**：新增 ≤1 表（按基准判定）；删除 runtime 账本目录 + 文件 IO 代码。
- [ ] PR 合并。

---

#### B2. EVAL-01B：全量校准评分投影

```text
Status: NOT_STARTED
```

**目标**：每场 FINISHED 比赛自动产生"模型 vs 市场"评分——不管推没推荐。

- [ ] 触发：EVAL-01A 赛果写入事件（复用 04A 事件→投影模式，不建新管线框架）。
- [ ] 输入：该 fixture 开赛前**最后一次** `dynamic_prematch_evaluations` 评估
      （`model_probabilities` + `market_probabilities`）+ `results` + picks 的 CLV
      （复用 `forward_ledger_performance.py` 的 `CLV_METHOD` 与 `_log_loss`，禁止重写公式）。
- [ ] 输出（全部落 `read_model_checkpoint`，不建新表）：
      `performance:fixture:{id}`（双方 log loss/Brier/RPS、CLV、联赛、STRICT/ADVISORY 分层标签）；
      `performance:cohort:{scope}`（按联赛/分层/7-30-90 天窗口滚动聚合，含样本计数）。
- [ ] 幂等：同一 fixture 重算 hash 一致；投影带 projection_version/source_event。

**不做**：不做 UI；不做任何"评分→参数"自动反馈（那是 EVAL-02B 门禁的事）。
**验收**：staging 全部已完结且有评估记录的比赛 100% 产生 `performance:fixture:*`；
抽 5 场人工复算一致；API 守卫不变绿（评分在写侧）。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B3. EVAL-01C：Dashboard 表现视图（CLV 第一 KPI）

```text
Status: NOT_STARTED
```

- [ ] API/Web 只读表现页，仅读 `performance:*` 投影：
      ① CLV 第一位（canonical picks 分布、均值与置信区间、正 CLV 占比）；
      ② 全量校准（model vs market 滚动 log loss 差、校准曲线）；
      ③ STRICT vs ADVISORY 分层表（命中率、CLV、样本数并列）；
      ④ 样本进度条（对照预注册目标；未达标时命中率旁强制"样本不足"标注）。
- [ ] 前端不做任何概率/指标重算（04B 守卫覆盖 `apps/web/src`，保持绿）。

**验收**：页面数字与投影逐项一致；20 轮只读零写；15/30 场视觉验收。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B4. EVAL-02A：首发盲区防护（防守面，先于增量验证）

```text
Status: NOT_STARTED
```

**目标**：ADVISORY 联赛（无赛前首发）的 pick 不再裸奔；盲区里"模型大幅打赢市场"按逆向选择风险处理。

- [ ] **分歧成因分类器**（写侧 `analysis_calculator`）：用 `matchday_market_observations`
      timeline 计算 `divergence_age_ratio` 与 `movement_ev_share`，按第三节授权基准 (b)
      固化阈值输出三态标签。
- [ ] **降级规则**：ADVISORY + `MOVEMENT_CREATED_DIVERGENCE` → 强制 `WATCH`，
      reason `MARKET_MOVED_AGAINST_BLIND_SPOT`。
- [ ] **风险披露**：decision contract reason 结构新增 `LINEUP_UNOBSERVABLE`
      （ADVISORY 联赛所有卡携带）；按永久红线 10 同步校验器与守卫；
      新增字段不是语义变更，pick/non-pick 互斥不动。
- [ ] **轮换先验**：用赛后阵容记录为 ADVISORY 联赛建基线与球队轮换率
      （复用 `build_team_baseline`）；高轮换球队盲区比赛追加 `HIGH_ROTATION_PRIOR`。
- [ ] **赛后归因**：`performance:fixture:*` 追加赛后首发相对基线偏离度，
      "输给轮换"与"输给运气"分开统计。
- [ ] **δ 溢价**：本任务 δ=0 只标注；标定与生效按第三节授权基准 (b) 自动执行，
      结果写入本文件即生效。

**不做**：不动 STRICT 联赛逻辑；不改 EV 公式；不解冻任何数值调整。
**验收**：ADVISORY 卡 100% 携带 `LINEUP_UNOBSERVABLE`；重放一场"移动产生分歧"样例
验证降级 WATCH；合同守卫全绿；分层统计出现盲区归因字段。
**资产账本**：新增 0；删除 0。
- [ ] PR 合并。

---

#### B5. EVAL-02B：首发增量门禁验证（进攻面，样本驱动）

```text
Status: NOT_STARTED
前置：A2（F10 已删）、A3（球员身份可联接）、B2（评分基建）、
      每联赛 LINEUP_CONFIRMED 配对评估历史 ≥120 场
```

- [ ] **Tier-1 特征集（仅这四个，禁止顺手加特征）**：缺阵球员上季+本季出场分钟占比；
      按位置组（GK/DEF/MID/FWD）缺阵价值占比；XI 连续性计数（最近 5 场首发过的人数）；
      阵型变化标志。全部从 `structured_lineup_players`、`team_lineup_baselines`、
      Transfermarkt 估值链计算。
- [ ] **配对样本**：同一 fixture 的 `LINEUP_CONFIRMED` 前后两次持久化评估（04A 天然产生）。
- [ ] **门禁**：现有 `lineups/evaluation.py::evaluate_market_adjustment`（禁止重写框架），
      按联赛×市场跑，参数按第三节授权基准 (b)。
- [ ] **解冻**：仅通过门禁的联赛×市场，把 `analysis_calculator.py` / `prematch/repository.py`
      中 `lineup_ah_adjustment / lineup_totals_adjustment` 的硬编码 0 替换为计算值；
      报告写入本文件即生效；滚动复验含 0 自动回冻。
- [ ] 预注册文档先于实验提交。

**资产账本**：新增 0；删除 0。
- [ ] PR 合并（可多个 PR：预注册 → 门禁报告 → 解冻，各自独立回滚）。

---

#### B6. OPS-01：联赛扩容 Runbook（A3 后随时可执行，与 B 序列并行）

```text
Status: NOT_STARTED
```

- [ ] 固定流程 runbook 存 `docs/runbooks/`：seed 导入 profile/season → crosswalk 身份
      建立与 review → `league_readiness_audit` 核验 → `--set-enabled true` →
      观察 7 天数据完整性 → 归入 ADVISORY 或 STRICT 分层。
- [ ] 配额约束：启用前用 `quota_usage` 现值测算新增请求量，超预算联赛排队。
- [ ] 每联赛执行记录追加到本文件。

---

#### B7. EVAL-03：OU 正式链路泛化（Market Candidate Contract）

```text
Status: NOT_STARTED
```

- [ ] `strategy/formal_recommendation.py` 从只读 `canonical_ah_market` 泛化为市场无关
      candidate 接口，AH/OU 同构（报价身份、新鲜度、概率、EV、不确定性、结算契约同一套）。
- [ ] Formal 总开关保持关闭——只消除结构不对称，不开放任何推荐（永久红线 5）。
- [ ] AH/OU 走同一 candidate 校验路径的单元与合同测试；开关值不变的静态断言；
      影子模式下 OU candidate 可走到被开关拦截前的最后一步。
- [ ] PR 合并。

---

### 模型升级（EVAL-03 之后，另行立项，不在本清单）

Dixon-Coles、市场混合权重校准等，必须过 EVAL-01 门禁（时间切分+预注册+全量校准对比）。

---

## 五、闭环论证（全部完成后的链路）

```text
采集(scheduler→worker→DB)
→ 事件(ODDS_CHANGED / LINEUP_CONFIRMED)          [04A，已闭合]
→ 评估+持久化(analysis_calculator→evaluations)    [04A，已闭合]
→ 投影(read_model_checkpoint)                     [04A/04B，已闭合]
→ 展示(API/Web 只读, fail-closed)                 [04B，已闭合]
→ 赛果(results 表 DB 权威)                        [EVAL-01A 闭合]
→ 评分(performance:* 全量 log loss/Brier/CLV)     [EVAL-01B 闭合]
→ 展示回望(CLV KPI/分层/进度)                     [EVAL-01C 闭合]
→ 反馈(门禁裁决→参数解冻/溢价标定/联赛准入)       [EVAL-02A/02B/OPS-01 闭合]
→ (改进后的评估进入下一轮采集评估)                 [环路回到顶部]
```

## 六、资产账本总表

| 方向 | 内容 |
|---|---|
| 新增表 | 目标 0；唯一例外 EVAL-01A `outcome_ledger`（三条判定基准全满足才建） |
| 新增文件权威 | 0（永久红线 2） |
| 删除 | legacy shim/adapter（A9/ARCH-P1-04D）、F10 死代码（A2）、≥3 张 crosswalk（A3）、runtime 账本目录（B1）、`shadow_strategy_*` 僵尸表（A7 裁决后） |
| 防回流 | 每任务静态守卫测试；A7 终态盘点矩阵；GOVERNANCE-01 双门禁；PR 8 问模板 |

## 七、任务状态与 PR 强制说明格式

状态流转（追加在对应任务下）：

```text
开工:   Status: IN_PROGRESS / Branch / PR / Base SHA / Started at / Owner
阻塞:   Status: BLOCKED / Blocker / Evidence / Next required decision
待验收: Status: IMPLEMENTED_PENDING_ACCEPTANCE / Implementation SHA / CI run / Staging SHA / Evidence / Rollback
完成:   Status: DONE / Merged PR / Merge SHA / CI run / Staging acceptance / Completed at
```
每个 PR 描述必须回答：

```text
1. 本 PR 删除了哪个事实来源、fallback 或重复路径？
2. 是否新增数据库表？（除 EVAL-01A 授权基准情形外，是=违反红线，停止）
3. 是否新增配置文件？若是，说明为什么不是新运行权威。
4. 唯一业务范围是什么？
5. 如何回滚？
6. old/new 如何对账？
7. Provider/Formal/Lock/Production 开关是否不变？
8. 完整 CI 与 staging 证据在哪里？
```

立即停止条件：一个 PR 跨两个任务；新增竞争权威；删除仍有读写的数据；未断言就 drop；
放宽安全开关；清单外修改模型数学；CI 未过；staging 对账失败；历史数据 hash/count 异常。
停止后在本文件记 `BLOCKED`，不得自行绕过。

## 八、待议区（记录不实施）

- A2 死代码复核中"证据不足"的疑似项（记录后由后续 P2-06 矩阵裁决）。
- **RESOLVED 2026-07-25**：`PROJECT_STATE.repository` 已在 ARCH-P1-04C closure-integrity
  remediation 中同步到 PR #397、base/main `9b2dc44bed22f237868d1471cbb8d9950917edcb`。

---

## 九、机器合同附录：Scripts 权威矩阵

> 本附录是 ARCH-HYGIENE-02 已验收的机器可读合同，不是任务状态副本；任务状态仍只由本文件第四节维护。

<!-- SCRIPT_AUTHORITY_MATRIX_START -->
| path | 唯一分类 | 直接调用方 | 传递调用链 | 运行环境 | 部署引用 | 运维文档 | 决定 | 证据 |
|---|---|---|---|---|---|---|---|---|
| `apps/api/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.api / Compose Uvicorn | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/scheduler/main.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.scheduler / Compose `python -m` | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `apps/web/scripts/write-meta.mjs` | `DEPLOYMENT` | package.json predev/prebuild | npm → script | build | 是 | 无 | `KEEP` | E3 |
| `apps/worker/celery_app.py` | `RUNTIME_ENTRYPOINT` | Dockerfile.worker / Compose Celery | config → process | runtime | 是 | 无 | `KEEP` | E3/E5/E6 |
| `migrations/env.py` | `MIGRATION_ONLY` | alembic.ini / Alembic CLI | Alembic → env | migration | 否 | 无 | `KEEP` | E5/E6 |
| `scripts/audit_football_data_co_uk.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_formal_ah_historical_sources.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_market_mainline_ladder.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_pr370_totals_quarter_ev.py` | `ONE_TIME_RECOVERY` | 人工审核后重算 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/audit_transfermarkt_asset.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/audit_w2_runtime_authorities.py` | `MANUAL_OPS` | 人工审计生成；unit test 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/build_canonical_historical_ah_facts.py` | `ONE_TIME_RECOVERY` | 人工历史重建 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/build_fah_approval_package.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/build_stage5_demo_datasets.py` | `ONE_TIME_RECOVERY` | 人工历史数据重建 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/build_stage7i_final_evidence.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/build_stage7i_successor_candidates.py` | `MANUAL_OPS` | 人工 CLI；unit test 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/capture_runtime_release_evidence.py` | `DEPLOYMENT` | 发布证据人工 CLI | operator → script | staging | 否 | 无 | `KEEP` | E3 |
| `scripts/capture_stage7i_fixture_lifecycle.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/check_architecture_governance.py` | `CI_DIRECT` | architecture-governance.yml | GitHub CI → script | CI | 是 | 无 | `KEEP` | E2/E3/E5 |
| `scripts/check_boss_console_baseline.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | 无 | `KEEP` | E2/E3 |
| `scripts/check_compose_staging_ports.py` | `DEPLOYMENT` | deploy_stage7h / predeploy smoke | operator/CI → script | staging/CI | 是 | STAGE7H_VPS_STAGING | `KEEP` | E3/E4/E5 |
| `scripts/check_dashboard_v2_baseline.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_public_ingress.py` | `CI_TRANSITIVE` | test_public_ingress_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_team_values_mapping.py` | `MANUAL_OPS` | W2_TEAM_VALUES_MAPPING | operator → script | offline | 否 | W2_TEAM_VALUES_MAPPING | `KEEP` | E4/E5 |
| `scripts/check_tracked_outputs.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4/E5 |
| `scripts/check_w2_acceptance.py` | `MANUAL_OPS` | W2_ACCEPTANCE_RUNBOOK | operator → script | local | 否 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E4/E5 |
| `scripts/check_w2_all.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4 |
| `scripts/check_w2_analysis_governance.py` | `CI_TRANSITIVE` | test_analysis_governance.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_formal_tracking.py` | `MANUAL_OPS` | W2_FORMAL_TRACKING | operator → script | ops | 是 | W2_FORMAL_TRACKING | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_future_refresh_staging_contract.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | 无 | `KEEP` | E2/E3/E5 |
| `scripts/check_w2_gate5_preflight.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_league_remediation_readiness.py` | `MANUAL_OPS` | league remediation doc | operator → script | offline | 否 | league remediation doc | `KEEP` | E4/E5 |
| `scripts/check_w2_market_timeline.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_production_readiness.py` | `MANUAL_OPS` | API image / packaging test | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_s2_readiness.py` | `CI_TRANSITIVE` | test_w2_handicap_walkforward_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_stage10a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage10b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage10c.py` | `MANUAL_OPS` | STAGE10C_DAILY_OPERATIONS | operator → script | ops | 否 | STAGE10C_DAILY_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_stage10d.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage11a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage12a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage12b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage13a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | WORLD_CUP_DRY_RUN | `KEEP` | E2/E4 |
| `scripts/check_w2_stage14a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage15a.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | LONG_TERM_OPERATIONS | `KEEP` | E2/E4 |
| `scripts/check_w2_stage1_contracts.py` | `CI_DIRECT` | ci.yml / check_w2_all | CI → script | CI | 是 | LOCAL_DEVELOPMENT | `KEEP` | E2/E3/E4/E5 |
| `scripts/check_w2_stage3_data_model.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | README | `KEEP` | E2/E4/E5 |
| `scripts/check_w2_stage4_ingestion.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/check_w2_stage4b_live_smoke.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | LIVE_INGESTION_VERIFIED | `KEEP` | E2/E4 |
| `scripts/check_w2_stage5_asof.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage5b.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage6_market.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage6b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7_models.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage7b.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage7c.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | FORWARD_HOLDOUT_CYCLE | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7d.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | FORWARD_HOLDOUT_AUTOMATION | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7e.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | STAGE7E_AUTORUN_OPERATIONS | `KEEP` | E2/E4 |
| `scripts/check_w2_stage7f.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7g.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/check_w2_stage7h.py` | `DEPLOYMENT` | deploy_stage7h_staging.sh | operator → deploy → script | staging | 是 | STAGE7H_VPS_STAGING | `KEEP` | E3/E4/E5 |
| `scripts/check_w2_stage7i.py` | `MANUAL_OPS` | 人工 CLI；integration tests 验证 | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/check_w2_stage8_replay.py` | `CI_TRANSITIVE` | check_w2_all.py | CI → all → script | CI | 否 | 无 | `KEEP` | E2 |
| `scripts/check_w2_stage9a.py` | `MANUAL_OPS` | STAGE9A_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9A_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/check_w2_stage9b.py` | `DEAD` | 无 | 无 | none | 否 | 无 | `DELETE` | D1/D2 |
| `scripts/debug_w2_formal_market.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/debug_w2_formal_recommendations.py` | `CI_TRANSITIVE` | test_formal_explainability_audit.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/debug_w2_modeling_sanity.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/debug_w2_s2_calibration_validation.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/deploy_stage7h_staging.sh` | `DEPLOYMENT` | staging runbooks | operator → script | staging | 否 | STAGE7H_VPS_STAGING / HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/diagnose_staging_runtime.sh` | `DEPLOYMENT` | STAGING_RUNTIME_HARDENING | operator → script | staging | 否 | STAGING_RUNTIME_HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/export_w2_audit_tables.py` | `MANUAL_OPS` | audit export runbook | operator → script | ops | 是 | w2_audit_table_export | `KEEP` | E3/E4/E5 |
| `scripts/export_w2_world_cup_team_ids.py` | `MANUAL_OPS` | W2_TEAM_VALUES_MAPPING | operator → script | offline | 否 | W2_TEAM_VALUES_MAPPING | `KEEP` | E4/E5 |
| `scripts/generate_release_gate_manifest.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/generate_w2_report.py` | `MANUAL_OPS` | HTML dashboard acceptance doc | operator → script | offline | 否 | W2_HTML_DASHBOARD_V3_ACCEPTANCE | `KEEP` | E4/E5 |
| `scripts/import_stage5b_historical_data.py` | `ONE_TIME_RECOVERY` | 人工历史导入 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/import_team_identity_crosswalk.py` | `ONE_TIME_RECOVERY` | 人工 crosswalk 导入 | operator → script | offline | 否 | 无 | `KEEP` | E7 |
| `scripts/ingest_football_data_co_uk.py` | `MANUAL_OPS` | FOOTBALL_DATA_INGEST_TEMPLATE | operator → script | offline | 否 | FOOTBALL_DATA_INGEST_TEMPLATE | `KEEP` | E4 |
| `scripts/inventory_existing_football_data.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/lmm_coverage_audit.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/lmm_materialize_stored_lineups.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/lmm_transfermarkt_snapshot.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/materialize_analysis_card_canary.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/materialize_captured_matchday_odds.py` | `ONE_TIME_RECOVERY` | 人工 odds 恢复 | operator → script | staging manual | 否 | PR370 closure report | `KEEP` | E4/E7 |
| `scripts/materialize_team_value_asof.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/preflight_runtime_writable.py` | `DEPLOYMENT` | staging parity tests | CI/operator → script | staging/CI | 否 | 无 | `KEEP` | E3/E5 |
| `scripts/probe_analysis_chain.py` | `MANUAL_OPS` | PR370 acceptance docs | operator → script | staging read-only | 否 | PR370 acceptance docs | `KEEP` | E4 |
| `scripts/project_stage10b_live_snapshot.py` | `MANUAL_OPS` | STAGE10B_DASHBOARD_LIVE_WIRING | operator → script | offline | 否 | STAGE10B_DASHBOARD_LIVE_WIRING | `KEEP` | E4 |
| `scripts/project_stage10c_matchday_read_model.py` | `CI_TRANSITIVE` | test_stage10c_matchday.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/publish_w2_static_report.py` | `MANUAL_OPS` | A-151 static report runbook | operator → script | ops | 是 | A-151_STATIC_REPORT_WEB_ROOT | `KEEP` | E3/E4/E5 |
| `scripts/reconcile_pr370_validation_ledger.py` | `ONE_TIME_RECOVERY` | 人工 ledger 恢复 | operator → script | staging manual | 否 | 无 | `KEEP` | E7 |
| `scripts/recover_staging_runtime.sh` | `DEPLOYMENT` | STAGING_RUNTIME_HARDENING | operator → script | staging | 否 | STAGING_RUNTIME_HARDENING | `KEEP` | E3/E4/E5 |
| `scripts/render_ai_card_text.py` | `MANUAL_OPS` | README / stage1 contract | operator → script | local | 否 | README | `KEEP` | E4/E5 |
| `scripts/replay_provider_fixture.py` | `MANUAL_OPS` | INGESTION_OFFLINE_REPLAY | operator → script | offline | 否 | INGESTION_OFFLINE_REPLAY | `KEEP` | E4/E5 |
| `scripts/run_fah_master_pipeline.py` | `MANUAL_OPS` | FAH data handoff | operator → script | offline | 否 | W2_FAH_PRIVATE_DATA_HANDOFF | `KEEP` | E4 |
| `scripts/run_predeploy_e2e_smoke.sh` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | PR370 deployment context | `KEEP` | E2/E3/E4 |
| `scripts/run_prematch_refresh.py` | `CI_TRANSITIVE` | test_prematch_refresh_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_readiness_fault_injection.sh` | `DEPLOYMENT` | hardening test harness | operator/test → script | staging | 否 | 无 | `KEEP` | E3/E5 |
| `scripts/run_stage10c_daily_cycle.py` | `MANUAL_OPS` | STAGE10C_DAILY_OPERATIONS | operator → script | ops | 否 | STAGE10C_DAILY_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage11a_backup_restore_drill.py` | `MANUAL_OPS` | 人工 CLI / stage11 checker reads | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage12a_migration_dry_run.py` | `MIGRATION_ONLY` | check_w2_stage12a | CI checker → script contract | migration | 否 | 无 | `KEEP` | E6 |
| `scripts/run_stage12a_shadow_dry_run.py` | `MANUAL_OPS` | 人工 CLI / stage12 checker reads | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage12b_shadow_comparison.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage13a_world_cup_dry_run.py` | `MANUAL_OPS` | WORLD_CUP_DRY_RUN | operator → script | offline | 否 | WORLD_CUP_DRY_RUN | `KEEP` | E4 |
| `scripts/run_stage14a_league_audit.py` | `MANUAL_OPS` | whitelist workorder | operator → script | offline | 否 | W2_WHITELIST_TECH_WORKORDER | `KEEP` | E4/E5 |
| `scripts/run_stage15a_operations_dry_run.py` | `MANUAL_OPS` | LONG_TERM_OPERATIONS | operator → script | offline | 否 | LONG_TERM_OPERATIONS | `KEEP` | E4 |
| `scripts/run_stage4b_live_smoke.py` | `MANUAL_OPS` | LIVE_INGESTION_VERIFIED | operator → script | ops | 否 | LIVE_INGESTION_VERIFIED | `KEEP` | E4 |
| `scripts/run_stage6_market_backtest.py` | `MANUAL_OPS` | stage6 checker reads / 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage7i_observer.py` | `MANUAL_OPS` | 人工 CLI；unit tests | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/run_stage8_replay.py` | `MANUAL_OPS` | stage8 checker reads / 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_stage9a_shadow_replay.py` | `MANUAL_OPS` | STAGE9A_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9A_SHADOW_OPERATIONS | `KEEP` | E4/E5 |
| `scripts/run_stage9b_shadow_cycle.py` | `MANUAL_OPS` | STAGE9B_SHADOW_OPERATIONS | operator → script | offline | 否 | STAGE9B_SHADOW_OPERATIONS | `KEEP` | E4 |
| `scripts/run_w2_ah_formal_evidence.py` | `CI_TRANSITIVE` | test_w2_ah_formal_evidence_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_factor_model_remediation.py` | `ONE_TIME_RECOVERY` | 人工 remediation 恢复 | operator → script | staging manual | 否 | 无 | `KEEP` | E7 |
| `scripts/run_w2_formal_tracking.py` | `MANUAL_OPS` | W2_FORMAL_TRACKING | operator → script | ops | 是 | W2_FORMAL_TRACKING | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_forward_outcome_ledger.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_free_tier_2024_backtest.py` | `MANUAL_OPS` | league evaluation docs | operator → script | offline | 否 | PL/Understat evaluation docs | `KEEP` | E4 |
| `scripts/run_w2_handicap_walkforward.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_independent_signal_backfill.py` | `ONE_TIME_RECOVERY` | 人工 backfill | operator → script | staging manual | 是 | 无 | `KEEP` | E3/E5/E7 |
| `scripts/run_w2_league_whitelist_audit.py` | `MANUAL_OPS` | competition README / tests | operator → script | offline | 否 | competition README | `KEEP` | E4/E5 |
| `scripts/run_w2_market_baseline_eval.py` | `MANUAL_OPS` | architecture review docs | operator → script | offline | 否 | W2_MARKET_BASELINE_EVAL | `KEEP` | E4 |
| `scripts/run_w2_market_timeline_refresh.py` | `MANUAL_OPS` | market timeline runbook | operator → script | ops | 是 | W2_MARKET_TIMELINE_LOCK_SNAPSHOTS | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_matchday_refresh_plan.py` | `CI_TRANSITIVE` | test_matchday_refresh_plan_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_outcome_result_refresh.py` | `MANUAL_OPS` | 人工 CLI | operator → script | ops | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_w2_pro_day1_sprint.py` | `MANUAL_OPS` | S13 odds probe doc | operator → script | offline | 否 | W2_S13_ODDS_PROBE | `KEEP` | E4 |
| `scripts/run_w2_r2_offline_evaluation.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/run_w2_replay_frontdoor.py` | `CI_TRANSITIVE` | test_replay_frontdoor_cli.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/run_w2_report_runner.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_w2_settlement_history.py` | `MANUAL_OPS` | API image / tests | operator → script | ops | 是 | 无 | `KEEP` | E3/E4/E5 |
| `scripts/run_xg_history_backfill.py` | `ONE_TIME_RECOVERY` | 人工历史 xG 回填 CLI | operator → script | offline recovery | 否 | 无 | `KEEP` | E7 |
| `scripts/seed_competition_runtime_authority.py` | `MANUAL_OPS` | 人工 competition authority CLI（production 默认值 / `--set-enabled`） | operator → script | ops | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/seed_staging_dashboard.py` | `ONE_TIME_RECOVERY` | 人工 staging 恢复 | operator → script | staging manual | 否 | W2_RELEASE_SYNC | `KEEP` | E4/E7 |
| `scripts/select_stage7i_successor.py` | `MANUAL_OPS` | 人工 CLI；unit tests | operator → script | offline | 否 | 无 | `KEEP` | E4/E5 |
| `scripts/smoke.py` | `MANUAL_OPS` | Makefile | operator → make → script | local | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/summarize_w2_league_audit_diagnosis.py` | `CI_TRANSITIVE` | league evidence tests | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/summarize_w2_league_provider_usage.py` | `MANUAL_OPS` | provider usage doc | operator → script | offline | 否 | W2_PROVIDER_USAGE_RECONCILIATION | `KEEP` | E4/E5 |
| `scripts/summarize_w2_league_whitelist_scope.py` | `CI_TRANSITIVE` | test_league_whitelist_full_scope.py | CI → Pytest → script | CI | 否 | 无 | `KEEP` | E2/E5 |
| `scripts/verify_release_sync.py` | `DEPLOYMENT` | W2_RELEASE_SYNC | operator → script | staging | 否 | W2_RELEASE_SYNC | `KEEP` | E3/E4 |
| `scripts/w2_data_asset_registry.py` | `MANUAL_OPS` | 人工 CLI | operator → script | offline | 否 | 无 | `KEEP` | E1/E4 |
| `scripts/watch_staging_runtime.sh` | `DEPLOYMENT` | w2-staging-watchdog.service | systemd → script | staging | 是 | 无 | `KEEP` | E3/E5 |
| `src/w2/gates/gate5_preflight_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-gate5-preflight` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/matchday/cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-matchday` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/observability/stage7i_observer_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-stage7i-observer` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/shadow/comparison_import_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject comparison import | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `src/w2/strategy/shadow_cycle_cli.py` | `RUNTIME_ENTRYPOINT` | pyproject `w2-shadow-cycle` | console → module | runtime CLI | 否 | 无 | `KEEP` | E3/E6 |
| `tests/secret_scan.py` | `CI_DIRECT` | ci.yml | GitHub CI → script | CI | 是 | W2_ACCEPTANCE_RUNBOOK | `KEEP` | E2/E3/E4/E5 |
<!-- SCRIPT_AUTHORITY_MATRIX_END -->
