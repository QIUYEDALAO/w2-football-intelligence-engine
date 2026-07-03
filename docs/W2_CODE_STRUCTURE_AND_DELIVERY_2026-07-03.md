# W2 代码瘦身 + 结构重构 + 推荐展示升级（合并执行文档）

出具：Claude ／ 2026-07-03（v2，合并瘦身审查）／ 基线 `feat/w2-audit-table-export`
本文档是唯一执行依据，合并了三部分：一、代码瘦身（删除清单）；二、结构重构；三、推荐展示方案。技术员按第四部分的 PR 顺序执行。

## 执行总原则（删除类改动的三条铁律）

1. **git 历史就是档案**：物理删除前先打标签 `git tag archive/pre-slim-2026-07`，任何被删内容可随时找回，不需要"复制一份留着"。
2. **每批删除 = 一个独立 PR**：PR 描述必须附"引用核查清单"（证明零调用的 grep 输出），合并前全测试绿 + `make check`（`scripts/check_w2_all.py`）+ staging 冒烟。
3. **两周回退窗口**：删除类 PR 合并后观察两周，期间发现误删直接 revert 单个 PR。该窗口只约束 B 通道清理类 PR（全部安排在休赛期），不构成任何上线等待。

---

## 一、代码瘦身（本次审查新增）

审查方法：对 `src/w2` 全部模块构建引用图（区分 src 内部 / apps / scripts / CI / Makefile / 测试），对 928 个 git 跟踪文件逐目录清点。结论：约 **30% 的跟踪文件属于产物、一次性阶段脚本或零调用模块**，可安全移除。

### T1 产物与遗留目录（低风险，先做）

| 对象 | 现状 | 处理 |
|---|---|---|
| `reports/`（根目录） | **146 个报告产物被 git 跟踪**（1.5MB，历史 stage 证据） | `git rm -r --cached reports/` + 加入 `.gitignore`；本地磁盘保留；此后运行产物只落 `runtime/`（已 ignore） |
| `archive/` | 54 个旧脚本/旧报告 | 整目录 `git rm -r`（标签已保历史） |
| `apps/web/dist/` | **构建产物 bundle 被提交进 git** | 立即 `git rm -r --cached`（不必等 #135） |
| `Dockerfile.d/` | 空目录 | 删除 |
| 远端分支 | `chore/stage*`、`codex/*` 等大量已完结分支 | 保留最近 30 天有提交的，其余删除远端引用（本条可选，不进 PR） |
| CI 防回归 | — | 在 CI 加检查：禁止新增 `reports/`、`runtime/`、`**/dist/` 下的跟踪文件 |

### T2 一次性阶段脚本（中风险）

`scripts/` 共 85 个文件，其中 **53 个带 stage 编号**（check_w2_stageX / run_stageX / build_stageX / deploy_stageX），是历史阶段验收的一次性工具，阶段已完结。

保留白名单（核查过的现役调用方：CI、Makefile、调度、日常运维）：

```
check_w2_all.py                     check_w2_stage1_contracts.py (CI/Makefile 用)
check_w2_future_refresh_staging_contract.py (CI 用)
run_predeploy_e2e_smoke.sh          smoke.py
export_w2_audit_tables.py           run_w2_report*.py
run_w2_settlement_history.py        run_w2_handicap_walkforward.py
run_xg_history_backfill.py          （+ 独立信号回填/临场刷新类 run_*.py）
replay_provider_fixture.py          recover_staging_runtime.sh
seed_* / select_* 中仍在 runbook 引用的
```

其余 stage 编号脚本全部删除。执行方式：先 `git ls-files scripts | grep -E "stage[0-9]"` 生成候选清单入 PR 描述，逐个 grep 确认不在 CI/Makefile/runbook 现役引用中，再删。

### T3 零调用模块（中高风险，逐个给了结论）

引用图扫描发现约 40 个模块无 src 内部调用。**零调用 ≠ 全部该删**——已逐个核对真实调用方，分三类：

**删除（连同其一次性脚本与测试）：**

| 模块 | 行数 | 依据 |
|---|---|---|
| `monitoring/stage7i_lifecycle.py` + `stage7i_supervision.py` + `observability/stage7i_observer_cli.py` | 1,562 | stage7i 观察期已完结；仅 3 个 stage7i 脚本与自身测试引用；对应 runbook 移入 docs 归档标注 |
| `strategy/shadow_cycle_cli.py`、`shadow/comparison_import_cli.py`、`gates/gate5_preflight_cli.py` | 249 | 零调用 CLI（CI/Makefile/runbook 均无现役引用），阶段门禁已过 |
| `markets/baselight_limited_ah.py` | 293 | stage5b 时代的受限 AH 实现，已被 canonical AH + simulate 路径取代 |
| `strategy/lock_ledger.py` | 290 | 被 #122 RecommendationLock 冻结快照取代（删除前 grep 确认无 settlement 路径引用） |
| `infrastructure/alembic_version.py` | 46 | 零调用工具，alembic 自带能力覆盖 |
| 上述模块对应的 `tests/unit/test_*` | ~1,200 | 随模块删除 |

**保留——看似零调用，实为在册未来消费方（删了会伤后续任务）：**

| 模块 | 服务于 |
|---|---|
| `markets/historical_dataset.py` | #131 S2 拟合语料（Gate3 历史数据集） |
| `backtest/lambda_fit_gate.py`、`backtest/s2_calibration_validation.py`、`backtest/s2_readiness.py`、`backtest/handicap_walkforward.py` | #131 walk-forward 与切参门禁 |
| `settlement/history.py`、`matchday/settlement.py` | 自动结算（scheduler 与 run_w2_settlement_history 在用） |
| `ingestion/independent_signal_backfill.py`、`ingestion/quota_budget.py` | A2/A3 回填与配额（休赛期主任务） |
| `monitoring/health.py`、`api/routers.py` | apps/api 入口在用 |

**跟随删除（依赖 T2 决定）：** `api/dashboard_read_models.py`、`models/challenger.py`、`models/forward_autorun.py`、`operations/{governance,production_readiness,alerts,slo,drift}.py`、`historical/{builder,quality,splitters}.py`、`recovery/backup.py`、`security/baseline.py`、`strategy/correlation.py` 等——它们的唯一调用方是 T2 待删的 stage 脚本。**规则：先删脚本，跑引用扫描，二次确认为零调用后随批删除；有任何非 stage 调用方则保留。**

### T4 预期减量与验收

- 跟踪文件：928 → 约 650（reports 146 + archive 54 + apps/web 50 + scripts ~50 + dist）
- src 代码：删除约 3,500–4,500 行零调用/遗留代码
- 验收：`git ls-files | wc -l` 达标；全测试绿；`check_w2_all` 通过；staging 报告与审计表导出正常跑一轮；两周窗口无 revert。

---

## 二、结构重构（存量代码的健康化）

### S1（P0）repository.py 神模块拆分

`src/w2/api/repository.py` 共 4,878 行（第二大文件的 4 倍），承担 8 种职责，是历史上 dashboard 反复出 BUG 的后端土壤。机械搬移、不改行为：

| 新模块 | 迁出内容（现行号段） |
|---|---|
| `api/read_repository.py` | 纯 checkpoint/read model 读取（~280–420） |
| `features/inputs.py` | history/ratings/values/h2h/xg 输入构建（~1290–1450、2130–2500） |
| `api/dashboard_assembly.py` | 单场 payload 组装与 formal 接线（~4075–4200 及关联） |
| `markets/ah_canonical.py` | AH 符号/展示（~3260–3420），与 `strategy/formal_recommendation.py` 的 canonical 部分合流 |

验收：repository.py ≤ 800 行；全测试绿；重构前后同一输入的 dashboard payload 哈希一致（对拍脚本入 PR）。

### S2（P1）FORMAL 契约收敛

同一套规则手写在三处：`repository._valid_formal_recommendation_payload`、`match_decision._has_valid_formal_recommendation`、`recommendation_lock_snapshot._require_formal_ah_recommendation`，且已现实漂移（锁定层查 expected_value、报告层不查）。收敛为 `contracts/formal_contract.py` 单一函数，三个检查点（纵深防御）保留但都调用它。

### S3（P1）工具函数收敛

`_number/_dict/_list` 在 8–15 个模块各写一份、行为有细微差异。收敛到 `w2/common/coerce.py` 一次性替换。

### S4（P2）小项

`report_generator._score_line` 对每场重复调用 `decide_match`（传入已算好的 decision）；因子权重/刻度常数收拢到 `FactorScaleParams`（#128 已建）；双阈值（0.25 格 vs EV 3.5%+k·SE）主从关系写进 contracts 文档。

---

## 三、推荐展示方案：静态生成式 Dashboard

### 诊断：旧 dashboard 为什么修不好

`apps/web` 是 4,043 行 TypeScript + Vite 构建链的 SPA，在浏览器里用第二套逻辑重新推导状态、方向、盘口显示。后端契约每动一次前端就漂移一次——幻影 FORMAL、"方向未识别 +2.5"等历史 BUG 全部发生在这层。修 BUG 是追赶漂移，结构上追不完。展示层唯一正确姿势：**只渲染，不决策。**

### 方案：HTML 是报告的第三种输出格式

```
/v1/dashboard payload → decide_match（不变）→ render_report(format=html)
                                             → 静态单文件 runtime/reports/w2_day_YYYY-MM-DD.html
```

1. **同源**：与 markdown 报告同一 payload、同一 decide_match、同一禁词 guard（HTML 文本一样过 `_assert_safe_report_text`）。FORMAL 才渲染方向/比分，非 FORMAL 渲染原因码，契约零新增。
2. **零依赖静态文件**：服务端一次性渲染、数据内嵌，无框架、无构建链、无轮询；允许 ≤100 行内联原生 JS 做纯客户端过滤/折叠。
3. **分发即文件**：每足球日一个 HTML（不进 git），nginx 静态目录或直接打开，按日留档与审计表同期。
4. **刷新即重新生成**：报告语义本来就是快照 + as-of。早间/临场/每小时由 runner 定时重生成；健康门禁不过不产新页，旧页 as-of 自证过期。秒级实时在赛前锁定制度下没有决策价值。

### 信息架构（五大联赛周末 40–50 场）

顶部：足球日 + as-of + 六计数（场次/正式/观察/数据不足/盘口未就绪/已锁定）。FORMAL 卡片置顶（方向、盘口@赔率、我们的盘 vs 市场盘 vs 差距、top3 比分、ISC、走势恒标"参照·未验证"、as-of）；其余按联赛分组紧凑表，一行一场；状态/联赛过滤 chips。不做：命中率区块（#132 达标前只显示"观察中 n/30"）、页内操作、自动轮询。视觉原型已单独确认。

### 为什么不会重蹈覆辙

旧 SPA 三类 BUG 源——前后端状态漂移（此方案无前端逻辑）、契约不一致（同一 decide_match）、构建链问题（无构建链）——结构上不存在，不是靠"这次小心"。

---

## 四、执行顺序（快速上线版 · 2026-07-03 修订）

上线与清理是两条互不阻塞的通道。**上线不需要删除任何东西**：旧 `apps/web` 不部署、不引流即为冻结，零成本。原"1–2 周"等待只属于删除类改动的回退窗口，全部移入休赛期，不再出现在上线路径上。

### A 通道 · 立即上线（目标 72 小时内，无任何等待期）

| 时序 | 动作 | 说明 |
|---|---|---|
| T+0 | #125 回填实跑（history + h2h：dry-run 核对配额决策后即转实跑） | 根治"数据不足"，当晚场次 ISC 即修复，推荐开始正常产出 |
| T+0 | #123 四张审计表 staging 验收收尾 | 按原验收清单，与回填并行 |
| T+0 → T+2 | #134 HTML 渲染器开发 + 部署（1–2 天工作量） | 与 #125 并行；上线后 runner 定时早间/临场重生成页面 |
| T+2 | 上线判定：当个足球日跑通"markdown 报告 + 四表 + HTML 页"三件套 | 即视为上线，无观察期前置 |

世界杯剩余每个比赛日都是正式产出日：FORMAL → 锁定 → 结算，同时为 #132 积累种子样本。

### B 通道 · 休赛期清理（决赛 7/19 之后启动，串行执行）

| 序 | PR | 内容 | 预估 |
|---|---|---|---|
| 1 | #136 | T1 产物出库 + gitignore + CI 防回归 + 打 `archive/pre-slim-2026-07` 标签 | 0.5 天 |
| 2 | #137 | T2 一次性 stage 脚本删除 + T3 死模块删除（含跟随删除二次扫描） | 1 天 |
| 3 | #138 | S1 repository.py 四模块拆分（含 payload 哈希对拍） | 1–2 天 |
| 4 | #139 | S2 契约收敛 + S3 coerce 收敛 + S4 小项 | 1 天 |
| 5 | #135 | 删除 `apps/web` + compose `web` 服务 + `infra/Dockerfile.web`（放最后，届时 #134 已稳定运行数周） | 0.5 天 |

两周回退窗口只约束 B 通道的删除/重构 PR，全部落在休赛期（7/20–8 月初），不占用任何比赛日，也与 A2 历史回填、S2 拟合等休赛期任务并行不冲突。

## 五、总验收（Definition of Done）

1. 跟踪文件从 928 降到约 650，`runtime/`、`reports/`、`dist/` 零跟踪，CI 防回归生效。
2. repository.py ≤ 800 行，FORMAL 契约单点定义，全库 `_number/_dict/_list` 单份实现。
3. 每个足球日自动产出三件套：markdown 报告、四张审计表、静态 HTML 页——同一 payload、同一决策、同一禁词防线。
4. `apps/web` 及其构建链从仓库与部署栈中消失，compose 不再有 web 服务。
5. 全测试绿 + check_w2_all 通过 + staging 完整跑通一个足球日；删除类 PR 全部度过两周回退窗口零 revert。

## 附：本次瘦身审查的方法与限制

引用图基于静态 grep（import 与模块名双向匹配），已区分 src/apps/scripts/CI/Makefile/runbook/测试六类调用方；apps/web 打包产物中的字符串匹配已作为噪音排除。本审查环境无法运行测试套件，因此所有删除必须由技术员在每个 PR 内以全测试 + check_w2_all + staging 冒烟兜底——这也是三条铁律的由来。
