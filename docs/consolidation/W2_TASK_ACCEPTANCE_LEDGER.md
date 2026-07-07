# W2 系统升级 · 任务与验收台账

用途:记录每一条下发给 Codex 的指令、执行结果、我方(reviewer)验收结论、以及据此进入的下一阶段。供后续接手者一眼看清系统怎么一步步变成现在的样子。

维护规则:**每下发一条指令、每验收通过进入下一阶段,都追加一条。** 台账只增不改历史条目;结论有修正就新增一条注明。

时区:北京时间。日期:2026-07。

---

## 当前状态速览(读者先看这里)

| 维度 | 起点 | 现在 |
|---|---|---|
| 主干 | 无 always-on 日线,靠 stage 脚本临时拼 | `w2-matchday` 入口 + 统一 DecisionCard + 受控刷新 + 审计 + 复盘 + 老板视角 dashboard(均已合并,部分为 skeleton 已在真数据上初步跑通) |
| 决策契约 | FORMAL/CANDIDATE/ANALYSIS_PICK/RECOMMEND 四套词并存,dashboard 读取时现场调和 | 唯一 `DecisionTier` 落 domain;dashboard 读 `decision_tier`,旧字段仅兼容 shim |
| 白名单 | 仅 `world_cup_2026` enabled | 14 联赛 profile;`league_id` 硬门;**mapping+fixtures 14/14 PASS**;odds 真矩阵:**世界杯+巴西+中超+瑞典超+挪超 PASS**,阿甲/MLS 薄(二级源),五大待八月;全部 `enabled=false` |
| 数据 | 免费 100/天、当前赛季被 plan 挡住 | 已开 Pro(7,500/天、解锁当前赛季 + odds);历史验证已用免费 Understat 完成 |
| 模型 | 手设先验(`BASELINE_PRIOR`)、从未用真数据验证 | 拟合 lambda + temperature 校准;**五大 ~0.99**(跨季/多折稳健、不过拟合);**在赛联赛重验 ~1.05**(弱但校准诚实,五大结论**不可迁移**) |
| 数据 · Pro | 免费 100/天、当前赛季被 plan 挡 | 已开 Pro;在赛 5 联赛 2026+历史数据落地(挪超待补、瑞典超 2025 差 14 场) |
| 纪律 | "绿得发慌" | 全程受控、不造假绿灯、诚实标 BLOCKED、好结果也自查降级 |
| 部署/启用 | — | **零 enable、零 staging/production 部署**(始终是单独批准步,未触发) |

---

## 阶段台账(时间顺序)

### S0 · 战略诊断与契约(规划,未动生产码)
- **产出**:《Decision Contract V1/V2》《Consolidation Roadmap V1/V2》《Dashboard 全链路任务清单》、老板视角 dashboard 样稿、白名单技术工单。
- **关键决定**:两层出口——`ANALYSIS_PICK`=分析推荐(可展示、可追踪、默认不可锁);`lock_eligible/RECOMMEND`=正式可锁(需 +EV);staging 用 A(不绑 +EV)、production 用 B。
- **去向**:据此进入白名单与主干实现。

### S1 · 白名单落地(config)
- **指令**:把推荐白名单写成 `config/competitions/` profile,全部 `enabled=false`,provider id 标 Stage14 待验。
- **执行**:新增 8 个 national_league profile(巴西/阿甲/瑞典超/挪超/美职联/中超/荷甲/葡超)。
- **验收**:JSON + schema 校验通过,均 `enabled=false`,与 top_five 同构。
- **去向**:交技术员按工单做覆盖审计。

### S2 · #187 合并 + 首次 evidence-only 审计
- **指令**:合并 #187;main CI 绿后跑一次已批准的 EVIDENCE_ONLY 审计 cap=60;只读诊断,不部署/不启用。
- **执行**:#187 squash merge → main `a7c367c`;审计 42 calls,14/14 `can_enable=false`,`provider_mapping/fixtures/bookmaker_depth` 全 FAIL。
- **验收**:我核实——五大与世界杯这些**已知正确 id 也 FAIL**,判断非映射/数据问题。
- **去向**:只读根因定位。

### S3 · #188 根因诊断
- **指令**:只读定位根因,用已抓 `/tmp` 证据,不猜 profile、不再打 API。
- **执行**:PR #188(Draft)+ 根因文档;结论 A=套餐/鉴权。
- **验收**:我核实代码(`league_whitelist_provider_audit.py:939` `if "plan" in keys → PROVIDER_PLAN_RESTRICTED`)——是 API 真实 `errors.plan` 信号,非 count=0 推断;在赛的巴西控制组也 restricted。**确认瓶颈 = API-Football 套餐,不是代码/数据。**
- **去向**:ops 决策(升级套餐)或走免费历史路。

### S4 · 免费历史可行性(#189)
- **指令**:免费额度只读定位"免费能不能拿历史 fixtures";修 `--audit-season-override` 查询形态;清 dashboard legacy 残留(P2);扩多比赛日离线 E2E。
- **执行**:发现"免费没戏"是 **`next=5`+season 查询形态 bug**,非窗口限制;改走 `status=FT`;PL 2023/2024 fixtures 各返回 380 场;P2 清理;PR #189。
- **验收**:我核实——`dashboard/recommendations.py` 现**先读 `decision_tier`**、旧四字段仅兜底 shim(P2 真修);历史 override 走 `status=FT`(查询修复真);合并 #189 → main `697354f`。
- **去向**:免费历史数据可用,进全量映射。

### S5 · id 锚定映射(#190)
- **指令**:`provider_mapping` 改为 `league_id` 硬门,`name/country/season/team_count` 降 advisory(修脆弱性 + 免额度反复 rerun)。
- **执行**:13 年度联赛 2024 fixtures 全 PASS;失败仅是显示名/国名别名(修了 4 个);id 全对。合并 #190 → main `1c4af67`。
- **验收**:我核实 `_provider_mapping_item` 现只因 `league_id` 不符 FAIL,其余入 `advisory_mismatches`。
- **去向**:映射收工,转模型验证。

### S6 · 免费 2024 回测 harness(#191)
- **指令**:用免费 2024 历史(代理 xG)搭回测+校准 harness,产 preliminary 指标。
- **执行**:harness 建成;6/13 联赛、样本 2135;Brier 0.6225 / log_loss 1.0357 / RPS 0.217 / ECE 0.0434(均匀基线 1.0986)。`calibration_status=BLOCKED`。
- **验收**:我解读——胜过随机但远低于市场级,且**跑的是 xG 代理非真 xG**,是降级地板。作为 harness + preliminary 合并 #191 → main `59ebf4e`(不当校准通过)。
- **去向**:测"真 xG 是否救模型"。

### S7 · 真 xG 增益实验(#192,Understat)
- **指令**:用免费 Understat 真 xG 喂现有 delta harness,PL 2024 代理 vs 真 xG,零 API-Football。
- **执行**:Understat 380 场、delta 样本 330;proxy log_loss 1.0259 → true 1.0164,**Δ 仅 -0.0094**,ECE 反变差。结论 `MIXED_OR_SMALL_TRUE_XG_GAIN`。
- **验收**:我解读——**瓶颈是模型不是数据**(喂真 xG 也榨不出信号)。$0 提前避开"为差模型买好料"。PR #192 Draft(head `252aaed`)。
- **去向**:改模型。

### S8 · 模型迭代 1 拟合+校准(#193)
- **指令**:五大 Understat 离线拟合 lambda(替代 `BASELINE_PRIOR`)+ temperature 概率校准,walk-forward 无泄漏,$0。
- **执行**:样本 1510(train 1057/val 453);val log_loss **0.9699** / Brier 0.5777 / ECE 0.0411;Δ vs 先验 log_loss -0.0354、ECE -0.0730。`MODEL_ITERATION_PROMISING`。PR #193 Draft。
- **验收**:我核实——切分是**时间序列**(`chronological_prefix_train_suffix_validation`),lambda 与 temperature **只在 train 拟合**,无泄漏。0.97 真实但为单折乐观值。
- **去向**:稳健性验证。

### S9 · 迭代 1 稳健性验证(#193,续)
- **指令**:train/val gap + 跨季外样本 + 多折 walk-forward + Dixon-Coles/Elo 对照,证 0.97 非单折侥幸。
- **执行**:train/val gap **0.0085**(不过拟合);2023→2024 **0.9895**、2024→2023 **0.9878**;rolling 4/4 赢 baseline,均值 **0.9899**、stddev 0.0094。`ROBUST_IMPROVEMENT`。head `f459a4d`。
- **验收**:我核实——Codex **主动把 0.97 降级为稳健 ~0.99**(自查降级=可信证据)。诚实数字 ~0.99:真实稳健提升,仍短市场级 ~0.03(按 ADR-0026 本就不需跑赢市场)。**模型达"称职分析级"。**
- **去向**:模型达到收益递减点;用户开 Pro,转真·上线路径。

### S10 · Pro 首日冲刺(数据 + 审计 + 在赛联赛模型重验)
- **指令**:开 Pro 后首日——数据采集 + 审计 + 模型在在赛联赛重验,≤7000 calls/天,数据持久落地;**不 enable、不部署、不启实时循环**(单独批准步)。
- **执行**:新分支 `feat/w2-pro-day1-data-audit-model-recheck`;PR **#194** Draft。Pro 确认(plan=Pro、7500/天、巴西 2026 fixtures 380、errors 空)。本地缓存 **7421** raw(fixtures 15 / leagues 15 / statistics 4535 / odds 990 / lineups 1865)。数据:巴西/阿甲/MLS/中超 **2026+2024+2025 完整**;瑞典超 2026+2024 完整、2025 stats 228/242;挪超未采(额度耗尽,尾端 quota remaining -14)。离线重验:2024 sample 1752 **log_loss 1.0521** ECE 0.0312;2025 sample 1898 **log_loss 1.0620** ECE 0.0225。
- **验收**:我核实/解读——Pro 与数据链路(当前赛季 fixtures/odds/xG/lineups)真通,**基础设施首次在 live 数据上验证 ✓**。但**模型在在赛联赛 log_loss ~1.05–1.06(仅略胜均匀 1.0986),远弱于五大 ~0.99**;ECE 反而好(0.02–0.03)= 校准诚实但判别力弱("准而不锐")。**确认五大模型结论不能迁移到这些联赛**;在这些联赛模型会保守(多 SKIP/WATCH、少 pick)——行为正确,但产品价值有限。零 enable / 零部署,守住。
- **去向**:额度重置后补数据缺口 + 跑完整 14 联赛审计;产品价值锚定八月五大。

### S11 · 数据补齐 + 全 14 联赛审计(Pro,#194 续跑)
- **指令**:补瑞典超/挪超缓存;跑完整 14 联赛真实审计(含 odds)→ 出"可进 staging"清单;仍不 enable/不部署。
- **执行**:缓存补齐(leagues 26 / fixtures 26 / statistics 5121 / odds 1155 / lineups 2105;#194 累计 provider ~8434)。14 联赛 audit inventory:**provider_mapping 14/14 PASS、fixtures 14/14 PASS**、odds **1/14**、bookmaker_depth **1/14**(仅 world_cup)。离线 recheck:2024 sample 1994 log_loss 1.054 ECE 0.030;2025 sample 2139 log_loss 1.055 ECE 0.030。HEAD `750789c`。
- **验收**:我核实——**白名单身份+赛程在 Pro 上彻底验通(14/14)✓**。odds 只 WC 过:审计对每联赛拿 `first_future_fixture` 探 AH+OU+bookmaker 深度(`league_whitelist_audit.py:388`)。big-5 歇夏无 fixtures → odds FAIL **属预期**;在赛联赛 odds FAIL **待定**,多半是 API-Football 对这些非主流联赛 **AH/OU 深度覆盖薄**(门槛未过),非套餐问题。模型在赛联赛 ~1.05(弱),与 S10 一致。
- **去向**:探一场确认 odds 是"真覆盖薄"还是"探错场次";产品价值锚定八月五大。

### S12 · odds 覆盖真相探针(#194)
- **指令**:探针区分在赛联赛 odds FAIL 是"覆盖薄"还是"探错场次";探 big-5 历史 odds 确认八月就绪。
- **执行**:2 provider calls;报告 `W2_S12_ODDS_COVERAGE_TRUTH`。**Brazil** 最近可用场次 1X2+AH+OU+3 bookmaker → **探错场次非覆盖薄**;**China(CSL)** 5 天窗口内 1X2+AH+OU+**最高 10 bookmaker** → 同;**MLS** 2026 future odds 全空 → 暂按真薄/需二级源;**PL 2024 historical** odds 未确认保留,八月以 near-kickoff 实探为准。HEAD `546eeab`。
- **验收**:我核实/解读——**"odds 1/14"是审计假阴性**:探 `first_future_fixture`(超 odds 窗口)误杀了实际有 AH/OU 的 Brazil/CSL。真相:**Brazil/CSL odds 可用(CSL 深度还不错),MLS 真薄,阿甲/北欧未探,五大待八月实探**。odds 没那么差 ✓;但**模型在这些联赛仍 ~1.05 弱 → odds 可用 ≠ 能出好单**。
- **去向**:修审计探针(near-kickoff 选场)+ 补探剩余联赛得真矩阵;产品价值仍锚八月。

### S13 · 修审计 odds 探针 + 真矩阵(#194)
- **指令**:修 odds 探针为"窗口内最近开踢"选场;重跑 14 联赛得真矩阵;补探阿甲/北欧;MLS 标二级源。
- **执行**:探针改为优先选 odds 窗口内最近未来 fixture(`league_whitelist_audit.py` + `run_w2_pro_day1_sprint.py`);`MIN_BOOKMAKER_DEPTH` 保持 3(Brazil 实测正好 3,调高误杀)。真矩阵:**PASS = world_cup / brasileirao / CSL / allsvenskan / eliteserien**;**FAIL = argentina / mls**;big-5/eredivisie/primeira 待八月 near-kickoff。MLS 标 `SECONDARY_ODDS_PROVIDER_DECISION.md` 候选。S13 provider calls 1。HEAD `98eb29e`。
- **验收**:我核实——探针修复后审计可信。**4 个在赛联赛(巴西/中超/瑞典超/挪超)odds 可用**;阿甲/MLS 真薄 → 二级源轨道(阿甲先 watchlist、near-kickoff 重探)。但这些联赛模型仍 ~1.05 弱 → odds 可用 ≠ 能出好单。**审计现在对八月五大 enable 决策可信,这是 S13 的真正目的。**
- **去向**:进入 F1 固化——合并 Draft PR(#192→#193→#194)到 main。

---

## 待办 / 下一步(交接者看这里)

- **S13(下一步)**:修审计 odds 探针(near-kickoff 选场)+ 重跑得真 odds 矩阵 + 补探阿甲/北欧;MLS 标二级源候选。
- **已修正认知**:odds 不是普遍薄——那是审计假阴性;Brazil/CSL 实际有 AH+OU(CSL 深度不错),仅 MLS 真薄。**所以在赛联赛的唯一硬约束是"模型弱 ~1.05",不是 odds。**
- **产品价值锚点 = 八月五大**:模型 ~0.99 + odds 覆盖好,两样都强,才是真正出单时机。在赛联赛有 odds 但模型弱 → 出单少而保守。
- **随之而来的岔路(待你定)**:要么**投模型**(在赛联赛/整体的判别力才是真瓶颈),要么**固化现状、等八月**。
- **Pro 月的聪明用法**:趁额度在,**批量拉五大多季历史 xG+odds** 存本地(可复用、Pro 到期不影响),供后续模型开发。
- **上线(单独批准步,尚未做)**:在赛联赛即便过审,因模型弱只适合"跑机器趟坑",不宜据模型出单。
- **仍挂 Draft**:#188、#192、#193、#194。合并/转 Ready 需 reviewer 决策。
- **台账本身**:已提交在分支 `docs/w2-task-acceptance-ledger`(PR **#195**,commit `0461470`),仅含本文件。workspace 保留活文档副本;**每阶段更新后,再把最新快照同步一次到该分支(追加提交、更新 #195)**——docs 分支即台账的长期归宿,不 squash 死。

## 全程保持的纪律不变量

无赛前泄漏;provider 受控(allowlist/hard cap/ledger/dedup);数据持久、可复现;不造假绿灯(诚实标 BLOCKED / preliminary);好结果也自查降级;**零 enable / 零部署**至今;raw payload/header/key 不提交。

---

## 原始目标对账(初始"真系统"5 支柱 + Roadmap V2)

用户最初对"真系统"的定义(5 支柱)与当时的 Consolidation Roadmap V2,对现状核账:

| 原始目标 | 状态 | 说明 |
|---|---|---|
| ① 每天赛前稳定拿到关键数据 | ✅ 基本达成 | Pro 数据链路验通(fixtures/xG/odds/lineups);覆盖审计在位 |
| ② 自动刷新 | ✅ 机制在 | 受控刷新护栏就位;实时 scheduler 循环待八月启用 |
| ③ 清楚判断 | ✅ 达成 | 唯一 `DecisionTier` + 统一 DecisionCard;dashboard 只读 `decision_tier` |
| ④ 该出就出 / 不能出给可执行原因 | ⏳ 待八月 | 契约 + reason_code 就位;真出单需 odds(五大八月) |
| ⑤ 可控·可审计·可复盘 | ✅ 达成 | append-only 审计、卡片哈希、replay 前门、离线验收、本台账 |
| Roadmap S1 决策契约落地 | ✅ | `DecisionTier`/`lock_eligible`/`outcome_tracked`;P2 考古清除 |
| Roadmap S2 `w2-matchday` 主干 | ✅(skeleton 已在真数据跑通) | 入口 + 就绪门 + 受控刷新;live 全流程待八月实跑 |
| Roadmap S3 老板视角 dashboard | ✅(skeleton) | L1 决策页 + L2 抽屉 + 复盘导航 |
| Roadmap S4 复盘前门 | ✅(skeleton) | 只读 replay,哈希一致 |
| 模型 BASELINE_PRIOR → 验证 | ⏳ 部分 | 五大离线拟合 ~0.99 稳健(#193);**尚未接为线上 champion** |

**结论:"造脊椎"的原始路线图(S0–S4)已基本完成;剩下的是"上线"(八月)与可选的"模型增强"。**

---

## 前瞻路线图 · 固化 → 八月上线 → 后续(操作员按此接手)

决策:**固化现状、等八月**。新操作员按下列步骤接续,勿跳过红线。

**F1 · 固化(现在,交接前)**
- [x] **S13(完成)**:审计 odds 探针改 near-kickoff 选场,真矩阵可信(见 S13 条)。
- [ ] **← 当前动作:处置 Draft PR(关键固化)**:按 **#192 → #193 → #194** 顺序审阅合并进 `main`(#193 基于 #192;#194 并行于 main,合并时留意 `league_whitelist_audit.py`/`free_tier_2024.py` 冲突),再 #195(台账)、#188(诊断)。**合并 = 把现状锁进 main,别留一堆 Draft 让接手者猜。** 线上行为不变(拟合模型仍离线、零 enable)。
- [ ] README + stage 叙事同步真实现状(清除"Stage 3"等旧描述)。
- [ ] 本台账持续维护、常驻 `docs/w2-task-acceptance-ledger`。

**F2 · 八月就绪(开季前 / 开季时)**
- [ ] 五大 fixtures 出现后 near-kickoff 实探 odds,确认 AH/OU 深度(补 S12 历史不确定)。
- [ ] 把 #193 五大拟合模型**接为线上 champion**(替代 `BASELINE_PRIOR`):走 challenger→champion(`models/challenger.py` + forward-holdout),**仅五大**。
- [ ] `w2-matchday` 在五大 fixtures 上做一次 **live 全流程 dry-run**:确认真出 DecisionCard、dashboard 渲染、replay 一致。
- [ ] 受控 scheduler 按 T-24/3/90/30/15 启用(护栏已在)。

**F3 · 上线(八月开季)**
- [ ] 审计通过(mapping+fixtures+odds)的**五大**先 **staging enable**(单独批准 PR + 配额/回滚证据)。
- [ ] staging 每日跑 `w2-matchday` → 产出 ANALYSIS_PICK / WATCH / SKIP(带 reason);积累 `outcome_tracked`。
- [ ] staging 稳定 + 校准可接受后 → **production enable**(分析级·非稳赢口径)。
- [ ] 老板视角 dashboard 每日更新;当日复盘可用。

**F4 · 后续(可选,上线后)**
- [ ] **模型增强**(此前搁置的岔路):用真实 forward 数据迭代;加 `squad_value`;向在赛联赛/更多联赛扩判别力。
- [ ] MLS / 薄 odds 联赛:接二级 odds 源(`docs/providers/SECONDARY_ODDS_PROVIDER_DECISION.md`)。
- [ ] `lock_eligible` / `RECOMMEND` 上档:需独立前向 +EV 证明,默认关。

**不变红线**:分析级·非稳赢;provider 受控;不造假绿灯;enable/部署永远是单独批准步;raw/key 不提交。
