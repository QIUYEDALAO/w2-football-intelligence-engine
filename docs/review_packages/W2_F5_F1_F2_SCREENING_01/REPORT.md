# W2-F5-F1-F2-SCREENING 最终报告

状态：`DONE_FAIL_NOT_MEASURABLE / SCREENING_ONLY`

## 冻结与边界

- 生产基线：`1de3c1ef554d00a408577f59f4864e04f1d341da`。
- 预注册提交：`4652a5f8`；JSON SHA-256 `5e105f3184c884409324dadac6f819dd3d2ef4325e0bdf9eac082a702f730171`；Markdown SHA-256 `a36a195f91e0c84e9775ef2e53900deba8accdedfe83d3cb07d96d2d786cd7e1`。
- loader 提交：`839fd128`；安全 factor presence 检查提交：`31555ee0`；结果前 runner 冻结提交：`edede1cd`。
- loader 仅暴露 `2026-01-01T00:00:00Z <= kickoff < 2026-08-23T00:00:00Z`。开球晚于 2026-08-22、2024/2025、penaltyblog 烧毁赛季在 loader 后均为 `0`，断言触发 `0`。
- 家族固定为 F5/F1/F2，DELTA 轴，Bonferroni alpha `0.016667`；样本量下限 `300`。
- 本任务只用于筛选，不能作为准入依据；干净确认集未被消耗。

## 固定源与 loader 审计

| 来源 | 原始记录 | loader 后记录 | loader 后月份 | 主要排除 | 断言触发 |
|---|---:|---:|---|---|---:|
| completed history team-side | 38,706 | 5,256（2,628 fixtures） | Jan 656; Feb 772; Mar 840; Apr 1,084; May 1,080; Jun 16; Jul 358; Aug 450 | window 前 33,450 | 0 |
| PIT factor snapshots | 10,266 | 2,628 | Jan 328; Feb 386; Mar 420; Apr 542; May 540; Jun 8; Jul 179; Aug 225 | window 前 7,638 | 0 |
| production-lambda capture inputs | 136 | 77 | Aug 77 | cutoff 后 59 | 0 |
| fixture identities | 409 | 255 | Jul 32; Aug 223 | cutoff 后 154 | 0 |

固定源 SHA-256：history `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`；snapshot `aa77f112bae6d3f5a86b7ffc4a169baa77d5a2060e1a4a6a7e99a84ece96f3d3`；capture inputs `137e0263c5f942d549552df76b976aa09e66d0dc36781037fab3fd54210299b9`；fixture identities `b6ccd5c3ed528e16e6ac6930ac3a03e763b79c5375d84d00be75981f1084209f`。

预期“约 4,076 场”的说法未在任务 A 的固定 artifacts 中复现：实际 completed history/snapshot cohort 是 `2,628` 场。没有替换数据源或扩张到确认集来追齐预期数量。

## 因子存在性与 complete-case 排除

受保护的结构检查（只返回 ID/计数，不返回值）显示：

- 2,628 个 snapshot 的因子节点只有 `F3_REST_FITNESS`、`F6_H2H`、`F7_STRENGTH_FORM`，各 2,628；F5/F1/F2 均为 0。
- 77 条 capture inputs 只有四项 xG 输入及 fixture/kickoff/capture 标识；F5/F1/F2 均为 0。
- 255 条 identity capture 只有 fixture/provider identity/kickoff；F5/F1/F2 均为 0。
- 2,628 个 completed fixture 中，38 场能 join 到 production-lambda capture；这 38 场的三项目标标量仍全部缺失。其余 2,590 场缺 baseline capture。

| 因子 | 缺 baseline capture | 有 baseline 但缺因子 | 可用 fixtures=clusters |
|---|---:|---:|---:|
| `F5_RECENT_AH_COVER` | 2,590 | 38 | 0 |
| `F1_MARKET_MOVEMENT` | 2,590 | 38 | 0 |
| `F2_BOOKMAKER_INTENT` | 2,590 | 38 | 0 |

没有使用默认值、均值或先验填补。

## 结果

| 因子 | Brier 改善 | 单侧 95% 下界 | p | 是否过 0.016667 | 取值分布 | 结论 |
|---|---|---|---|---|---|---|
| `F5_RECENT_AH_COVER` | 不可计算 | 不可计算 | 不可计算 | 否 | n=0，min/p25/median/p75/max/std/zero 均不可计算 | FAIL_NOT_MEASURABLE |
| `F1_MARKET_MOVEMENT` | 不可计算 | 不可计算 | 不可计算 | 否 | n=0，min/p25/median/p75/max/std/zero 均不可计算 | FAIL_NOT_MEASURABLE |
| `F2_BOOKMAKER_INTENT` | 不可计算 | 不可计算 | 不可计算 | 否 | n=0，min/p25/median/p75/max/std/zero 均不可计算 | FAIL_NOT_MEASURABLE |

样本量在任何拟合前即低于 300，因此实际 coefficient fit `0` 次、bootstrap `0` 次。预注册的 10,000 次 bootstrap 只适用于可测因子；这里执行它会伪造空样本推断。

本结果只说明“任务 A 固定 artifacts 无法测量这三项”，不说明三因子信息量为零，也不支持接入或排除。若要筛选，必须先形成与 completed target fixture 绑定、严格 PIT 的 F5/F1/F2 capture，并另行预注册；本任务按跑一次、报一次、停的规则不换源重跑。

## Stop lines 与 identity

- 干净确认集（kickoff > 2026-08-22）：读取 `0`、消耗 `0`。
- 生产写、ledger、migration、部署、GitHub/GHCR、Provider：`0`。
- `CALIBRATION_VERSION`、模型参数/权重、registry、lambda、`historical_replay_cutoff`、split 边界：改动 `0`。
- 未接入 `calibrate_lambdas`，代码行为未改变。
- identity：按 M4 回报“未修改、未重新实测”。
- RESULTS.json SHA-256：`af54804b647169dba2bbef19d144de3dfd4b049a0cb3caebb4edfcd90d209bf4`。

## 本地验收

- loader 定向：`3 passed`；canonical serialization：`57 passed`；package matrix：`5 passed`；Ruff 与 `git diff --check`：PASS。
- 全量：`2952 passed / 9 skipped / 5 failed`。新增的 3 个 loader tests 解释了相对父提交的 passed 数增加。
- 以下 5 个失败在干净父提交 `1de3c1ef` 逐 node ID 精确复跑，结果 `5 failed`，均同样复现：
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`
  - `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`
- 失败原因分别是本机 Docker CLI 无 Compose 子命令、子进程 PATH 无 `python`、Docker 无法创建用于 uid/gid 权限检查的目录；均非本分支回归。
