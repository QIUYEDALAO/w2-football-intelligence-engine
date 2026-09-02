# W2-DC-RHO-XG-AVAILABILITY-PROBE

状态：`DONE_READ_ONLY_PROBE`

结论：`DISTRIBUTION_SHAPE_01` 按当前冻结的 22 联赛 cohort **不可执行**。22 个联赛的 API-Football `league_id` 均可解析，但只有 10 个联赛的小样本返回数值 xG；其余 12 个联赛均为 `0/20`。因为后续修订明确禁止为可行性缩小或更换 cohort，预注册应改为 `BLOCKED_ON_XG_AVAILABILITY`，不能把 10 联赛子集写成原 22 联赛研究已可执行。

本报告只回答 xG 可得性与调用预算。不拟合、不读取 Football-Data 赛果/结算列、不写预注册、不修改代码、模型参数、校准身份、ledger 或生产状态。

## 1. 来源与口径

- Football-Data archive：`/Users/liudehua/.hermes/data/w2/football-data-co-uk/raw/season_zips/2324_data.zip`
- 实测 SHA-256：`f86ac89c3df57be812fc25d4d4aeca0ef98b910483e59560c0f7b406118e3c5a`
- archive members：`B1 D1 D2 E0 E1 E2 E3 EC F1 F2 G1 I1 I2 N1 P1 SC0 SC1 SC2 SC3 SP1 SP2 T1`
- 本地 `extracted/2324/`：只有 `D1 E0 F1 I1 SP1`
- Football-Data 只读取 `Date / HomeTeam / AwayTeam / AHCh / PCAHH / PCAHA / PC>2.5 / PC<2.5`；未访问比分、胜平负、结算或收益列。
- Provider 使用仓库既有 `ApiFootballClient`，live allowlist 仅为本任务需要的 `status / leagues / fixtures / statistics`。数值 xG 沿用既有严格解析：双方 team id 都必须出现 `Expected Goals`/`expected_goals` 且可转为 `float`，才计一场完整数值 xG。
- 非五大联赛从 2023/24 archive 全季均匀抽 20 场；五大联赛只从 `2024-02-22` 之后窗口均匀抽 20 场。fixture 对齐只使用日期与双方队名，不读取或比较赛果。

## 2. 逐联赛结果

| Football-Data | API-Football league_id | 可解析 | 探针窗口 | 数值 xG | 判定 |
|---|---:|---|---|---:|---|
| B1 | 144 | 是 | 全季 | 20/20 | AVAILABLE |
| D1 | 78 | 是 | 2024-02-22 后 | 20/20 | AVAILABLE |
| D2 | 79 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| E0 | 39 | 是 | 2024-02-22 后 | 20/20 | AVAILABLE |
| E1 | 40 | 是 | 全季 | 20/20 | AVAILABLE |
| E2 | 41 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| E3 | 42 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| EC | 43 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| F1 | 61 | 是 | 2024-02-22 后 | 20/20 | AVAILABLE |
| F2 | 62 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| G1 | 197 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| I1 | 135 | 是 | 2024-02-22 后 | 20/20 | AVAILABLE |
| I2 | 136 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| N1 | 88 | 是 | 全季 | 20/20 | AVAILABLE |
| P1 | 94 | 是 | 全季 | 20/20 | AVAILABLE |
| SC0 | 179 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| SC1 | 180 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| SC2 | 183 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| SC3 | 184 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| SP1 | 140 | 是 | 2024-02-22 后 | 20/20 | AVAILABLE |
| SP2 | 141 | 是 | 全季 | 0/20 | UNAVAILABLE_ZERO_NUMERIC_XG |
| T1 | 203 | 是 | 全季 | 20/20 | AVAILABLE |

可用 10 联赛：`B1 D1 E0 E1 F1 I1 N1 P1 SP1 T1`。不可用 12 联赛：`D2 E2 E3 EC F2 G1 I2 SC0 SC1 SC2 SC3 SP2`。

`0/20` 只表示本次冻结小样本没有双方数值 xG，不能外推为 Provider 永久不支持该联赛；但在当前预注册 arming 前，它足以阻止把该联赛当作可执行 xG cohort。

## 3. Football-Data 五列完整场次

10 个可用联赛的 2023/24 全季五列完整场数为 `3,588`。

结合已烧五大联赛窗口的排除要求，后续可用范围应按“非五大全季 + 五大 `2024-02-22` 后”计数，共 `2,453` 场：

| 联赛 | 五列完整目标场 |
|---|---:|
| B1 | 312 |
| D1 | 104 |
| E0 | 123 |
| E1 | 552 |
| F1 | 108 |
| I1 | 132 |
| N1 | 306 |
| P1 | 306 |
| SP1 | 130 |
| T1 | 380 |
| 合计 | 2,453 |

这里的 `2,453` 只是可用子集的结构/必需列计数，不是 22 联赛原 cohort 的 admitted count，也不是缩小 cohort 的授权。

## 4. 全量 xG 调用预算

预算包含：联赛解析、当季与前季 fixtures 身份发现、每个目标 fixture 的 statistics，以及为双方严格 5+5 历史补足的更早 fixture statistics。所有 statistics 按唯一 fixture 去重。

- 可复核下界：`2,985` 次。组成是 `2,453` 个目标 statistics、已从同联赛 2022 fixtures 确认的 `485` 个唯一历史 statistics，以及 `47` 次 league/fixture discovery。
- 保守上界：`3,626` 次。对 192 支目标球队均保留 1 次独立历史 discovery 与最多 5 个历史 statistics，不假设跨队 fixture 能去重。
- 日限 `7,500`、保留 `1,500` 时，可用预算为 `6,000/天`；因此上下界都需要 `1` 个配额日。

这个预算只说明 10 个可用联赛子集的采集成本。原 22 联赛 cohort 仍因 12 个联赛 `0/20` 而不可执行；花费更多配额不能把空 xG 变成数值 xG。

## 5. 本轮调用与护栏

- 实际 Provider 调用：`486/500`
  - `status` 2
  - `leagues` 2
  - `fixtures` 42（22 联赛探针 + 20 次可用联赛当季/前季预算核查）
  - `statistics` 440（22 × 20）
- 首次成功配额观测：`remaining=6814 / limit=7500`
- 最后观测：`remaining=6324 / limit=7500`
- `remaining < 1500`：未触发
- HTTP、plan、quota error：0

remaining header 在运行中不是严格单调，本报告以本地逐请求精确计数报告实际调用数，并把 Provider header 仅作为每次 fail-closed reserve 权威；不以首尾 remaining 差值替代调用计数。

## 6. 对任务 2 的绑定结论

```text
DISTRIBUTION_SHAPE_01_22_LEAGUE_COHORT = NOT_EXECUTABLE
PREREGISTRATION_NEXT_STATUS = BLOCKED_ON_XG_AVAILABILITY
AVAILABLE_SUBSET = 10_LEAGUES / 2453_UNBURNED_FIVE_COLUMN_COMPLETE_FIXTURES
SUBSET_EXECUTION_AUTHORITY = NOT_GRANTED
FIT = FORBIDDEN
TEMPORAL_HOLDOUT_READ = FORBIDDEN
```

任务 2 可以把本报告的来源、范围与预算写入草案，但不得把 22 联赛改成 10 联赛来获得表面可行性。

## 7. 验证回执

- 定向 Provider/quota：`46 passed`
- canonical serialization：`18 passed`
- package matrix：`5 passed`；本任务只新增 review report，无 package matrix 登记项需要同步
- Ruff：通过
- 全量：`2949 passed / 9 skipped / 5 failed`
- 五个失败在父提交 `1de3c1ef554d00a408577f59f4864e04f1d341da` 用相同 node ID 复跑均失败：
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]` — 宿主 Docker 无 Compose 插件
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]` — 宿主 Docker 无 Compose 插件
  - `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking` — 宿主 PATH 无裸 `python`
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid` — macOS 无法按 Linux UID/GID 行为执行
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime` — macOS 无法按 Linux UID/GID 行为执行
- 任务相关失败：0
- identity：`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`
- verdict：`APPROVED_VALIDATED`
