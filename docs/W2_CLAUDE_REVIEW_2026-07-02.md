# W2 技术审计报告的审查意见

审查人：Claude ／ 日期：2026-07-02 ／ 基线：`feat/w2-audit-table-export` @ `9cb2948`（#123 PR 分支；#114–#122 已在其提交历史中，#123 的 main 合并仍未发生，与送审报告一致）

## 0. 审查结论

送审报告对工程链路的描述基本属实，方向判断正确（先审计闭环、再补独立数据、再校准模型）。但报告对代码现状**滞后约一周**，系统性低估了已完成度：A4 身价数据已落地、S1 模拟引擎已实现并接入主链路、A2/A3/A6 采集管线与配额防线已建成。因此升级重点应从"建设"改为"执行回填 + 校准验证"，并优先修复本次审查新发现的两个建模问题（中性场主场优势、proxy-Elo 重复计入 xG）。

## 1. 核验方法

按送审报告第 11 章清单逐文件读码核对；对 `simulate.py`、`team_score.py` 做了运行时行为抽查（本审查环境无法安装 pytest/sqlalchemy，未能跑完整测试套件与导出脚本，相关项以读码结论为准，runtime 验收仍留给 staging）。未读取 `.env`。

## 2. 报告声明 vs 代码实况

### 2.1 与代码不符（报告过时）的声明

| # | 报告声明 | 代码实况 | 证据 |
|---|---------|---------|------|
| 1 | "A4 身价 JSON items 为空，F8 仍 MAPPING_MISSING" | **已完成**：48 支队伍人工策展数据，含 observed_at / source_url / primary_source / confidence / reviewed_by；F8 数据齐时 READY 且计入 ISC | `config/team_values/world_cup_2026.v1.json`；`team_factors.py:307-362` |
| 2 | "S1 完整实力 λ → 二元泊松/蒙特卡洛未落地" | **已基本实现**：xG+Elo+身价+阵容 → `calibrate_lambdas` → 蒙特卡洛泊松 → fair_ah / fair_ou / top3 比分 / AH 结算分布**同源**输出，确定性种子，市场赔率不进 λ。已接入 dashboard 主链路 | `strategy/simulate.py:61-153`；`strategy/calibration.py`；`api/repository.py:1423-1450` |
| 3 | "ISC 是未来验收口径" | **已是运行时硬门槛**：`FORMAL_MIN_INDEPENDENT_SIGNALS=3`，不足直接 blocker `INSUFFICIENT_INDEPENDENT_SIGNALS`；报告层同样 `INDEPENDENT_SIGNAL_MINIMUM=3` 短路为 DATA_INSUFFICIENT。计数口径正确：5 个权威信号组，全部 xG 派生合并算 1，赛事重要性不计入 | `strategy/formal_recommendation.py:16,222-224`；`reporting/match_decision.py:23,80-86`；`pricing/team_score.py:16-20,39-45` |
| 4 | "A2/A3/A5/A6 未完成" | **管线已建、数据未回填**：`independent_signal_backfill.py` 支持 history/h2h/squad_value/ratings 四类任务并接 quota 决策；`quota_budget.py` 已实现 core_only / backfill_stop 分档。真实历史优先、xG 代理兜底且诚实标注 `PROXY_ONLY`。缺口是**从未实际执行回填**（`runtime/independent_signal_backfill/` 不存在），A5 真 Elo 源未接 | `ingestion/independent_signal_backfill.py`；`ingestion/quota_budget.py`；`api/repository.py:1322-1348,2133-2182` |
| 5 | "B2 比分/OU 独立 xG 正解未完成" | `independent_xg_poisson` 已存在并在 xG READY 时用于比分参照；另有 `models/dixon_coles.py`（含拟合函数）**已写好但未接入**任何在线路径 | `markets/poisson.py:42-52`；`api/repository.py:1462+`；`models/__init__.py` |

### 2.2 核验属实的声明

FORMAL 五状态短路顺序（LOCKED → DATA_INSUFFICIENT → MARKET_NOT_READY → WATCH → FORMAL）、FORMAL payload 双层防线（`_valid_formal_recommendation_payload` + `_has_valid_formal_recommendation`）、`formal_eligible` 不再 phantom true（`repository.py:4100-4107`）、market_ah 主队视角与 away_line=-market_ah（`repository.py:3262-3306`）、禁词 guard 与 as-of 强制（`report_generator.py:14-24,247-256,363-366`）、runner 健康门禁 fail-fast 且 provider_calls=0（`report_runner.py:88-126,175-180`）、冻结快照强制 release_sha / data_profile / 赛前性（as_of 与 locked_at 必须早于开球）与规范化 SHA-256（`recommendation_lock_snapshot.py:16-63`）、RecommendationLock / Settlement / AuditEvent 皆挂 before_update/before_delete 拒绝钩子（`models.py:470-479`）、settlement 带 lock_id 且缺失时标 `MISSING_LOCK_SNAPSHOT`（`audit_export/tables.py:524-525`）、四表导出空表也写 header、非 FORMAL 行推荐字段置空（`tables.py:216-218,472-479`）、命中率仅作赛后观察且 30 样本以下只显示"观察中 n/N"、`not_a_formal_gate=true`（`tracking/formal_results.py:21,620-631`；`api/schemas.py:197-198`）、盘口时间线恒带 verified=false / direction_allowed=false 并独立成表按 fixture_id join。

### 2.3 行为抽查结果

用真实代码路径跑 `run_simulation`（20000 次）：

- 强弱悬殊（法国型 vs 海地型，xG+Elo+身价全喂）：fair_ah = **-2.25**，top 比分 2-0/3-0/4-0，主胜 92.2%。报告担心的"碾压被压成小盘、恒平手、翻受让"在当前路径**未复现**。
- 均势对阵：fair_ah = 0.0，top 比分 1-1/1-0/0-1。不同对阵产生不同比分分布。
- 同一 fixture 重跑结果完全一致（确定性种子成立）。
- 仅有 xG 时同一悬殊对阵 fair_ah = -1.25：说明 Elo 与身价信号将盘口差距从 1.25 拉到 2.25，A5/A4 对准确性的贡献是实测可见的。
- ISC 抽查：xG 派生代理因子不增加信号组、重要性不计入，`missing_independent_sources` 如实列出缺失组。

## 3. 新发现的问题（送审报告未提及）

**P0-1 中性场主场优势偏置。** `calibrate_lambdas` 无条件给名义主队加 `home_advantage_goals=0.12`（`calibration.py:12,67-73`）。世界杯 2026 绝大多数比赛是中性场（`config/competitions/world_cup_2026.v1.json:14` 已定义 `neutral_site_policy`，但校准层未使用），这会系统性把每场 fair_ah 推向名义主队约 0.06 球，在 0/±0.25 盘附近足以翻转推荐方向。修复成本低：按主办国/中性场 gate 该参数。

**P0-2 proxy-Elo 使 xG 双重计入 λ。** ratings 缺真实来源时回退为 xG 代理 Elo（`repository.py:2452-2477`，1500+xG差×100），该 Elo 又作为独立项进 `elo_gap_weight=0.28` 的 λ 修正——xG 信号被计了两次，悬殊对阵的 λ 差会被放大。因子层已诚实标注 PROXY_ONLY，但**模拟层没有区分**（`input_readiness["ratings_ready"]` 对代理也为 True）。建议：ratings 为 PROXY_ONLY 时对 λ 传 `elo=None`，直到 A5 真实 Elo 接入。

**P1-1 独立泊松，非二元泊松。** 现实现为两个独立泊松（无进球相关性、无低分修正）。平局与半球盘 push 概率存在已知系统偏差（低比分格被低估）。`models/dixon_coles.py` 已写好含拟合函数，属"已造好未装上"。建议在 S2 阶段接入 Dixon-Coles ρ 修正并与独立泊松做 walk-forward 对比，不必推倒重来。

**P1-2 双阈值契约未声明。** 策略层门槛是 EV ≥ 3.5%（`formal_recommendation.py:14`），报告层门槛是 |edge_ah| ≥ 0.25 球（`match_decision.py:24`）。两者量纲不同、各自独立判定，可能出现"payload 为 FORMAL、报告降级 WATCH（EDGE_BELOW_FORMAL_THRESHOLD）"。作为纵深防御可接受，但主从关系应写进 contract 文档，审计表里两个口径都要可见（现已导出 edge_ah 与 expected_value，满足）。

**P2-1 λ 裁剪边界。** 极端悬殊时 λ_away 触底 0.15、总进球上限 4.40 会绑定（抽查中 λ_away=0.1526 即触底）。属 S2 校准参数化范围，先记录再拟合。

**P2-2 身价数据来源为二级转载。** source_url 是 planetfootball 转载页，primary_source 才是 Transfermarkt；48 队 confidence 统一 0.9。建议：抽样 5-8 队与 Transfermarkt 原页核对一次并记录核对日期；转载来源的 confidence 与一手来源分级。

**P2-3 测试与运行时验收缺口。** 本环境无法执行 pytest 与导出脚本（无 PyPI），单测文件齐备（audit_export / ISC / formal rules / lock snapshot / dixon_coles 等均有对应测试）。#123 的 PR-head staging runtime 验收仍是打开项，与送审报告一致。

## 4. 对第 14 章七个决策问题的答复

1. **报告 + 四张审计表替代 live Dashboard 作为主交付？** 同意。决策集中在 decide_match、输出确定性、审计表可回测，均已验证成立。Dashboard 退役为只读调试视图即可。
2. **是否批准 A4 人工策展？** 追认批准——它已经完成且质量合格（带来源、日期、复核人）。补充要求见 P2-2。
3. **Transfermarkt 队级 vs Kaggle player-level 求和？** 队级总身价为主（现状即是）。Kaggle 仅作年度交叉验证，不进主链路，避免两套口径打架。
4. **是否接 API-Football 历史/H2H 端点并设 quota budget？** 批准，且这是当前**最高优先级执行项**：管线与配额防线已建好，只差实际运行。按 quota_budget 现有分档执行，先小窗口（next36、max_fixtures=20）试跑并留 raw payloads 落盘。
5. **正式推荐坚持"真实数据 + 策略自洽"，不引入命中率开闸？** 同意并坚持。代码已内建该立场（not_a_formal_gate、posthoc_only、30 样本观察中），不要动摇。
6. **先 #123 再 A 系列？** 同意顺序，但 A 系列的定义要改：不是"建设 A2/A3/A5/A6"，而是"执行 A2/A3 回填、接入 A5 真实 Elo 源、验证 ISC 实际抬升到 ≥3 的场次覆盖率"。
7. **production 准入条件？** 建议清单：① #123 staging 四表验收通过且每日生成；② 当日场次中 ISC≥3 的比例达到约定阈值（建议 ≥70%）；③ P0-1/P0-2 修复合入；④ 锁定→结算闭环在 staging 至少跑通一个完整足球日；⑤ CI 全绿含禁词/泄漏测试；⑥ quota 防线在真实配额下演练一次；⑦ 回滚方案与 release_sha 追溯演练。

## 5. 升级路线修订（相对送审报告 §12-13）

阶段一（#123 收尾）不变。阶段二重排如下：

- **#124（新）P0 建模修复**：中性场 home_advantage gate + proxy-Elo 不进 λ。改动小、直接影响每场 fair_ah，应插队最先做。
- **#125 A2/A3 执行回填**（管线已有，跑起来、落盘、验证 F3/F5/F6 转 READY）。
- **#126 A5 真实 Elo/ratings 源接入**（替换 rolling_xg_proxy；国际队可用公开 Elo 数据集人工策展，方式同 A4，避开爬虫红线）。
- **#127 A4 复核与更新节奏**（抽样核对 + confidence 分级 + 窗口期更新计划）。
- 阶段三聚焦 **S2**：λ 参数 walk-forward 拟合、Dixon-Coles 接入对比、B4 让球标定；calibration_status 从 BASELINE_PRIOR 升级为带样本量与验证窗口的版本号。
- 阶段四 settlement_history 自动结算（只读锁定快照）不变。

不建议做的事项与送审报告一致：UI 重构、推送、文案包装、命中率包装、拍脑袋调阈值。

## 6. 红线检查

本次审查未读取 `.env`；确认市场赔率未进入 λ（`calibrate_lambdas` 入参仅 xG/Elo/身价/阵容）；盘口时间线输出恒带"参照·未验证"且 direction_allowed=false；锁定快照强制赛前性，赛后无法补造；Settlement/Lock/AuditEvent 不可变钩子在位。未发现红线违规。

## 7. 一句话总结

送审报告的路线是对的，但现状比报告写的更好：地基和引擎都在了。别再建设，去点火——跑回填、接真 Elo、修中性场偏置，然后用锁定快照攒 walk-forward 样本做 S2 校准。
