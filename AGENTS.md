# W2 Repository Agent Instructions

在修改 W2 前，必须读取：

- `AI_PROJECT_CONTEXT.md`
- `PROJECT_STATE.yaml`
- `NEXT_ACTION.md`
- `docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`
- `docs/operations/W2_ASSET_UNIQUENESS_AUDIT_20260731.md`
- `docs/operations/W2_AUDIT_PERSPECTIVE_REGISTRY.md`
- GitHub Issue #454 v5 FINAL
- Issue #455
- Issue #456

#457 保持 OPEN，Agent 不得自行改变其状态或严重度。

## 本地同步前置

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' origin/main
```

预期可信 main：

```text
dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
```

main 漂移、workspace 不干净或来源不明时，停止代码编辑。

## 任务层级

```text
TOP_LEVEL_TASK = EVAL-02B
CURRENT_WORKSTREAM = EVAL-02B-T00
TASK_AUTHORITY = docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
ACTIVE_EXECUTION_AUTHORITY = Issue #454 v5
```

T00 是整改 workstream，不得替换顶层任务身份。

## 污染隔离

```text
PR #453 = QUARANTINED / DO NOT MERGE / DO NOT REPAIR IN PLACE
```

禁止 merge、rebase、cherry-pick 或复制：

- PR #453；
- `agent/eval-02b-c9-*`；
- `e875050f6bc0286aed389aadfce1e17b2063635a`；
- 其他 automation-authored remediation。

所有实现必须在可信 main 的本地 clean worktree 中正常 edit/commit/push，并以 Draft PR 提交。

## 不可协商规则

1. 缺失、非法、陈旧、未知或不可验证的安全输入必须拒绝。
2. Provider 可能收到请求后，后续失败必须持久化、冒泡、停止调用并禁止自动 retry。
3. 幂等必须证明预期约束与全部存储业务字段一致。
4. Required empty、吞异常、无锁、未执行都不是成功。
5. 同一业务事实只能有一个可版本化、可独立复算的计算权威；不同定义需显式版本化。
6. 历史 identity/hash 不得无迁移方案覆盖。
7. 不得删除、skip、xfail 或放宽 required event、五态 `1e-9`、package matrix、delta、lineage、migration、故障注入或历史守卫。
8. 禁止 workflow 向业务 PR 分支 push 或使用写权限自改实现。
9. 同源测试不等于独立 oracle。
10. 完成声明必须列明覆盖/未覆盖视角、implementer 和独立 reviewer。

## R5 canonical serialization

- 先 inventory，再在 SER-02 裁决 `ensure_ascii`；
- 强制 `allow_nan=False`；
- 合同明确 serializer version、UTF-8、Unicode、number/Decimal/date/datetime 和 unsupported type；
- 建立 `src/w2/domain/` 唯一版本化 authority；
- 不覆盖历史 hash；
- SER-05 oracle 由不同作者实现且不得 import 生产 serializer；
- CI 阻止第二个未授权 serializer/hash writer。

## PR #450 守卫

必须建立全部删除测试的守卫等价性矩阵，`UNCLASSIFIED_REMOVED_GUARDS = 0`。至少恢复 historical PR non-authority 和 retired staging-address absence guards。

## Canary 硬失败

```text
SERIALIZER_VERSION_MISSING
INDEPENDENT_PAIR_HASH_MISMATCH
INDEPENDENT_BOOTSTRAP_SEED_MISMATCH
NAN_OR_INFINITY
ANY_REQUIRED_DELTA_ZERO
LINEAGE_MISMATCH
```

全部必须终止 canary，不得 warning 或人工改判。

## 执行停止线

不得调用真实 Provider、创建真实 canary 授权、启动持续 scheduler、开放 Candidate/Formal/Lock/Production 或自动合并。

最终输出：

```text
REAL_PROVIDER_CALL_EXECUTED = false
REAL_CANARY_AUTHORIZATION_CREATED = false
AUTO_MERGE_EXECUTED = false
READY_FOR_INDEPENDENT_SECOND_REVIEW = true|false
```
