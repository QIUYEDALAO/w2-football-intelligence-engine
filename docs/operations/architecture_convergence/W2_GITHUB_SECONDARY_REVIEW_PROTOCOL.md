# W2 GitHub 二次验收强制协议

```text
Protocol ID: GITHUB_SECONDARY_REVIEW_PROTOCOL_V1
Status: ACTIVE
Applies to: 所有架构收敛 PR 的外部 GitHub 二次验收、整改复验和合并决定
Task/status authority: W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
Review-method authority: 本文件
```

## 一、强制首读

任何助手在开始 GitHub 二次验收前，必须先读取本文件；未读取时，验收状态只能是：

```text
REVIEW_NOT_STARTED
```

读取版本规则：

1. 存在待验收 PR 时，从该 PR 的 **exact head** 读取本文件；
2. 若该 PR 不包含本文件，则读取该 PR base 对应的最新版本；
3. 没有待验收 PR 时读取 `main`；
4. 不得只凭交接文字、Codex 回执、PR 描述或上一次会话记忆下结论。

读取本文件后，再按 `PROJECT_STATE.yaml.context_read_order` 读取总清单、机器状态和当前动作指针。

## 二、验收原则

二次验收是独立、闭环的全量复核，不是对 Codex 回执的逐句确认，也不是只检查上一轮指出的增量问题。

每次复验都必须从实际 PR head 重新执行完整矩阵。不得采用“发现一个问题、发一次指令、下一轮再发现一个”的碎片化方式。

### TASK_SCOPE_AND_REVIEW_BOUNDARY_V1

任务范围与验收边界遵守以下强制合同：

1. 架构收敛总清单决定当前任务范围与既定验收项目；
2. 不得把清单外的未来强化、通用框架或后续任务临时扩大为当前 PR 门禁；
3. 当前 diff 引入的回归，以及生产、安全、数据或权限边界变化，可以阻塞当前
   PR；
4. 超出当前任务范围的实现可以直接删除，不以已经写入代码为保留理由；
5. 总清单已经批准的验收、exact-head CI、staging 验收与安全门禁不得减少；
6. 实现、重复测试和重复回执可以精简，但验收程序不得精简。

```text
TASK_SCOPE_AUTHORITY = W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md
CURRENT_DIFF_REGRESSION_CAN_BLOCK = TRUE
SAFETY_BOUNDARY_CHANGE_CAN_BLOCK = TRUE
OUT_OF_SCOPE_IMPLEMENTATION_MAY_BE_REMOVED = TRUE
APPROVED_ACCEPTANCE_GATES_MAY_BE_REDUCED = FALSE
IMPLEMENTATION_MAY_BE_SIMPLIFIED = TRUE
ACCEPTANCE_PROCEDURE_MAY_BE_SIMPLIFIED = FALSE
```

## 三、强制闭环矩阵

### 1. 身份与范围

必须核对：

- PR 状态、Draft 状态、base、exact head、mergeability；
- changed files、完整 diff、提交列表；
- 本地/远端/PR/CI head 是否一致；
- CI 是否确实运行在当前 exact head；
- 是否出现越过本任务范围的生产代码、数据库、配置、fallback 或安全开关改动。

### 2. 实际输入闭环

必须从代码重新枚举被改逻辑的**全部真实输入**，不能只看测试名称或回执声明。

输入包括但不限于：

- Python、YAML、JSON、Shell、环境文件和模板；
- tracked、staged、unstaged、untracked、ignored 文件；
- 数据库、文件系统、环境变量、网络和 subprocess 输入；
- 动态 glob、递归扫描、默认路径和用户可传路径。

对于生成器、审计器和静态守卫，必须明确验证：

```text
ACTUAL_READ_SET = IDENTITY_GUARD_COVERAGE_SET
```

任何实际会被读取、但没有被版本身份或完整性守卫覆盖的输入，均为阻塞项。

### 3. 转换与内容完整性

必须核对：

- 版本 SHA 的语义和取得时点；
- hash 是在最终序列化内容上计算，还是在后处理之前计算；
- 路径 alias、字段删除、兼容输出和 manifest 是否改变最终 payload；
- 失败路径是否 fail-closed；
- 生成中 HEAD、输入或依赖发生变化时是否拒绝发布。

对于带自哈希的 JSON，必须抽查或自动验证：删除 `artifact_sha` 后重算，结果等于原值。

### 4. 输出和破坏性操作闭环

必须枚举所有：

- 文件创建、覆盖、移动、删除和目录替换；
- 数据库 DDL/DML；
- 用户可控输出目录；
- 临时目录、备份目录和失败恢复路径。

必须验证路径边界、所有权证明、原子替换和失败回滚。不得因“正常默认路径安全”而忽略自定义路径或异常路径。

### 5. 绕过与对抗性检查

按任务相关性检查：

- staged / unstaged / untracked / ignored；
- 已知文件名和未知新 stem；
- JSON、Markdown、YAML、Shell 等不同类型；
- `git add -f` 绕过 `.gitignore`；
- 路径穿越、仓库根、HOME、文件系统根和关键源码目录；
- symlink 或等价路径绕过；
- 旧输出、损坏 marker、损坏 manifest 和部分发布失败。

静态守卫必须独立于 `.gitignore` 生效。

### 6. 删除、保留和引用闭环

删除文件或代码时必须核对：

- 全仓库精确引用和语义引用；
- CI、Docker、Compose、systemd/cron、Shell、subprocess、测试和运维文档；
- 保留对象是否被误删；
- 被删对象是否以 archive、兼容别名或其他路径重新出现；
- 所有人工维护文档是否无断链。

### 7. 权威状态一致性

必须逐项比较：

```text
PR exact head
CI head
总清单中的 implementation/final head 与 CI
PROJECT_STATE.yaml 中的 head 与 CI
NEXT_ACTION.md 的当前任务
PR 描述中的回执
```

总清单、`PROJECT_STATE.yaml`、`NEXT_ACTION.md` 与 GitHub 真实状态不一致时，不得用 PR 描述覆盖，也不得合并。

### 8. Exact-head CI

必须核对当前 exact head 的：

```text
verify
staging-parity
predeploy-e2e
```

若代码提交通过 CI 后又增加最终回执提交，则最终回执 head 也必须重新跑完整 CI。不得只引用前一 implementation head 的 CI 作为最终 PR head 证据。

### 9. 任务门禁

必须核对：

- 当前任务未在合并前标成 `DONE`；
- 合并项未提前勾选；
- `next_task` 未提前推进；
- 后续任务未开始；
- 真实 canary、Provider、Formal、Lock、OFFICIAL、Production 等边界保持既定状态。

## 四、禁止碎片化验收

在向 Codex发送整改意见前，必须先完成第三节全部适用项，并把本轮可发现的问题合并成**一份完整审查意见**。

同一 PR 的后续复验必须：

1. 验证上一轮全部整改；
2. 从零重新执行完整闭环矩阵；
3. 不只检查上一轮列出的差异；
4. 一次性汇总所有当前阻塞；
5. 后续 Codex 指令采用增量格式，不重复无变化的历史红线。

若后来发现的问题在上一轮 exact diff 中已经可见，应视为验收漏项，并在继续下一轮前修订本协议或对应检查矩阵。

## 五、验收输出格式

每次二次验收必须明确返回：

```text
PROTOCOL_READ = GITHUB_SECONDARY_REVIEW_PROTOCOL_V1
PR_EXACT_HEAD_VERIFIED = PASS|FAIL
FULL_DIFF_REVIEWED = PASS|FAIL
ACTUAL_INPUT_SET_ENUMERATED = PASS|FAIL
INPUT_GUARD_COVERAGE = PASS|FAIL
OUTPUT_AND_ROLLBACK_REVIEWED = PASS|FAIL
CONTENT_INTEGRITY_REVIEWED = PASS|FAIL
BYPASS_CASES_REVIEWED = PASS|FAIL
DELETION_AND_REFERENCES_REVIEWED = PASS|FAIL
STATUS_DOCUMENTS_CONSISTENT = PASS|FAIL
EXACT_HEAD_CI = PASS|FAIL
TASK_GATES = PASS|FAIL
FINAL_DECISION = MERGE|REMEDIATION_REQUIRED
```

若失败，审查意见必须包含所有当前阻塞、具体文件/位置、目标结果和验收方法。

## 六、合并动作

全部适用项通过时：

1. 写入最终外部验收记录；
2. 将 Draft 转为 ready（如有需要）；
3. 直接合并；
4. 返回 merge SHA；
5. 再从 GitHub 验证 `main` 已指向该合并结果；
6. 然后才给出下一任务指令。

存在任何阻塞时：

1. 保持 Draft；
2. 不合并；
3. 留下一份合并后的完整增量整改意见；
4. 不把代码审核重新交给老板人工完成。
