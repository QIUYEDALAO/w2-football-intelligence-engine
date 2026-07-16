# W2 系统升级 · 任务与验收台账

**【状态口径】当前状态以续18为准，S0–S13为历史记录，不能作为当前执行队列。**

用途:记录每一条下发给 Codex 的指令、执行结果、我方(reviewer)验收结论、以及据此进入的下一阶段。供后续接手者一眼看清系统怎么一步步变成现在的样子。

维护规则:**每下发一条指令、每验收通过进入下一阶段,都追加一条。** 台账只增不改历史条目;结论有修正就新增一条注明。

时区:北京时间。日期:2026-07。

---

## 状态标记

**F1 固化完成(2026-07-07):`main`=真实已验证状态,验证工作、README/stage 叙事、台账均已同步;无新增 league enable / 零部署,线上仍 `BASELINE_PRIOR`。但 F1 完成不等于可见产品完成;复查后下一实质动作修正为 S14(真正 L1 老板视角 dashboard + World Cup live 全流程证明),不是被动等八月。** 接手者先读下方 Reviewer 校正,再接续路线图。

## ⚠ Reviewer 校正(2026-07-07 复查发现)

上面的"F1 固化完成 / 八月待命"**不等于整个系统改造完成**。复查发现两处必须纠正:

1. **老板视角 dashboard 并未真正交付**(用户最初的头号痛点)。现状:`apps/web/src/components` 仍是 **32 个旧调试组件**(MatchCard / DataDiagnosticsPanel / ConfidenceDots / WatchStars…);我当初《Dashboard 全链路任务清单》定义的 L1 决策页新组件(`MatchdayHeader`/`DecisionCounts`/`DecisionRow`/`ReasonCodePanel`)**根本不存在**;git 里只有 `W2-DASH-L1/L2/DAYVIEW skeleton` 提交。**此前"dashboard 已在真数据跑通"是过度表述,实为未交付。**
2. **"等八月"过于被动**:`world_cup_2026` **现在就是 enabled + live + odds 可用**;巴西/中超/瑞典超/挪超也在赛且有 odds。有现成 live 赛事,不必干等。

**修正后的下一步(不是等 F2 八月,而是现在)= S14**:建真正的 L1 老板视角 dashboard + 用**世界杯**跑一次 live 全流程,把可见产品立起来。

**✅ 已解决(S14 + S15)**:dashboard 已交付并**部署 live**——**http://43.155.208.138/ 可直接打开**(新 boss-view L1 首屏,旧组件折 L2,只列未开赛世界杯)。系统不再是"八月待命":staging 可见产品已上线。production 对外仍待模型国际赛验证 / 八月五大。

## 🔴 战略裁决 + V3 进展(2026-07 · 市场基准 eval)

**⚠ 本块曾因两写冲突从 main 丢失(reviewer file-tool 编辑 vs Codex git 提交),现重加;台账后续由 Codex 单写提交。**

独立复盘 + 市场基准 eval(脚本 `run_w2_market_baseline_eval.py`;文档 `W2_ARCHITECTURE_REVIEW_2026_07.md` / `W2_MARKET_BASELINE_EVAL_2026_07.md` / `W2_MARKET_ANCHOR_PROPOSAL_2026_07.md` / `W2_REVISED_ROADMAP_2026_07.md`,均已进 main #205)**推翻多个此前结论**,已代码核实:

- 线上 `ANALYSIS_PICK` 来自 `bookmaker_intent` 手设启发式,**不是**被验证的拟合模型;拟合模型只在 `backtest/free_tier_2024.py`、**未接线上**。
- 市场基准(gap = 模型 − 市场,同批):**11 联赛全部落后 Pinnacle 收盘** +0.013(法甲)~+0.055(瑞典超);blend 全纯市场最优 → **模型零增量**。**"五大好/在赛弱""0.99 够用""锚八月"均推翻**(挪超第二好、德甲最差档;MLS 达标 .027;阿甲观察档)。
- **方向转市场锚定**:展示概率 = 去 vig 市场,模型 = 分歧雷达(gap ≤ 0.04 达标),EV 腿门槛改前向 CLV,联赛按 §4 准入矩阵(非月份)。**完整路线图见 `W2_REVISED_ROADMAP_2026_07.md`(V3),已取代旧 F1–F4。**

**V3 执行进展(2026-07-07)**:#205 战略产物进 main(`f28df3b`);#204(Draft `a47321f`,staging 已部署 http://43.155.208.138/)完成 **R1.0**(前向 ledger + odds 时间线 staging 自动调度已接)+ **R2.1**(DayView 输出 `MARKET_DEVIG` 市场概率,假"未就绪"已被真实概率取代)。**下一步**:R2.3(staging 启用 4 个 odds-PASS 在赛联赛,单独审批)+ R2.2(dashboard 三态验收 / 设计定案)。

## 当前状态速览(读者先看这里)

| 维度 | 起点 | 现在 |
|---|---|---|
| 主干 | 无 always-on 日线,靠 stage 脚本临时拼 | `w2-matchday` 入口 + 统一 DecisionCard + 受控刷新 + 审计 + 复盘。**老板视角 dashboard 已交付并部署 live**(#200/#201/#202):新 boss-view L1 首屏替换旧首屏、旧 32 组件折入 L2;**staging URL http://43.155.208.138/ 可直接打开**,旧静态报表移 `/static-report/` |
| 决策契约 | FORMAL/CANDIDATE/ANALYSIS_PICK/RECOMMEND 四套词并存,dashboard 读取时现场调和 | 唯一 `DecisionTier` 落 domain;dashboard 读 `decision_tier`,旧字段仅兼容 shim |
| 白名单 | 仅 `world_cup_2026` enabled | 14 联赛 profile;`league_id` 硬门;**mapping+fixtures 14/14 PASS**;odds 真矩阵:**世界杯+巴西+中超+瑞典超+挪超 PASS**,阿甲/MLS 薄(二级源),五大待八月;全部 `enabled=false` |
| 数据 | 免费 100/天、当前赛季被 plan 挡住 | 已开 Pro(7,500/天、解锁当前赛季 + odds);历史验证已用免费 Understat 完成 |
| 模型 | 手设先验;线上跑的正是它,拟合模型只在 backtest 文件、未接线上 | **市场基准裁决(见🔴)**:拟合模型 11 联赛全部落后 Pinnacle 收盘 +0.013~+0.055,blend 全纯市场最优(零增量);"五大好/在赛弱""0.99 够用""锚八月"均被推翻。方向 = **市场锚定 + 分歧雷达**;线上概率层已出 `MARKET_DEVIG` |
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

### S14 · 真正交付 boss-view dashboard + 世界杯 live 证明(#200)
- **背景**:复查发现 dashboard 只有 skeleton、旧 32 组件仍在(见 Reviewer 校正)。用户点破"等八月太被动,世界杯现在就 enabled+live"。
- **执行**:建真 L1 组件(`MatchdayHeader/DecisionCounts/DecisionRow/ReasonCodePanel`);世界杯 live 探针 15 calls、4 场 → 4 ANALYSIS_PICK(0 可锁,均标模型未对国际赛验证);旧组件折 L2。
- **验收**:我核实——首屏真立起来,但证据在 /tmp(用户打不开)。我用真实数据在 chat 里渲染 + 出了一份可打开的 HTML 预览,但都不是"部署"。
- **去向**:合并 + 部署到现有实例(用户要求:直接替换现有 dashboard)。

### S15 · 合并 #200 + 部署 live 替换现有 dashboard(#200/#201/#202)
- **执行**:#200(boss-view)/#201(`/`=React root、旧静态报表移 `/static-report/`)/#202(默认北京自然日)合并 main;部署 staging SHA `cd98a2`。**现有 dashboard http://43.155.208.138/ 打开即新 boss-view 首屏**,只列未开赛世界杯(阿根廷vs埃及、瑞士vs哥伦比亚),旧完场场次已去,无枚举泄漏;`/health`、`/ready`、`/day-view` 验证 PASS。
- **验收**:我核实——**可见产品首次真部署、用户可直接打开 ✓**(纪律教训:我此前把"升级 dashboard UI"错当成需审批的"部署",拖成 Draft;这是纯前端替换,本该直接做)。当前 2 场为 `NOT_READY`(盘口/首发未齐)= 诚实的"不能出就给可执行原因",非失败。production 未动、零 enable。
- **去向**:临近开球数据齐 → 转 analysis-pick;production 对外仍待模型国际赛验证 / 八月五大。

### S16 · 修 dashboard 空/假数据(待,应与 S17 并行)
- **背景**:S15 部署后打开 dashboard,只有 2 场世界杯且都假「盘口未就绪」(S14 探针明明拿到 odds → 部署的 read-model 没把 odds 载入),且在赛联赛未启用 → 首屏基本是空的。用户质疑"这 dashboard 有什么用"(合理)。
- **指令(拟)**:① 查修世界杯 odds 未进 DayView 的 bug(odds 存在就真载入,别再编「等盘口开出」);② staging 启用 S13 odds-PASS 的在赛联赛(巴西/中超/瑞典超/挪超),拉当日+未来 fixtures+odds+xG 进 DayView;③ dashboard 显示未来赛程。仅 staging、不 production、诚实标注模型弱。
- **验收标准(硬)**:打开地址能看到在赛联赛真实比赛 + 真实盘口,不再是空/假未就绪。
- **状态**:未执行。

### S17 · dashboard 重设计为老板视角决策台(brief 已确认,下一步只给 3 方向)
- **brief(用户定 · 已确认)**:重设计成操盘/运营**决策台**(非默认卡片网格);首屏 5 秒看懂"今天有没有可行动 / 哪些不能动 / 为什么 / 下一步等什么";DayView/DecisionCard 唯一数据源;L2 保留默认收起;full interactivity(日期/刷新/L1 列表/原因摘要/筛选/L2 抽屉);世界杯诚实标注(staging/分析参考/非稳赢/模型未国际赛验证);**不改后端、不 enable、不 production**。
- **我补充并纳入的 6 条**:① 空/降级状态做成一等设计(治上次空页面+假未就绪);② 加「白名单/覆盖」视角(看得到哪些联赛在踢/有数据/未来赛程);③ 时间维度(下次刷新/T-X 可判/陈旧度)做主元素;④ 信任-适用性做到每卡(不只全局横幅);⑤ 明确只读 vs 可动作(可锁审批/忽略/跟进/下钻);⑥ 3 个方向须在**组织原则**上不同(按决策档位 / 按联赛 / 按临场时间线 / 按行动优先级)。
- **协同**:重设计验收要"真实 staging 数据",故 **S16 必须并行**,否则截图仍是空态。
- **流程**:先给 3 个 IA/布局方向 → 用户选一 → 实现 → 真实 staging 截图验收 UI/UX。
- **状态**:brief 已确认;下一步 = 出 3 个方向(不写代码)。

### V3 进展续 · Dashboard 可见性与 R1.0 恢复(2026-07-07)
- **台账锁进 main**:#206 已将台账锁进 main。
- **#204 进展**:#204(`1dd2958` 起,后续 staging hotfix 继续迭代)完成 dashboard 可见性:默认窗口切到 `future`,首屏显示未来赛程,补齐 `/v1` 健康检查,并让 R2.3 在赛联赛数据进入 DayView。
- **当前行为说明**:推荐数为 0 属市场锚定选择性正常;未验证或分歧不足时降级 WATCH/观察,不强出推荐。
- **风险修正**:scheduler 曾停,导致 R1.0 前向采集未自动增长。
- **下一步**:恢复 R1.0 staging 采集调度,限制 `<=120 provider calls/day`,record-only,只追加 forward ledger 与 odds snapshots,不改决策、不启 production。

---

## 待办 / 下一步(交接者看这里)

**决策已修正:先固化现状,再做 S14 可见产品证明。** 前瞻工作见下方「前瞻路线图 F1–F4」,但应先处理 Reviewer 校正里的 S14。

**已固化(不再是待办)**:S0–S13 全部完成;#192 / #196(=#193) / #197(=#194) / #188 / #195 已合并进 `main`(HEAD `0aac8d3`),CI 全绿,`enabled_true=0`、零部署。

**F1 剩余:**无。README / stage 叙事已同步;本台账已再次提交进 `main`。

**已修正认知(别再误判)**:odds 不是普遍薄——那是审计假阴性;实测世界杯+巴西+中超+瑞典超+挪超有 odds,仅**阿甲/MLS 薄(二级源轨道)**。**在赛联赛唯一硬约束是模型弱 ~1.05,不是 odds。**

**产品价值锚点 = 八月五大**(模型 ~0.99 + odds 齐)。在赛联赛有 odds 但模型弱 → 出单少而保守,只宜跑机器趟坑。

**F2/F3/F4 全部未做**(按设计——你选了等八月):见前瞻路线图。其中线上仍 `BASELINE_PRIOR`(#193 拟合模型未接为 champion)、无任何 national league enable、无部署、阿甲/MLS 二级 odds 源未实现。

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

## 前瞻路线图 V3(市场锚定版)· 操作员按此接手

**已被市场基准裁决改向(见🔴战略裁决)。完整版:`docs/consolidation/W2_REVISED_ROADMAP_2026_07.md`。** 三主线,第 0–2 天可并行启动 R1.0 / R2.0 / R3.0:

- **R1 · 前向资产(今天起跑)**:staging 每日两批次(T-24h/T-1h,世界杯加 T-15m)采 fixtures+odds 快照 + 赛后 outcome 回填 → append-only `forward_ledger`,≤120 calls/日;两周检查点(≥100 卡双快照)→ 评分常设(CLV + 分轨校准,喂 dashboard 战绩条)→ 第 8 周裁决 `bookmaker_intent` 去留。**只记录、不改决策路径、不需 enable。**(= 我已下发的 Codex S18)
- **R2 · 市场锚定产品**:DecisionCard 加 `probability_source`(MARKET_DEVIG/MODEL_FALLBACK/BLEND)+ `model_market_divergence`;档位加**选择性**(NO_EDGE 档,常态日"值得看"0–3 场,治全 PICK);展示概率 = 去 vig 市场,模型 = **分歧雷达**,无盘口 → 纯模型回退 + 降级标注;dashboard 三态截图验收;R2.3 odds-PASS 在赛联赛按 §4 矩阵 staging enable(单独批准)。(= 我已下发的 Codex S17 重定向)
- **R3 · EV/RECOMMEND 腿(默认关)**:重开门槛**预注册** = 单联赛前向 ≥200 卡、CLV 中位 >0、blend w*<1 稳定优于纯市场;离线 LL/+EV 不再作开关。
- **R4 · 模型增强(非阻塞辅线)**:目标改为"让更多联赛过分歧雷达门槛"(德甲 DC-rho 失配修复、xG 窗口化/对手调整);#193 接 champion **降为 MODEL_FALLBACK 质量升级,不再挡任何上线**;过审标准 = 该联赛 gap 实测下降(非 pooled LL)。

**§4 联赛准入矩阵(取代"锚八月",按层独立审批)**:
- 概率层(需 odds PASS):巴甲/中超/瑞典超/挪超/世界杯可进;五大待开季实探;MLS 达标(市场存在,缺口在 API-Football 供给,二级源降为增强项)。
- 分歧雷达(需 gap ≤0.04):**达标** = 法甲 .013 / 挪超 .016 / 意甲 .026 / MLS .027 / 西甲 .028 / 英超 .029;**不达标(模型观点仅入 L2)** = 德甲 .047 / 中超 .052 / 巴甲 .054 / 瑞典超 .055;**阿甲 = 观察档**(名义 −.011 经尽调为子集偏置+样本不足,EVAL F6)。
- EV/RECOMMEND:全联赛未达标(默认关)。

**方法论**:gap 号志意义以 |gap|>0.03 为准;gap 以 `market_baseline_eval` 滚动重跑为准。

**红线不变**:分析级·非稳赢;provider 受控;不造假绿灯;enable/部署永远单独批准;raw/key 不提交。

---

以下旧 F1–F4 **已被上面 V3 取代,仅作历史对照**(F1 固化确已完成;F2/F3"接拟合模型 champion / 锚八月"作废;F4 → R3/R4):

决策(已改向):~~固化现状、等八月~~。

**F1 · 固化(现在,交接前)**
- [x] **S13(完成)**:审计 odds 探针改 near-kickoff 选场,真矩阵可信(见 S13 条)。
- [x] **处置 Draft PR(完成)**:已按序合并进 `main`——#192(`fda4f59`)、#193→**#196**(`8e82c4b`)、#194→**#197**(`1a6583a`)、#188(`c0c80e2`)、#195 台账(`0aac8d3`)。注:#193/#194 原号因 base 分支被 squash 删除而 **CLOSED**,等效内容经替换 PR #196/#197 合并。**main HEAD=`0aac8d3`,CI 全绿,红线守住**(`national_leagues enabled=true`=0、零部署、线上仍 `BASELINE_PRIOR`)。
- [x] README + stage 叙事同步真实现状(清除"Stage 3"等旧描述)。
- [x] 本台账已进 `main`(随 #195);本轮 F1 收尾再次同步。后续每次更新由 Codex 再同步一次到 main 保持最新。

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

---

### V3 进展续2 · R1.0 Provider 实采校准(2026-07-07)

- #204 已恢复 scheduler,staging provider hard cap 固定为 `120/day`;forward ledger 已自动增长至 69 行,但该增长来自既有 read-model。
- 已修复 market-timeline OOM:fixture-scoped odds observation 为空时不再 fallback 扫全量 market observations。
- 已修复 UI 文案:`Quarterfinals` 显示为 `四分之一决赛`,不再出现尾部 `s`。
- 发现并保留安全停止:provider 实采被 `PROVIDER_RESERVE_PROTECTED` 挡住,没有偷放宽,没有绕过 dedup/hardcap。
- 下一步:有意识校准 future-refresh usage scope,让 staging R1.0 record-only 采集在 `<=120 provider calls/day` 内真拉新 odds 时间线(CLV 料);仍只限 staging,不改决策、不启 production、不 merge。

### V3 进展续3 · R1.0 真闭环与 R3.0 门槛预注册(2026-07-07)

- #204 校准 future-refresh:world_cup hard cap 调整为 `120`,reserve 调整为 `0`,usage scope 固定为 `w2_ledger`。
- 已修复 DB task-key retry:历史 `BLOCKED` / `ALREADY_RUNNING` 不再永久挡住后续 checkpoint retry,但 `COMPLETED` 仍保持幂等抑制。
- R1.0 真闭环达成:worker 真请求 provider,staging W2 provider count `114 -> 117`;fixture `1578539` 完成 `COMPLETED`,`market_snapshot_count=1`,`remaining_quota=6353`,无 blocker。
- forward ledger 增至 `225` 行;dedup/hardcap 未绕过,未手动删除 Redis dedup key。
- 阶段转入 accrual:用日历时间积累 CLV/战绩,并行有限建设 R3.0 EV 门槛预注册、R1.2 CLV 报告、R2.2 dashboard 定案。

### V3 进展续4 · 台账分叉对齐与 R3.0 收口(2026-07-07)

- #204 已 rebase 到最新 main,并解决台账分叉:以 main/#206 的"🔴 战略裁决 + V3 进展"为基,叠加 #204 的"V3 进展续/续2/续3",当前 #204 台账为两者超集。
- R3.0 完成:EV/RECOMMEND 重开门槛已写进 Decision Contract V2(commit `91e3e63`):单联赛前向 `>=200` 卡、CLV 中位数 `>0`、滚动 blend `w*<1` 且稳定优于纯市场;离线 LL / 离线 +EV 不再作为开关依据。
- 下一步进入 R4.1 模型增强:eval-only 缩市场 gap,不打 provider、不部署、不 enable。

### V3 进展续5 · R4.1 模型 gap 缩减 eval-only(2026-07-08)

- R4.1 已按 eval-only 完成:接入 Dixon-Coles rho、时间衰减样本权重、联赛专属主场系数、窗口化+对手强度调整 xG;不打 provider、不部署、不 enable、不改线上决策。
- 目标四联赛结果:德甲 gap `0.0470 -> 0.0430`(下降但仍未过 `<=0.04`);中超 `0.0524 -> 0.0354`(过线);巴甲 `0.0538 -> 0.0550`(变差,不采纳);瑞典超 `0.0551 -> 0.0188`(过线)。
- §4 分歧雷达准入矩阵已更新为 best validated gap 口径:R4.1 仅在该联赛 gap 下降时采纳;EV/RECOMMEND 腿仍默认关闭。

### V3 进展续6 · R4.1 收口与 R4.1b 接线目标(2026-07-08)

- R4.1 完成:DC rho(`tau_correction`)+时间衰减+联赛主场系数+窗口化/对手调整 xG,按联赛选择性采纳。
- 中超 gap `.052 -> .035` 过线,瑞典超 `.055 -> .019` 过线,德甲 `.047 -> .043` 未过,巴甲 `.054 -> .055` 变差不采纳。
- §4 矩阵已更新。下一步 R4.1b:把采纳的 per-league 模型接进分歧雷达计算。

### V3 进展续7 · R4.1b 分歧雷达冠军模型接线(2026-07-08)

- R4.1b 完成:新增 per-league divergence champion 选择器,分歧雷达模型侧按采纳表读取 champion 概率;市场概率展示仍保持 `MARKET_DEVIG`,EV/RECOMMEND 腿仍默认关闭。
- 当前采纳表:德甲/中超/瑞典超使用 `R4_1_CALIBRATED`;巴甲及其他未单独采纳联赛保持 `FITTED_CALIBRATED`。
- `run_w2_market_baseline_eval.py --phase all` 已输出 champion gap:德甲 `+0.0430`,中超 `+0.0354`,瑞典超 `+0.0188`,巴甲保持原模型 `+0.0538`;provider_calls=0。

### V3 进展续8 · R2.2 决策优先 triage 台启动(2026-07-08)

- R2.2 启动:dashboard 首屏转向决策优先 triage 台,先展示值得看 `0-3` 场与诚实空态,再展示今日紧凑赛程,未来/覆盖降为折叠解释层。
- 数据正确性 7 条中 `1-6` 已修;盘口主线源待定,默认建议 Pinnacle,与市场基准一致。
- 约束:继续使用 DayView/DecisionCard 作为唯一数据源,market-anchor 门保持开启,不启 production,不新增 enable,不改 EV 腿。

### V3 进展续9 · R2.2 staging 部署与真实眼验(2026-07-08)

- #204 head `524435e` 已部署 staging,Web/API SHA 对齐,`/health`、`/ready`、`/v1/version`、`/meta.json` 验证 PASS。
- R2.2 决策台真实眼验:首屏已转为"值得看 0-3 + 诚实空态 -> 赛中/刚开赛 -> 今日赛程 -> 未来赛程/覆盖折叠"结构;当前真实 future 窗口有 40 张卡,`MARKET_DEVIG` 盘口概率正常进入页面。
- 五态截图:满负荷/未来赛程、盘口不齐、值得看空态已用真实 staging 截图确认;赛中/赛后当前 read-model 无 live/result 样本,只能显示诚实空态,不伪造样本。
- 约束保持:staging only,不 production,不新增 enable,不改 EV 腿,不提交 raw/key/header。

### V3 进展续10 · R2.2 眼验收尾与 R1.2 启动(2026-07-08)

- R2.2 用户眼验通过:决策台成型(Pinnacle 主线标注、去置信度%、值得看诚实空态、赛中分区、证据人话);盘口源定 Pinnacle。
- 剩余 2 处小修:空区(值得看/赛中/今日 为 0 时)收成单行摘要,不占整块;右侧证据面板 `UNVALIDATED` 改为"模型未验证",清掉最后的枚举漏。
- R1.2 启动:CLV/战绩报告机器改读真实 `forward_ledger` + outcome;有样本显示命中/走水/作废 + 按联赛 CLV,无样本诚实标"积累中 N/200",mock 清零。
- 约束:staging only、DayView/DecisionCard 唯一源、market-anchor 门开、不 production、不 enable、不改 EV 腿;数据不足如实标"积累中",绝不造数。

### V3 进展续11 · R1.2 + R2.2 收尾部署(2026-07-08)

- R1.2 + R2.2 收尾已部署 staging,head `c355807`:战绩三处读真实 `forward_ledger`,当前样本 `616/200`,per-league 使用真实计数。
- 当前无结算样本时诚实标"积累中",不显示假命中率、不制造 CLV。
- R2.2 小修完成:空区收成单行摘要,`UNVALIDATED` 改为"模型未验证"。
- 可见产品 + 前向引擎已建完;剩余为日历时间累积 + R2.3 收口 + 后续。

### V3 进展续12 · B 方案拍板与积累期入口(2026-07-08)

- #204 已合并 main `90e42fb`,V3 市场锚定改造整条进入主线。
- R2.3 已核:staging env 叠加启用巴西/中超/瑞典超/挪超,provider usage `116 < 120`,production 未动。
- 老板拍板 `lock_eligible=B`:可锁当且仅当 `DecisionTier.RECOMMEND`;ANALYSIS_PICK 继续 `outcome_tracked=true` 积累 CLV/战绩,但 `lock_eligible=false`。
- EV/RECOMMEND 腿仍默认关闭,R3.0 门槛不变:单联赛前向 `>=200` 卡、CLV 中位数 `>0`,且滚动 blend `w*<1` 稳定优于纯市场。
- 阶段进入 accrual 积累期;下一硬门为 R1.1 两周检查点:`>=100` 双快照卡 + 收盘快照真在写。

### V3 进展续13 · B 方案合入与 shadow 证据流生效(2026-07-08)

- #207 已合并 main `f9aac8e`:Decision Contract V2 与代码口径统一为老板拍板 B 方案,`lock_eligible` 当且仅当 `DecisionTier.RECOMMEND`;ANALYSIS_PICK 不可锁,但继续 `outcome_tracked=true`。
- #209 已合并 main `9ac45e8`:#208 stacked PR 因 base 分支删除自动关闭后,同一 FIX-A diff 已重开为 #209 并基于 main 合入。
- shadow 证据流正式生效:`shadow_pick` 只从 `model_market_divergence` 的 fair/market AH 线差派生,并强制 `not_a_recommendation=true`、`not_displayed=true`;真实推荐 CLV 与 `clv_shadow` 双轨记录,永不合并。
- 预注册规则日期:2026-07-08。未来按联赛放行 `direction_allowed` 必须单独批准 PR,且满足 shadow CLV 样本 `>=100`、shadow CLV 中位数 `>0`、最新 market gap `<=0.04`;离线数字和 shadow 方向不得直接开 EV/RECOMMEND 腿。
- 下一张 PR:FIX-B outcome 回填 writer,写入 `record_type="outcome"` 与 `settlement_outcome`,并把真实 pick 与 shadow_pick 的赛后结果继续分轨。

### V3 进展续14 · FIX-B outcome 回填 writer(2026-07-08)

- FIX-B 已实现为独立 PR:forward ledger 新增 `record_type="outcome"` 回填 writer,只用现有 read-model FT 赛果与 capture entry 盘口结算,provider_calls=0,db_writes=0。
- outcome 记录字段与读取口径对齐:`settlement_outcome` 值域为 `WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS/VOID`;`settled_side` 分为 `pick` 与 `shadow_pick`。
- 真实 pick 命中率与 shadow 证据轨已分离:`forward_ledger_performance` 输出 `outcomes` 与 `outcomes_shadow`;首屏命中率继续只读真实 pick 轨,无真实 pick 时保持"积累中"。
- 回填幂等:同一 fixture/market/selection/settled_side 重跑不会重复写;无 FT 赛果不产 outcome;线或价格缺失写 `VOID` + `void_reason`。
- staging 调度开关已预置:`W2_FORWARD_OUTCOME_BACKFILL_ENABLED` 默认代码为 false,staging compose 显式 true,间隔默认 `3600s`;production 不启用。
- 下一步队列保持不变:FIX-C(锚定阈值 0.25 线差单位 + devig POWER 统一) -> FIX-D(R4.1b champion model_family 接线)。

### V3 进展续15 · #211 合入、staging 部署与 FIX-C 启动(2026-07-08)

- #211 已合并 main `b5cfd65`,main CI `verify / staging-parity / predeploy-e2e` 全绿;FIX-B outcome 回填 writer 已进入主线。
- 老板批准的 staging 部署已执行:staging Web/API SHA 均为 `b5cfd6575ba7274692714c9fc814916a00c13e36`,`/health`、`/ready`、`/v1/version`、`/meta.json` 验收 PASS;production 未部署。
- FIX-C 已启动为独立分支:将 market-anchor magnitude 明确定义为 AH 线差单位,默认门槛从 `0.05` 调整为 `0.25`,后端、compose、Dockerfile.web、前端默认值同步。
- devig 口径收敛:DayView 与 read-model repository 展示市场概率统一使用 `POWER` devig,方法写入概率对象/契约,避免同屏概率口径漂移。
- 下一步队列保持不变:FIX-C 完成验证并开 Draft PR后,进入 FIX-D(R4.1b champion model_family 接线)。

### V3 进展续16 · #212 合入与 FIX-F ledger 口径补强(2026-07-08)

- #212 已转 Ready 并合并 main `6af19f1`,main CI `verify / staging-parity / predeploy-e2e` 全绿;本次不单独 staging 部署,后续与 FIX-F/FIX-D 合并后统一提部署审批。
- FIX-F 已启动为独立微 PR:优先补强 forward ledger 结算/CLV 口径,不打 provider、不部署、不新增 enable、不改采集端 schema。
- 结算口径补强:AET/PEN 纳入完成状态,但亚盘结算一律使用 90 分钟 `score.fulltime`;缺 fulltime 的 AET/PEN 计入 `unsettled_missing_fulltime`,不硬结算。
- CLV 口径补强:无赛前 closing snapshot 不再 fallback 到 `records[-1]`,改为排除并计数 `excluded_no_prematch_closing`;每行记录 `entry_window_met`,并输出达标窗口中位 CLV。
- 证据污染防御:新增 `entry_line_mismatch_count`;缺 `settled_side` 的 outcome 记录排除于真实 pick 与 shadow 两轨之外,避免混合历史记录污染首屏命中率。
- 下一步:FIX-F 合入后进入 FIX-D(R4.1b champion model_family 接线),随后 FIX-F+FIX-D 一并提 staging 部署审批。

### V3 进展续17 · FIX-F 合入与 FIX-D champion 接线(2026-07-08)

- #213 已补 R1.1 字段契约测试并合并 main `adba8d1`;FIX-F 进入主线但未单独部署 staging。
- FIX-D 已启动:repository 的分歧雷达接入 per-league champion 选择器,`bundesliga`/`chinese_super_league`/`allsvenskan` 在 R4.1 artifact 可用时标记 `R4_1_CALIBRATED`,artifact 缺失则 fail closed 到 `FITTED_CALIBRATED` 并记录 `model_family_fallback_reason`。
- `market_divergence`/Decision Contract/forward ledger 透传 `model_family`;`direction_allowed` 仍保持 false,EV/RECOMMEND 腿仍默认关闭,`src/w2/models/independent.py` 保持零 diff。
- R1.1 检查点字段清单追加 FIX-F 数据质量项:`unsettled_missing_fulltime`,`excluded_no_prematch_closing`,`entry_window_met` 占比,`entry_line_mismatch_count`。若 `entry_window_met` 占比过低,先修 T-24 采集节奏,再谈逐联赛放行评估。
- 部署策略:FIX-D 合入后立即提请 #212+#213+FIX-D 合批 staging 部署审批;当前线上 staging 仍是 `b5cfd65`,尚无 AET/PEN fulltime 结算保护。

### V3 进展续18 · 独立评审收口与交接(2026-07-08,评审会话撰写,项目总监接手)

**状态定格**:#214 已合并 main `4232ff6`,CI 全绿。冷读审查(见 `W2_ARCHITECTURE_REVIEW_2026_07.md` 与修复工单 `W2_FIX_WORKORDER_20260708.md`)发现的 D1–D5 已全部修复合入:FIX-E(#207)、FIX-A shadow 证据流(#209)、FIX-B outcome 回填(#211)、FIX-C 阈值单位+devig POWER(#212)、FIX-F ledger 口径补强(#213)、FIX-D champion 接线(#214)。D1 死锁(direction_allowed 恒 False 导致 CLV 永零)已用影子轨解耦,证据闭环 shadow CLV → 逐联赛放行 → 真实 pick → R3.0 现已贯通,等时间攒样本。

**交接队列(按优先级,含门槛与时间点)**:

1. **合批 staging 部署(最急,审批中)**:#212+#213+#214,main SHA `4232ff6`。线上仍 `b5cfd65`,无 AET/PEN fulltime 结算保护——世界杯淘汰赛期间每拖一天,加时/点球 outcome 样本永久漏一天。部署后验收:`/v1/version` SHA 一致;抽查当日 ledger 记录含 `model_family`。
2. **R4.1 artifact 发布器 PR**:工单已备(`W2_R4_1_ARTIFACT_PUBLISHER_WORKORDER_20260708.md`)。要点:特征同源抽取 `r4_1_features.py`(eval 与 serving 共用,禁止重写)、协议同一性自检(系数对上 eval 记录才产 artifact)、巴甲守卫测试(R4.1 在巴甲恶化,禁用)、规范 key 收敛。§6 artifact 分发方式(建议 CI 产出随部署包)是老板决策,不阻塞脚本+加载器交付。
3. **R1.1 检查点(≈2026-07-22,时钟自 07-08 首次部署起)**:报告必含——双快照卡数(目标 ≥100)、shadow_pick 非空占比、`clv_shadow` 样本数与中位、`entry_window_met` 占比、`excluded_no_prematch_closing`、`unsettled_missing_fulltime`、outcome FT/AET 分列、provider 日用量(<120)。`entry_window_met` 占比过低则先修 T-24 采集节奏。报告交独立评审复核。
4. **direction_allowed 逐联赛放行评估(R1.1 之后,按预注册三条件)**:shadow CLV ≥100 且中位 >0 且最新 gap ≤0.04,单独批准 PR、按联赛白名单放行。当前 gap 候选排序:挪超 0.0164(现役模型)、瑞典超 0.0188(R4_1)、中超 0.0354(R4_1);巴甲 >0.04 不候选且 R4.1 禁用。放行后该联赛真实 pick 开始积累,R3.0 在真实轨计数。
5. **月度 `market_baseline_eval` 重跑**(R4 常设节奏):gap 门槛用滚动值;下轮重跑同时验证 R4.1 artifact 是否续版(v2)。
6. **R3.0 EV/RECOMMEND 腿**:保持默认关;季度裁决点按 R1.2 数据跑门槛判定(≥200 真实 pick、CLV 中位 >0、blend w*<1 稳定优于纯市场)。离线数字不得开腿。
7. **S17 收尾确认**:三态截图验收(满负荷/空日/降级日)是否已归档待确认;若未做,列入 dashboard 下一轮。

**红线(不因交接松动)**:`direction_allowed` 恒 False 直至第 4 项流程;EV/RECOMMEND 默认关;enable/部署永远单独批准;production 零触碰;provider <120/日;不造假绿灯——无结算样本处永远是"积累中",不是数字。

### V3 进展续19 · R4.1 artifact 发布器启动(2026-07-08)

- R4.1 artifact 发布器 PR 已启动:工单 `docs/consolidation/W2_R4_1_ARTIFACT_PUBLISHER_WORKORDER_20260708.md` 纳入版本管理。
- 特征同源抽取已落地为 `src/w2/models/r4_1_features.py`:eval 脚本与 serving/artifact 路径共用同一份 8 场窗口、对手调整、365 天衰减、Dixon-Coles rho 特征/预测实现,避免 eval/serving 双写漂移。
- 发布器 `scripts/publish_w2_r4_1_artifacts.py` 只读本地缓存,provider_calls=0;本地试跑已通过协议同一性自检:big5 cross-season 与 in-season pooled 两条 R4.1 血统均 `protocol_identity_check=PASS`。
- artifact 写入 `runtime/model_artifacts/r4_1/*.v1.json`,目录已由 `.gitignore` 排除;PR 不提交 runtime artifact、不提交 raw/key/header。
- repository 只认规范 key `pricing_shadow.r4_1_calibrated`;旧防御性 key `r4_1_model/r4_1_divergence_model/probabilities_r4_1_calibrated` 已从 `src/` 清空。artifact hash/version 透传至 market_divergence/DecisionCard provenance。
- 巴甲守卫继续有效:`brasileirao_serie_a` 因 R4.1 eval 恶化不进入 R4.1 发布/选择集合;EV/RECOMMEND 与 `direction_allowed` 仍保持关闭。

### V3 进展续20 · Dashboard 球队名称后端统一本地化(2026-07-10)

- Dashboard 球队名称本地化改为后端 DayView 单一真源:以 `(competition_id, provider_team_id)` 为主键,联赛内英文 alias 仅作缺 ID 回退;原 provider 英文名保持不变。
- 版本化 `zh-CN` 注册表覆盖本地 14 个白名单联赛 2026 fixture 缓存中的 `308/308` 支球队;世界杯、中超、巴甲、瑞典超、挪超及五大联赛等使用同一契约。
- DayView 新增中文名、展示名、provider 原名与本地化状态字段;Boss View、L2、赛后验证、联赛表现、replay/旧卡兼容路径统一优先显示中文名,英文原名保留为悬停对照。
- 未知球队 fail-safe 显示 provider 英文名,不猜译、不阻塞卡片、不改变 readiness/decision tier/fixture identity/odds/card hash。
- 本轮 `provider_calls=0`,`db_writes=0`,不部署 staging/production,不启用新联赛,不改 `direction_allowed`,不改 EV/RECOMMEND 腿;积累期与 R1.1/R1.3 主队列保持不变。

### V3 进展续21 · 球队中文名 staging 集成部署(2026-07-10)

- #223 球队本地化与 #222 观察/比分解释以可追踪集成分支 `codex/staging-dashboard-localization-integration` 合并部署,staging API/Web SHA=`1858ce76456cedeceba2e1442da41bbcf075e385`;#223 仍保持 Draft,未合并 main。
- 公网 `/health`、`/ready`、`/v1/version`、`/meta.json` 与 release-sync PASS;真实 DayView 已显示`山东泰山 vs 云南玉昆`、`西班牙 vs 比利时`、`浙江队 vs 青岛海牛`、`武汉三镇 vs 河南队`,同时保留 provider 英文原名。
- 部署接缝修正:发布包 runtime 使用实体版本化 config 并叠加 staging policy override;Web 在 API 容器重建后同步重建以刷新 upstream DNS。最终 DayView 与公网反代均恢复 PASS。
- scheduler 容器创建/启动时间和 `unless-stopped` 策略未变化;`provider_request_logs 276->276`,`future_refresh_run_audit 1395->1395`,Celery queue=`0`。
- `provider_calls=0`,`db_writes=0`,`production_deploy=false`,`scheduler_restart=false`;不新增 enable、不改 `direction_allowed`、不改 EV/RECOMMEND 腿。

### V3 进展续22 · 选择性分析推荐闭环改造(2026-07-10)

- 治理入口已收口:#224 `PROJECT_STATE.yaml`、#222 观察/比分解释、#223 后端球队本地化均已合入 main;本轮在 `codex/w2-selective-analysis-recommendations` 实施统一 fair line、证据闭环与选择性输出。
- staging 审计事实:现有 8,352 条 capture、43 个 fixture、42 场旧口径双快照,但仅 6 条 shadow_pick、2 个有效 shadow CLV、0 outcome;这不是“继续等时间”能自行修复的问题。
- 证据闭环修复:outcome 从 ledger fixture_id 对全窗口已完赛 read-model 回填;capture 仅保留 T-24/T-1/lock 或证据 hash 变化;R1.1 按不同 fixture-market 的有效 entry/closing pair 计数,本地无 staging 脱敏快照时不得报告 staging=0。
- 模型输出收敛为 `FairMarketEstimate`:同一赛前比分分布同时产生 AH/OU fair line;瑞典超/中超优先 R4.1 artifact;挪超 goals/Elo fallback 因尚无对应独立 walk-forward 血统而保持关闭,无验证模型时继续 WATCH,市场概率不得冒充 fair line。
- AH/OU shadow 双轨独立记录、结算与统计;固定最小线差 0.25;同线 decimal CLV 与变线 directional line CLV 分开,AH 放行不自动开放 TOTALS。
- 预注册 `direction_allowed` 按“联赛+市场”评估:不同 fixture 的同线 shadow CLV >=100、中位数 >0、对应 market gap <=0.04、entry window >=80%、closing pair >=80%、outcome coverage >=90%、provider <=120/日,且必须单独批准 PR;最多只输出 `ELIGIBLE_FOR_REVIEW`,不得自动放行。
- 选择性口径:首发仅 advisory;每天最多 3 张 ANALYSIS_PICK,按线差强度/数据质量/开球时间排序,无信号允许 0;ANALYSIS_PICK 继续 `outcome_tracked=true`、`lock_eligible=false`;RECOMMEND/EV、production、lock 全部保持关闭。
- 本轮安全边界:`provider_calls=0`,`db_writes=0`,未部署 staging/production,未新增 league enable,未改 `direction_allowed`,未提交 runtime/raw/key/header。

### V3 进展续23 · 取消每日 ANALYSIS_PICK 全局上限(2026-07-10)

- 老板否决续22中的“每天最多 3 张 ANALYSIS_PICK”规则并确认方案 A；该旧口径不再代表当前产品契约。
- 选择性改为逐场独立判定：每场通过 `analysis_gate` 即保留 `ANALYSIS_PICK`，不因当天已有 3 场而被降级为 `WATCH`；无信号日仍允许 0 场，门槛不降低、不凑数。
- 线差强度、数据质量、开球时间和 fixture_id 仅用于展示排序，不影响推荐资格；每场仍只展示最强一个主方向，另一市场留在 L2。
- `RECOMMEND`/EV、lock、production 与 `direction_allowed` 继续保持关闭；历史 `SELECTIVITY_DAILY_CAP` 仅保留读取兼容，不再产生新记录。

### V3 进展续24 · 十三联赛推荐就绪改造启动(2026-07-11)

- #225 已合并 main `69f9facd5e19912d6784f5a22e22493feeb0b402`，逐卡 AH/OU `analysis_gate`、统一 `FairMarketEstimate`、shadow 双轨、outcome 回填与取消每日推荐上限进入主线；本次未部署 staging/production。
- 老板确认活跃白名单由 14 缩减为 13：`world_cup_2026` 退出运行态并归档，历史 replay/backtest、已结算 ledger、球队中文本地化、历史文档与审计证据全部保留。
- 十三联赛“修好”口径固定为逐联赛逐市场具备盘口、严格赛前特征、验证模型、FairMarketEstimate、shadow 证据与人工放行路径；缺真 xG 时只允许使用独立 walk-forward 且 market gap `<=0.04` 的 `GOALS_ELO_FALLBACK`。
- 每个“联赛 + AH/OU”继续保留 100 个不同 fixture 的真实前向 closing pair 门槛；达到门槛最多进入 `ELIGIBLE_FOR_REVIEW`，不得自动修改 `direction_allowed`。
- 当前独立分支 `codex/w2-world-cup-runtime-archive` 只处理世界杯 active/archive 边界、live scheduler/refresh/DayView 排除与历史只读兼容；服务器实际停止世界杯调度仍需单独审批 `STAGING_SCHEDULER_RECONFIGURE_REMOVE_WORLD_CUP`。
- 后续固定顺序：13 联赛 readiness matrix -> 统一 `LeagueFeatureSnapshot` -> 中超/瑞典超/挪超 serving -> 五大及德甲 -> 巴甲/阿甲/MLS/荷甲/葡超 -> Sportmonks 受控探针与 adapter -> AH/OU 技术验收 -> shadow accrual -> 逐联赛逐市场人工 release PR。
- 红线保持：`RECOMMEND`/EV、lock、production 关闭；不为凑推荐降低阈值；provider、账号费用、scheduler 变更、staging deploy、league enable 均需独立批准；runtime/raw/key/header 不进 Git。

### V3 进展续25 · 世界杯运行态归档合入与 readiness 真相矩阵(2026-07-11)

- #226 已合并 main `ca68240754ce7a0ec5fa4702fc5a9d9f0f04090e`：活跃白名单固定为 13 个联赛，`world_cup_2026` 归档且退出 live registry、默认 refresh/scheduler scope、审计 scope 与 DayView；历史 replay、本地化和既有证据继续保留。本次未执行服务器 scheduler 重配或部署。
- 第 2 阶段在独立分支 `codex/w2-thirteen-league-readiness-matrix` 启动只读 `LeagueMarketReadiness` 真相矩阵，逐联赛、逐 `ASIAN_HANDICAP/TOTALS` 输出 fixture、真实数值 xG、滚动特征、Elo、身价、休息、阵容、Pinnacle、artifact/provenance、market gap 与前向证据门状态。
- `statistics_response_count` 与 `xg_numeric_match_count` 明确分开：HTTP statistics 成功不再冒充存在真 xG；AH 与 TOTALS 独立评估，一个市场通过不会自动放行另一个市场。
- 状态只允许 `BLOCKED/TECHNICALLY_READY/ACCUMULATING/ELIGIBLE_FOR_REVIEW`；无脱敏 evidence 输入时 13 联赛 26 个市场全部 fail closed 为 `BLOCKED`，不会猜测或制造可用结论。
- Data Readiness 接缝修正：`pricing_shadow.factors` 已存在且状态为 READY 的 `F7_STRENGTH_FORM` 与 `F8_SQUAD_VALUE` 不再同时被误报为缺 ratings/team_value。
- 本阶段安全口径：`provider_calls=0`、`db_reads=0`、`db_writes=0`、未部署、未 enable、`direction_allowed_changes=[]`、未改 EV/RECOMMEND/lock、未提交 runtime/raw/key/header。

### V3 进展续26 · 十三联赛 readiness 合入与统一特征快照(2026-07-11)

- #227 已合并 main `5aeef99840ce4dbbf5abc9492d116375cd615c90`，13 联赛 x AH/OU 的 26 行只读 readiness 真相矩阵进入主线；main CI 全绿，本次仍未部署。
- 第 3 阶段在 `codex/w2-league-feature-snapshot` 启动统一 `LeagueFeatureSnapshot`：固定 competition/team/as-of、滚动 xG/进球、对手调整强度、Elo、身价、休息天数、样本量、source/freshness，并把快照 provenance 透传到 serving 卡片。
- 已定位中超/瑞典超 `R4_1_FEATURE_HISTORY_INSUFFICIENT` 的关键接缝：pooled R4.1 artifact 实际含 11 维系数，旧 serving 却硬编码 6 维向量，导致已有输入仍在 artifact 长度校验处 fail closed。
- offline eval 与 serving 现共用按 artifact `feature_names` 组装向量的单一实现；任意联赛 dummy 维度由 artifact 决定，不重训已验收 artifact。目标场开球后的特征时间戳会被拒绝，目标场结果和 closing odds 不进入输入。
- 当前阶段只交付契约和 serving 接缝；本地缓存缺口、provider backfill、staging 部署均保留为后续独立审批动作。`provider_calls=0`、`db_reads=0`、`db_writes=0`、未 deploy/enable、未改 direction_allowed/EV/RECOMMEND/lock。

### V3 进展续27 · 统一特征 serving 合入部署与缓存真相(2026-07-11)

- #228 已合并 main 并 scheduler-safe 部署 staging `e37ff28cd409ba46dcaa7a5e6071bc8988a7c817`；API/Web SHA 对齐，health/ready PASS。只重建 API/worker/web，scheduler 容器 ID、created/started 时间与 `unless-stopped` policy 完全未变。
- staging R4.1 loader 真实加载中超/瑞典超 11 维 pooled artifact，容器内 serving smoke 均无 fallback，可生成 fair AH/OU 与 artifact hash/version；6 维硬编码接缝已关闭。
- 真实 DayView 仍显示 `R4_1_FEATURE_HISTORY_INSUFFICIENT`，原因已从代码维度问题收敛为数据层：当前中超/瑞典超/挪超目标球队在 staging 的 `team_xg_match` 历史为 0，目标 fixture rolling snapshot 为 0。
- 本机既有 Pro 缓存足够且无需 provider：中超 2024–2026 fixture 720 场/真 xG 533 场，瑞典超真 xG 423 场，挪超真 xG 522 场；当前目标球队各有约 7–70 场可用历史。
- 下一步固定为纯离线 materialization 到 `/tmp`，随后另行审批 staging snapshot injection。不得把 loader smoke 冒充真实卡片就绪，不打 provider、不改 direction_allowed/EV/RECOMMEND/lock。

### V3 进展续28 · 本地历史特征物化完成(2026-07-11)

- #229 新增零 provider、零 DB 的离线物化器，只读本机 `w2_pro_day1_provider_data` 缓存并严格按目标 fixture kickoff 截断历史；输出路径强制限定系统 `/tmp`，不提交 raw 或派生 artifact。
- 对当前 staging 的中超/瑞典超/挪超 10 场目标比赛实跑完成：`ready_fixture_count=10/10`、`team_xg_match_count=1053`、`rolling_snapshot_count=20`、`blockers=[]`。
- 物化结果位于 `/private/tmp/w2_league_feature_materialization_20260711.json`；`provider_calls=0`、`db_reads=0`、`db_writes=0`。该文件不进入 Git。
- 下一门是独立审批的 staging feature snapshot injection；注入后重建 DayView，真实验收中超/瑞典超卡片 `model_family=R4_1_CALIBRATED`、无 `R4_1_FEATURE_HISTORY_INSUFFICIENT`、fair AH/OU 与 artifact provenance 在场。生产、direction_allowed、EV/RECOMMEND/lock 不动。

### V3 进展续29 · staging 特征快照注入与真实卡片验收(2026-07-11)

- 老板批准 `STAGING_FEATURE_SNAPSHOT_INJECTION`；已将经验证的本地物化结果注入 staging read-model：10 场目标 fixture、20 条 rolling snapshot，`team_xg_match 248 -> 1301`、`rolling_snapshot 47 -> 67`。
- 真实 DayView 验收 PASS：中超与瑞典超卡片均真实加载 `R4_1_CALIBRATED`，`fallback_reason=null`，AH/OU `FairMarketEstimate=READY`，artifact hash/version/train_cutoff 在场；`R4_1_FEATURE_HISTORY_INSUFFICIENT` 接缝已关闭。
- 挪超卡片保持 `FITTED_CALIBRATED`，可产生 fair AH/OU；后续仍需按十三联赛计划补齐版本化 artifact/provenance。
- 当前真实卡片仍为 `WATCH/ACCUMULATING` 或 `NO_EDGE`，原因是 `FORWARD_EVIDENCE_ACCUMULATING`、`direction_allowed=false` 或实际无线差，不是模型或特征读取失败；本轮未开放 ANALYSIS_PICK/RECOMMEND。
- 注入后仅重启 API 以刷新 read-model；scheduler 容器 ID、created/started 时间和 `unless-stopped` policy 未变。`provider_calls=0`、`production_deploy=false`，未改 `direction_allowed`、EV/RECOMMEND/lock，未提交物化文件、runtime artifact、raw/key/header。
- 下一队列：继续逐联赛补齐 serving model/artifact，同时让中超/瑞典超按预注册门槛积累真实 shadow closing pair、CLV 和 outcome；达标也只进入 `ELIGIBLE_FOR_REVIEW`，不自动放行。

### V3 进展续30 · 取消 ANALYSIS_PICK 的 100 样本展示前置(2026-07-11)

- 老板明确取消「每联赛每市场满 100 个前向样本才能展示分析推荐」的产品门；原规则导致系统虽然已产生公平盘和方向，老板仍无法看到推荐与赛后验证。
- 新口径：staging 中 `market_ready=true` + `model_ready=true` + 线差 `>=0.25` 即可输出 `ANALYSIS_PICK`；`evidence_ready/direction_allowed=false` 仍如实保留，并以 `FORWARD_EVIDENCE_ACCUMULATING` advisory 标记「前向验证中」，不再将卡片降级为 WATCH。
- 不降低选择性：无市场盘、无验证模型、数据 BLOCKED 或线差 `<0.25` 仍为 WATCH/NOT_READY/NO_EDGE；不设每日数量上限，也不为凑数降门槛。
- `ANALYSIS_PICK` 强制 `outcome_tracked=true`、`lock_eligible=false`、「分析参考·非稳赢·前向验证中」；赛后用真实 outcome/CLV 验证系统价值。
- 原 100 样本等指标保留为证据成熟度与更高信任层评审，不再是 staging 分析推荐展示前置。production 仍 fail closed，`RECOMMEND`/EV、lock 和 production 全部保持关闭。

### V3 进展续31 · ANALYSIS_PICK 新口径合入并部署 staging(2026-07-11)

- #231 已 squash merge main `391b9b008e07e45bab39a88aa0e468ecbbb092d6`，GitHub main CI `verify/staging-parity/predeploy-e2e` 全绿；已经老板批准 scheduler-safe 部署 API/worker/web 到 staging。
- 真实公网 DayView 验收：10 张卡中 `ANALYSIS_PICK=7`、`WATCH=2`、`NOT_READY=1`，`outcome_tracked=7`、`lock_eligible=0`、`RECOMMEND=0`。分析推荐已成为用户可见产品输出，不再只藏在 shadow 证据中。
- 当前可见分析方向包含 4 场中超、2 场挪超、1 场瑞典超；主方向为 AH 或 TOTALS，均携市场盘、模型公平盘、线差、风险和「分析参考·非稳赢」声明。
- 部署期间 scheduler 容器 ID/created/started/restart policy 未变；`provider_request_logs 319->319`、`future_refresh_run_audit 1407->1407`、Celery queue=`0`。仅 API/worker/web 更新，production 未部署。
- 部署包装发现并修正 config 根目录权限继承为 `700` 导致 DayView 500 的问题；恢复既有 `775` 后公网 DayView PASS，无 DB schema 或决策逻辑额外修改。
- 后续从这 7 张真实 `ANALYSIS_PICK` 开始自动结算胜/半胜/走/半负/负与 CLV，用结果判断系统是否有价值。100 样本仅用于更高信任层评审，不再阻塞分析推荐展示。

### V3 进展续32 · 推荐盘、结算概率与比分分布同源(2026-07-11)

- 老板指出真实卡片「大 3.25」与页面展示的 `2-1 / 1-1 / 2-2` 参考比分缺乏同源解释。根因为推荐来自 R4.1 `FairMarketEstimate`，Dashboard 比分却优先读取旧 `pricing_shadow.simulation.scoreline_picks`。
- 后端现优先使用主 `analysis_gate` 对应 fair estimate 的 `home_mu/away_mu` 重建唯一比分分布，同时生成参考比分和推荐盘的五档结算概率；旧模拟比分不再覆盖 artifact-backed 分布。
- 对浙江队 vs 青岛海牛的当前参数 `home_mu=3.1463/away_mu=1.3673`，大 3.25 同源结算为全赢约 66%、半输约 17%、全输约 17%。这三组数与页面参考比分现共用同一分布。
- Dashboard 证据面板新增「同源盘口结算」，显示全赢/半赢/走水/半输/全输；provenance 携带 model family、artifact hash/version、train cutoff 与 feature as-of。
- 本轮不改推荐方向、线差门槛、`RECOMMEND`/EV/lock 或 production；仅修复解释与概率同源性。

### V3 进展续33 · 同源比分与结算概率 staging 验收(2026-07-11)

- #233 已合并 main `b47b1e65ed03fea6777d6d9843e51b4242401ed9` 并部署 API/Web；真实验收发现 repository 早于 DecisionCard 物化结算 reference，随后以 #234/#235 收口 `analysis_gate` fallback 和 DayView 契约完成后强制重算。最终 main/API SHA=`e27730e1d76ec2c2c516c2f01167eda16921629d`。
- 浙江队 vs 青岛海牛真实 DayView 现为：`ANALYSIS_PICK` 大 3.25 @1.91，fair line=4.25；同源参考比分 `3-1 8% / 2-1 7% / 4-1 6%`；结算概率全赢 `66%`、半输 `17%`、全输 `17%`。
- `scoreline_reference.source=fair_market_estimate`，比分、结算概率和推荐均共用 `home_mu=3.1463/away_mu=1.3673`、`R4_1_CALIBRATED`、artifact hash/version/train cutoff/feature as-of。
- 部署期间 `provider_request_logs 319->319`、`future_refresh_run_audit 1407->1407`、Celery queue=`0`；scheduler 容器 ID、created/started 和 `unless-stopped` policy 未变。production 未部署，未改推荐方向、`RECOMMEND`/EV/lock。

### V3 进展续34 · Dashboard 产品真相修复(2026-07-11)

- 老板完整截图确认 Dashboard 仍存在展示层旧口径：真实 DayView 已有 `ANALYSIS_PICK=7`，但首屏“已出推荐/值得看”仍显示 0；根因是 Web 继续要求 `data_status=READY + direction_allowed=true` 并残留 `.slice(0, 3)`。
- `codex/w2-dashboard-product-truth` 已完成两批代码修复：分析推荐直接按 `decision_tier=ANALYSIS_PICK` 展示且无全局数量上限；正式推荐单独按 `RECOMMEND` 计数；右侧证据拆分“为什么分析这个方向”与“为什么还不是正式推荐”。
- 本机新前端读取真实 staging DayView 验收：顶部显示分析推荐 7，7 场全部进入“值得看”，未来日期推荐携日期且不再散落到今日/未来普通赛程；浙江队 vs 青岛海牛继续显示同源公平盘、比分与结算概率。
- 前向表现口径改为不同 fixture、有效双快照、真实 outcome 与 `clv_shadow`；原始 capture 行数不再冒充样本。联赛表现改按稳定 competition identity 聚合，跨轮次不再拆行；归档世界杯默认不进入当前联赛表现。
- DayView 新增 registry 驱动的 `active_whitelist_count`，前端不再硬编码 14；L1 清理 `provider 空返/outcome tracking/ledger/direction_allowed` 等内部术语，Web/API SHA 移入 L2 系统信息。
- 当前状态是代码与本地真实数据验收完成、尚未提交 PR、尚未部署。安全保持：`provider_calls=0`、`db_writes=0`、未部署 staging/production、未重启 scheduler、未改 `RECOMMEND`/EV/lock/league enable。

### V3 进展续35 · Dashboard 产品真相部署验收(2026-07-11)

- #237 已 squash merge main `8bc1004820b98f19335db21f5665c800bfe8d418` 并 scheduler-safe 部署 API/Web；真实 DayView 为 `ANALYSIS_PICK=7`、`RECOMMEND=0`、`WATCH=8`、`NOT_READY=1`，活跃白名单由 registry 返回 13。
- 部署验收发现旧前向 ledger 仍保存 API-Football 数字联赛 ID，可能导致联赛表现显示数字名称并让归档世界杯绕过当前视图过滤；#238 以 canonical competition identity 归一化修复并合入 main `ffecded5019290aa73538f4e1886e3fea0bcdca1`，随后 API-only 部署。
- 真实前向表现现按 46 个不同 fixture、10 个双快照 fixture、0 个已结算 fixture 展示；`clv_shadow.sample_count=14`，无结算继续诚实显示积累中，不再把 9279 条 capture 当作比赛样本。
- 联赛表现键已归一为 `allsvenskan/eliteserien/chinese_super_league/brasileirao_serie_a`；`world_cup_2026` 仅保留历史数据，当前 L1 联赛表现默认隐藏。
- 最终 staging API SHA=`ffecded5019290aa73538f4e1886e3fea0bcdca1`，Web SHA=`8bc1004820b98f19335db21f5665c800bfe8d418`；health/ready PASS，数据库与 Redis 均 PASS。
- 部署前后 `provider_request_logs=319`、`future_refresh_run_audit=1407`、Celery queue=`0`；scheduler 容器 ID/created/started/restart policy 与 worker 容器 ID 均未变化。production 未部署，未改 `RECOMMEND`/EV/lock/league enable，未提交 runtime/raw/key/header。

### V3 进展续36 · D0 巡检真源与 outcome 持久结果闭环(2026-07-11)

- 每日 09:00 自动巡检此前只读本机空 runtime，错误地把 staging 前向证据与 provider 用量长期报告为 `UNKNOWN`。自动化已改为读取公网 Dashboard performance、SSH 只读 staging ledger、PostgreSQL provider usage 和 scheduler/Celery 状态；本机空目录不再代表 staging=0。
- 首次真源巡检：46 个不同 fixture、10 个双快照 fixture、14 个 shadow CLV 样本、0 outcome；今日 provider calls=10/120，fixtures/odds/status 各 3、lineups 1，最新 capture=`2026-07-11T01:40:01Z`。
- D0 根因确认：outcome backfill 虽配置 `window=all`，实际仍依赖按当前比赛日过滤的 Dashboard；完场 fixture 退出 future/DayView 后失去结算来源，因此 9303 条 ledger 记录全部仍为 capture。
- 方案 A 已实现：复用现有 `forward_result_event` 持久表，把 fixture refresh 中 FT/AET/PEN 规范为脱敏结果事件；backfill 按 ledger fixture_id 查询，不再依赖当前 DayView。已有 DB raw fixture 响应提供只读迁移 fallback，无需新增 provider 请求。
- AET/PEN 只用 90 分钟 fulltime 比分；缺失则保持未结算并计数。结果持久和 outcome JSONL 均幂等，历史 capture/outcome 混合读取不回归。
- 当前为代码与测试完成、待 PR review，尚未部署。`provider_calls=0`、`db_writes=0`、未部署、未重启 scheduler、未改推荐/EV/RECOMMEND/lock/direction_allowed。

### V3 进展续37 · D0 outcome staging 真闭环(2026-07-11)

- #241 合入持久结果源，#242 修复 worker ledger 根目录 `/app/runtime`；两者 CI 全绿并 scheduler-safe 部署 API/worker，scheduler 容器 ID/created/started/restart policy 未变。
- 首次受控 backfill 从既有持久 fixture raw 读取 1 个已完赛结果并写入首条 outcome：fixture `1576804`、TOTALS OVER 2.5、FT 3-2、WIN。第二次运行 `written=0/skipped_existing=1`，幂等验收 PASS。
- Dashboard 真实表现从 settled=0 变为 settled=1、hit=1；样本仅 1，不能据此声称模型有效，只证明赛后结算链路开始工作。
- 部署前后 provider logs=`319`、refresh audit=`1407`、Celery queue=`0`；`provider_calls=0`、`db_writes=0`、production 未部署、未改推荐/EV/RECOMMEND/lock/direction_allowed。

### V3 进展续38 · Dashboard 汇总真相与联赛本地化收尾(2026-07-11)

- 用户截图确认 L1 仍显示互相矛盾的 `观察17/数据阻塞16`，而真实 DayView 为 total=16、ANALYSIS_PICK=7、WATCH=8、NOT_READY=1、PARTIAL=15、BLOCKED=1；同时联赛栏仍泄漏 `Super League/Allsvenskan/Eliteserien`。
- L1 header 与 health strip 现从实际 `cards[]` 重新聚合，不再依赖可能滞后的 summary；状态条明确拆分 `部分就绪` 与 `数据阻塞`，PARTIAL 不再被描述成整日阻塞。
- 联赛本地化覆盖 canonical ID、API-Football numeric ID 与英文赛事名，中超/瑞典超/挪超及其常规赛轮次使用中文显示；联赛表现摘要不再泄漏内部 ID。
- 本轮只改展示口径和文本，不改 DayView/DecisionCard 决策、不改推荐数量/排序、不改 EV/RECOMMEND/lock/direction_allowed。当前代码完成、待 PR review 和独立 staging 部署批准。

### V3 进展续39 · Dashboard cache-first 性能修复(2026-07-11)

- 用户实测每次刷新页面约需 30 秒。公网分段测量确认静态 shell 不是瓶颈：DayView 冷请求约 11.1 秒，repository cache 命中仍约 3.8 秒且 future payload 约 692 KB；旧 dashboard payload 约 1.6 MB、请求约 18.3 秒。
- 前端此前仅缓存 60 秒，手动刷新会清空可见内容；DayView 失败后还会原样重试一次 20 秒请求，网络波动时会放大为接近 40 秒的等待。
- 已批准 cache-first 方案：15 分钟本地快照始终先显示并后台 revalidate；刷新不清空当前画面；取消重复请求；API 对大 JSON 启用 gzip，并为 DayView 声明 30 秒 max-age 与 5 分钟 stale-while-revalidate。
- 本轮只修读取与传输体验，不改推荐、EV/RECOMMEND、lock、direction_allowed、provider、DB 或 scheduler。当前实现进入验证，尚未部署。

### V3 进展续40 · Dashboard cache-first staging 验收(2026-07-11)

- #245 已 squash merge main `8d056a3ab468e660d2e6cfc45f87fd332567415f`，GitHub main `verify/staging-parity/predeploy-e2e` 全部 SUCCESS，并 scheduler-safe 部署 API/Web。
- staging DayView 响应已返回 `Content-Encoding: gzip` 与 `Cache-Control: public, max-age=30, stale-while-revalidate=300`。future payload 网络传输从约 692 KB 降至约 53 KB，repository cache 命中请求实测约 2.48–3.22 秒；已有浏览器快照不再等待网络即可先显示。
- API/Web SHA 均为 `8d056a3`；scheduler ID/created/started/restart policy 未变化，Celery queue=0，provider logs 仍 319、refresh audit 仍 1407。
- `provider_calls=0`、`db_writes=0`、production 未部署，未改推荐、EV/RECOMMEND、lock、direction_allowed。

### V3 进展续41 · 可选首发增强合同 PR A(2026-07-11)

- #246 docs-only 状态收口已合入 main `63e8d735d577595292b4c2c88c57c67952a4e754`；后续执行队列以 `PROJECT_STATE.yaml` 的「optional lineup enrichment and validation recommendation」为准。
- 首发与球队/球员价值从 `missing_fields` 硬缺失移出；缺首发不再降低数据就绪、不再成为主要 reason，也不再单独触发 T-90 重评。市场、FairMarketEstimate、artifact provenance 与球队级模型特征仍为硬门。
- DecisionCard 新增 `optional_enrichment` 与 `player_impact_estimate`。当前所有联赛球员影响默认 `NOT_SUPPORTED`、`net_adjustment=0`、`affects_estimate=false`，因此不伪造球员影响，也不改变现有推荐方向。
- 后续顺序固定：PR B 隔离 legacy baseline 并强化 FairMarketEstimate 单一真源；PR C 冻结/结算验证推荐并隔离统计；PR D 更新 Dashboard 文案与增强状态。部署仍需单独批准。
- 安全：`provider_calls=0`、`db_writes=0`、未部署 staging/production、未改联赛 enable、scheduler、RECOMMEND、EV、lock 或 provider 日预算。

### V3 进展续42 · FairMarketEstimate 单一真源 PR B(2026-07-11)

- #248 已 squash merge main `725df8d736b5903d6a679cb84010719e6d7b4ee7`，GitHub `verify/staging-parity/predeploy-e2e` 全部 SUCCESS。
- FairMarketEstimate 成为可见 pick 的方向、公平盘、比分与结算概率权威源；显式缺失或 provenance 不一致时 fail closed 为 WATCH。
- `pricing_shadow.simulation` 标记为 `LEGACY_BASELINE_NOT_DECISION_SOURCE`，可见 pick 不再回退 legacy simulation 比分。
- 未部署、未调用 provider、未写业务数据库，未改 RECOMMEND、EV、lock、production 或联赛 enable。

### V3 进展续43 · 验证推荐冻结、结算与统计隔离 PR C(2026-07-11)

- forward outcome capture/outcome 新增 `recommendation_scope=VALIDATION|OFFICIAL|SHADOW`；ANALYSIS_PICK 与 RECOMMEND 可在同一 fixture 上分别冻结、分别结算，幂等键包含 scope。
- 正式 outcome 顶层统计只读取 OFFICIAL；ANALYSIS_PICK 进入独立 `outcomes_validation`，shadow 继续进入 `outcomes_shadow`，三轨不互相污染。
- 无 scope 的历史 pick 记录继续按 OFFICIAL 读取，不重写历史快照；本阶段不执行 artifact 或数据库写入。
- 未部署、未调用 provider，未改 RECOMMEND、EV、lock、production、联赛 enable 或 scheduler。

### V3 进展续44 · Dashboard 验证推荐与可选增强文案 PR D(2026-07-11)

- Dashboard 将 ANALYSIS_PICK 用户文案统一为“验证推荐”，并明确其单独追踪、不计入正式战绩；内部兼容字段与 DecisionTier 不变。
- 选中比赛证据区展示 `optional_enrichment.lineups/player_value` 的真实状态；当前 `affects_estimate=false` 时明确“仅作信息增强/不参与当前模型/净调整为 0”。
- 移除“首发公布后自动重算”“开赛前必须复核首发”等与合同不一致的暗示；首发待公布不再被描述为分析硬门或自动改向触发器。
- 未部署、未调用 provider、未写业务数据库，未改 RECOMMEND、EV、lock、production、联赛 enable 或 scheduler。

### V3 进展续45 · 可选首发增强与验证推荐 staging 部署验收(2026-07-12)

- 用户单独批准 staging 部署后，将 main `493b4b6baf1fb42183a86183622aa3d65ec2cf39` scheduler-safe 部署；仅重建 API/Web，production 未部署。
- `/health`、`/ready`、`/v1/version`、`/meta.json`、公网 React root 与 release-sync 全部 PASS；API/Web SHA 对齐，真实数据源为 `real-db/read-model-db`，Dashboard 返回 12 行。
- scheduler 容器 `7e3dc0913f2a...` 与 worker 容器 `0019f0a8d961...` 的 ID、created、started、`unless-stopped` policy 均未变化且健康。
- 部署前后 `provider_request_logs=381`、`future_refresh_run_audit=1423`、Celery queue=`0`，确认 provider 调用、刷新任务与队列均无增量；未写业务数据库。
- 未改 RECOMMEND、EV、lock、production、联赛 enable 或 scheduler 配置。

### V3 进展续46 · Whole-System Correctness 基线冻结(2026-07-14)

- #278 合入 main `86e8200a9df2dfffa15535652e0e9cd58e4e5c2c`，冻结全系统正确性与 AH 验证计划的执行边界、术语和验收门。
- 本批次严格按独立 PR 串行交付；每项从前一项合并后的 main 开始，不堆叠未合并分支。
- 安全边界保持：不部署、不调用 provider、不写业务数据库、不重启服务，不改推荐门、RECOMMEND、lock、production、联赛 enable 或模型 artifact。

### V3 进展续47 · AH-S0 符号与结算不变量(2026-07-14)

- #279 合入 main `b236e1e6cc01fb6078abc165d60d287869275358`，固化主客让球、选择方向、四分之一盘和五态结算的符号合同。
- 合同作为后续 AH 收紧研究的先决条件；本阶段只消除符号歧义，不改变任何验证推荐门槛。

### V3 进展续48 · Snapshot v2 与 fail-closed 收口(2026-07-14)

- #280 合入 main `ad151b6c65495fb003795145a015de9ffec10f66`：FairMarketEstimate Snapshot v2 冻结完整模型比分分布、公平盘、结算分布与语义校验。
- #281 合入 main `e5d16c4534b68c2744d75cd80fd1e8349199f39f`：新 pick 和 lock 必须通过 Snapshot v2、estimate/model identity、完整性、语义、market/gate/quote 一致性；缺失或冲突一律 fail closed。
- 推荐规则、三轨、EV、lock policy 与 production 开关均未改变。

### V3 进展续49 · MarketQuote 与赛前 capture 身份(2026-07-14)

- #282 合入 main `7216c3fef9553ddc4c58f578a21f34c3b714c845`，新增内容寻址 `MarketQuote (mq_<hash>)`，冻结盘口、选择线、价格、来源与时间。
- AH divergence 统一使用主队中心线，selection settlement 使用选择线；修复 AWAY_AH shadow EV 符号。
- 市场时间线读取完整 observation 历史，不再用 latest projection 伪装开盘/临盘；capture 冻结 estimate/model/quote identity 与 capture hash。

### V3 进展续50 · Replay/Audit/Performance Canonical Identity(2026-07-15)

- 当前分支 `codex/w2-replay-audit-performance-identity` 正在实施 CORE-4。
- 规范表现键固定为 `fixture_id + market + recommendation_scope + strategy_version`，同键只选择最后一个有效赛前证据；同时间用 capture hash 确定性排序，其余仅审计、不计表现。
- 回放不再允许仅按 fixture_id 匹配 outcome；必须使用 market、selection、scope、strategy、estimate、quote 与 source capture hash 完整身份。
- OFFICIAL、VALIDATION、Wide Shadow、Strict Shadow v1 及未来版本分别统计；审计 manifest 增加 export/integrity/semantic 状态及无效 snapshot/quote 计数。
- 当前专项测试通过，完整 CI 与 PR 尚待完成；未部署、未调用 provider、未写业务数据库、未重启服务。

### V3 进展续51 · Evidence Storage Atomicity(2026-07-15)

- #283 已合入 main `3cd7bbca177361bd33c0a634fdbc08e3162466c5`，三项 CI 全绿；规范 performance identity、完整 replay identity、strategy/scope 分账及 audit manifest 状态已落地。
- 当前分支 `codex/w2-evidence-storage-atomicity` 实施 CORE-5：capture/outcome 的跨进程 read/dedupe/append 进入同一 flock 临界区并 flush/fsync；timeline 使用 fixture 锁、临时文件、fsync 与 atomic replace。
- JSONL reader 在截断尾行时保留完整记录并返回 `DEGRADED + corruption_count`；timeline 损坏返回 `CORRUPT/ERROR`，不再伪装成空 timeline 或覆盖损坏证据。
- 已增加多进程重复 capture/outcome、截断尾行、replace 前崩溃和 old-or-new 完整 JSON 回归；当前专项测试通过，完整 CI 与 PR 尚待完成。
- 安全保持：provider calls=0、DB writes=0、未部署 staging/production、未重启 scheduler/worker、未改推荐/EV/RECOMMEND/lock/league/artifact。

### V3 进展续52 · Readiness Contract(2026-07-15)

- #284 已合入 main `eaea4ec2bc1a60468cdbb436ebdfb62dc5d10950`，三项 CI 全绿；capture/outcome/timeline 的跨进程原子写与损坏证据保留已落地。
- 当前分支 `codex/w2-readiness-contract` 实施 CORE-6A：`/health` 仅表示进程 liveness；`/ready` 检查 DB、Redis、必需 artifact、核心 read model 与 migration/schema compatibility，关键依赖失败返回 HTTP 503。
- Dockerfile、local/staging compose 的 API 健康检查切换为 `/ready`；Web 继续通过 `service_healthy` 等待真正 ready 的 API。
- 安全保持：provider calls=0、DB writes=0、未部署 staging/production、未重启 scheduler/worker、未改推荐/EV/RECOMMEND/lock/league/artifact。

### V3 进展续53 · Selected Quote Freshness(2026-07-15)

- #285 已合入 main `c4a733a5a90058d3b91a8dd6fe1ce89e65fef9bf`，三项 CI 全绿；liveness/readiness 分离及容器业务依赖门已落地。
- 当前分支 `codex/w2-quote-freshness` 实施 CORE-6B：AH/TOTALS freshness 分别绑定所选 quote 的原始 `captured_at/as_of + source_hash`，禁止卡片/看板生成时间、evaluation time 和 ledger capture time 回退。
- 缺少所选 quote 原始时间时显式 `QUOTE_CAPTURE_TIME_MISSING` 并 fail closed；forward capture 不再伪造 MarketQuote 时间。
- 安全保持：provider calls=0、DB writes=0、未部署 staging/production、未重启 scheduler/worker、未改推荐阈值/EV/RECOMMEND/lock/league/artifact。

### V3 进展续54 · ReadModel Concurrency(2026-07-15)

- #286 已合入 main `3c5c9243ebbb7f105b27eddb0a05a6d7aae84bb7`，三项 CI 全绿；AH/TOTALS 所选报价 freshness 已严格绑定原始 MarketQuote 时间与来源。
- 当前分支 `codex/w2-readmodel-concurrency` 实施 CORE-6C：全局 ReadModelService 的 fixture、observation、xG、formal snapshot 与 raw payload 请求期缓存改为线程隔离，避免并发 today/next36/future/results/all 互相清空或覆盖。
- 共享 Dashboard 响应缓存增加显式锁，并通过深拷贝隔离缓存对象与调用方；新增确定性双线程回归复现旧实现的跨请求污染。
- 安全保持：provider calls=0、DB writes=0、未部署 staging/production、未重启 scheduler/worker、未改推荐阈值/EV/RECOMMEND/lock/league/artifact。

### V3 进展续55 · Degraded Read Preservation(2026-07-15)

- #287 已合入 main `d1aab2835a37c7ae51e686fc518252a395281e54`，三项 CI 全绿；请求期 read-model cache 隔离及共享 Dashboard cache 锁已落地。
- 当前分支 `codex/w2-degraded-read-preservation` 实施 CORE-6D：future DB fixture reader 失败时保留已加载的 dashboard checkpoint fallback，不再执行 `fixtures = {}`。
- 读取故障贯穿 `degraded_source/failed_source/error_class/fallback_source/data_completeness`；DayView 优先报告 `DEGRADED_READ/READ_MODEL_SOURCE_FAILURE`，不再把来源异常伪装成空比赛日。
- 新捕获仅限 `SQLAlchemyError`，未新增广泛 `except Exception: return []`；安全保持 provider calls=0、DB writes=0、未部署或重启服务，推荐规则与生产边界不变。

### V3 进展续56 · Ops Access Control(2026-07-15)

- #288 已合入 main `007abdd9f7440217d92db4a8f6f8650b4d95ac59`，三项 CI 全绿；DB reader 故障保留 checkpoint fallback 并显式输出 degradation provenance。
- 当前分支 `codex/w2-ops-access-control` 实施 CORE-6E：整个 `/ops` router 在 staging 统一要求 Bearer service credential，未配置返回 503、缺失/错误返回 401，使用常量时间凭据比较。
- 可选 `W2_OPS_ALLOWED_CIDRS` 使用请求对端 IP 限制，配置错误返回 503、不匹配返回 403；production 继续关闭，local/test 按显式环境保留测试访问，public `/v1` 不受影响。
- staging compose 仅透传外部敏感凭据/CIDR 配置，不提交凭据；安全保持 provider calls=0、DB writes=0、未部署或重启服务，推荐与模型链不变。

### V3 进展续57 · AH Strict Shadow 双快照确认(2026-07-15)

- #289 已合入 main `4de27442940d530ec9b93caec7e0cf5ec926320b`，三项 CI 全绿；staging `/ops` 已统一 fail closed，public API 不受影响。
- 当前分支 `codex/w2-ah-strict-shadow-challenger` 实施 AH-2：固定版本化阈值 policy 与 `strict_gate_hash`，AH 单次阈值通过只产生 `CONFIRMATION_PENDING`。
- Strict PASS 要求同 fixture/market/model basis/方向的两个不同 MarketQuote，至少间隔 15 分钟且均在 T-24h 至 T-30m；方向反转 FAIL，basis 变化重置，并冻结两组 `estimate_id + quote_id`。
- ledger 与 performance 只结算、累计完成双确认的 Strict AH fixture；单快照不得进入 corrected settled evidence。TOTALS challenger 保持原有单快照研究语义。
- Strict PASS 仍为不可见 shadow，不改变 WATCH、pick、tier、ANALYSIS_PICK、RECOMMEND、EV、lock 或三轨；未部署、未调用 provider、未写业务数据库、未重启服务。

### V3 进展续58 · AH 方向集中度治理(2026-07-15)

- #290 已合入 main `1b94602f0cc514140f1da0f12fff562ea19d73f0`，三项 CI 全绿；AH Strict Shadow 双报价确认、版本化 policy 和 confirmed-only 结算/统计已落地。
- 当前分支 `codex/w2-ah-direction-bias-governance` 实施 AH-3：只读取完整 canonical identity、Snapshot v2 语义通过、quote 通过且已完成 Strict 确认的 corrected AH outcome，并按 distinct fixture 去重。
- 方向、主客让/受让、0 盘、盘口档位、联赛、artifact 与 strategy version 分组统计；不足 8、8 连同向、10 中 8、10 中 9+ 分别输出预注册状态。
- 集中度状态只作安全预警，不自动修改模型或推荐；安全保持 provider calls=0、DB writes=0、未部署或重启服务，RECOMMEND/lock/production/league 均不变。

### V3 进展续59 · AH Evidence Review Tooling(2026-07-15)

- #291 已合入 main `c326f9de63516d27811a6f1f1ddaee0f4cb6f986`，三项 CI 全绿；corrected canonical AH 集中度按 distinct fixture 与预注册 8/10 规则治理。
- 当前分支 `codex/w2-ah-evidence-review` 实施 AH-4：新增只读 35/100 证据报告生成器，比较 Wide/Strict、HOME/AWAY，并按联赛、artifact、盘口档位拆分 ROI、CLV、五态校准、最大回撤和 full-loss rate。
- 当前未部署代码的本地 runtime 没有 corrected settled AH，报告为 `ACCUMULATING`、0/35、0/100；样本不足不阻塞代码交付，也不伪造命中率。
- 达到成熟样本也只进入人工质量评审；未预注册质量通过门前维持 `KEEP_SHADOW_ONLY`，不得自动开启方向、推荐或 lock。未调用 provider、未写业务数据库、未部署或重启服务。

### V3 进展续60 · Whole-System 批次完成与上下文重基线(2026-07-15)

- #292 已合入 main `4c70fd9a9051a3870fe27d9c0bb9b0af44b06f1a`，三项 CI 全绿；AH 35/100 只读证据评审工具已落地，当前本地 corrected settled evidence 为 0，状态 `ACCUMULATING`。
- #278 至 #292 的 correctness、identity、storage、readiness、ops 与 AH shadow/governance 工程阶段全部完成；最终代码测试为 `1316 passed, 4 skipped`，Ruff/Mypy/TypeScript/Web/acceptance 均通过。
- 历史 Draft #277 基于计划前旧状态并会重写当前 `PROJECT_STATE`，已关闭并由本次 docs-only 最终重基线替代；#203 继续保持历史 Draft，不在当前队列。
- 仓库状态进入 `READY_FOR_STAGING_DEPLOY_REVIEW`，并不表示已部署。staging 仍运行旧 SHA `493b4b6...`，production 未部署；后续部署必须单独批准并执行完整 release/readiness/business gate。
- 本批次累计 provider calls=0、业务 DB writes=0、staging/production deploy=false、scheduler/worker restart=false、历史 snapshot/outcome rewrite=0；RECOMMEND、lock、production、联赛 enable 与模型 artifact 均未改变。

### V3 进展续61 · Whole-System Correctness staging 部署与验证重基线(2026-07-15)

- `main@3d67a769704e544fb544979c96cf3162328d090c` 已部署到 staging；API、Web、worker、scheduler 的 OCI revision 全部对齐该 SHA，migration 保持 `0023_create_checkpoint_refresh_schedule (head)`。
- `/health`、`/ready`、数据库、Redis、worker、scheduler 与 Web/API release sync 通过；四个目标容器 restart count 均为 0。production 未部署。
- staging `/ops` service credential 与基于实际 Compose bridge 的 `127.0.0.1/32,172.18.0.0/16` allowlist 已生效；缺失/错误/正确凭据分别返回 `401/401/200`。凭据明文不进入仓库、日志、响应或本台账。
- 40 场审计共 80 个 FME Snapshot v2，integrity invalid=0；READY=2、INSUFFICIENT=78。corrected Strict AH 仍为 0/35、0/100，`RECOMMEND=0`、lock=0。
- 初次十请求冷缓存并发验收出现 7 次瞬时 nginx 504；后续规定并发复测和连续六次稳定窗口无新增 5xx/502。该项保持开放 WARN，必须先完成只读根因诊断，不得直接增加 timeout 或降低业务门。
- 部署验收主动 provider calls=0，scheduler 恢复后的 provider delta=0，关键业务表计数与部署前一致，历史 ledger 前缀未改写。rollback manifest 已保留，未执行 rollback。

### V3 进展续62 · Validation Correctness Recovery 部署前收口(2026-07-15)

- 只读冻结 staging ledger 到 `/opt/w2/shared/validation-baselines/denominator-20260715-20260715-071647Z`；manifest SHA-256=`a7b92f76197c30008b78a4cfaa7efc508b15087f34217003f79595f37c21e5f4`，10937 条记录、103 条 raw outcome、corruption=0，原 ledger 未修改。
- #295 修复 canonical outcome denominator：VALIDATION raw/canonical/audit-only=`43/16/27`，Wide Shadow=`60/22/38`；历史兼容 outcome 留在 audit/compatibility 层，不能成为 corrected evidence。
- #296 增加 Dashboard 同 key single-flight 与 ledger projection cache，消除冷缓存并发重复构建；未增加 nginx timeout，未修改业务门。
- #297 固定 FME blocker precedence，并把 feature/xG readiness 与 market readiness 解耦；无盘口仍以 `MARKET_UNAVAILABLE` 为第一 blocker，已有 xG 不再被写成 UNKNOWN，且不会生成 pick。
- #298 增加只读 Strict AH canary checker，复用 canonical capture/outcome、Strict policy、FME semantics 与 MarketQuote verifier；冻结基线返回 `NO_CORRECTED_STRICT_CANDIDATE_YET`、candidate=0、exit=0。
- 四 PR 合并后的 `main@51baa80fc4a8878b6a76e3782ff6586f1f39f269` 集成验收为 `1370 passed, 4 skipped`，Ruff/Mypy/TypeScript/Web/offline acceptance/tracked-output guard 全部 PASS。canonical duplicate/conflict/cross-track contamination 均为 0。
- staging 尚未重部署，仍为 `3d67a769704e544fb544979c96cf3162328d090c`；下一步是一次性 staging 部署及冻结/实时 denominator、冷并发、FME 和稳定窗口验收。production、RECOMMEND、lock、OFFICIAL、threshold、artifact、league enablement 均未改变。
- 安全：provider calls=0、业务 DB writes=0、历史 ledger/snapshot/outcome rewrite=0、staging deploy=false、production deploy=false、scheduler/worker restart=false。

### V3 进展续63 · Validation Correctness Recovery staging 验收(2026-07-15)

- staging 单次部署完成，目标 `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`；API、Web、worker、scheduler 同 SHA、healthy、restart=0、OOM=false，migration 保持 `0023_create_checkpoint_refresh_schedule (head)`，rollback manifest 已在服务切换前创建且未执行回滚。
- 冻结与实时 ledger 口径一致：VALIDATION raw/canonical/audit-only=`43/16/27`，Wide Shadow=`60/22/38`；canonical duplicate、conflict、identity-aware unmatched、cross-track contamination 均为 0。Dashboard canonical validation denominator 为总推荐 25、已结算 16、pending 9，10 HIT、4 MISS、2 PUSH、0 VOID，decisive hit rate 71.43%。
- 冷并发 1/2/4/8 共 15 请求全部 200、无 502/504，每 key owner=1、waiter=0/1/3/7；暖 225 请求全部 200。冷 p50/p95/max=`93.7203/109.6345/110.398s`，暖 p50/p95/max=`2.4401/18.4901/61.5158s`。原 504 已消除，但冷路径和大响应序列化仍为性能 WARN，不授权提高 timeout。
- future 40 场/80 Snapshot：READY=38、INSUFFICIENT=42；fallback 为 `FME_PROVENANCE_INCOMPLETE` 24、`R4_1_FEATURE_HISTORY_INSUFFICIENT` 18；integrity/semantic invalid=0。第一 blocker 为 `MARKET_UNAVAILABLE` 34、`QUOTE_CAPTURE_TIME_MISSING` 6；19 场 no-market 仍显示 xG READY，accidental promotion=0。
- Strict canary 在冻结与实时源均为 `NO_CORRECTED_STRICT_CANDIDATE_YET`、candidate=0、source PASS、contamination=0。Corrected Strict 仍从 0/35、0/100 累积，历史兼容战绩不得进入 corrected evidence。
- 运行安全：主动 provider calls=0、scheduler provider delta=0、业务 DB writes=0、历史 rewrite=0、queue=0、lock=0、OFFICIAL canonical=0、Web 5xx=0；ops 401/401/200。production、RECOMMEND、threshold、artifact、league enablement 均未改变。
- 最终结论：`STAGING_VALIDATION_RECOVERED_WITH_WARNINGS`。WARN 仅为冷路径高延迟；production 和 RECOMMEND 继续 BLOCKED。

### V3 进展续64 · Boss View 性能恢复验收与 staging 回滚(2026-07-15)

- #301、#302、#303 已依次合并，`main@4dbaf517f62af47fbfbc11acfb21092e8b1380f2` 完成 direct lightweight DayView、L2 按 fixture 懒加载和关键路径指标；合并后 `1383 passed, 4 skipped`，Ruff/Mypy/TypeScript/Web/offline acceptance 全部 PASS。
- 新 L1 经真实公网 nginx 路径测试 45/45 HTTP 200、0 timeout、0 502/504；VPS 到公网地址的 cold p50/p95/max=`1.7903/3.0731/10.1041s`，warm=`0.0072/0.0179/0.0183s`，每个 cold key owner=1、waiter=0/1/3/7。
- L2 历史 fixture `analysis-card` 验收返回 502；内核证据确认 uvicorn 在约 `1022048 KiB` anonymous RSS 时触发 memory-cgroup OOM kill，Docker 以 exit 137 自动重启 1 次。违反“L2 不影响首屏、0 5xx、0 restart/OOM”硬门，未通过发布验收。未提高 nginx/Web timeout。
- 已按 `/opt/w2/shared/rollback-manifest-4dbaf517f62af47fbfbc11acfb21092e8b1380f2.json` 回滚，并从已知良好 release 源精确重建；staging API/Web/worker/scheduler 全部恢复 `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`、healthy、restart=0。
- 回滚后 VALIDATION=`43/16/27`、Wide=`60/22/38`，duplicate/conflict/unmatched/contamination 均为 0，Strict=0、provider delta=0、queue=0。production、RECOMMEND、lock、OFFICIAL、threshold、artifact 和联赛 enablement 均未改变。
- 最终结论：`STAGING_ROLLED_BACK_PERFORMANCE_BLOCKED`。下一项只能是独立 L2 critical-path 修复 PR，以 bounded per-fixture projection 取代完整 Dashboard 重建，并证明内存低于 API cgroup 上限后再申请 staging 重部署。

### V3 进展续65 · Frozen L2 Audit OOM Recovery 部署前收口(2026-07-16)

- #305、#306、#307 已依次合并，代码目标 `main@5005df4e4873e618399bedaf4f32c9e5bbb2ef8f`。冻结 forward capture 现在通过逐行、有界、exact capture identity 查询生成 per-fixture 审计投影；不得装载全 ledger 或重建 FeatureSet、Simulation、FME、完整 Dashboard。
- 公共 `/v1/fixtures/{fixture_id}/audit-detail` 只读取冻结 capture，响应上限 512 KiB；公共 `/analysis-card` 只返回冻结兼容投影或小型 fail-closed 响应，完整分析重建仅保留给显式离线入口。
- Boss View 首次展开 L2 只请求一次 exact `audit-detail`，缓存键绑定 fixture/capture/estimate/API SHA；盘口时间线为二级独立懒加载。404/409/413/503 不影响 L1，迟到响应不能覆盖新 capture。
- 原 OOM fixture `1576804` 已形成脱敏回归 fixture；原事故为 API 在约 1 GiB cgroup 上限触发 OOM kill、exit 137 和重启。新契约要求响应不超过 512 KiB、单请求新增峰值不超过 192 MiB，并禁止 HTTP live rebuild。
- 合并后全量验收为 `1406 passed, 4 skipped`；Ruff、Mypy、TypeScript、Web build、offline acceptance、tracked-output guard 全部 PASS。冻结 denominator 继续为 VALIDATION `43/16/27`、Wide `60/22/38`，duplicate/conflict/unmatched/contamination=0，Strict=0。
- staging 仍运行 rollback release `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`。下一步仅允许一次 staging 批量重部署；任一 OOM、exit 137、restart/oom_kill 增量、5xx、超大响应、身份不一致或 denominator/三轨边界变化都必须自动回滚。production、RECOMMEND、lock、OFFICIAL、threshold、artifact 与联赛 enablement 均未改变。

### V3 进展续66 · Frozen L2 Audit Recovery staging 回滚(2026-07-16)

- docs gate #308 合并后尝试部署 `main@2658d37f8ec7e69de5b5737ff37fb8e9cd822c35`；四服务镜像、artifact v1、migration head、API readiness 和 DayView business gate 均通过，API/Web/worker/scheduler 曾短暂同 SHA、restart=0。
- L1 公网验收先于 L2 压力测试失败：`today` 15/15 HTTP 200，但暖请求约 1.70–1.84 秒；`next36` 15/15 HTTP 200、p95 约 4.99 秒、max 5.10 秒；`future` 声明响应约 4,039,702 bytes，12 秒仅传输约 0.99–1.14 MB并触发 client timeout。该结果违反 L1 timeout=0、cold max<12 秒、warm p95<=1.5 秒硬门。
- 因前置 L1 硬门失败，未继续执行原 OOM fixture 的 L2 串行/并发压力矩阵，不能宣称 staging L2 已恢复。新 release 在回滚前 API RSS 从约 223.6 MiB升至观察峰值 328.9 MiB，delta约105.3 MiB；cgroup oom/oom_kill=0、exit137=0、restart=0。
- 已用四服务冻结镜像回滚到 `c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`；API/Web/worker/scheduler 均 running、restart=0，`/ready` PASS，watchdog active。provider总数保持485（delta=0）、队列保持0；历史 ledger 2026-07-07至07-14逐文件 hash完全一致，07-15部署前字节前缀 hash一致，仅允许后续 append。
- 回滚后 canonical 口径仍为 VALIDATION `43/16/27`、Wide `60/22/38`，duplicate/conflict/identity-unmatched/contamination=0，Strict=0，RECOMMEND=0、lock=0、OFFICIAL=0。最终结果为 `STAGING_ROLLED_BACK_L2_BLOCKED`；下一修复必须先缩小/分页 `future` L1 payload并满足公网延迟门，不得通过提高 timeout、降低业务门或移除审计字段掩盖。

### V3 进展续67 · Bounded Future DayView Pagination 部署前门(2026-07-16)

- #310–#312 已依次合并到 `main@b72005b6364dfbf3adaea4de98c448157d9dcab0`：L1 capture 改为流式、显式 allowlist 的 latest prematch summary index；DayView 改为 snapshot-bound cursor 分页；Boss View 首屏只取20场并由用户显式加载更多。
- `future` 旧响应约4,039,702 bytes，属于多卡与原 capture 字段共同造成的 `MIXED` 膨胀。新契约限制单页512 KiB、单卡24 KiB、page size默认20且最大50；整窗 `counts` 与当前页 `page_counts` 分离，cursor stale返回409且禁止跨snapshot合并。
- DayView HTTP 路径不再调用全 ledger loader，不在分页前 prime 全部盘口或构造全部卡片；L1保留 `audit_capture_hash/audit_estimate_id`，L2继续使用exact frozen `audit-detail`，没有回退旧无界Dashboard，也没有提高12秒客户端或nginx timeout。
- 合并后全量验收：`1422 passed, 4 skipped`；Ruff、Mypy（245源文件）、TypeScript、Web build、offline acceptance、tracked-output guard全部PASS。三个代码PR的verify、staging-parity、predeploy-e2e均PASS。
- canonical基线必须保持 VALIDATION `43/16/27`、Wide `60/22/38`，duplicate/conflict/identity-aware unmatched/cross-track contamination=0，Strict=0、RECOMMEND=0、lock=0、OFFICIAL=0。staging仍运行回滚版本`c4bcceb5...`，下一步才是单次批准的批量部署与L1→L2硬门验收。

### V3 进展续68 · Bounded Future DayView Pagination staging 回滚(2026-07-16)

- docs gate #313 合并后的目标 `main@22d1357bba6fc4b761c8cafae98dd917ea0caf25` 曾按 migration→API→worker→Web→scheduler 顺序完整切换；四服务revision一致、restart=0，artifact v1、migration head和`/ready`均通过。
- L1内容正确性显著恢复：future 40场分2页，page union=40、duplicate=0；页面约41 KiB、最大单卡约1.8 KiB、stale cursor=409，所有请求HTTP 200且无502/504/browser timeout。future首屏冷请求5.95秒，满足4/8/12秒冷门。
- 延迟硬门仍未全过：暖请求约1.6–2.0秒，高于p95<=1.5秒；第二页3.87秒，高于next-page p95<=3秒。按L1前置门规则未执行原OOM fixture及Frozen L2压力矩阵，也未宣称staging L2恢复。
- 回滚前API RSS约254.4 MiB，cgroup oom/oom_kill=0、exit137=0、restart=0。已恢复四服务到`c4bcceb5cb777639251e0db91a9c1f54f5b9c87b`，`/ready`、API/Web release sync和watchdog均通过，restart=0。
- provider保持485（delta=0）、Celery queue保持0；部署前后ledger manifest hash均为`cacf1af56e3b5983b13214f7cae446f6f55e7e48fda4f2f0c6e9bebc0ca0a4f4`。因此canonical denominator与三轨证据未改变，RECOMMEND/lock/OFFICIAL/production仍关闭。

### V3 进展续69 · Public Edge Observer 证据完整性阻断(2026-07-16)

- #314–#325 已合入 GitHub `main@b303588d6a3a2e7288c46877206f7f5ef31eeb87`；#324 固化双独立公网 observer 合同，#325 修复 fresh connection 只保留部分样本的问题。三项 CI 在 #325 合并前均为 SUCCESS。
- 开始检查确认 staging API、Web、worker、scheduler 稳定运行 `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`，四服务 healthy、restart=0，`/health`、`/ready` 与 remote IPv4 `43.155.208.138` 通过；production 未部署。
- GitHub-hosted Observer A run `29492624556` 在 DIRECT/no-proxy/IPv4 完整延迟矩阵中初步通过所有性能与可靠性阈值。当前外部主机 Observer B 的冷连接、并发与可靠性初步通过，但 future page 1 warm reused p95=`2.086251s`，高于 `1.5s`。
- 两组 artifacts 均不具备正式资格：所有 `request_id` 为空，且每个样本缺少 `timestamp`。根因是 observer 丢弃了含 nginx request ID 的 DayView JSON body，却读取 staging nginx 未回传的 `x-request-id` header。GitHub workflow success 仅表示命令完成，不构成正式 observer PASS。
- 当前正式分类为 `OBSERVER_COVERAGE_INSUFFICIENT`，尚未进入 staging 部署、L1 或 Frozen L2。本轮没有 provider call、业务 DB write、历史 rewrite、服务切换或回滚；稳定 staging 保持 `c89555b...`。
- 下一步仅修复 observer 证据采集：保留同一 curl 进程的 keep-alive 语义，为每个响应使用独立临时 body，只提取 `request_id`，并记录 UTC timestamp 与 Server-Timing；不得修改 Dashboard、FME、分页、denominator、阈值或 12 秒 timeout。旧 artifacts 不得追认为正式 PASS。
- VALIDATION `43/16/27`、Wide Shadow `60/22/38`、Strict `0/35` 与 `0/100` 的冻结边界未被本轮改动；RECOMMEND=0、lock=0、OFFICIAL canonical=0、production=false。

### V3 进展续70 · Public Edge Observer Evidence V2 部署前门(2026-07-16)

- context PR #326 已合并为 `main@c33a5ff35f94de767cc0e4d308a41fb76157fc6c`；active workstream、完整已知问题、GitHub context read order、冻结规格和 terminal condition 已进入 main。
- Observer V2 报告/样本/collector 固定为 `w2.public_edge_latency.v2`、`w2.public_edge_latency.sample.v2`、`w2.public_edge_observer.v2`；V1 或缺字段 evidence 不得形成正式 PASS。
- collector 在权限受限临时目录中逐 transfer 保存独立 body/header metadata，只提取合法唯一 request ID 与 allowlisted Server-Timing map；body、raw header、query 与环境内容不进入报告或 artifact，成功/失败均清理。
- DIRECT 的 no-proxy 从实际 curl command 与清理后的环境推导；IPv4/IPv6 由 curl flag 与 `ipaddress` 双重验证。FRESH 一进程一 transfer；REUSED 仅按 `num_connects==0` 标记，服务端 reconnect 不按请求位置伪装 reuse。
- curl transport failure、HTTP 502/504 保留 status、exit code、可用 timing 与 bytes，标记为 failure evidence 并使 observer 失败；metadata/配对/能力/临时路径错误才属于 collector hard error。
- unit 与本地真实 HTTP/1.1 curl integration 共 31 项 PASS，覆盖 keep-alive、fresh、reconnect、malformed/empty/oversized、502 HTML、timeout 与临时目录清理；真实 staging smoke 同时保留一个12秒 transport failure与一个 correlated HTTP 200，证明失败事实不会消失。
- 本实现未修改 Dashboard、nginx timeout、FME、denominator、pagination、Frozen L2、threshold、recommendation、lock 或 OFFICIAL；未部署 staging/production，provider calls=0、业务 DB writes=0、历史 rewrite=0。

### V3 进展续71 · Known-Issue Closure 最终 staging 验收与 Frozen L2 identity 回滚(2026-07-16)

- #326 已合并上下文与冻结规格，#327 已合并 Observer Evidence V2，代码目标为 `main@461e4973b957981132cfcfd9fc370e0021f8bae2`；local `1470 passed, 4 skipped`，GitHub verify/staging-parity/predeploy-e2e 全 PASS。
- Observer A run `29500925481`（source `20.55.87.183`）与 Observer C run `29501365248`（source `20.94.54.82`）各 24 份 V2 report 全 PASS；current external source `120.231.34.97` 仅暖 reused 延迟失败。server diagnostics 通过，正式裁决为 `ROUTE_SPECIFIC_WARNING`，staging 可继续而 production 仍 blocked。
- `461e497...` 的五类镜像 revision 校验、artifact v1、migration head、API business gate及 API→worker→Web→scheduler 切换均 PASS。L1 today/next36/future union 为 `3/3`、`13/13`、`40/40`，future 两页 `20+20`，duplicate=0，最大页/卡 `43249/1697` bytes，stale cursor=409，并发 1/2/4/8 全 200；direct API/isolated nginx 暖 p95=`0.048960/0.041900s`。
- Frozen L2 legacy fixture `1576804` 正确返回 historical compatibility。fixture `1492140` 的当前 L1 exact identity 为 capture `720d570b505e6e06571f2101d23641743251c271fa9262008ebacddfb7ec2b12`、estimate `null`，L2 返回 `409 AMBIGUOUS_CAPTURE`；另一个 v2 capture 虽为 integrity/semantics PASS，不能替代 L1-bound identity。完整串行/并发 L2 stress 因前置硬门失败未执行。
- 已按 mode-600 四服务 rollback manifest 恢复 `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`；四服务 healthy、restart=0、OOM/oom_kill=0、health/ready PASS。provider `508→508`、active calls `0→0`、queue `0→0`、ledger manifest 与 bytes 完全一致，业务 DB/historical rewrite=0。
- 最终正确性仍为 VALIDATION `43/16/27`、Wide `60/22/38`、duplicate/conflict/identity-unmatched/cross-track contamination=0；Strict candidate/confirmation/canonical=`0/0/0`，RECOMMEND=0、lock=0、OFFICIAL canonical=0、production=false。最终状态 `BLOCKED_STAGING_ACCEPTANCE`，下一步仅允许修复 L1 exact Snapshot-v2 capture/estimate identity 后重跑 staging L2。

### V3 进展续72 · L2-02 Exact Identity 只读诊断硬阻断(2026-07-17)

- GitHub `main@47be9b09b3a6dc830de4765d7f20306f6f6f38c6` 与 run `29505350840` 三项 CI 全 PASS；staging API、Web、worker、scheduler 继续稳定运行 `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`，`/health`、`/ready` PASS。
- 对 fixture `1492140` 的 staging ledger 只读脱敏扫描确认，content hash `720d570...` 恰有两个 occurrence：captured_at/football_day 不同，checkpoint 均为 `EVIDENCE_CHANGE`；除 occurrence 字段外 ledger 内容等价，但两条都没有顶层、pick、analysis-gate estimate，`fair_market_estimate_ids=[]`，Snapshot v2 数量均为 0。
- 最新 L1 occurrence 因此不存在唯一权威 estimate。ledger 中另有 3 条 integrity/semantics/evidence-eligible 均通过的 v2 capture，但它们与当前 L1 的 analysis gate、quote、card hash、evidence hash 不完全等价，禁止替换或借用。
- HTTP 409 的直接根因分类为 `SAME_HASH_MULTI_OCCURRENCE`，不是 estimate extraction loss，也不是同 hash 的业务内容冲突。新增 occurrence ID 可以消除 hash 多义性，但不能凭空生成当前 record 不具备的 eligible estimate，因而无法满足 `audit_available=true` 与 corrected-evidence 硬门。
- 本批次按 `HARD_BLOCKER_CURRENT_SCOPE` 停止：未修改代码、FME、Snapshot schema、阈值、分页、denominator 或三轨；未创建回归 fixture、未部署、未调用 provider、未写业务 DB、未改历史 ledger。staging 无需回滚且保持 `c89555b...`。
- 最终状态提升为 `BLOCKED_EXACT_IDENTITY`。下一动作不再是本范围内的 lookup/UI 修复；必须另行授权修复“当前 capture 本身缺少 Snapshot v2 evidence”的上游生成问题，产生新的同-record 权威证据后，再重新读取 GitHub 上下文并重做 exact-identity 诊断。

### V3 进展续73 · L2-02 Exact Identity 实现完成、staging 待验收(2026-07-17)

- 以 GitHub `main@68cc49f50262d506fae99cf90b1edea7adaa1f23` 为唯一上下文启动；staging 继续运行 `c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`。L2-02 在 staging 验收前保持 blocking，production、RECOMMEND、lock、OFFICIAL 继续禁止。
- 根因已定位为前向账本 CLI 将含完整 Snapshot v2 的权威 Dashboard 再经过公开 L1 有损投影，导致账本捕获丢失 Snapshot 与 estimate identity。新增内部 evidence adapter 保留同请求、同记录的不可变证据，公开 L1 仍保持 bounded，不暴露完整快照。
- 新增确定性 `audit_capture_id=aci_<sha256>` 区分 occurrence identity 与原有 content `capture_hash`；DayView index 只从同一 capture 内的 integrity/semantics/evidence-eligible Snapshot v2 提取 estimate。Boss View 与 Frozen L2 绑定并交叉校验 capture ID、hash、estimate 三元组，旧 hash-only 客户端继续兼容但遇多义即 409。
- 提交 fixture 1492140 最小脱敏双 occurrence 回归，证明 controlled append-only v2 recapture 可被精确寻址；fixture 1576804 的 historical compatibility 与 no-live-rebuild 边界保持不变。未硬编码生产 fixture 逻辑，未修改 FME 数学、Snapshot schema、estimate/model ID、quote、score matrix、settlement、pagination、denominator 或三轨。
- 本地全量 `1481 passed, 4 skipped`；Ruff、Mypy（247 source files）、TypeScript、Web build、offline acceptance、tracked-output guard 与 diff check 全 PASS。provider calls=0、业务 DB writes=0、历史 rewrite=0、staging/production deployment=false。
- 唯一代码 PR 为 #330，当前状态为 `IMPLEMENTATION_COMPLETE_STAGING_PENDING`。下一步仅允许该 PR 通过 verify/staging-parity/predeploy-e2e 后合并，部署最新 main，并在真实 kickoff 前执行一次不回填时间的 append-only controlled capture，再完成 L1/L2 与 denominator/三轨安全验收。
