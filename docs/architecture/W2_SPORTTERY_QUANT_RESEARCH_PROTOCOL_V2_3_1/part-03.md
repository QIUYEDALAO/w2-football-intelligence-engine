```text
已实测：
  BATCH_SUPPORTED(FiroApi tf/odds)   = false（逗号分隔 400，按日期 400）
  BATCH_SUPPORTED(API-Football odds) = true（?date= 批量，10/页）
  API-Football 配额                   = 7,500 次/日（Pro）
  竞彩场次                            = 赛季内 30–56/日，夏季 4–18/日（F22）

【自举期 14–30 天】
  FiroApi all-list         4 次/日
  FiroApi tf/odds          ~15 次/日（指纹）
  API-Football /odds       ~56 次/日（配额内）
  → FiroApi 约 450 次一次性 ≈ ¥90

【稳态】
  FiroApi all-list         3–4 次/日  ≈ ¥24/月
  API-Football             ~56 次/日  → 配额 7,500 内，边际零成本
  → 月成本 ≈ ¥24（v2.3 写的 ¥264–1,000 作废）

仍须实测并记录：RATE_LIMIT ｜ RETRY_BUDGET（失败重试是否计费）
                CALLS_PER_DAY_P50/P95/MAX ｜ EXPECTED_CAPTURE_COVERAGE
```

#### Q4 重新设计（依 F21）
```text
SKEW_AT_CAPTURE = |竞彩 capture 时刻 − 同 capture 内锐利源 odds update 时间|
门槛在 Freeze B 依 Track 1 实测分布确定
必报：SOURCE_STALENESS_竞彩 / SOURCE_STALENESS_SHARP
```

### 8.2 Phase A · 学习期

**PRIMARY 生命周期合同（冻结）：**
```text
每个 PRIMARY_VERSION 注册时声明：
  evaluation_start ｜ evaluation_end ｜ minimum_active_cycles
  active_market_scope ｜ entry_policy_id ｜ code_hash
MIN_PRIMARY_ACTIVE_CYCLES = 2
不得因首周期表现差提前停止，不得因表现好提前晋级
只允许 Cycle 4 末一次正式检验

运行窗口：INCUMBENT Cycle 1–4 ｜ PRIMARY_A Cycle 1–2 ｜ PRIMARY_B Cycle 3–4
EXPLORATORY_ONLY 每周期 ≤2 个，永不晋级；表现好只能成为后续新 PRIMARY，
                 其探索期样本不得并入确认性样本
```

**Incumbent 比较合同（冻结）：**
```text
初始 INCUMBENT = NO_SELECTION（空仓基准）
PRIMARY_METRIC = ③ 的分层 residual lift
COMPARISON     = 共同 eligible universe 上的预注册分层配对检验
INCUMBENT 空仓时以该 universe 全池均值为对照
```

**多重检验族（冻结）：**
```text
族 = 全部曾注册 PRIMARY_CHALLENGER × 每个假设内部冻结分层数 × 冻结市场范围
方法 = Holm–Bonferroni，α_family = 0.05（可替代：置换 max-T，Freeze B 二选一）
EXPLORATORY_ONLY 不计入族大小
★ 每个 PRIMARY 只有一次确认性检验 → 无需额外 alpha-spending
```

**晋级条件（Cycle 4 末一次性判定）：**
```text
A1  某 PRIMARY 在其全部注册后周期上，③ 合并均值 > 0
A2  合并样本 ③ 的 cluster-robust 95% CI 下界 > 0，经 Holm 校正后仍显著
A3  n ≥ §8.3 公式计算值
A4  跨赛季结构：至少跨 2 个 season_id；必报 POOL_COMPOSITION_DISTANCE、
      LEAVE_ONE_SEASON_OUT、LEAVE_ONE_LEAGUE_OUT、策略×联赛/赛季异质性
      （不预写硬阈值，如需最低构成差在 Freeze B 用不含赛果的数据冻结）
A5  EDGE_LIFT（分层加权）> 0 且 CI 下界 > 0
A6  MUTUALLY_EXCLUSIVE = 0 且 MAX_PRIMARY_SELECTIONS_PER_FIXTURE = 1
A7  ③ 为正不集中：剔除最大贡献联赛后仍 > 0（**F23 警示**）
A8  SHARP_PROXY_COVERAGE ≥ MIN_SHARP_PROXY_COVERAGE
A9  全部版本披露完整
A10 优于 INCUMBENT
A11 ★ 该 PRIMARY 的全部腿映射置信度达标（§5.2）
```

**硬停止**：`S1` Cycle 4 末无 PRIMARY 满足 A1–A11 ｜ `S2` 全部 PRIMARY 失败且层级 meta 模型总体效应 95% CI 上界 ≤ 0

### 8.3 样本量与效应量

```text
n_raw = DEFF × ( (z_{1−α*/2} + z_{1−β}) × σ(d̄) / δ )²

α* = Holm 校正后水平 = α/m ｜ 1−β ≥ 80% ｜ σ(d̄) = √(d̄ − 1) ｜ DEFF 实测
```
**已作废的旧式**：`n = (1.96σ/δ)²` —— 代入自身得门槛塌缩为 `ROI_hat > δ`，**功效恰为 50%**。

| δ | 裸功效 80% | +Holm(m=4) | +DEFF=2 |
|---|---|---|---|
| +5% | 3,785 | 5,378 | ≈10,800 |
| +3% | 10,514 | 14,937 | ≈29,900 |
| +10% | 949 | 1,349 | ≈2,700 |

**σ 随赔率变化**：`σ = √(d̄−1)`，`n ∝ (d̄−1)`。策略漂向冷门则 n 再乘 `(d̄−1)/1.2`。

**门槛从 0 改为 c（执行经济性下限）：**
```text
Phase B 检验 H₀: ROI ≤ c，而非 ROI ≤ 0
c 由成交摩擦、结算扣减、实体店执行成本确定，Freeze B 前定
δ 与 c 必须是同一个量或声明关系；禁止同时保留两个 δ
```

**时间尺度（依 F19+F22）：**
```text
合格率 4.4% × 每日可选腿（赛季内 120 / 夏季 36）→ 年均约 4 条合格腿/日
δ=+5%  → ≈10,800 腿 → ≈7.4 年
δ=+10% → ≈2,700 腿  → ≈1.8 年
★ 时间尺度完全由未知的 δ 决定 → 本协议不给固定时间承诺
★ Phase A 前 2 个周期的首要产出是测出 δ 的量级，不是筛出策略
```

### 8.4 Phase B
```text
B1 单一冻结 version 累积独立腿 ≥ 重算值，全部来自 PRIMARY_EXECUTABLE_UNIVERSE
B2 平注 ROI 的 cluster-robust bootstrap 95% CI 下界 > c
B3 平注 ROI 点估计 ≥ δ
B4 ③ 在整个 Phase B 保持为正
B5 剔除最大贡献联赛/月份后仍 > c；前 5% 比赛贡献利润 < 50%
B6 期间未做任何策略调整
B7 跨 ≥2 个赛季结构
```

---

## 9. 统计方法

```text
有效样本量必报：RAW / UNIQUE_FIXTURE / UNIQUE_LEAGUE / UNIQUE_SEASON_COUNT
                MAX & AVERAGE_FIXTURE_REUSE ｜ EFFECTIVE_SAMPLE_SIZE ｜ DEFF

★ 置信区间必须 cluster-robust：
    聚类不只抬高 n，更直接抬高一类错误率
    DEFF=1.5 → 5.5%（2.2×）｜ DEFF=2.0 → 8.3%（3.3×）｜ DEFF=3.0 → 12.9%（5.2×）
    且 Holm 作用在已失真的 p 值上无效
    重采样单位 = 整个 fixture（若日相关更强则整日）
    方法 = BCa bootstrap ≥10,000 次（收益右偏，正态区间在此 n 下覆盖不准）
    估计量定义在 fixture 层而非腿层（一场 3 腿 = 对同一个 M 的 3 倍暴露）
    种子在 §12 冻结

集中度必报：TOP_10_LEAGUE/FIXTURE/DAY_PROFIT_CONTRIBUTION ｜ PROFIT_BY_SEASON
            LEAVE_ONE_LEAGUE_OUT ｜ LEAVE_ONE_SEASON_OUT
校准：Log loss ｜ Brier ｜ RPS ｜ ECE ｜ 十分位校准曲线
平注/复利分离：双口径报告，主判据一律平注
```

---

## 10. Freeze A 的授权范围

**授权**
```text
✅ L1 原始采集（双源）  ✅ Signal Ledger（append-only + 修订追踪）
✅ 竞彩↔API-Football 映射表自举
✅ AS_OF_SIGNAL_VIEW / POST_EVENT_ENRICHMENT 隔离
✅ Track 1 数据质量报表
```

**不授权**
```text
❌ L2 策略注册执行  ❌ L3 Shadow 订单  ❌ L4 Kelly/复利/熔断
❌ Phase A  ❌ Phase B  ❌ Portfolio  ❌ 2×1  ❌ 真钱
❌ 修改现有 V4 推荐链、Scheduler、Dashboard
```

### Freeze A 清单
```text
□ Q0 双源供应商许可（附外部证据）
□ L1 字段清单（§4.1）｜ market_identity 定义
□ ENTRY_SNAPSHOT_POLICY：capture_times / entry / close（§6.1）
□ 成交可得性记录字段 ｜ AS_OF / POST_EVENT 隔离规范（§6.2）
□ append-only 与修订追踪（Q8）｜ 缺失机制口径（§6.3）
□ 执行宇宙分割（§4.3）
□ HAD sharp mapping = API-Football bet id 1 ｜ HHAD = 方案 B
□ 映射表自举方案与切换条件（§5.2）
□ Q1–Q16 验收定义与分母分类
□ ★ §14 的工程边界确认（哪些复用、哪些新建）
```

### Freeze B 清单（Track 1 完成后，仅用不含赛果的统计）
```text
□ 可用市场范围 ｜ MAX_SHARP_OVERROUND ｜ MIN_SHARP_PROXY_COVERAGE
□ Q4 时间偏差门槛 ｜ σ_design ｜ DEFF 估计
□ δ（单一值）｜ c ｜ Phase A/B 样本量
□ 主去水方法确认 ｜ 多重检验方法
□ FLAT_FRACTION ｜ 首批 PRIMARY 与 entry_policy_id ｜ Cycle 1 起点
□ 映射表切换条件是否达标（§5.2）
```
