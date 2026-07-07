# W2 架构复盘(独立评审)· 2026-07-07

性质:独立第三方评审(与执行会话分离);基于真实代码与本地缓存数据;只读,零 provider calls,不改线上路径,不动台账(台账由执行会话维护)。
被评对象:main HEAD `76d8d21`(S16 之后)。
配套产物:`scripts/run_w2_market_baseline_eval.py`、`docs/consolidation/W2_MARKET_BASELINE_EVAL_2026_07.md`、`docs/consolidation/W2_MARKET_ANCHOR_PROPOSAL_2026_07.md`。

---

## 0. 核心判断(一句话)

**被验证的东西没上线,上线的东西没被验证**——六周验证功夫花在一个不出货的模型上(#193 拟合模型只存在于回测报告生成器里),而实际出货的 ANALYSIS_PICK 由一套从未回测过的盘口启发式驱动;同时,评估体系缺市场基准,导致台账多个战略结论(0.99 够用、在赛弱、锚八月)建立在没有参照系、甚至跨模型错比的数字上。

## 1. 已核实的结构性问题(带出处)

### 1.1 模型与服务
- 线上路径 = `src/w2/strategy/calibration.py` 手设权重(`BASELINE_PRIOR`:elo 0.28、身价 0.18、主场 0.12、`dixon_coles_rho=0.0`),从未拟合。
- #193 拟合模型(`_fit_offline_lambda_model`,5 特征 log-linear Poisson + temperature)**全仓库唯一引用点是 `src/w2/backtest/free_tier_2024.py`**;无持久化、无推理封装、无 champion 接线。"接为 champion"是一整块缺失的模型服务层,不是配置开关。
- `src/w2/models/independent.py::predict_from_features` 的 8 个 ModelFamily 是常数微调的装饰品(BIVARIATE_POISSON=base+0.05 等),不是真实实现;`models/dixon_coles.py` 的 attack/defence 是矩估计而非对手调整 MLE,且 `tau_correction`(平局修正)在拟合路径与线上路径均未使用。
- 特征浅:`RollingXgState` 是累计均值(无窗口、无衰减、无对手强度调整);独立 Poisson 无 rho → 平局定价系统性偏差,temperature 全局旋钮救不了分类别偏差。

### 1.2 评估方法(本次复核实测,详见 EVAL 文档)
- **台账"在赛联赛 ~1.05 弱"跑错了模型**:S10/S11 复验走 `build_walk_forward_predictions` → 手设常数先验 + 纯进球特征(缓存的 xG statistics 根本没进模型)。#193 拟合协议此前从未在在赛联赛运行。本次补跑(同协议、同缓存、跨季 2024→2025):**pooled 1.0278**(手设先验 1.0416,台账口径 ~1.055)。"弱"的相当一部分是"没拟合"。
- **联赛粒度异质性推翻二分法**:拟合后 挪超 0.929、中超 0.985 **优于** PL 0.998 与 Bundesliga 1.034(绝对 log loss);Bundesliga 拟合后反而比手设先验差(1.034 vs 1.025)。"五大=0.99=好,在赛=1.05=弱"在联赛粒度不成立;pooled 平均掩盖了一切。
- **市场基准从未计算**:当前代 harness 的 baseline 只有 uniform/elo/prior(`free_tier_2024.py` `forbidden_inputs`);devig 组件(`markets/devig.py`)与 s2 gate 的市场对照是旧线,未接入 #191–#194 评估。跨联赛比较绝对 log loss 无效(熵不同),没有市场基准,"够不够/弱不弱"都无法判定。
- 验证目标与出货目标错位:出 AH/OU/半场/比分推荐,验证的是 1X2 log loss;AH 结算代码在(`settle_asian_handicap`)但从未验证 AH 赢盘概率。

### 1.3 决策链与产品
- `strategy/analysis_recommendation.py`:AH/OU 只要 intent 非 INSUFFICIENT/LEAKAGE/CONFLICTED 即出 PICK;半场市场有数据必出(P>0.5 即表态);比分市场有矩阵必出。**ANALYSIS_PICK 衡量"有没有数据",不是"有没有信号"**(S14 世界杯 4/4 全 PICK 非巧合)。
- 方向来自 `strategy/bookmaker_intent.py` 的线动启发式(开盘→现价、晚段反转、sharp-soft 价差,阈值全部手设),**从未对赛果回测**;且 scheduler 未跑 → 没有连续盘口时间线在积累,这套启发式将来想回测都没有数据。
- confidence 公式(intent×0.75 + 数据齐全度加分)奖励覆盖率而非信号强度。
- `formal_recommendation.py` 的 +EV 腿(阈值 3.5%+1SE):用一个(在五大)比市场差 ~0.02–0.04 log loss 的模型对市场算 EV,筛出的"价值"将以模型误差为主(赢家诅咒);15% 上限与 ≥3 独立信号缓解但不治本。EV 腿的前置条件应是该联赛模型-市场 gap 达标。
- 前向战绩为零:`outcome_tracked` 管道在,无任何积累。分析级产品唯一护城河是可查证战绩,该资产只能用日历时间换。

### 1.4 架构
- 治理面(40 模块、append-only 审计、replay、as-of 防泄漏)扎实,是真资产;但决策逻辑碎在 ≥4 个子系统(scorecard 因子、bookmaker_intent、value_engine、formal_recommendation),阈值互不一致(0.035 vs 0.025/0.05);建模真相压在一个 2087 行单文件(`free_tier_2024.py`)。头重脚轻:世界级合规包着中等偏下的信号引擎。

## 2. 高杠杆 vs 花架子

高杠杆(天级投入):市场基准接入评估(已完成 pipeline,待 CSV);拟合模型加 DC rho + 联赛主场系数 + 时间衰减(组件在仓库里);拟合模型接 champion(持久化+推理封装);ANALYSIS_PICK 加选择性(模型-市场分歧度门槛 + NO_EDGE 档);**立即开始前向 ledger + odds 时间线积累**(详见提案文档)。

花架子(现在别做):更多模型族/集成;player-level/深度学习;把世界杯当验证(64 场验证不了模型,当 demo);MLS/阿甲二级 odds 源;继续加治理仪式;在 PICK 无选择性时先做 S17 重设计(重新排版无差别 PICK 是在错的层抛光——S17 的信息架构依赖档位先有含义)。

## 3. 没想到的路子

市场锚定建模(展示层概率 = 市场先验 × 模型残差微调;详见提案文档);产品从"出单"转"分歧雷达 + 解释 + 可查战绩";验证什么就卖什么(要么验证 AH 赢盘概率,要么首推 1X2);odds 时间线作为战略数据资产(解锁 CLV 评分,百级样本可判拣选质量)。

## 4. 只做一件事

市场基准 eval——**本评审当日已完成**($0、零 provider calls、11 联赛、join≈100%、全 Pinnacle 收盘)。裁决:五大 gap 0.013–0.047(德甲 0.047 最差,"0.99 够用"不成立);在赛联赛拟合后 gap 0.016–0.055(挪超 0.016 全系统第二,"在赛=弱"不成立);blend 实验无一联赛稳定跑赢纯市场(当前模型对收盘零增量信息 → EV 腿禁开;阿甲名义反例经尽调为子集偏置,见 EVAL F6);"锚八月"两个前提条件均被数据打破。完整结果与预注册判定规则见 `W2_MARKET_BASELINE_EVAL_2026_07.md`。

## 5. 公道话

诚实纪律(不造假绿灯、自查降级、as-of 防泄漏、只读审计)是同类项目少见的真资产。问题不是纪律,是火力配置:把下一阶段的认真,从"包装决策的仪式"挪到"产生决策的信号"上。
