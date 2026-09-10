# F1P package matrix 治理差异核对报告

```text
TASK_ID        W2_AH_FACTOR_ACCURACY_F1P_MATRIX_RECONCILIATION_20260910
HEAD           8208eb3f21923da85e96b9e36c7a4cae72302861   (F1P)
PARENT         71cffa8d4ab8e7a7d4a779cc91951c97f594a261   (F1 窄整改)
FINAL_STATE    CONTRACT_TESTS_PASS_PENDING_PACKAGE_MATRIX_RECONCILIATION
MATRIX_CHANGED false
```

## 1. 结论先说

**F1P 没有引入任何新增回归。** 基线与 F1P 的 package matrix 失败节点**完全相同**，
B 集合（F1P 新增失败）为空。

治理矩阵确实与现实不符，但**那是基线就已存在的过期记录，且范围远大于 F1P**，
不属于本任务可维护范围。因此**不修改矩阵**，按执行令 §4 收口为
`CONTRACT_TESTS_PASS_PENDING_PACKAGE_MATRIX_RECONCILIATION`，不进入 F1R。

## 2. 事实核对

```text
git status --porcelain=v1     空（工作树干净）
git rev-parse HEAD            8208eb3f21923da85e96b9e36c7a4cae72302861
git diff --stat 71cffa8d..HEAD
                              10 files changed, 1860 insertions(+), 0 deletions(-)
                              仅 F1P 交付包 7 个 + scripts/quant 3 个 .py
```

无其他未授权修改。

## 3. 基线对照方法

执行令建议在 `/tmp` 建基线工作树。**改用已存在且合规的**
`/Users/liudehua/Documents/Projects/W2-workspaces/w2-f1p-baseline-71cffa8d`
（HEAD 恰为父提交 `71cffa8d`，`git status` 干净）：

- 仓库 `AGENTS.md` 明确要求"每个额外工作树必须建在 `W2-workspaces/` 下"；
- 该工作树已在正确位置且正是所需提交，再建一个只会多一份冗余副本。

定位到的治理测试文件（未猜测）：

```text
tests/contract/test_src_w2_package_matrix.py
  test_matrix_covers_every_top_level_package_once
  test_matrix_rows_match_the_current_dependency_graph
  test_matrix_callers_entrypoints_and_classifications_are_complete
  test_runtime_entry_surfaces_are_included_in_the_analysis
  test_p2_05_is_done_and_eval_01b_is_current

治理数据文件
  docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
  （SRC_W2_PACKAGE_MATRIX_START / END 之间的表格）
```

## 4. A / B / C 三类集合

两侧运行完全相同的 5 个节点，均为 `2 failed, 3 passed`。

**A —— 基线已有失败（2）**

```text
tests/contract/test_src_w2_package_matrix.py::test_matrix_rows_match_the_current_dependency_graph
tests/contract/test_src_w2_package_matrix.py::test_matrix_callers_entrypoints_and_classifications_are_complete
```

**B —— F1P 新增失败：空集。**

**C —— 基线失败在 F1P 消失或变化：空集。**

`test_matrix_covers_every_top_level_package_once` 在**两侧都通过**：
F1P 没有在 `src/w2/` 下新建任何顶层包（`src/w2/quant_research` 两侧都不存在），
代码全部落在 `AGENTS.md` 允许的 quant 隔离路径 `scripts/quant/`。

## 5. 逐项核对执行令 §3 的五个问题

由于该测试的断言触发顺序随字典/集合遍历而变，本报告不依赖"先报哪条断言"，
而是直接用测试自身的 `_matrix()` / `_graph()` / `_external_callers()`
在两个提交上计算全部行的数值再逐行 diff。

### 5.1 domain direct_callers 的变化是否仅由 F1P 引用造成

**是，且只多一个文件。**

```text
computed domain.direct_callers
  基线 71cffa8d   apps:0;scripts:18;migrations:0;tests:43
  F1P  8208eb3f   apps:0;scripts:19;migrations:0;tests:43
新增的唯一 caller  scripts/quant/f1p_forward_factor_contract.py
```

该文件 import `w2.domain.canonical_serialization`——这正是 `AGENTS.md`、
`QUANT_AGENTS.md` 与 Freeze A0 Binding E2 **强制要求的复用**
（"必须复用现有序列化器，禁止第二套"）。所以这次引用是**合规行为本身**，
不是违规。

**但它并不构成新增失败**：矩阵里 `domain` 那一行写的是 `scripts:12`，
在基线就已经比真实值 18 少 6；F1P 只是把真实值推到 19，让同一行的偏差从 6 变成 7。
**这一行在 F1P 之前就已经在让该测试失败。**

### 5.2 / 5.3 reverse_callers 与 competitions 是否为基线已有过期记录

**是，且过期范围远不止这两处。** 在基线提交上，矩阵与现实不符的行共 **15 处、
涉及 14 个包**（`row` 为矩阵记录值，`computed` 为测试实算值）：

```text
api            direct_callers      row scripts:2   computed scripts:3
competitions   direct_callers      row tests:29    computed tests:30
domain         direct_callers      row scripts:12  computed scripts:18   tests:42 vs 43
infrastructure direct_callers      row scripts:20  computed scripts:23   tests:59 vs 63
ingestion      direct_callers      row tests:26    computed tests:27
matchday       direct_callers      row scripts:5   computed scripts:4    tests:15 vs 14
matchday       python_file_count   row 12          computed 10
models         direct_callers      row tests:8     computed tests:9
prematch       direct_callers      row scripts:8   computed scripts:12   tests:37 vs 39
pricing        direct_callers      row tests:3     computed tests:4
providers      reverse_callers     row 含 matchday  computed 不含 matchday
readiness      reverse_callers     row domain,matchday  computed domain
refresh        reverse_callers     row matchday    computed -
strategy       direct_callers      row tests:20    computed tests:25
tracking       direct_callers      row tests:21    computed tests:24
```

**F1P 之后，这 15 处里只有 `domain.direct_callers` 的 computed 值动了 1**，
其余 14 处一字未变。

### 5.4 F1P 是否违反"每个顶层包登记一次"

**没有。** `test_matrix_covers_every_top_level_package_once` 两侧均通过。
F1P 未在 `src/w2/` 下新增顶层包，`src/w2` 整棵树变更 0 字节。

### 5.5 scripts/quant 是否属于允许的 quant 隔离路径

**是。** `AGENTS.md` 与 `QUANT_AGENTS.md` 都写明新增 quant 代码只能落在
`src/w2/quant_research/` 或 `scripts/quant/`。F1P 选择后者，
正是为了不新增 `src/w2` 顶层包（这一点在 F0 阶段已有先例并被采纳）。

## 6. 为什么不修改治理矩阵

执行令 §4 要求五个条件同时成立才允许修改。**第 5 条不成立，第 1 条也不足以支撑**：

1. **最小登记无法让测试变绿。** 即使把 `domain` 那一行从 `scripts:12` 改成
   `scripts:19`，剩下 14 处过期记录仍会让同样两个节点继续失败。
   也就是说，这个测试并不是"因为 F1P 才红"的，修 F1P 那一行也关不掉它。
2. **归属属于另一条工作流。** 该文件是架构收敛工作线的总清单
   （`NEXT_ACTION.md` 将其列为"Historical operational task authority"），
   按既有约定其变更需 Owner 逐项验收。
3. **动它会越界。** 要让测试真正通过，必须一次性重算并改写 15 处记录，
   那是一次完整的架构收敛登记刷新，远超"F1P 治理差异核对"的范围，
   也会把一个未经该工作流验收的改动混进本任务。

因此：**不修改矩阵、不调整阈值、不删除记录、不放宽检查、不硬编码结果。**
也**未新增**针对 F1P caller 归属的矩阵断言——执行令允许在"满足条件时"新增，
条件不满足，新增断言只会把一个注定失败的行钉死在本任务里。

## 7. F1P 唯一 skip 的保留说明

```text
scripts/quant/tests/test_f1p_forward_factor_contract.py:255
SKIPPED: market is pinned to ASIAN_HANDICAP by the contract itself
```

`market` 被合同硬钉为 `ASIAN_HANDICAP`，任何其他取值在到达身份计算之前就已被
`MARKET_OUT_OF_CONTRACT` 拒绝，因此无法构造"仅 market 改变但仍合法"的身份变异用例。
这是合同设计的必然结果，不是覆盖缺口。该 skip 予以保留，理由写在测试内。

## 8. 验证结果

```text
F1P 定向          72 passed / 1 skipped
scripts/quant     294 passed / 1 skipped
matrix 5 节点     2 failed / 3 passed（两侧一致，见 §4）
全仓 pytest       10 failed / 3071 passed / 9 skipped
                  与干净生产基线 3ac86c14 的失败集合逐条相同
ruff check .      10 errors，与 3ac86c14 基线差集为空
compileall src scripts   exit 0
git diff --check  clean
两次 runner       4 个产物逐字节一致
```

## 9. 产物哈希前后对照

```text
                                              任务开始前   任务结束后
W2_AH_FACTOR_ACCURACY_F0_20260910               5/5 OK      5/5 OK
W2_AH_FACTOR_ACCURACY_F1_20260910               6/6 OK      6/6 OK
W2_AH_FACTOR_ACCURACY_F1P_20260910              6/6 OK      6/6 OK
W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909  13/13 OK  13/13 OK
```

两次 runner 重跑后 F1P 包仍与其**已提交的** `HASHES.sha256` 完全吻合，
工作树 `git status` 为空——即重跑没有改变任何冻结产物。

## 10. 边界

```text
PROVIDER_CALLS = 0            PRODUCTION_DB_READS = 0
PRODUCTION_DB_WRITES = 0      DEPLOYMENT_EXECUTED = false
未部署 / 未重启 VPS / 未 push / 未建 PR
未修改 src/w2/prematch、strategy、api、dashboard、Scheduler、
       Provider allowlist、migrations、生产配置
未删除 / skip / xfail / 弱化任何既有治理断言
```

## 11. 状态

```text
F1P = CONTRACT_TESTS_PASS_PENDING_PACKAGE_MATRIX_RECONCILIATION
F1R = NOT_STARTED
R1  = BLOCKED_BY_F1P
D1  = NOT_AUTHORIZED
W1  = NOT_STARTED
F2  = BLOCKED     F3 = BLOCKED     F4 = BLOCKED
```

矩阵收口需要架构收敛工作线单独授权：一次性重算并刷新那 15 处过期登记，
由该工作流验收。收口完成后，F1P 才可转 `F1P_ACCEPTED` 并考虑进入 F1R。
