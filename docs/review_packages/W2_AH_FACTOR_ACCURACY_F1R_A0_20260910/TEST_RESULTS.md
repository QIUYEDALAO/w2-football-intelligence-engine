# F1R-A0 测试与自检结果

```text
F1R-A0 定向  scripts/quant/tests/test_f1r_a0_offline_factor_recorder.py   86 passed
F1P 定向                                                       72 passed / 1 skipped
quant 全集   scripts/quant/tests                              380 passed / 1 skipped
package matrix                                                5 passed
arch P2-05                                                    6 passed
全仓 pytest                          8 failed / 3073 passed / 9 skipped
  相对 d8c8bf82 基线：新增失败 0，消失失败 0，测试 ID 逐条相同
ruff check .                         Found 10 errors —— **不是 exit 0**，
  但与干净生产基线 3ac86c14 的 10 条逐条相同，差集为空（本轮未引入任何新 lint）
ruff check .                         与 3ac86c14 基线差集为空
python -m compileall -q src scripts  exit 0
git diff --check                     clean
两次 runner                          产物逐字节一致
```

## 强制测试矩阵逐条对应

```text
 1 正常四因子完整批次        test_01_* —— 四条全部 PARTICIPATED、有分、有权重、
                             逐因子 evidence_time 严格早于 evaluated_at；
                             另断言四个证据时点**不全相同**（否则逐因子合同没有意义）
 2 缺少任一因子              test_02_* —— 四个因子各删一次，参数化 4 条
 3 重复 factor_id            test_03_*
 4 不同 evaluation/attempt/fixture
                             test_04_* —— 混批拒绝（参数化 2 条）+ fixture 不匹配
 5 不同 evaluated_at         test_05_*
 6 缺失 applied_weight       test_06_* —— 并扫描源码确认记录器不自带任何权重常量
 7 缺失 evidence_time        test_07_* —— 并断言 PARTICIPATED 缺 observed_at 直接拒绝
 8 evidence_time == 评估时间 test_08_*
 9 evidence_time > 评估时间  test_09_*
10 混合时间格式不能绕过      test_10_* —— 空格/T/Z/+00:00/+09:00 同一晚瞬间，
                             参数化 4 条；另加 naive 拒绝
11 created_at 不能证明 PIT   test_11_* —— 改 created_at 后身份不变、仍为幂等
12 scoreless 带 score 被拒   test_12_* —— 并验证缺数据批次仍形成四条明确观测
13 PARTICIPATED 无 score 被拒 test_13_*
14 source capture hash 非法  test_14_* —— 空/短/大写/非十六进制，参数化 4 条
15 identity 篡改             test_15_*
16 幂等重放                  test_16_* —— 账本逐字节不变
17 同 ID 异内容冲突          test_17_*
18 修订链                    test_18_* —— 新增 4 条，旧 4 条留在文件前缀且值不变
19 dangling supersedes       test_19_*
20 cycle                     test_20_*
21 批次失败后磁盘 0 新行     test_21_* —— 另有 8 处失败用例各自断言账本未变
22 AS-OF 无 post-event 字段  test_22_* —— 视图与 factor_inputs 双重检查；
                             并断言赛果字段混入 contribution.inputs 会被拒
23 TOTALS out-of-contract    test_23_*
24 F0/F1/F1P 冻结哈希不变    test_24_* —— 参数化 3 个包，实跑 shasum -c
25 无自建 serializer/hash    test_25_* —— AST + 源码扫描，两个文件
26 无网络、无生产数据库依赖  test_26_* —— AST 断言，含 w2.prematch/strategy/api/
                             dashboard/providers/ingestion/scheduler/infrastructure
```

另有 2 条：runner 两次运行逐字节一致；已发布结果显式声明四项"未做"。

## 一个刻意的设计取舍及其测试

缺数据的因子没有 `observed_at`，但契约要求每条观测都有 PIT 可证的证据时点。
处理方式是用 `FeatureContext.as_of`（"我们去看的那一刻"），并把语义写进
`factor_inputs.evidence_time_semantics`。

**两种语义不允许混用**，有测试锁定：

```text
PARTICIPATED 且缺 observed_at  → PARTICIPATED_WITHOUT_OBSERVED_AT（拒绝）
缺数据状态                      → SOURCE_QUERIED_AT_AS_OF（允许）
```

即 as_of 只能为**缺席**作证，永远不能替一个真实分数充当观测时点。

## F1P 合同未被改动

语义标签走 `factor_inputs` 这个既有自由映射，**没有新增合同字段、没有降级**。
F1P 包哈希 7/7 通过，其 6 份合同产物内容未变。

## 保留的 skip

`test_f1p_forward_factor_contract.py:255` 的 1 条 skip 予以保留：
`market` 被合同硬钉为 `ASIAN_HANDICAP`，构造不出"仅 market 改变但仍合法"的
身份变异，属设计必然，不是覆盖缺口。

## package matrix 同步

新增的 F1R-A0 脚本 import 了 `w2.features` 与 `w2.competitions.registry`
（§4 要求用真实四因子来源），使这两个包各多 2 个 scripts caller。
已用机械生成器 `regenerate_src_w2_package_matrix.py` 同步，
治理文档 diff **2 增 2 删**，重算后 `DRIFT_ROWS=0`，matrix 5/5 与 arch P2-05 6/6 均通过。


## 窄整改新增的测试

### P0 —— kickoff 不能冒充来源观测时点

```text
result-derived 因子缺显式来源时点         参数化 F5/F6，各自整批拒绝、磁盘 0 新行
传入值等于 kickoff                        参数化 F5/F6，SOURCE_OBSERVED_TIME_IS_KICKOFF_DERIVED
底层类前提                                直接断言 TeamMatchHistory.observed_at == kickoff_at
来源时点晚于 evaluated_at                 PIT_EVIDENCE_TIME_AFTER_EVALUATED_AT
F3/F9 的语义与 F5/F6 分开验证             断言三种规则各自生效，且 F5/F6 记录的是传入值
非 result-derived 因子被塞来源时点        SOURCE_OBSERVED_TIME_NOT_APPLICABLE（防止偷换）
```

### P1 —— 参与与权重必须来自评分权威

```text
READY + 非独立信号 / 非权威 source_group / 未知 group / 零权重
                                          参数化 4 条：一律 participated=false、
                                          FACTOR_ADMISSION_FAILED、score=null、
                                          weight_entered_weight_sum_used=false
逐项与权威一致                            participated 集合、每条 applied_weight、
                                          以及权重合计与 weight_sum_used 相符
权重与权威不一致                          APPLIED_WEIGHT_DISAGREES_WITH_SCORING_AUTHORITY
不复制过滤逻辑                            源码断言不出现 AUTHORITATIVE_SIGNAL_GROUPS /
                                          NON_SCORING_GROUPS / is_scoring_factor
```

### P1 —— 批次原子性（故障注入）

```text
第一行写入失败                            账本逐字节不变，行数仍为 4
中途写入失败                              同上
fsync 失败                                同上
提交点 os.replace 失败                    同上
以上三个阶段各自                          不残留临时文件
成功提交                                  四行全部落盘且可 readback
失败后重试                                仍能正常提交，不被前次失败污染
旧行原样重写                              新文件以旧内容为字节前缀
重写后重放                                仍是幂等 no-op
```

**validation failure 与 mid-write failure 是分开测的**：前者在打开文件之前就拒绝
（上文各条 `_bytes(ledger)` 断言），后者在临时文件里失败、原账本不受影响。


## 第二次窄整改新增的测试

```text
READY 但非独立信号 / 非权威 group / 未知 group / 零权重
                          参数化 4 条：participated=false 且 applied_weight == 0
INSUFFICIENT_DATA / SOURCE_UNAVAILABLE
                          参数化 2 条：applied_weight == 0，declared_weight 保留
三类无分状态同时出现       断言三种状态都被覆盖，且每条 applied_weight == 0
完整批次逐行核对           participated 集合与权威一致；每行权重等于权威值或 0；
                          SUM(applied_weight) == weight_sum_used
缺数据批次同样闭合         SUM == weight_sum_used
不变量必须能失败           人为给未参与行塞 0.1，断言被拒绝（守卫非空转）
已发布参考账本             每条 FACTOR_ADMISSION_FAILED 行 applied_weight == 0
已发布结果自洽             两个批次的 applied_weight_sum 与自带权威块一致
交付身份一致               parent/task_id/final_state 在 RESULT 与 INDEX 之间一致，
                          且不等于 d8c8bf82 或 0821f472
```

修订链测试改为修订 `factor_version` 而非 `applied_weight`：给一个未参与的因子
改权重现在会被新不变量拒绝，那正是期望行为，所以夹具改用一个合法的修订字段。


## 全仓失败集合：两种调用方式，两套精确数字

执行令要求用工作树自己的解释器 `./.venv/bin/python`。这会改变一个既有测试的结果，
原因与本任务无关，如实分列：

```text
./.venv/bin/python -m pytest -q      9 failed / 3072 passed / 9 skipped
uv run … python -m pytest -q         8 failed / 3073 passed / 9 skipped
```

差的那一条是：

```text
tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking
```

它在第 22 行 `subprocess` 调用裸名 `"python"`：

```python
["python", "scripts/check_sc18_input_authority.py"]
```

`uv run` 会在 PATH 上放一个 `python` shim，所以通过；直接用 `./.venv/bin/python`
不会，于是 `FileNotFoundError: No such file or directory: 'python'`。

**归属证明（自包含、可复现）**：

```text
该测试文件在 d8c8bf82 与 HEAD 之间          git diff --stat 无输出（逐字节相同）
本轮改动是否触及 tests/ 或 SC18 输入        无
同一节点 + PATH 上有 python shim            1 passed
同一节点 + 直接 venv 解释器                 1 failed
在早于全部 F1R 工作的 71cffa8d 工作树上
用同样的直接调用复跑该节点                   1 failed
```

即：这是调用方式与 PATH 的事实，不是本任务引入的回归。

### 逐节点差集（同一调用方式内比较）

`uv run` 口径下，目标与 `d8c8bf82` 的失败集合**逐条相同，新增 0、消失 0**：

```text
tests/contract/test_api_projection_read_authority.py::test_missing_projection_is_explicit_system_degraded_not_empty
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]
tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]
tests/contract/test_production_odds_reads.py::test_api_dashboard_card_keeps_historical_v3_identity_immutable
tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid
tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime
tests/regression/test_stage3_contracts.py::test_no_hardcoded_real_teams_leagues_or_fixtures
tests/unit/test_ev_migration_2b.py::test_frozen_29601_rows_match_exactly
```

`./.venv/bin/python` 口径下即上表加 SC18 一条，共 9 条。

### 关于 `EV_CONTRACT_2A_20260906/differences.json`

执行令提到该文件在目标与基线都缺失。已核实：
`docs/review_packages/EV_CONTRACT_2A_20260906/` **在整个仓库历史里从未被提交过**
（`git ls-tree` 在 `d8c8bf82` 与 `HEAD` 都为空，`git log --all` 无任何记录，
也不在 `.gitignore` 内）。因此 `test_frozen_29601_rows_match_exactly`
在两个提交上以相同文件状态失败，属仓库既有事实。
本轮未从其他工作树复制该文件，也未改动 EV_CONTRACT。

### Ruff

```text
./.venv/bin/ruff check .     Found 10 errors，exit=1 —— **不是 exit 0**
与 3ac86c14 干净基线的 10 条逐条相同，差集为空；本轮未引入任何新 lint
```
