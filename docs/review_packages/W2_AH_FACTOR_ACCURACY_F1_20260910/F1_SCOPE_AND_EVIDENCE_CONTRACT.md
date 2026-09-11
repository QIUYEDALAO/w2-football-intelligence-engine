# F1 范围与证据合同 —— AH 四因子历史重建可行性调查

```text
主线            AH-FACTOR-ACCURACY-V1
当前阶段        F1（历史重建可行性调查）
TASK_ID         W2_AH_FACTOR_ACCURACY_F1_READINESS_20260910
PARENT_COMMIT   f5dd9c23cf90cd836139bacbde559421f6dd59a2
执行方 Claude Code；验收方 Codex；Obsidian 由 Codex 维护，本任务不写
```

## 1. 本任务是什么

**历史重建可行性调查**，不是调权任务，不是模型实现任务。唯一要回答的是：
冻结 148 条中的 AH 84 条，其 F3/F5/F6/F9 赛前因子值是否存在可证明的、独立的、
严格 PIT 的重建来源。

不能形成完整矩阵就诚实收口，**不得为了推进 F2 而填补缺失值**。

## 2. 输入身份

```text
OFFICIAL_148_SOURCE_BUNDLE.jsonl
  sha256 = da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4  [运行前后一致]
OFFICIAL_148_MANIFEST.jsonl                                                  [同包，hash 覆盖]
F0 交付包 W2_AH_FACTOR_ACCURACY_F0_20260910                                  [5/5 OK]
```

## 3. 矩阵合同

`AH_84_FACTOR_MATRIX_F1.jsonl`：84 条 AH × 4 因子 = **336 行**，
每行一个 `(evaluation_id, factor_id)`，键唯一（有测试锁定）。

一行要被判为 `EXACT_PIT_RECONSTRUCTIBLE`，必须**同时**具备六项：

```text
signed_score、factor_status、original_weight、participated、
evidence_time_utc、source_sha256
```

并满足 PIT 规则：

```text
evidence_time_utc < evaluated_at        必须严格早于，相等也不通过
```

任一项缺失即不得标 exact。

### 三个状态的判定口径

```text
EXACT_PIT_RECONSTRUCTIBLE   六项齐全 + 严格早于 + 可绑定到该 evaluation
SOURCE_ONLY_POST_CAPTURE    存在按本 evaluation 键控的来源，但其读取时点在
                            evaluated_at 之后（本轮 264 行属此）
NOT_RECONSTRUCTIBLE         无来源，或来源虽早于 evaluated_at 却是另一个观测时刻、
                            无逐因子证据时点、且无法绑定到该 evaluation
```

**判定优先级已明确写入代码**：按本 evaluation 键控的来源（provenance 更强）
优先决定状态，即使它是 post-capture；未绑定的更早快照不能因为"时间更早"
而被提升为更好的状态。

### 快照列与历史列严格分开

对存在赛前卡归档的 9 场，快照值放在**独立命名**的列里：

```text
snapshot_only_signed_score / snapshot_only_weight / snapshot_only_status /
snapshot_only_participated / snapshot_capture_utc / snapshot_gap_hours
```

`snapshot_only_` 前缀是刻意的：这些是**另一个时刻**的观测值，不是
`evaluated_at` 当时的值。历史列 `signed_score` / `original_weight` 一律保持
`NOT_RECONSTRUCTIBLE`，有测试断言快照值永远不会写进历史列。

## 4. 禁止填充

不得用以下任何一项填充历史值：

```text
当前权重、当前注册表、结果时间、赛果、当前分析卡、事后滚动网页、人工推断
```

代码层面的保证（均有测试）：

- `matrix_rows()` 的函数体内不出现 `settlement` / `profit_units` / `"score"` / `GRADE`；
- **翻转全部 84 条 AH 的结算、盈亏与比分后重跑，336 行的六个历史字段、
  row_status、provenance、not_estimable_reason 与全部快照列逐条不变**；
- `original_weight` 恒为 `NOT_RECONSTRUCTIBLE`，且断言不等于当前任何权重值。

## 5. 边界

```text
REAL_PROVIDER_CALLS = 0      PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0      PRODUCTION_DB_WRITES = 0
DEPLOYMENT_EXECUTED = false  OBSIDIAN_WRITES = 0
F2_AUTHORIZED = false        F3_AUTHORIZED = false
```

未抓捷报、未访问 API-Football、未访问 VPS、未读生产库、未新建 worktree、
未 rebase/reset、未删除 F0 产物、未 push、未建 PR、未部署。

代码只落在 `scripts/quant/`；`src/w2/prematch`、`src/w2/strategy`、`src/w2/api`、
`src/w2/dashboard`、`migrations` 变更 0 字节。

本地 SQLite 以 `mode=ro` 只读探查，读取前后 SHA-256 均已记录且未变。
