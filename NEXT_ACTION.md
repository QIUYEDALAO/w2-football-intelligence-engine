# NEXT ACTION

当前唯一工作：

```text
W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
```

当前仍不是建设 Signal Ledger、Portfolio、Risk、Kelly 或 Dashboard。先用冻结的 V 赛季验证模型与 PRE 经济代理；只有 V gate 通过，才在同一任务中继续完成 D+V 最终重拟合并冻结 H 预测/选择，随后停在 H 赛果解封前。

## Current authority

- `CURRENT_CONTEXT.md`
- `CURRENT_STATE.yaml`
- `CURRENT_TASK_CHECKLIST.md`
- `AI_QUANT_PROJECT_CONTEXT.md`

这些文件位于 `context/current`，直接覆盖更新，不创建上下文 PR、CI、RC、镜像或部署。

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
CURRENT_STATUS = R1_R2_FREEZE_REPORTED_PREUNLOCK_RECHECK_REQUIRED

V_RESULT_ACCESS = AUTHORIZED_ONCE_ONLY_AFTER_PREUNLOCK_RECHECK_PASS
H_RESULT_ACCESS = CLOSED
```

## R1/R2 frozen artifacts

```text
V_CANDIDATE_PREDICTION_MANIFEST_SHA256 =
591314c9f13fc3256ca51aef6c65953150f40912e776ff8d6347b1701d24033f

V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 =
e582585aaa57ac5cac894a2fad071dfadfa6ad7890b84ba4c8b3d74e4bd3fe13
```

Reported receipt:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r1_v_manifest_20260807/artifacts/R1_R2_FREEZE_RECEIPT.json
```

## Required execution

### A. Pre-unlock verification

Before reading any V result:

1. Recompute both V manifest SHA-256 values.
2. Validate the full R1/R2 receipt and every referenced model/source manifest.
3. Confirm deterministic rerun identity.
4. Confirm V/H result access was zero during manifest generation.
5. Confirm M4 PRE had zero visible CLOSE fields.
6. Confirm all four L2 candidates exist for PRE/CLOSE and OU/AH.
7. Confirm no Pinnacle fallback, Provider call, production write or tracked source change.

Any mismatch:

```text
FINAL_RESULT = BLOCKED_R1_R2_FREEZE_RECHECK
V_RESULT_ACCESS = CLOSED
H_RESULT_ACCESS = CLOSED
```

Stop immediately.

### B. One-time V evaluation

Only after A passes:

- unlock V results once;
- keep H results closed;
- evaluate all frozen L2 candidates only;
- calculate paired Log Loss, Brier, calibration and predictive lift for OU 2.5 and AH half-goal lines;
- settle only the already frozen OU 2.5 PRE selections at original PRE line and PRE price;
- select the final L2 value from `0.01, 0.1, 1.0, 10.0` using V only;
- do not add features, candidates, markets, thresholds or devig methods.

### C. Conditional branch

If the frozen V continuation gate fails:

```text
H_RESULT_ACCESS = PERMANENTLY_CLOSED
FINAL_VERDICT = NO_EDGE | INSUFFICIENT_EVIDENCE
```

Stop. Do not open H.

If the V gate passes:

1. Refit fixed final M2/M4 PRE/M4 CLOSE models on D+V.
2. Freeze final model/training/feature/parameter hashes.
3. Generate all H predictions without H outcomes.
4. Generate frozen OU 2.5 H PRE selections without H outcomes.
5. Compute H selected-order count and design-side economic MDE without results.
6. Freeze:
   - `H_PREDICTION_MANIFEST_SHA256`
   - `H_SELECTION_MANIFEST_SHA256`
7. Stop before reading H results.

## Stop line

```text
H_RESULT_COLUMNS_READ = false
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PROVIDER_CALLS = 0
PRODUCTION_DB_WRITES = 0
PR_CREATED = false
CI_RUN = false
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
