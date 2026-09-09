# 测试与自检结果

```text
定向测试 scripts/quant/tests/test_factor_gate.py          10 passed
既有回归 -k "lifecycle or dynamic or prematch_read or projection"
                                                          263 passed / 1 failed
Ruff（lifecycle / read_model_projection / scripts/quant）  All checks passed
py_compile                                                exit 0
四轨确定性双跑 CALIBRATION_COMPARISON.json                9acf6a68…2ccc 两次一致
```

## 唯一失败项：已验证为既有失败

```text
tests/contract/test_api_projection_read_authority.py::test_missing_projection_is_explicit_system_degraded_not_empty
```

在**未修改、干净**的基线工作树 `w2-settlement-fix-20260909`（HEAD = `3ac86c14`，dirty=0）
上复跑同一条测试，同样失败于同一处 `KeyError`（`test_api_projection_read_authority.py:546`）。
故与本次改动无关。**未删除、未 skip、未 xfail、未弱化任何既有测试。**

## 覆盖的测试矩阵项

```text
1  AH factor unavailable + 经济通过 → 阻断        PASS
2  AH factor admission failed + 经济通过 → 阻断   PASS
3  AH factor/EV conflict + 经济通过 → 阻断        PASS
4  AH factor/EV 一致 + 经济通过 → 候选            PASS
5  TOTALS 行为不变                                PASS
9  被阻断 AH 仍在正式漏斗分母                     PASS
10 历史 payload 向后兼容且显式非通过              PASS
12 148 条精确复现 -20.375u                        PASS（独立复算器）
13 近 10 条精确复现 -3.98u                        PASS
19 两次完整运行 byte-identical                    PASS
```

未覆盖：6（不进正式推荐）、7（不发通知）、8（不新增盈亏记录）、11（identity 含因子裁决身份）、
14（事故重放 -0.88u）、15–18、20 —— 见 REPORT.md §6。
