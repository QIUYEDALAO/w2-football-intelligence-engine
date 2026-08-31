# V1 统一准入合同与前向相对准确度登记能力

状态：`IMPLEMENTED_PENDING_ACCEPTANCE`（本地实现，未部署）

生产影响更正：此前“不会改变当前生产行为”的说法错误。旧合同为 `EV>0 + delta>=0.05 + EV-SE>0`；本实现改为 `EV>0 + cashflow_price_edge>=0.05 + EV-SE>0`。生产 530 条评价中旧合同候选 216 条，76 条仅被 delta 拦截，且 76/76 的 cashflow edge 均达 0.05，理论新增候选 76 条（约放宽 35.19%）。详见 `ADMISSION_CONTRACT_CORRECTION.md`。因此本变更不得在 AH 斜率修复前单独部署。

## 变更

- 统一经济准入合同为 `w2.economic_admission.cashflow.v1`：`EV > 0`、五态
  `cashflow_price_edge >= 0.05`、`EV - SE > 0`。`probability_delta` 仍持久化，
  但在正式 denominator opportunity 中仅作诊断。
- `analysis_evidence`、`market_candidate`、`lifecycle` 与
  `recommendation_decision_v4` 共用 `w2.domain.admission_contract`，消除 lifecycle
  与 market-candidate 的合同漂移。缺 edge 的正式 opportunity fail closed。
- `candidate-eval.v2` 是新的机会策略身份；旧 `candidate-eval.v1` 保留读取/测试兼容，
  不与新策略跨 identity 合并。
- 新增 `market_relative_accuracy_registry` 与空的 append-only ledger。登记键绑定
  model、calibration、market、evaluation policy、经济合同和评分合同；登记要求 AH/TOTALS
  各自至少 1,500 场，且两边 one-sided bootstrap 上置信界均不高于 0。当前无任何登记，
  因此前向门没有授予任何模型状态。

## 冻结协议

`docs/operations/V1_MARKET_RELATIVE_ACCURACY_FORWARD_ADMISSION_PREREGISTRATION_20260831.json`

SHA-256：`087e00084131b6d754261a7a2757b3095f96e9ddfffc875a221e7a2ac0608175`

协议明确排除已查看的 354 条后验 cohort，不允许从它选择阈值、参数或授权。

## 验证

```text
231 个相关准入/生命周期/候选/通知/registry 测试通过
2500 passed, 3 skipped（unit + API projection + evidence contract）
Provider 0；生产 DB 写入 0；未部署；未 migration；无 GitHub 操作
ledger 文件大小 0 bytes
```

独立复核：

```bash
PYTHONPATH=src .venv/bin/pytest -q \
  tests/unit/test_admission_contract.py \
  tests/unit/test_market_relative_accuracy_registry.py \
  tests/unit/test_dynamic_prematch_lifecycle.py \
  tests/unit/test_market_candidate.py \
  tests/unit/test_analysis_market_evidence.py \
  tests/unit/test_point_ev_calibration_identity.py \
  tests/unit/test_candidate_notification_outbox.py
```

此实现不等于部署、不等于 calibration 授权，也不等于 EV 已被前向验证；部署与任何
registry 登记必须另行验收。
