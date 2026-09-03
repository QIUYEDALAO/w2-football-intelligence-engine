# W2-REMOVE-COVERAGE-SHORTCIRCUIT-01

## 结论

在基线 `1de3c1ef554d00a408577f59f4864e04f1d341da` 上，六个因子的联赛覆盖档案已从运行时短路条件改为纯诊断信息。生产只读快照在执行时已自然增长到 455 张 shadow card（派发时为 454 张）；同 fixture、同缓存输入的成对重放显示，F1、F2 与 F9 确实被覆盖门遮住了可用数据，F5 与 F8 则确认底层数据仍缺失，F6 的结果完全不变。

删除短路后，325 张 card 新增了真实可用的 xG 组，但都只有 1 个独立信号组，仍低于 `INDEPENDENT_SIGNAL_MINIMUM = 3`。因此 `DATA_INSUFFICIENT` 保持 430，实际可输出仍为 25；安全门没有被绕过。

本任务未修改 registry、权重、信号 allowlist/组集合、最低信号数、lambda、`CALIBRATION_VERSION` 或概率模型。

## 修改范围

仅删除以下六处 `coverage_or_unavailable(...)` 及其提前返回：

- `F1_MARKET_MOVEMENT` / `bookmaker_depth`
- `F2_BOOKMAKER_DIVERGENCE` / `bookmaker_depth`
- `F9_TRUE_XG` / `xg`
- `F5_RECENT_AH_COVER` / `settled_ah`
- `F6_H2H` / `h2h`
- `F8_SQUAD_VALUE` / `squad_value`

`coverage_available()` 与 `coverage_or_unavailable()` 本身保留，其他调用方行为不变。`FeatureContribution` 新增 `coverage_profile_status`，保存相应联赛 coverage profile 的原始字符串；六个因子的成功、缺数与泄漏阻断返回路径均携带该值，公开 contribution payload 也原样输出。该字段不参与状态、分数、独立信号或任何门槛判定。

## 测量方法与边界

### 修改前生产基线

- 生产数据库仅在 `REPEATABLE READ READ ONLY` 事务内读取，事务结束回滚。
- 运行时共有 455 张 shadow card；派发中的 454 是更早快照，不是本次选择性增减样本。
- 线上镜像中的 framework、market/live/team factors、engine、analysis calculator、team score 与 pricing shadow 八个文件，经 SHA-256 核对均与基线 `1de3c1ef` 同字节。
- 生产写、Provider、ledger、migration 与配置写均为 0。

### 修改后反事实重放

- 对同一批 455 个 fixture 使用相同的持久化缓存输入，先运行基线覆盖门，再在同一一次性 Python 进程内将六处覆盖门替换为 no-op，进行成对重放。
- 当前 registry 已禁用 Allsvenskan 与 World Cup，按当前 enabled 集合只能新生成 404 张。为了完整重放已经存在的 455 张 checkpoint，仅在该一次性进程内把对应 registry entry 的 `enabled` 设为 `True`；coverage profile 原值保持不变，未写数据库或配置文件。
- “修改后”均指上述只读、同输入的进程内计算，不代表代码已部署。

## 六因子 status 分布

| 因子 | 修改前（455） | 删除覆盖短路后（455） | 结论 |
| --- | ---: | ---: | --- |
| F1 `MARKET_MOVEMENT` | UNAVAILABLE 455 | READY 441；INSUFFICIENT_DATA 14 | 441 场已有真实盘口移动输入 |
| F2 `BOOKMAKER_DIVERGENCE` | UNAVAILABLE 455 | DEGRADED 427；INSUFFICIENT_DATA 28 | 427 场已有可计算但降级的市场共识 |
| F5 `RECENT_AH_COVER` | UNAVAILABLE 455 | INSUFFICIENT_DATA 455 | 覆盖门移除后仍缺 canonical settled-AH evidence |
| F6 `H2H` | READY 9；UNAVAILABLE 446 | READY 9；UNAVAILABLE 446 | 覆盖门未改变真实 H2H 可得性 |
| F8 `SQUAD_VALUE` | UNAVAILABLE 455 | UNAVAILABLE 455 | 覆盖门移除后仍缺可用 value mapping/snapshot |
| F9 `TRUE_XG` | READY 25；UNAVAILABLE 430 | READY 350；UNAVAILABLE 105 | 额外 325 场已有真实 xG 输入 |

状态语义复核也发现，派发前提中“F6/F8 缺数据使用 `INSUFFICIENT_DATA`”与当前代码不完全一致：F6 的 `NO_H2H_HISTORY` 和 F8 的 `VALUE_DATA_UNAVAILABLE` 都返回 `UNAVAILABLE`。本任务未顺手改变该既有状态语义。

## 独立信号与输出安全门

| `independent_signal_count` | 修改前 | 删除覆盖短路后 |
| ---: | ---: | ---: |
| 0 | 430 | 105 |
| 1 | 0 | 325 |
| 2 | 0 | 0 |
| 3 | 16 | 16 |
| 4 | 9 | 9 |
| 5 | 0 | 0 |

实际信号组组合：

| 组合 | 修改前 | 删除覆盖短路后 |
| --- | ---: | ---: |
| 无独立信号组 | 430 | 105 |
| `xg` | 0 | 325 |
| `ratings + team_fixture_history + xg` | 16 | 16 |
| `h2h + ratings + team_fixture_history + xg` | 9 | 9 |

- `DATA_INSUFFICIENT`：430 → 430。
- 可输出：25 → 25。
- 新出现的 325 张 card 只有 `xg` 一组，仍被 minimum=3 拦截；没有薄到单组的数据因此翻成可输出。
- F1/F2 虽然出现 READY/DEGRADED 数据，但 registry、`ALLOWED_INDEPENDENT_FACTORS` 与 `AUTHORITATIVE_SIGNAL_GROUPS` 均未改，因此仍不进入独立评分。本任务只区分“门挡住了数据”与“底层确实缺数据”。

## 模型与 identity 不变性

455 个 fixture 的逐场成对比较结果：

| 检查项 | 结果 |
| --- | ---: |
| lambda mismatch | 0 |
| model probability mismatch | 0 |
| calibration version mismatch | 0 |
| `CALIBRATION_VERSION` | `w2.formal.lambda_baseline_prior.v1` |
| identity | `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` |
| identity verdict | `APPROVED_VALIDATED` |

这符合本任务的边界：改变的是因子取数前的覆盖审计短路及诊断展示，不是 lambda 或概率模型。

## 测试与回归判定

定向回归覆盖：

- `NOT_AUDITED_STAGE14_REQUIRED` 不再令六因子提前返回；
- 真缺数据仍进入各因子自己的缺数据分支；
- 六因子均保留 `coverage_profile_status`；
- analysis-card contribution payload 输出该诊断字段。

提交前最终复核：

- 本任务直接相关测试：`18 passed`。
- canonical serialization：`57 passed`。
- package matrix：`5 passed`。
- 全量 pytest：`2950 passed / 9 skipped / 5 failed / 5 warnings`，耗时 `408.10s`。
- Ruff：PASS。
- `git diff --check`：PASS。

父提交 `1de3c1ef` 已在干净 detached worktree 对以下相同 node ID 精确复跑，结果为 5 failed；因此它们不是本次删除覆盖门引入的回归：

- `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`
- `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`
- `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`
- `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`
- `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`

对应宿主限制分别为 Docker Compose 插件不可用、缺少 bare `python`、以及 macOS Docker UID/GID/bind-mount 行为。曾出现的第六个 package-matrix 失败确属本分支测试 import 扩大 caller count；已把 payload 断言移入原本就依赖 analysis calculator 的测试模块并定向验证通过，未修改 package-matrix 期望以掩盖回归。

## 安全解释

覆盖档案说明“该联赛是否完成覆盖审计”，不是“本场数据是否存在”。移除短路后，真实数据可见，但 `coverage_profile_status` 仍明确展示未审计状态。使用方在依赖新增 F1/F2/F9 输出前，应同时查看实际因子状态、coverage profile 与独立信号数；本任务没有把“有数据”提升为“已审计”或“可独立定价”。

## Stop lines

生产写 0；ledger 0；migration 0；部署 0；GitHub/GHCR 0；Provider 0；registry 0；权重 0；lambda 0；`CALIBRATION_VERSION` 0；`ALLOWED_INDEPENDENT_FACTORS` 0；`AUTHORITATIVE_SIGNAL_GROUPS` 0；`INDEPENDENT_SIGNAL_MINIMUM` 0。
