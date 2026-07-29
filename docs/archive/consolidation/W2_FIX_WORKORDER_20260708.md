# W2 修复工单(冷读审查 D1–D5)· 2026-07-08

来源:独立冷读审查(main `90e42fb` + #207)。审查结论:#207 可合入;main 有 1 个高危(D1)+ 2 个中危(D2/D3)+ 若干低危(D4/D5)。
**全局红线(每条 PR 都适用)**:零 provider calls(所有修复均为 $0 离线改动);不新增任何 `enabled:true`;不触碰 production;staging 配置只按本工单指定项改;不造假绿灯;ledger 文件 append-only,不回写历史记录;台账由执行会话照常追加,本工单不改台账。

**PR 切分与顺序**:FIX-E 随 #207 合入顺手做 → FIX-A(最高优先,R1.1 检查点前必须落地)→ FIX-B → FIX-C → FIX-D。每条独立 PR,独立验收。

---

## FIX-A(高危 D1)· 影子拣选:把"证据积累"从"展示放行"解耦

**问题**:`_market_anchor_blocks_pick`(`src/w2/domain/decision_adapter.py:279`)要求 `direction_allowed=True`,但唯一生产者 `src/w2/analysis/market_movement.py::build_market_divergence` 全分支硬编码 `direction_allowed: False`(4 处),SIGNIFICANT/ACTIONABLE 状态无生产路径。staging 默认 `W2_MARKET_ANCHOR_DISPLAY_ENABLED=true` → 全部 PICK 降档 WATCH → pick payload 只随最终档位挂载(`decision_adapter.py:92-96`)→ ledger 记录无 pick → `_clv_key`(`forward_ledger_performance.py:171`)要求 `pick.market ∈ {ASIAN_HANDICAP, TOTALS}` → **CLV 样本恒 0,R3.0 门槛(≥200 卡 CLV)结构性不可达**。

**修法(方案 a,已选定)**:展示层继续不给方向(保持 direction_allowed=False 现状不动),但 ledger 记录"影子拣选"——模型当时的方向倾向 + 当时报价——无论展示档位。CLV 在影子轨上积累。

### A1 · `src/w2/tracking/forward_outcome_ledger.py`

1. `SCHEMA_VERSION` 升为 `"w2.forward_outcome_ledger.v2"`。
2. `build_forward_outcome_records` 每条记录追加字段 `record_type: "capture"`,并新增 `shadow_pick` 字段,派生规则(纯赛前、确定性、只用卡上已有数据):
   - 从 `card["model_market_divergence"]` 取 `model_fair_line` 与 `market_line`,parse float,任一缺失或不可解析 → `shadow_pick: null`。
   - `delta = fair − market`;`|delta| ≤ 0.005` → null;`delta < 0` → selection `HOME_AH`;`delta > 0` → selection `AWAY_AH`(AH 线约定:主让为负,fair 比市场更负 = 模型认为主队更强)。
   - 结构:`{"market": "ASIAN_HANDICAP", "selection": ..., "model_fair_line": ..., "market_line_at_capture": ..., "divergence_line_units": round(delta,4), "derived_from": "model_market_divergence", "display_tier_at_capture": <decision_tier>, "shadow": true, "not_a_recommendation": true, "not_displayed": true}`。
   - **不在采集时设阈值过滤**(阈值留给分析端),最大化数据资产。
   - v1 只做 AH;TOTALS(`fair_ou`/`market_ou`)留 TODO 注释,不实现。
3. `_record_key` 追加 `record_type` 维度:`"|".join([...现有四段..., record_type or "capture"])`,并兼容读旧 v1 记录(缺 record_type 按 "capture")。

### A2 · `src/w2/tracking/forward_ledger_performance.py`

1. CLV 拆双轨:现有 `clv` 块(真实 pick)不动;新增 `clv_shadow` 块,结构与 `clv` 相同,`_clv_key` 的影子版从 `record["shadow_pick"]` 取 market/selection(仅 `record_type=="capture"` 的记录参与)。报价提取复用 `_quote`(current_odds.ah 的 home_price/away_price)。
2. **两轨绝不合并**;`clv_shadow.method` 标注 `"shadow_pick_entry_minus_closing_same_line; not_displayed_direction"`。
3. 顶层报告加 `accrual_note`:`"shadow CLV 为积累期证据流,用于未来按预注册规则放行 direction_allowed;非展示战绩"`。

### A3 · 契约预注册(根因修复)

`docs/consolidation/W2_DECISION_CONTRACT_V2.md` 追加一节「分歧雷达放行规则(预注册,2026-07-08)」:

> 单联赛满足以下全部条件,方可经**单独批准 PR** 将该联赛 `direction_allowed` 置真(生产者按联赛白名单放行,不是全局开关):① shadow CLV 样本 ≥100;② shadow CLV 中位数 >0;③ 该联赛最近一次 `market_baseline_eval` gap ≤0.04。放行后真实 pick 开始积累,R3.0(≥200 真实 pick CLV)在真实轨上照旧计,门槛数字不变。修改本规则需评审记录。

### A4 ·(可选 UI,单独小 commit)`apps/web/src/components/BossDecisionView.tsx`

前向 ledger 条加一行影子轨:`影子CLV(证据积累,未展示方向){n ? clvUnits(...) : "积累中"}`,并沿用现有"不制造战绩"文案区。不改其他视图。

**验收(硬)**:①单测:构造 WATCH(被锚定门降档)卡 → ledger 记录含 shadow_pick 且 `not_a_recommendation:true`;fair/market 缺失 → shadow_pick null;②单测:两条 capture(T-24、T-1h)+ shadow_pick → `clv_shadow.sample_count==1` 且 `clv` 仍为 0;③旧 v1 jsonl 混入 → 读取不炸、按 capture 处理;④`rg "direction_allowed" src/w2/analysis` 仍全为 False(本 PR 不放行任何方向);⑤零 provider calls、零 enable diff。

---

## FIX-B(D4c)· outcome 回填 writer

**问题**:`_outcome_counts` 永远 0(无人写 outcome),命中率永远"积累中"——诚实但空转;R1.1 需要 outcome。

**指令**:`src/w2/tracking/forward_outcome_ledger.py` 新增 `backfill_outcomes(runtime_root, day_view_or_results_source, *, dry_run=True, write_artifacts=False)`:

1. 只处理已有 FT 赛果的 fixture(从现有 read-model/结果源取终场比分;**不打 provider**)。
2. 对该 fixture 的每条含 `pick` 或 `shadow_pick` 的 capture 记录(按 `_clv_key`/影子键去重到"每 fixture×market×selection 一条"),用 `w2.domain.odds.settle_asian_handicap` 结算(entry 记录的 line+price),产出记录:`{"record_type": "outcome", "schema_version": v2, "football_day", "environment", "fixture_id", "competition_id", "card_hash": <entry 的 card_hash>, "settlement_outcome": WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS/VOID, "settled_side": "pick"|"shadow_pick", "final_score": {...}, "settled_at": <UTC>}`。线或价缺失 → `VOID` 并带 `void_reason`。
3. 追加到当日同一 jsonl(`_record_key` 已含 record_type,不会与 capture 撞 key);重跑幂等(同 key skip)。
4. `forward_ledger_performance` 侧:`_outcome` 已读 `settlement_outcome`(`:258`),无需改;但 hit/miss 统计必须**按 `settled_side` 分轨**输出(`outcomes` 与 `outcomes_shadow`),UI 命中率只读真实 pick 轨——影子轨命中率只进报告,不上首屏。
5. 接一个 celery task/scheduler tick(默认间隔 3600s,env `W2_FORWARD_OUTCOME_BACKFILL_INTERVAL_SECONDS`,`W2_FORWARD_OUTCOME_BACKFILL_ENABLED` 默认 false,staging compose 置 true)。

**验收**:①单测:构造 capture+终场比分 → outcome 记录正确结算(覆盖 WIN/PUSH/HALF_LOSS/VOID 四例);②幂等:重跑 written==0;③无 FT 赛果的 fixture 不产 outcome;④`settled_side` 分轨,首屏命中率仍只由真实 pick 驱动(无真实 pick 时保持"积累中")。

---

## FIX-C(D2 + devig 统一)· 阈值单位 + 单一去 vig 口径

1. **阈值单位**:`MIN_MARKET_ANCHOR_DIVERGENCE`(`decision_adapter.py:31`)当前 0.05 施加于 AH **线差**——低于最小盘口步长,形同虚设。改:常量名 `MIN_MARKET_ANCHOR_DIVERGENCE_AH_LINE = 0.25`;env `W2_MARKET_ANCHOR_MIN_DIVERGENCE` 语义改为"AH 线差单位",compose 两个文件默认 `0.05`→`0.25`,`Dockerfile.web` 与 `BossDecisionView.tsx:52` 的 VITE 默认同步 0.25,前端展示处标注单位「线差」。契约 V2 的放行规则节(FIX-A3)加一句:"magnitude 单位=AH 线差;概率空间阈值待展示概率分档后另行预注册"。
2. **devig 统一**:`src/w2/dashboard/day_view.py:222` 用 PROPORTIONAL,`src/w2/api/repository.py`(~4177)用 POWER,同屏两个"市场概率"可能不一致。统一为 **POWER**:day_view `_market_probabilities` 改 `DevigMethod.POWER`,`method` 字段照实输出;搜索并更新断言 PROPORTIONAL 的测试;在 `docs/consolidation/W2_DECISION_CONTRACT_V2.md` 的卡片契约节加一行:"展示用市场概率一律 POWER devig,方法进 provenance"。

**验收**:①`rg "PROPORTIONAL" src/w2/dashboard src/w2/api` 只剩注释/枚举定义;②单测:同一 odds 输入,day_view 与 repository 概率一致(±1e-9);③阈值单测:线差 0.20 被拦、0.30 放行(在 direction_allowed=True 的测试构造下);④compose/Dockerfile/前端默认值三处一致为 0.25。

---

## FIX-D(D3)· R4.1b 冠军接线上 + 模型族标注

**问题**:`src/w2/models/divergence_champion.py` 只被 eval 脚本引用;线上 divergence 全联赛用同一模型,与 R4.1b 裁决(bundesliga/chinese_super_league/allsvenskan 应用 R4_1_CALIBRATED)不一致。

**指令**:
1. 在 `src/w2/api/repository.py` 产出 `pricing_shadow.fair_ah`/模型概率并调用 `build_market_divergence`(~3706)的位置,接 `divergence_model_family_for(competition_id)` + `select_divergence_champion_probabilities`:R4.1 三联赛若 R4_1 artifact 可用则用其概率/公平线,否则保持 FITTED_CALIBRATED 并记 `fallback_reason`(选择器已支持)。
2. 无论走哪支,divergence mapping 增加 `model_family` 字段(+ 可选 `model_family_fallback_reason`);`decision_adapter._model_market_divergence` 透传该字段;ledger 已整体拷贝 mapping,无需改。
3. **不改模型本身、不动 FORBIDDEN_MARKET_FIELDS、不因此放行 direction_allowed。**

**验收**:①单测:chinese_super_league 卡 → `model_family=="R4_1_CALIBRATED"`(artifact 可用构造)或 `FITTED_CALIBRATED`+fallback_reason(不可用构造);premier_league 卡恒 FITTED_CALIBRATED;②ledger 记录透传 model_family;③模型特征零变化(`git diff src/w2/models/independent.py` 为空)。

---

## FIX-E(D5)· #207 收尾(随 #207 合入)

1. `src/w2/domain/decision_policy.py::DecisionPolicyConfig`:`compute_lock_eligible` 已不读任何 config 字段。二选一并全库一致:(a) 删除未用字段并同步更新 `decision_adapter.py:138-143` 的构造与全部测试;(b) 保留但加 docstring:"自 #207 起 lock 判定只依赖 decision_tier;以下字段仅供上游 RECOMMEND 准入使用"。禁止维持现状(误导)。
2. `environment_policy.py` stamp:`production_action_allowed: False` 与 `production_action_allowed_tiers: ["RECOMMEND"]` 并存,给 tiers 键加注释或改名 `production_action_candidate_tiers`,消除"已放行"误读。
3. `tests/unit/test_decision_contract_v2_wiring.py:340/398` 的 `direction_allowed: True` 构造处加注释:`# 未来生产者契约:当前无生产路径置真;放行规则见契约 V2 预注册节`。

**验收**:CI 绿;`rg "allow_staging_recommendation_id_generation" src/` 无残留或有 docstring 说明;两处注释存在。

---

## 全局验收(合并后一次性核)

1. staging 跑一日:ledger 出现 `record_type: capture` 且 shadow_pick 非空占比 >0;`forward_ledger_performance` 报告 `clv_shadow.sample_count` 随双快照增长;首屏战绩条仍"积累中"(无真实 pick,不显示命中率)——**这是预期,不是故障**。
2. `enabled:true` 全库计数不变(仅 world_cup);production 零触碰;provider 日用量仍 <120。
3. 台账追加一条:D1–D5 修复合入 + 预注册放行规则生效日期。
