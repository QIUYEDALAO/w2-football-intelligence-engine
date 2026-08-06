# 《W2 竞彩足球量化 · 研究与迭代协议》 v2.3.1
## Freeze A 候选版

**起草**：2026-08-05 ｜ **起草方**：Claude Code
**状态**：Freeze A 候选。§3.3 已由 GPT 裁决为方案 B。

---

## 0. v2.3.1 相对 v2.3 的变更

| # | 变更 | 依据 |
|---|---|---|
| **D1** | **数据源改为双源**：FiroApi 只拿竞彩 SP，Pinnacle 及其余全部走 API-Football | 实测两源 Pinnacle 赔率完全一致（F26） |
| **D2** | **新增 §5.3 竞彩↔API-Football 映射表自举** | 两边 ID 体系不通（F30），但赔率可当指纹 |
| **D3** | **Q14 成本重算：¥264/月 → ¥24/月 + 一次性 ¥90** | F28 批量可行 + API-Football 配额 7,500/日 |
| **D4** | **新增 §14 工程边界与复用清单** | reality-checker 实测：12 项只有 3 项 WIRED（F31） |
| **D5** | 新增 F25–F32 | 本轮实测 |
| **D6** | §3.3 确认方案 B（GPT 裁决），并记录换源后仍不变的理由 | F25：Pinnacle 在 API-Football 上同样不提供 id=9 |

---

## 1. 硬事实

### 1.1 市场结构

| 编号 | 事实 |
|---|---|
| **F1a** | 打平的精确条件（与去水法无关）：`p_true > 1 / SP` |
| **F1b** | proportional 去水下竞彩超额率 ≈ 12.9%，相对门槛 1.129。**Shin/power 下逐选项另算** |
| F2 | 单腿无条件基线 ROI ≈ −12.5%（12 年 80,238 场） |
| F5 | 2串1 无优势基线 −21.6% ~ −23.4% |
| F8 | 夏季场次池零场五大联赛 |
| F9 | W2 五特征模型在 10/11 联赛劣于 Pinnacle 收盘；`w_market` 多为 1.0 |
| F10 | 生产 `dixon_coles_rho = 0.0`，τ 修正为恒等函数 |
| F13 | 截图覆盖当日 81.7% 场次，27% 比赛押互斥方向 |
| F14 | **FiroApi 侧** Pinnacle 不提供 marketId 9（三项让球胜平负） |
| ~~F15~~ | ~~Pinnacle 超额率 8.58%~~ **作废，见 F18** |

### 1.2 第一轮实测（2026-08-05 上午）

| 编号 | 事实 | 样本 |
|---|---|---|
| **F16** | **替代终点机制有效**：收盘价 EV 代理与实际 ROI 单调对应（11 档逐档吻合）。proxy>0 的腿 ROI **+5.01%**，fixture-cluster 95% CI **[+0.61%, +9.42%]** | 240,714 腿 |
| **F17** | Pinnacle 对竞彩场次的 1X2 覆盖率 = **100.0%** | 91 场 |
| **F18** | Pinnacle 超额率中位数 **3.55%**，均值 3.72%，P90 4.66% | 91 场 |
| **F19** | `SHARP_CLOSING_EV_PROXY > 0` 的腿占 **4.4%**（竞彩自身收盘价口径 2.73%） | 273 腿 |
| **F20** | **FiroApi Pinnacle 历史不回溯**：2026-06-20 起有；2026-03-07 / 2025-11-08 返回零机构 | 探测 5 日 |
| **F21** | 竞彩与 Pinnacle 最后更新时刻偏差：中位数 **151 分**，P95 **1600 分** | 91 场 |
| **F22** | **赛季内竞彩每日 30–56 场**，夏季仅 4–18 场 | 5 日 |
| **F23** | F16 的 +5.01% 集中度差：前 5 联赛贡献 66.6% 利润，剔除后降至 **+1.95%** | 6,574 腿 |
| **F24** | 即使在 proxy>0 子集内，平局仍为 **−8.48%**（胜 +8.89%，负 +4.08%） | 6,574 腿 |

### 1.3 ★ 第二轮实测（2026-08-05 下午，双源验证）

| 编号 | 事实 |
|---|---|
| **F25** | API-Football：Pro 计划 **7,500 次/日**；Pinnacle **id=4**；玩法表含 `Handicap Result id=9`，但实测 `?bookmaker=4&bet=9` → **results=0**，**Pinnacle 在此源同样不提供三项让球** |
| **F26** | **两源 Pinnacle 赔率完全一致**：江原FC vs 富川FC（2026-08-01），FiroApi `1.56/3.99/6.79` ＝ API-Football fixture 1507016 `1.56/3.99/6.79` |
| **F27** | **机构编号 11/11 实测一致**（含非连续的 13/15/36）→ 赔率层同源 |
| **F28** | **API-Football `/odds?date=&bookmaker=4` 支持批量**：10 条/页，2026-08-01 共 **56 页** |
| **F29** | **API-Football 历史赔率同样为 0**（2026-03-07 / 2025-11-08 / 2024-05-11）→ **F20 是行业普遍限制，非 FiroApi 缺陷** |
| **F30** | **两源 ID 体系不通**：FiroApi `idEvent 2552931` 在 API-Football `/fixtures?id=` 无返回；API-Football fixture id 为 150xxxx 量级 |
| **F31** | **W2 声称可复用的 12 项基础设施，实测只有 3 项 WIRED**（详见 §14）。**调度器从未部署**：`w2-staging.service` 仅启 `api worker web`；部署脚本把「scheduler 运行数 = 0」当作成功条件；`celery_app.py` 无 `beat_schedule` |
| **F32** | **无任何 schema / 角色隔离**：45 个迁移中 `CREATE SCHEMA|GRANT|CREATE ROLE|search_path` 零命中；一库一角色（`w2_user` 即 owner）。**Provider 控制为进程级全局 env 读取，无 per-consumer 作用域，两个进程无共享配额上限** |

### 1.4 F16 的适用边界（必须随引用一同出现）
```text
F16 使用竞彩自身收盘价作真值代理 = 事后信息
证明的是「若有可靠的收盘期真值代理，则该代理预测 ROI」
不证明「Pinnacle 在入场时刻能扮演该代理」—— 后者是 Phase A 的核心待验命题
```

---

## 2. 定位（不变）

```text
Track 0 历史研究   → 候选生成 + 失败排除。不产出 GO
Track 1 数据质量期 → 数据验收 + 参数估计。不产出结论
Track 2 Phase A    → 前向候选筛选
Track 3 Phase B    → 单一冻结策略，唯一产出 PROVEN / NOT_PROVEN
```

**历史研究的限制**：L-1 as-of 时间戳缺失 ｜ L-2 全样本已被使用 ｜ L-3 反复修改会过拟合 ｜ **L-4 两源历史赔率均为 0（F20+F29）** ｜ L-5 只能用于候选生成与失败排除

---

## 3. 锐利参照市场

### 3.1 市场对应（冻结）

| 竞彩市场 | 锐利参照 | 状态 |
|---|---|---|
| **HAD**（胜平负） | Pinnacle `Match Winner`（API-Football bet id 1），覆盖率 100%（F17） | ✅ **Phase A/B 主研究市场** |
| **HHAD**（让球胜平负） | **两源均不提供**（F14 + F25） | ⚠️ 方案 B |

### 3.2 竞彩侧数据完整
1 次 `all-list` 即返回 HAD 与 HHAD 三项 SP + `goalLine`。**竞彩侧无缺口。**

### 3.3 HHAD 裁决：**方案 B**（GPT 已裁决）
```text
HAD  = Phase A / Phase B 主研究市场
HHAD = 全量采集，仅进入 Track 0 与 EXPLORATORY_ONLY
      原始数据、goalLine、三项 SP、Pinnacle 完整亚盘阶梯一律照常采集
```
**★ 换源后此裁决不变**：F25 实测 Pinnacle 在 API-Football 上同样不提供 `bet=9`。

### 3.4 方案 A 的正确公式与降级（仅供 EXPLORATORY）

设 `g` 为施加于主队的整数让球，`M = 主队进球 − 客队进球`：
```text
让胜: M + g > 0  ⟺  M ≥ 1 − g
让平: M + g = 0  ⟺  M = −g
让负: M + g < 0  ⟺  M ≤ −g − 1
```
**通用式：**
```text
P(让胜) = 亚盘 home line (g − 0.5) 的主队侧公平概率
P(让负) = 亚盘 home line (g + 0.5) 的客队侧公平概率
P(让平) = 1 − P(让胜) − P(让负)
```
**推荐实现（CDF 法，自带单调性校验）：**
```text
F(k) = P(M ≤ k) 由完整半球阶梯构造
P(让胜)=1−F(−g) ｜ P(让平)=F(−g)−F(−g−1) ｜ P(让负)=F(−g−1)
F 沿阶梯必须单调非减；违反则标记 STALE_OR_MISPARSED
```
**实现警告：**
```text
① 禁止用 −g 的整球线走捷径（走盘退款使走盘概率在两边约掉，不可还原）
② 四分之一球线是分注，不得当单一半球线概率点读取
③ 该 bug 在 g ≥ 0 时算出负概率（大声失败），g ≤ −2 时静默失败（让平高估约 +20pp）
   →「日志无负概率」不能证明映射正确
```

### 3.5 已删除的错误经济解释
```text
✗ 「可用空间 ≈ 竞彩超额率 − Pinnacle 超额率」
```
推导：若两市场去水概率一致，`EV = 1/(1+O_J) − 1 = −O_J/(1+O_J)`。**`O_P` 在归一化时被约掉。基线只取决于竞彩自身超额率**，以 12.9% 计为 **−11.43%**（与 F19 实测中位数 −10.96% 相符）。

`SHARP_REFERENCE_OVERROUND` 的正确定位 = **锐利代理的质量指标**，非可用边际预算。保留 `MAX_SHARP_OVERROUND`（初值 5%，F18 实测合格率 97.8%）。

---

## 4. 系统分层与执行宇宙

```text
L1  信号基础设施       每日采集 + append-only Signal Ledger      ← Freeze A 授权
L2  策略注册与冻结                                                ← Freeze B 授权
L3  LEDGER_M 测量账本  固定 1 单位/腿                              ← Freeze B 授权
L4  LEDGER_E 执行模拟  凯利/止损/分散/复利，不参与任何判据          ← Freeze B 授权
```

### 4.1 L1 必存字段（冻结）
```text
【竞彩侧 · FiroApi】
原始响应 + SHA-256 + capture_id + capture_schedule_id
供应商 updateTime ｜ 本系统接收时间
竞彩 match_id ｜ 场次编号 ｜ league ｜ kickoff ｜ season_id
market (HAD/HHAD) ｜ goal_line ｜ selection ｜ SP
sellStatus ｜ poolStatus ｜ cbtSingle ｜ cbtAllUp

【锐利侧 · API-Football】
fixture_id ｜ league_id ｜ bookmaker_id ｜ bet_id ｜ value ｜ odd
odds update 时间戳 ｜ timestamp_skew_seconds ｜ SHARP_REFERENCE_OVERROUND
完整亚盘阶梯（为未来 HHAD 验证留存）

【映射】
竞彩 match_id ↔ API-Football fixture_id ｜ 映射方式 ｜ 置信度 ｜ 建立时间

【赛后】
官方赛果 ｜ 无效/取消/延期状态
```

### 4.2 L3 / L4 分离
```text
LEDGER_M：每腿固定 1 单位；永不复利/止损/跳过/事后剔除
LEDGER_E：分数凯利、单注上限、日风险预算、单场暴露、共享腿约束、−50% 熔断、复利
★ LEDGER_E 的任何数字不得进入 §8 任何判据
★ 熔断只停 LEDGER_E；LEDGER_M 照常记录
★ Phase A 凯利只记录 f*，仓位用 FLAT_FRACTION（F9：模型 p 不可信）
```

### 4.3 执行宇宙分割
```text
PRIMARY_EXECUTABLE_UNIVERSE   cbtSingle = true   → 可进 Phase A 主门与 Phase B 主判
ALLUP_ONLY_RESEARCH_UNIVERSE  cbtSingle = false  → 仅研究，不触发单腿 GO
```
**Track 1 必须优先测 `CBT_SINGLE_AVAILABLE_RATE`。**
