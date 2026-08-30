# 5af584db B1-FIX 补充验收

```text
Task: V1-SLOPE-RECALIBRATION-PREREG-01 / Step 0
Implementation commit: 5af584dbe842ed7dca90944c3306576f230e0abc
Deployed baseline: 7024cb18f2856a98fd1569c1f87b79dfd2b633cb
Status: LOCAL_IMPLEMENTED_PENDING_DEPLOYMENT
Deployment performed: NO
Provider calls: 0
Production reads: 0
Production writes: 0
```

## 1. 精确血缘与范围

`5af584db` 是 `7024cb18` 的后代；本报告只审计以下精确区间，不把后续 A1/A2/A3
证据提交或 `816bb241` 市场形状审计混入实现 diff：

```bash
git merge-base --is-ancestor \
  7024cb18f2856a98fd1569c1f87b79dfd2b633cb \
  5af584dbe842ed7dca90944c3306576f230e0abc && echo ANCESTRY_OK

git diff --name-status \
  7024cb18f2856a98fd1569c1f87b79dfd2b633cb \
  5af584dbe842ed7dca90944c3306576f230e0abc
```

该精确提交只改 6 个文件：4 个生产源码文件、1 个测试文件、1 个治理清单文件。

## 2. 与已部署 release 的逐文件 diff

| 文件 | + / - | patch SHA-256 | 变更语义 |
|---|---:|---|---|
| `src/w2/prematch/analysis_calculator.py` | 3 / 0 | `fef5b78ae94371ed2c53fd9a97cf29c26a49bcc4dcb9a39d6296d1707cb8c63e` | mapping 转 `SimulationOutput` 时透传 `calibration_identity` |
| `src/w2/prematch/lifecycle.py` | 26 / 0 | `811b3d0a749ed341997d0982ea5a8ad759fecb663d5b5581a025f8d20c5a7d28` | payload 追加 identity 与完整 1X2，校验三侧有限、非负且和为 1；字段不进入 `identity_payload` |
| `src/w2/prematch/read_model_projection.py` | 26 / 0 | `71ac6a0686b5f8136596b680861440ef0bfb62e9874ff0abaf5f15957c628885` | 从完整 `score_matrix_summary` 取 home/draw/away 并写入动态评价输入 |
| `src/w2/strategy/simulate.py` | 8 / 1 | `96783558cab25675261e3a388b0d3a29a257006a34428b65edb42b9cd775d366` | 按当前 `CALIBRATION_VERSION` 与完整 `LambdaCalibrationParams` 计算 calibration identity |
| `tests/unit/test_point_ev_calibration_identity.py` | 56 / 0 | `fd110ff2576308212cfde0ce9911060a677f8663ab570433e65b8bb8c229cb8a` | 证明追加字段写入且前后 evaluation identity 相同 |
| `docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md` | 54 / 0 | `6d6e7c5b05fbd23a6f2f21b0ffcea7f2194823a87a62fbc12398d39a94bdf2f6` | 记录本地实现状态与治理边界 |

任一 patch 可独立重算：

```bash
git diff --no-ext-diff --binary \
  7024cb18f2856a98fd1569c1f87b79dfd2b633cb \
  5af584dbe842ed7dca90944c3306576f230e0abc -- \
  src/w2/prematch/lifecycle.py | shasum -a 256
```

将末尾路径替换为表中其他文件即可逐文件复核。

## 3. Frozen evaluation identity 兼容性

新增字段仅在 `identity_hash = _hash(identity_payload)` 计算完成后写入
`DynamicEvaluationVersion`；`identity_payload` 的字段集合未新增
`calibration_identity` 或 `one_x_two_probabilities`。

测试分别覆盖：

1. 直接 `classify_evaluation()`：基线输入与追加字段输入的 `identity_hash` 完全相同；
2. 真实 `_dynamic_evaluations()` 投影：同一 card 的 baseline/enriched 输出 identity 列表完全相同。

独立验证命令：

```bash
PYTHONPATH=src:. ../w2-allsv-production/.venv/bin/python -m pytest -q \
  tests/unit/test_point_ev_calibration_identity.py \
  -k 'forward_evidence_fields_are_persisted_without_changing_identity_hash or read_model_projection_appends_forward_fields_without_rekeying'
```

期望输出：

```text
2 passed, 35 deselected
```

## 4. Payload 实际写入证明

同一条独立命令同时直接断言 `DynamicEvaluationVersion.as_dict()` 中存在：

```json
{
  "calibration_identity": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "one_x_two_probabilities": {
    "home": 0.46,
    "draw": 0.24,
    "away": 0.30
  }
}
```

它不是只检查 dataclass 声明；测试从 `read_model_projection._dynamic_evaluations()` 运行到
最终 payload，并同时比较追加前后的 identity。

## 5. 部署结论

`5af584db` 仍是 **LOCAL_IMPLEMENTED_PENDING_DEPLOYMENT**：

- 没有部署到 release `7024cb18`；
- 生产现有动态评价记录没有因此获得新字段；
- 未迁移、未写生产、未调用 Provider；
- 本验收通过只解除“材料缺失”，不构成部署授权。
