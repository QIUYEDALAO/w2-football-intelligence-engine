# W2 系统升级 · 任务与验收台账

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
