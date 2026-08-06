# W2 Football Quant — Phase 0.5 Master Checklist

Current authority is the mutable `context/current` branch. Context changes do not use PR, CI or release workflows. This checklist governs the local read-only research execution only; it does not authorize production changes.

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
EXECUTION = AUTHORIZED_STAGEWISE
ACTIVE_TASK = Q05-R1
```

## Permanent boundaries

- no production code, model, DB, Scheduler, Provider allowlist or Dashboard changes;
- no Provider calls, image builds or deployment;
- no Signal Ledger, strategy productization, Portfolio, Risk, Kelly or real-money execution;
- Pinnacle-only confirmatory odds; no Bet365/Average fallback;
- V/H outcomes remain closed until the corresponding prediction and selection manifests are frozen;
- current `ev_se` is scenario dispersion, not a statistical standard error.

## Task sequence

### Q05-00 — Context reset

```text
STATUS = DONE
```

Current direction changed from Sporttery-specific infrastructure to W2 AH/OU edge-existence testing.

### Q05-01 — Outcome-blind inventory

```text
STATUS = DONE_REPORTED
FREEZE_0A = PASS
```

Authority:

```text
MMZ = 20 divisions × 7 seasons = 140 units
D = 2019/20–2021/22
V = 2022/23–2023/24
H = 2024/25–2025/26
```

### Q05-02 — Binding recheck

```text
STATUS = REQUIRED_AT_EXECUTION_START
```

Recompute B1–B5. Any mismatch stops before results are read.

### Q05-R1 — D training

```text
STATUS = NEXT
```

- unlock D results only;
- fit M2 pure-goals Dixon-Coles for 20 divisions;
- search 41 train-only rho values per division;
- fit M4 PRE and M4 CLOSE independently for L2 `0.01,0.1,1.0,10.0`;
- record training populations and all hashes;
- V/H remain closed.

### Q05-R2 — Freeze V candidate manifests

```text
STATUS = BLOCKED_R1
```

- generate every pre-registered V candidate prediction;
- generate OU 2.5 PRE selection candidates using the fixed 3% predicted-EV gate;
- freeze both V manifest hashes;
- stop before V outcome access.

### Q05-R2B — V one-time evaluation

```text
STATUS = BLOCKED_V_MANIFESTS
```

- unlock V once;
- evaluate predictive and PRE-economic candidate results;
- choose L2 only from the frozen grid;
- apply V continuation gate;
- V failure permanently closes H.

### Q05-R3 — Final D+V refit

```text
STATUS = BLOCKED_V_PASS
```

- refit fixed M2/M4 models on D+V;
- freeze final model, parameters, features and population hashes;
- H remains closed.

### Q05-R4 — Freeze H manifests

```text
STATUS = BLOCKED_R3
```

- static D+V model across both H seasons;
- generate H predictions and frozen PRE selections;
- freeze H prediction/selection hashes;
- compute selected-order count and design-side achieved MDE without outcomes;
- stop before H outcome access.

### Q05-R5 — H one-time audit

```text
STATUS = BLOCKED_H_MANIFESTS
```

- unlock H once;
- run paired predictive tests, two-stage bootstrap and Holm;
- settle frozen OU 2.5 PRE selections at fixed one-unit stake;
- report concentration, coverage and exclusion bias;
- forbid all H refit, selection, threshold, scope or devig changes.

### Q05-R6 — Final verdict

```text
STATUS = BLOCKED_R5
```

Allowed outcomes:

```text
INSUFFICIENT_EVIDENCE
NO_EDGE
PREDICTIVE_INCREMENT_ONLY
ECONOMIC_EDGE_CANDIDATE
```

Consequences:

- insufficient: no conclusion, optional new evidence protocol;
- no edge: stop quant-platform build;
- predictive only: minimal forward Signal Ledger/Shadow design only;
- economic candidate: authorize full W2 Football Quant Platform design, still no real money.

## Current stop point

```text
NEXT = Q05-R1
REQUIRED_STOP = V_CANDIDATE_PREDICTION_AND_SELECTION_MANIFESTS_FROZEN
V_RESULTS_READ = false
H_RESULTS_READ = false
```

Detailed substeps and acceptance criteria are in [`CURRENT_TASK_CHECKLIST.md`](../../CURRENT_TASK_CHECKLIST.md).
