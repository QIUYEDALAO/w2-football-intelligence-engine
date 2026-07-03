# W2 推荐准确性升级 · 执行任务清单

出具：Claude ／ 2026-07-02 ／ 基线 `feat/w2-audit-table-export @ 9cb2948`
目标：不以战胜市场为目标，在现有因子体系（F1–F10 + live 因子）内，把"评分 → λ → 模拟 → 推荐分析"做到**校准完美**：模型概率与真实频率长期一致，每条推荐可解释、可复盘。
前置：#123 四张审计表 staging/main 验收先完成（不与本清单冲突，批次一可并行开发）。

## 执行顺序总览

| 批次 | PR | 内容 | 依赖 | 预估 |
|---|---|---|---|---|
| 一 偏差修复 | #124 | 中性场 HA gate + proxy-Elo 不进 λ | 无 | 0.5–1 天 |
| 二 数据落地 | #125 | A2/A3 回填实际执行 | #123 | 1–2 天 + quota 窗口 |
| 二 数据落地 | #126 | A5 真实 Elo 静态映射 | 无 | 1 天 |
| 二 数据落地 | #127 | A4 复核 + F10 阵容接线 | 无 | 1 天 |
| 三 评分刻度 | #128 | 权重归一化 + 刻度参数化 | 无 | 1 天 |
| 四 分布升级 | #129 | 精确泊松矩阵 + Dixon-Coles 接入 | 无 | 1–2 天 |
| 四 分布升级 | #130 | λ 不确定度传播 | #129 | 1–2 天 |
| 五 闭环校准 | #131 | S2 walk-forward 拟合 | #125/#126/#129，样本积累 | 2–3 天 |
| 五 闭环校准 | #132 | 结算闭环校准报告 | #123，settlement 样本 | 1–2 天 |
| 五 闭环校准 | #133 | EV 不确定度门槛 | #130 | 0.5 天 |

通用红线（每个 PR 的 checklist，违者打回）：不读/不打印 `.env`；市场赔率与盘口不得进入 λ 或任何训练目标；不用赛后结果反推赛前字段；禁爬虫/凭证/运行时 LLM 取数；回填不得抢临场 odds/lineups 配额（走 `quota_budget` 决策）；Lock/Settlement 保持 append-only；报告禁词 guard 不得放松；所有新数据带 as-of 且 as-of ≤ kickoff。

---

## 批次一：偏差修复（先做，纯收益）

### #124a 中性场主场优势 gate

现状：`src/w2/strategy/calibration.py:12` 的 `home_advantage_goals=0.12` 无条件加给名义主队；`config/competitions/world_cup_2026.v1.json:14` 已有 `neutral_site_policy` 但校准层未用。世界杯多为中性场，这会系统性把 fair_ah 推向名义主队。

改动点：
1. `strategy/simulate.py` `SimulationInputs` 增加 `neutral_venue: bool = True`（默认中性，宁可少加不错加）。
2. `calibrate_lambdas` 增加同名入参：`neutral_venue=True` 时 `home_advantage_goals` 生效值为 0，并把生效值写入输出 `params`。
3. `api/repository.py:1423` 组装 `SimulationInputs` 处解析主办国：依据 competitions config 的 `neutral_site_policy` 与 fixture 场地国家/主队国家判定（HOST 主队非中性，其余中性）。判定不了时按中性处理并在 `input_readiness` 记 `venue_context: "UNKNOWN_TREATED_NEUTRAL"`。

验收：对称输入 + 中性场 → fair_ah = 0；主办国主队场次保留 HA；calibration payload 可见生效值与判定依据；新增单测覆盖三种场景（host / neutral / unknown）；现有测试全绿。

### #124b proxy-Elo 不进 λ

现状：ratings 缺失时回退 xG 代理 Elo（`api/repository.py:2452-2477`，1500+xG差×100），又经 `elo_gap_weight=0.28` 进 λ——xG 双重计入，悬殊盘被放大。

改动点：`api/repository.py:1339-1348` 之后、组装 `SimulationInputs` 时：若最终 ratings 的 `collection_status == "PROXY_ONLY"`（或 `source_group == "xg"`），则 `home_elo/away_elo` 传 `None`。因子层 F7 保持现状（诚实标注即可）。

验收：ratings 为 proxy 时 `input_readiness.elo_ready=false` 且 λ 不含 elo_delta（回归测试固定输入对比 λ 值）；真实 ratings（#126 之后）行为不变。

---

## 批次二：把数据喂进因子

### #125 A2/A3 回填实际执行（管线已有，只差跑）

现状：`ingestion/independent_signal_backfill.py` 与 `ingestion/quota_budget.py` 已完成，但 `runtime/independent_signal_backfill/` 从未落盘，读取端 `repository.py:2310-2360` 一直走 xG 代理兜底。

步骤：
1. staging 用 `dry_run=true` 跑 `team_fixture_history_backfill` 与 `h2h_backfill`，核对 quota 决策输出（预算、backfill_stop、core_only 三档）。
2. 实跑：`window=next36, max_fixtures=20, write_artifacts=true`，raw payloads 落 `runtime/independent_signal_backfill/raw_payloads/{fixtures,h2h}/`。
3. 增加调度入口（scheduler 每日一次，赛前 T-36h 窗口），任务失败不重试超过 1 次、不升级到临场配额。
4. 验证读取端：`_team_fixture_histories_from_raw_payloads` 返回非空、`is_independent_signal=true`；F3/F5/F6 转 READY；跑一次审计表导出对比 `independent_signal_count` 与 `missing_independent_sources` 前后差异。

验收：当日场次 ISC≥3 覆盖率 ≥70%（达不到则在 PR 记录原因与真实缺数清单）；quota 分档在真实配额下演练一次（人为压低 remaining 验证停采）；raw payload 均带 observed_at；prematch odds/lineups 预算未被占用；无 as-of 泄漏（回填只含 kickoff 前已完场比赛，现有过滤逻辑 `repository.py:2395-2400` 保持）。

### #126 A5 真实 Elo 静态映射（复制 A4 模式）

方式：人工策展，禁爬虫。来源建议 World Football Elo Ratings（eloratings.net）国家队快照，逐队记录。

步骤：
1. 新建 `config/team_ratings/world_cup_2026.v1.json`：`{team_id, team_name, elo, observed_at, source_system, source_url, confidence, reviewed_by}`，48 队与 `config/team_values/world_cup_2026.team_ids.csv` 的 id 对齐。
2. `repository.py` 新增 `_team_ratings_from_static_mapping`（仿 `_team_value_mapping`），构造 `TeamRatingSnapshot(source="world_football_elo", source_group="ratings", is_independent_signal=True)`；attack/defence/form 仍由真实历史推（`rating_from_history`），静态 Elo 只替换 elo 字段。
3. 读取优先级：static Elo > history 推导 > xG 代理（代理仅因子层展示，λ 按 #124b 不吃）。

验收：F7 `source_group=ratings`、`is_independent_signal=true`；ISC +1；悬殊对阵 fair_ah 前后对比表附在 PR 描述；`missing_independent_sources` 不再含 ratings；JSON 带日期与复核人。

### #127 A4 复核 + F10 阵容接线

A4 复核：抽样 6–8 队与 Transfermarkt 原页核对（人工，记录核对日期与偏差%）；confidence 分级（一手 0.95 / 转载 0.85）；更新 `config/team_values/README.md` 的更新节奏（小组赛后、淘汰赛前各一次）。

F10 接线：`SimulationInputs.lineup_strength_adjustment` 目前恒 0。改动：lineups READY 且 as-of ≤ kickoff 时，把 F10 因子分数（[-1,1] 截断）传入；lineups 未就绪传 0 并在 `input_readiness` 标注。

验收：抽样偏差记录在案（>10% 的队伍必须改数）；F10 生效场次 calibration payload 可见 `lineups` 权重项；无 as-of 泄漏测试。

---

## 批次三：评分刻度修正

### #128 权重归一化 + 刻度参数化

现状问题（本次审查实测确认）：`pricing/team_score.py:95-106` `_weighted_score` 不按可用权重归一化——READY 因子越多分差越大，跨场不可比；`pricing/supremacy.py` 用固定 0.16/0.25 格换算；各因子刻度常数（F3 `diff/4`、F6 `diff/2`、F7 `/300`）均为手设。

改动点：
1. `_weighted_score` 除以参与因子权重和（NEUTRAL 计半权保持现状），输出加 `weight_sum_used` 字段进 debug/audit。
2. 新建 `FactorScaleParams` 数据类集中管理全部刻度常数（默认值=现值，行为不变），`supremacy` 换算常数一并纳入。参数值与版本写入 pricing_shadow debug。
3. factors payload 每项增加 `sigma` 占位字段（常数默认），供 #130/#133 使用；缺失因子的语义从"贡献 0"改为"不参与归一化 + 全局 sigma 上调"（本 PR 只落 sigma 字段和归一化，语义升级在 #130）。

验收：构造两场 supremacy 相同、coverage 不同的比赛，归一化后 team_score 分差一致；默认参数下现有单测全绿（刻度参数化不改变行为）；audit 表/debug 可见 weight_sum_used 与 scale 版本。

---

## 批次四：模拟分布升级

### #129 精确泊松矩阵替换 MC + Dixon-Coles 接入

动机：10000 次 MC 的采样噪声约 ±1%，相对 3.5% EV 门槛不可忽略；`_poisson_probabilities`（`strategy/simulate.py:354-363`）已能给精确解。`models/dixon_coles.py` 已写好（含 `fit_dixon_coles`）但零调用。

改动点：
1. `run_simulation` 主路径改为精确联合矩阵：`P(h,a)=Pois(h;λh)·Pois(a;λa)·τ(h,a;ρ)`，max_goals=12，归一化后走**原有**的 `_fair_ah/_fair_ou/ah_settlement_distribution` 代码路径（它们已支持权重字典 + `simulations=1`）。删除采样循环；`seed` 字段保留但标注 `unused_exact_solution`。
2. τ 用 Dixon-Coles 低分修正，ρ 进 `LambdaCalibrationParams`（默认 0 = 独立泊松，保证可回退）；ρ 初值待 #131 拟合，本 PR 只接线。
3. `SIMULATION_MODEL_VERSION` 升 `w2.formal.exact_dc_poisson.v1`；lock snapshot 与审计表自动带出新版本。

验收：ρ=0 时与旧 MC 结果差异 ≤ 采样噪声（对拍测试）；ρ>0 时 0-0/1-1 概率上升、平局与 push 概率单调变化方向正确（单测断言）；输出完全确定、无 seed 依赖；同源性不破坏（AH/OU/比分仍出自同一矩阵）；PR 附 5 场典型对阵新旧输出对比表。

### #130 λ 不确定度传播

改动点：
1. `SimulationInputs` 增加 `lambda_sigma_home/away`（来源：xG 样本量、数据陈旧度、#128 的因子 sigma 汇总；映射规则先简单线性，参数进 calibration params）。
2. 联合分布改为 λ 的 Gamma 混合（等价负二项边际）或 K 点高斯求积近似——两者选实现简单者，要求解析或确定性数值，不回退到 MC。
3. `ah_expected_value` 同时输出 `ev_se`（EV 的标准误，来自 λ 不确定度传播）。

验收：sigma=0 退化为 #129 精确解（对拍）；sigma 单调增大 → 结算分布方差单调增大、极端比分尾部变厚（单测）；EV 与 ev_se 一并进 recommendation payload 与 lock snapshot。

---

## 批次五：拟合与闭环

### #131 S2 walk-forward 拟合

目标：`calibration.py` 全部手设参数（elo_gap_weight 0.28、squad_value_log_weight 0.18、home_advantage、clamp 边界、#129 的 ρ）改为历史拟合值，`CALIBRATION_STATUS` 从 `BASELINE_PRIOR` 升为 `WALK_FORWARD_VALIDATED(n=…)`。

步骤：
1. 训练数据：历史完场比赛的赛前输入快照（lock snapshots + Gate3 历史数据集 + 回填的 raw payloads），目标为**真实比分**的 log-loss/CRPS。市场盘口与赔率绝不进入特征或目标（红线）。
2. 时间切分 walk-forward（按足球日滚动），报告每窗口 holdout 指标；样本 n<200 时只出报告不切换默认参数（沿用 `s2_gate.n_min=200`）。
3. 产出 `config/calibration/lambda_fit.v1.json`（参数、置信区间、训练窗口、样本量、代码 sha），`calibrate_lambdas` 支持从配置加载；`CALIBRATION_VERSION` 带窗口标识。

验收：holdout log-loss ≤ baseline prior（否则不切换，报告留档）；无未来泄漏（每个预测点只用其 as-of 之前的数据，单测强制）；lock snapshot 记录新 calibration_version；参数变更有独立评审记录。
**［2026-07-03 修订］** n≥200 指历史拟合语料的完场样本数（可用历史赛季回填构建，与自家 lock/settlement 无关），且按赛事 profile 分别拟合。权威口径见 `W2_SAMPLE_STRATEGY_ADDENDUM_2026-07-03.md`。

### #132 结算闭环校准报告

目标：让"是否校准"成为每周可看的事实，而不是感觉。

改动点：
1. 新模块 `tracking/calibration_report.py`：从 `settlement_history` + lock snapshots 生成——按模型赢盘概率分桶（0.4–0.5、0.5–0.6…）的预测 vs 实际赢盘率、Brier、log-loss；按 tier / movement_pattern / 盘口深浅分层。
2. 桶内 n < `MIN_BUCKET_SAMPLES_FOR_RATE`(30) 只显示"观察中 n/N"，不出百分比（沿用 `tracking/formal_results.py` 口径）；整表 `not_a_formal_gate=true`。
3. 输出为审计导出的第五张表 `calibration_report`（空表有 header），并入 `audit_export/tables.py` 契约；报告生成器不引用它的百分比（禁词 guard 保持）。
4. （n 达标后二期）可选 isotonic 校准层：叠在模型概率上、独立版本号、可一键停用。

验收：空数据出 header；样本不足无任何百分比；每行带 as-of 与 release_sha；provider_calls=0、db_writes=0；禁词测试通过；报告能回答"模型说 60% 的桶实际是多少"。

### #133 EV 不确定度门槛

改动点：`strategy/formal_recommendation.py:128` 判定改为 `ev < FORMAL_EV_THRESHOLD + k * ev_se`（k 默认 1.0，可配置）即 WATCH，blocker 名 `EV_WITHIN_UNCERTAINTY_BAND`；`ev_se` 来自 #130。reverse value 门槛同步加罚。

验收：边界单测（EV=3.6%、ev_se 大 → WATCH；ev_se=0 行为与现在完全一致）；blocker 进审计表 `formal_blockers`；FORMAL 数量变化在 staging 观察一周并留档。

---

## 总验收（Definition of Done）

1. 当日场次 ISC≥3 覆盖率 ≥70%，且悬殊对阵 fair_ah 明确偏强队（审计表可查）。
2. 中性场对称输入 fair_ah=0；λ 中无 proxy-Elo、无市场信息（代码审查 + 单测双确认）。
3. 模拟输出为精确分布：无采样噪声、无 seed、AH/OU/比分同源，模型与校准版本可追溯到每条 lock snapshot。
4. calibration_report 每周生成：达标桶的预测赢盘率与实际差 ≤ 5 个百分点为"校准合格"；不合格触发 #131 重拟合，而不是改阈值。
5. 全程红线零违规：无赛后补造、无命中率开闸、无配额抢占、Lock/Settlement append-only。

达成以上五条后，系统在"给定现有因子"意义上接近理论上限，剩余误差归属足球随机性与数据可得性，应通过新增独立数据源（而非调参）继续改进。
