# F1R-A0 测试与自检结果

```text
F1R-A0 定向  scripts/quant/tests/test_f1r_a0_offline_factor_recorder.py   47 passed
quant 全集   scripts/quant/tests                              341 passed / 1 skipped
package matrix                                                5 passed
arch P2-05                                                    6 passed
全仓 pytest                          8 failed / 3073 passed / 9 skipped
  相对 d8c8bf82 基线：新增失败 0，消失失败 0，测试 ID 逐条相同
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
