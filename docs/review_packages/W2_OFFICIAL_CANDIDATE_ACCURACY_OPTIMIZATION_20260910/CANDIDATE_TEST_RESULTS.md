# 任务 2 测试与自检结果

```text
scripts/quant/tests（全部）                              163 passed
  test_confidence_shrinkage_candidate.py（本轮新增）      51 passed
  既有 112 条全部保留，未删除 / 未 skip / 未 xfail / 未弱化
全量 tests/（本工作树）              10 failed / 3071 passed / 9 skipped
全量 tests/（干净基线 3ac86c14）     10 failed / 3071 passed / 9 skipped
新增失败 0，消失的失败 0，测试 ID 逐条相同
Ruff（新增文件）                                        All checks passed
Ruff（全仓）与基线差集                                   空
compileall                                              exit 0
git diff --check                                        clean
两次完整运行 byte-identical                              3 个产物 hash 一致
输入包 shasum -c                                        13 / 13 OK（运行前后各一次）
```

## 十八项最低测试的对应关系

```text
 1 148 条 incumbent 精确复现        test_01_*  —— 三个分段的 log loss / Brier /
                                    calibration error / predicted graded rate
                                    与证据包 INCUMBENT 逐字段相等；
                                    并复核 148 行 / 111 fixture / -20.375u
 2 只使用历史已结算记录             test_02_*  —— 148 条逐条重算训练集合并核对
                                    training_rows；未来、同一瞬间、自身结果全部排除
 3 时间统一为 UTC                   test_03_*  —— 空格 / T / Z / +00:00 /
                                    +09:00 / -05:00 / naive 六种写法归一到同一瞬间；
                                    并锁定「文本比较会判反」的那对时间戳
 4 不可解析时间 fail closed         test_04_*  —— None / 空串 / 空白 / 垃圾串 /
                                    非法日期，两侧各一遍
 5 训练 < 20 条时 T=1               test_05_*  —— 0 / 1 / 19 条为 1.00；
                                    第 20 条起搜索确实会动；
                                    校准良好的训练集仍停在 1.00（搜索不偏向放大）
 6 网格只允许 1.00–2.00             test_06_*  —— 端点、101 个值、步长 0.01 全等；
                                    148 条拟合值全部落在网格内；上界 0 命中
 7 同分 tie-break 稳定              test_07_*  —— 均匀分布下全网格同分 → 取 1.00；
                                    训练集正反序拟合结果相同
 8 五态概率通过 1e-9                test_08_*  —— 整条网格 × 3 个分布；
                                    不满足的分布必须抛错；148 条校准后分布逐条核对；
                                    并逐态核对变换公式本身
 9 canonical Decimal EV 一致        test_09_*  —— 与权威独立重算逐位相等；
                                    AST 断言不存在第二个 EV / settlement 实现
10 direction/line/odds/factor 不变  test_10_*  —— 148 条 × 12 字段逐条全等；
                                    并断言 T>=1 使峰值不可能上升
11 缺 cashflow edge 必须 NOT_ESTIMABLE  test_11_*  —— 133 条逐条；
                                    推荐层计入 not_estimable 而非计入分母；
                                    源码断言未从盘口反推
12 LAST_10 不参与参数选择           test_12_*  —— 把近 10 条结算全部翻转后重跑，
                                    前 138 条温度逐条不变；且无记录用自身结果训练
13 两次完整运行 byte-identical      test_13_*  —— 进程内正反序一致、bootstrap 可重复；
                                    命令行两次完整运行 hash 一致
14 source bundle 不变               test_14_*  —— bundle sha256 == da9edb11…；
                                    运行后整包 shasum -c 仍 13/13 OK
15 不产生 Provider 调用             test_15_*  —— AST 断言三个源文件不导入
                                    requests/httpx/urllib/socket/aiohttp/
                                    w2.providers/w2.ingestion
16 不写生产数据库                   test_16_*  —— AST 断言不导入 sqlalchemy/psycopg/
                                    alembic；源码不含 insert/update/delete/session.add
17 不修改 src/w2/prematch           test_17_*  —— 双向：本任务代码不导入
                                    w2.prematch/strategy/api/dashboard/scheduler/
                                    operations；且 src/w2 下无任何文件引用本候选，
                                    src/w2/quant_research 不存在（整棵树未改）
18 不修改 Obsidian                  test_18_*  —— 源码不含 Obsidian / /Users/ /
                                    W2文档 / Desktop 任何字样
```

## 一处放错的目录，已改正

候选最初放在执行令允许的 `src/w2/quant_research/`。这会让
`tests/contract/test_src_w2_package_matrix.py::test_matrix_covers_every_top_level_package_once`
失败——`src/w2` 下每个顶层包都必须登记在架构收敛工作线的总清单
（`W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`）里。

我**没有**去改那份清单：它属于另一条工作线，按既有约定要 Owner 逐项验收。
改为放到同样被允许的 `scripts/quant/`，该测试恢复通过，且隔离性更强——
`src/w2` 整棵树本任务一个字节未改，生产侧连可 import 的模块路径都不存在。
移动前后三个产物 hash 逐字节相同，数值不受影响。

## 一处我写错的测试，已修正

`test_05_at_the_floor_the_search_actually_runs` 最初用 `WIN 0.5 / LOSS 0.45` 的
训练集，断言第 20 条起 `T > 1.00`，结果失败。**失败的是我的断言，不是代码**：
那个训练集在全部结算为 LOSS 时，升温会把 `p(LOSS)=0.45` 往 0.2 推，log loss 上升，
所以 `T=1.00` 才是正确答案。已改用真正过度自信且判错的训练集
（`WIN 0.90 / LOSS 0.08`，全部结算 LOSS），并**另加一条**反向测试：
校准良好的训练集必须仍停在 1.00，确保搜索没有被写成单向放大。

## 既有失败与基线一致

全量 10 条既有失败与干净基线 `3ac86c14` 逐条相同，未修复其中任何一条
（整改令历来禁止修复已知既有失败）。本任务未触碰 `src/w2/prematch/`，
也未触碰上一轮已验收的四轨脚本与结算产物。
