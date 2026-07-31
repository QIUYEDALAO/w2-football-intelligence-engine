# W2 Next Action

当前顶层任务：

```text
EVAL-02B
```

当前工作流：

```text
EVAL-02B-T00
```

当前执行权威：

```text
GitHub Issue #454 v5 FINAL FROZEN BASELINE
```

历史任务规格与已合并回执权威：

```text
docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
```

## 立即执行

```text
1. GitHub → 本地可信同步
2. 建立 clean worktree
3. T00-GOV（#455）
4. T00-SAFE R1–R5 + 存储/计算资产 inventory
5. R5 canonical serialization SER-01…SER-07（#456）
6. 从可信 main 重建 C9
7. 剩余 Gate A
8. fake-Provider 离线 rehearsal
9. 上下文/证据同步
10. 独立二次验收
```

#457 保持 OPEN，状态不由本文件重定性。人工侧工作与只读 Git/T00 可以并行；真实运行开关继续关闭。

## GitHub 本地同步前置

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' origin/main
git for-each-ref --format='%(refname:short) %(objectname)' \
  'refs/remotes/origin/agent/eval-02b-c9-*'
```

预期：

```text
origin/main = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

若不一致，停止代码编辑并提交 drift/provenance 报告。

## 禁止来源

```text
PR #453
agent/eval-02b-c9-*
e875050f6bc0286aed389aadfce1e17b2063635a
任何 automation-authored remediation commit
```

## 当前禁止

```text
Provider call
真实 canary authorization
persistent scheduler
Candidate
Formal
Lock
Production
auto merge
```

## 必读

- [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)
- [`AI_PROJECT_CONTEXT.md`](AI_PROJECT_CONTEXT.md)
- [`docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`](docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md)
- [`docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`](docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md)
- [`docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`](docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md)
- Issue #454 v5
- Issue #455
- Issue #456
- Issue #457（保持现状）
