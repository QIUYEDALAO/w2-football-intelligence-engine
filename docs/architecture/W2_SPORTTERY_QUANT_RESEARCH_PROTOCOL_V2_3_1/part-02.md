---

## 5. ★ 数据源分工（D1/D2/D3 重写）

### 5.1 双源架构（冻结）

| 数据 | 来源 | 调用形态 | 成本 |
|---|---|---|---|
| **竞彩 SP / 让球 / 销售状态** | **FiroApi `sports-lottery/all-list`** | **批量，全天一次** | 3–4 次/日 ≈ **¥24/月** |
| **Pinnacle 赔率** | **API-Football `/odds?date=&bookmaker=4`** | **批量，10/页 × ~56 页** | 56 次/日，配额 7,500/日 → **边际零成本** |
| xG / statistics / lineups / h2h | API-Football | 按需 | 同配额内 |
| 官方赛果 | FiroApi `text/match-results`（≤30 天窗口）或 API-Football | 批量 | 可忽略 |
| 历史比分（模型训练） | 项目方 Excel（12 年 / 119 联赛）+ football-data.co.uk | 本地 | ¥0 |

**依据**：F26 实测两源 Pinnacle 赔率完全一致；F27 机构编号 11/11 一致；F28 批量可行。

**★ 已知限制（F29）**：API-Football 历史赔率同样为 0。**跨赛季离线验证在两源上都做不了，只剩 football-data.co.uk（有历史收盘价）或纯前向。**

### 5.2 ★ 竞彩 ↔ API-Football 映射表自举（新增）

**问题**：两源 ID 体系不通（F30）。FiroApi 的 `idEvent` 是 TheSportsDB 体系，与 API-Football fixture id 无桥。

**解法：用赔率当指纹自举**（可行性依据 F26 —— 两源同一场的 Pinnacle 价逐位相同）

```text
【自举期 · 与 Track 1 同期，14–30 天】
  每日：
    FiroApi all-list                       → 竞彩场次 + SP           （批量）
    FiroApi tf/odds（每场 1 次）            → 该场 Pinnacle 价 = 指纹  （仅自举期）
    API-Football /odds?date=&bookmaker=4   → 当日全部 Pinnacle 价     （批量）
  配对：
    在同一日期内，找 Pinnacle 三项价完全相同的 API-Football fixture
    命中 → 写入永久映射：竞彩 teamId ↔ API-Football teamId
                        竞彩 leagueId ↔ API-Football league_id

【稳态】
  映射表建成后，FiroApi 只保留 all-list（竞彩 SP）
  Pinnacle 全部改走 API-Football
```

**自举期成本**：约 450 次 FiroApi ≈ **¥90 一次性**。

**必报指标：**
```text
FINGERPRINT_MATCH_RATE           指纹唯一命中率
AMBIGUOUS_MATCH_RATE             同日多场价格相同（需人工裁定）
UNMATCHED_RATE                   无法配对
MAPPING_CONFIDENCE               每条映射的建立依据与置信度
```

**★ 硬规则：映射置信度未达标的场次不得进入任何判据。** join 接错是静默灾难——会拿 A 场竞彩价比 B 场 Pinnacle 价，算出假的正 EV 且不可见。

**★ 切换条件（冻结）**：连续 ≥14 天 `FINGERPRINT_MATCH_RATE ≥ 98%` 且 `AMBIGUOUS_MATCH_RATE ≤ 1%`，方可停止 FiroApi 的 tf/odds。

### 5.3 去水方法
```text
主方法 = Shin   敏感性 = power / logarithmic、proportional
理由：比例去水在冷门上系统性高估概率（示例：热门 −2.4% 相对、冷门 +5.0% 相对，
      +5.0% 相当于 12.83% 门槛的 39%，方向恒定不会平均掉）
★ Phase B 结论必须在三法下重跑；符号依赖去水选择 → 判 NOT_PROVEN
★ ROI 类指标一律用原始赔率与实际赛果
```

---

## 6. 时间合同、数据隔离、指标（同 v2.3，摘要）

### 6.1 ENTRY_SNAPSHOT_POLICY
```text
capture_schedule_id ｜ capture_times（UTC，Freeze A 写死）
max_capture_delay_seconds ｜ signal_generated_at
entry_snapshot_id ｜ entry_locked_at ｜ sale_stop_at
close_snapshot_id ｜ close_snapshot_max_age
策略版本绑定 entry_policy_id，整周期不得更改，禁止自行挑选入场时刻
poolStatus != Selling 的 capture 标记 NOT_TRADEABLE，不得作 entry
必记：decision_to_snapshot_lag_seconds ｜ sale_status_at_decision
必报：decision-SP ROI 与 close-SP ROI 之差（量化时间戳假象）
```

### 6.2 数据访问强隔离（可测试的架构属性）
```text
AS_OF_SIGNAL_VIEW      只含 signal_generated_at 时刻已知字段，策略代码只能访问此视图
POST_EVENT_ENRICHMENT  SP_final ｜ Pinnacle close ｜ 赛果 ｜ 代理指标
                       只能在 entry_locked_at 之后追加
策略代码引用 POST_EVENT_ENRICHMENT → CI 失败
★ 仅 append-only 不足以防泄漏，必须视图级隔离
```

### 6.3 缺失机制与候选来源
```text
意向下注口径：每条已记录决策进分母；不可结算腿以 ROI=0 计入并单独报告
禁止静默剔除；必报 UNSETTLEABLE_RATE
若候选策略挖自 80,238 场历史样本：必须显式声明；该样本可供 nuisance 参数，
用于假设生成需声明且此后不得再进确认性样本
```

### 6.4 五个指标
| # | 指标 | 定义 | 角色 |
|---|---|---|---|
| ① | `SPORTTERY_PRICE_CLV` | `log(SP_entry / SP_close)` | 价格时机诊断 |
| ② | `SPORTTERY_DEVIG_MOVE` | `log(p_close_devig / p_entry_devig)` | 市场内部方向诊断 |
| **③** | **`SHARP_CLOSING_EV_PROXY`** | **`p_sharp_close_devig × SP_entry − 1`** | **Phase A 主门** |
| ④ | `MODEL_EX_ANTE_EV` | `p_model_asof × SP_entry − 1` | 策略自身预期 |
| **⑤** | **`REALIZED_UNIT_ROI`** | `(Σ SP × [中奖]) / N − 1` | **Phase B 最终裁判** |

**已删除**：`若 CLV ≤ 0 则 ROI 不可能为正`。

### 6.5 GOAL_LINE_CHANGED
```text
⑤ 始终保留原入场 goal_line 的订单并按该线结算，仅官方 VOID 时排除
① 仅当收盘存在同一 goal_line 时可计算
③ 仅当锐利收盘存在同一 goal_line 与市场形态时可计算，否则标记 NOT_COMPARABLE
必报：SHARP_PROXY_COVERAGE ｜ GOAL_LINE_CHANGED_RATE
      PROXY_MISSINGNESS_BY_STRATEGY ｜ ROI_OF_PROXY_MISSING_SUBSET
```

### 6.6 M2 / M3（冻结，同 v2.3）
```text
M2：rolling xG + 攻防强度 + 联赛级主场优势 + 时间衰减 + 训练窗口内拟合 rho
    rho 最小样本单联赛 ≥300 场，不足按联赛组层级收缩
    半衰期候选 {180,365,730} 天仅在 V 集选一次；rho 网格 [−0.20,0.20] 步长 0.01
    walk-forward 每 season 重训；禁止随机交叉验证
    禁止预设「fitted rho 一定改善平局概率」

M3：p_final,k = p_M1,k·exp(f_k(x)) / Σ_j [p_M1,j·exp(f_j(x))]
    多项 logistic（禁 GBM/GAM/树/神经网络）；L2，λ∈{0.001,…,10.0} 仅在 V 集选一次
    z-score（统计量仅训练窗口）；联赛固定效应，<200 场合并 OTHER
    校准 = temperature scaling（单参数 T），不使用模糊的 multinomial isotonic
    A 集与 Forward 禁止调参
```

---

## 7. 选择质量

```text
EDGE_LIFT 分层维度（冻结）：
  entry_policy_id ｜ market ｜ selection ｜ odds band ｜ league/competition class
  entry time bucket ｜ cbtSingle status ｜ sharp_proxy_eligible status ｜ 数据完整度
  在分层内算 residual lift，按样本量加权聚合

硬约束：
  MUTUALLY_EXCLUSIVE_SELECTION_RATE = 0
  MAX_PRIMARY_SELECTIONS_PER_FIXTURE = 1
不限制绝对覆盖率；高覆盖须证明 EDGE_LIFT > 0 且 CI 下界 > 0
```

---

## 8. 门禁、阶段与判据

### 8.0 Q0 · 供应商许可（L1 开发前置）
**签署 Freeze A 时必须附外部证据，不得由技术人员填 PASS。**
```text
必附：条款文件或书面确认（版本 / 取得日期 / SHA-256 或不可变存档）
须明确：长期保存原始响应 ｜ 衍生指标 ｜ 内部商业研究
        历史回补与修订政策 ｜ 调用限额与价格变更 ｜ 服务终止后数据使用权
★ 双源架构下，FiroApi 与 API-Football 两份条款都要
```

### 8.1 Track 1 · 数据质量观察期（14–30 天，只采集）

**capture opportunity 分类（先定分母再算比率）：**
```text
CAPTURE_OPPORTUNITY_ELIGIBLE ｜ NOT_LISTED_YET ｜ NOT_ON_SALE ｜ POOL_SUSPENDED
MARKET_NOT_OFFERED ｜ SHARP_NOT_COVERED ｜ SOURCE_MISSING ｜ TRANSPORT_FAILED
```

| 门 | 指标 | 分母 | 阈值 |
|---|---|---|---|
| Q1 | 时间戳覆盖率 | 全部成功 capture | ≥99% |
| Q2 | 竞彩 SP 快照完整度 | CAPTURE_OPPORTUNITY_ELIGIBLE | ≥99% |
| Q3 | Pinnacle 对齐率 | 满足 HAD mapping 条件的竞彩比赛 | ≥90%（F17 实测 100%） |
| **Q4** | **时间偏差** | 受控快照对 | **门槛在 Freeze B 依实测定**（F21 显示原 15/30 分不现实） |
| Q5 | match_id / fixture_id 跨日稳定 | — | 必须稳定 |
| Q6 | goal_line revision 频率 | — | 量化并有处理规则 |
| Q7 | 取消/延期/无效场语义 | — | 枚举完毕 |
| Q8 | 不可变性 | — | 首次收到的响应不得被覆盖；修订形成新 capture 记 `supersedes`/`revision_reason`；旧 SHA 永久保留。测 `SOURCE_REVISION_RATE` / `LATE_CORRECTION_RATE` / `HISTORICAL_BACKFILL_MUTATION_RATE`。**不要求供应商响应永不变化** |
| Q9 | 供应商独立性 | — | 时间戳是数据更新时间还是接口生成时间？是否系统性延迟？**F26/F27 已证赔率层同源，须记录该事实** |
| Q10 | σ 估计 | — | 测 ③ 的每腿 SD，用于 §8.3 |
| Q11 | `CBT_SINGLE_AVAILABLE_RATE` | 全部竞彩腿 | 实测后在 Freeze B 定门槛 |
| Q12 | `SHARP_PROXY_ELIGIBLE_RATE` | 有 Pinnacle 的腿 | F18 实测 97.8% |
| Q13 | 亚盘阶梯完整度 | HHAD 场次 | 为未来 HHAD 验证留存 |
| **Q14** | **采集容量与成本** | — | **见下（已实测重算）** |
| **Q15** | **★ 映射表质量（新增）** | — | `FINGERPRINT_MATCH_RATE` ≥98% ｜ `AMBIGUOUS_MATCH_RATE` ≤1% ｜ `UNMATCHED_RATE` |
| **Q16** | **★ 模型特征覆盖率（新增）** | 按联赛 | 比分历史可得率 ｜ xG 可得率 ｜ 身份映射可得率 |

#### ★ Q14 实测重算（D3）
