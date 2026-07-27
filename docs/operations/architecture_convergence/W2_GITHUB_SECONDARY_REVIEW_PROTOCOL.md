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
其中 `{CURRENT_TASK}` 必须在读取时替换为 `PROJECT_STATE.yaml` 的当前任务；动态读取
`{CURRENT_TASK}.spec.json`、`{CURRENT_TASK}.baseline.json` 和
`{CURRENT_TASK}.final.json` 中实际存在的文件，不得永久写死某个历史任务路径。

## 二、验收原则

二次验收是独立、闭环的全量复核，不是对 Codex 回执的逐句确认，也不是只检查上一轮指出的增量问题。

每次复验都必须从实际 PR head 重新执行完整闭环审查矩阵。CI 则以 trusted PRE
按 PR kind 与 changed paths 计算的 required plan 为准，不得采用“发现一个问题、
发一次指令、下一轮再发现一个”的碎片化方式。

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

### 3A. 冻结验收矩阵生命周期

每个适用的后续架构任务使用三个独立 artifact：

```text
{TASK}.spec.json       = immutable spec
{TASK}.baseline.json   = baseline/preflight receipt
{TASK}.final.json      = closure add-only final attestation
```

强制规则：

1. matrix 是否适用、PREFLIGHT 目标和任务顺序只从 trusted base/main 读取。
   `W2_PR_KIND: PREFLIGHT` 只能面向 base 中第一个非 `DONE` 且仍为
   `NOT_STARTED` 的当前任务；禁止提前冻结未来任务，禁止借清单重排改变适用性。
2. Artifact 权限按 PR kind fail-closed：
   - PREFLIGHT 可新增/修改 spec 与 baseline，但不得写 final；
   - IMPLEMENTATION 禁止新增、修改 spec/baseline/final/evidence；
   - CLOSURE 是唯一可新增 final attestation 的 PR kind，且只能 add-only；不得修改
     spec、baseline、既有 final 或 evidence；
   - rename、delete 和 `previous_filename` 同样受上述约束。
   文件名 stem、artifact payload `task_id` 与 PR `W2_TASK_ID` 必须一致；evidence
   artifact 的 `task_id` 也必须与引用它的 spec/receipt 一致，禁止跨任务写入。
3. baseline `subject_head` 必须等于 `spec.frozen_baseline_commit`。artifact 的存储位置
   由当前 GitHub PR/base/main ref 推导，不写入 artifact，也不得形成 closure commit
   的自引用。`INITIAL_FREEZE`
   仅允许 spec 首次新增；修改既有 spec 必须单独走 PREFLIGHT，以 `REVIEW_MISS`
   或 `SCOPE_AMENDMENT` 记录原因，并让 `supersedes_spec_sha256` 等于 trusted base
   spec 的真实重算 SHA-256。
4. baseline readiness 与 final acceptance 严格分离。baseline 只验证开工前置：
   spec/inventory 完整、真实输入可取得、runtime/SQL baseline 已捕获、mutation
   source 已冻结、generator 可重放、scope/禁止项已冻结。checker 仅由这六项派生
   `implementation_open_status=OPEN|BLOCKED`；baseline 可以诚实保留当前 case、
   layer 或 applicable claim 的 `FAIL`/`UNVERIFIABLE`，这些 remediation 前状态不得
   被误用来阻止开工。六类 case、三层 evidence、claims 与 frozen assertions 的最终
   PASS 只来自 implementation FULL CI 的 detached result。
5. Implementation PRE 不读取或写入 final。它直接通过 GitHub API 验证当前 exact
   head 的 `FULL` CI、该 run 的 detached result/evidence ZIP，以及同一 exact head
   的外部 PASS Review。trusted PRE 必须下载 ZIP，限制文件数量、路径与总大小，拒绝
   symlink、path traversal、重复文件和非 canonical JSON；重算 GitHub ZIP digest、
   result/index 内部 self-hash、spec/baseline hash，并验证 frozen assertions、inputs、
   cases、layers、claims 和 evidence-index 逐项完整。只看 artifact 名称或 metadata
   digest 不得 PASS；实现测试结果不得通过自引用 commit SHA 存入 Git。
6. Closure add-only final attestation 的 `subject_head` 指向已验收并合并的
   implementation head，并绑定 implementation PR/merge SHA、Full CI run、外部
   Review hash、spec/baseline hash、artifact ZIP digest、canonical result/evidence
   content hash，并持久化已在线验证的 canonical detached result 与 evidence index；
   不得包含或要求 final 文件所在 closure commit SHA。
7. POST 对每个 matrix-governed `DONE` 任务重新验证 PASS final、记录的 accepted
   implementation head、Full CI、implementation PR 与 merge SHA；任一缺失、失配或
   closure 改动 artifact 都 fail-closed。Actions artifact 尚存在时必须交叉核对；
   artifact 正常过期或不可取得后，允许依赖 Closure 已验证并 add-only 持久化的
   canonical attestation；ZIP digest/content 不一致不得使用 durable fallback。
8. 内存 SQLite/手写 payload 是 `SYNTHETIC_CONTRACT_TEST`；ORM 文件只是
   `DECLARED_ORM_SCHEMA`。`REAL_DB` 必须来自只读 SQL/`pg_catalog` 和真实行形状
   fingerprint；`REAL_PRODUCER_OUTPUT` 必须来自真实保存 payload、真实 staging 行或
   content-addressed 脱敏 artifact。
9. PASS input 的 evidence type 必须与 primary evidence 一致并属于 spec 允许的真实
   类型。valid case 必须绑定 `UNCHANGED_REAL_INPUT`；missing/malformed/stale/
   ambiguous/conflict 必须绑定
   `CONTROLLED_MUTATION_OF_SANITIZED_REAL_INPUT`、真实脱敏输入和
   `MUTATION_TEST`。普通 static、ORM 或 synthetic 证据不得单独产生 PASS。
10. mutation case 必须绑定 source artifact hash、canonical mutation manifest/hash、
    operation、expected output 与 observed output fingerprint；对应 mutation test
    必须声明其消费的同一 source artifact 和 manifest，禁止拼接无关 real evidence。
11. REAL_DB、REAL_PRODUCER_OUTPUT 与 CONTENT_ADDRESSED_SANITIZED_ARTIFACT
   必须使用机器 schema，绑定 generator、replay argv 与 hash、query hash（适用时）、
   migration head、captured_at、source identity、行数/结果 fingerprint、
   provider/db delta 和 `subject_head`。replay 必须在该 subject commit 的独立
   worktree 中运行冻结 generator，写入明确临时 output path，并逐字节重验 canonical
   JSON、artifact hash、row count 与 result fingerprint；无输出、不同输出、非零退出
   或修改 tracked tree 都失败，不能使用当前 main 的同名 generator。
12. checker 必须完整执行 lifecycle JSON Schema、验证 frozen baseline commit，使用
    目标 commit 的 tree/blob（不依赖当前工作树存在该路径）重算文件与证据 hash，并以
    AST 作用域确认 fully-qualified symbol/test、symlink 与仓库边界。
13. artifact payload 只记录被测版本 `subject_head`；storage ref 永远由 trusted
    GitHub PR/base/main 上下文推导，不写入 payload。PREFLIGHT 可以在新 head 保存
    evidence，而其 `subject_head` 仍可指向更早的 frozen main；validator 先从 storage
    ref 读取 artifact，再到 subject worktree 验证 generator/query/code/input 来源。
14. immutable spec 必须为每个 frozen assertion、input、六类 case、三层 evidence
    和每个 applicable claim 冻结 measurement plan：measurement id、精确 argv/
    command hash、完整 pytest nodeid 或 checker symbol、预期 evidence artifact、
    output schema、implementation exact-head binding、generator/file hash、允许退出码
    与 fingerprint 规则。Implementation/Closure 不得修改该 plan。
15. detached producer 属于治理权威。普通 PREFLIGHT/IMPLEMENTATION/CLOSURE 不得
    修改 governance workflow、`ci.yml` detached 生成链、lifecycle schema、
    checker、`scripts/classify_ci.py` 或本协议；只允许独立
    `ARCH-GOVERNANCE-*` 任务修改。FULL verify 通过未跟踪的
    source 只交付实际 argv/hash、退出码、完整 nodeid 与 passed/failed/skipped 计数、
    stdout/stderr hash、evidence/mutation/fingerprint 绑定及 CI identity 的 raw
    receipts，禁止携带作者填写的最终状态。CI_REQUIRED 必须从 trusted base checkout
    运行受保护 compiler，逐条拒绝缺失、额外、重复、skip、替换或非本次命令生成的
    measurement，再由原始回执派生 result/evidence ZIP；普通任务必须直接从 trusted
    base checkout 执行 collector/compiler，并在 trusted base cwd、清空 `PYTHONPATH`
    后加载同一 checkout 的 `classify_ci`。PR 工作树同名 module/package 不得进入依赖
    闭包。`ARCH-GOVERNANCE-03` bootstrap 已随 PR #410 合并完成；此后所有 PR
    （包括该任务的 remediation 和 Closure）都必须执行 trusted base
    collector/classifier/compiler，不再允许 candidate runtime。Implementation 不能
    覆盖派生结果，tracked source、all-PASS source 或 PR 自定义 collector/compiler
    一律拒绝。
16. 修改 GitHub Actions workflow 的任务必须在实现前冻结 workflow event × CI plan
    验收矩阵，并以解析后的 workflow job/step `if`、`env`、`needs` 做机器测试，不得
    仅检查字符串。矩阵至少覆盖 `pull_request FULL`、`pull_request PATH_AWARE`、
    `pull_request LIGHTWEIGHT`、`push main` 与 `workflow_dispatch`；逐一验证每个
    `on` 事件、每种 CI plan、每个 `always()` job、事件专属 context 的可达性，以及
    所有必需 env/path 在每条可达路径均已初始化。

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

Implementation 最终 exact head 必须通过 trusted PRE 计算的 required plan，并核对
同一 exact head 的 `CI_REQUIRED` receipt：

```text
Python/runtime implementation = FULL_MATRIX
docs/status-only closure = LIGHTWEIGHT_CI_REQUIRED
migration/mixed/unknown/CI-control = FULL_MATRIX
```

不得用 lightweight receipt 冒充 full receipt，也不得用前一 implementation head 的
receipt 作为当前 PR head 证据。只有 exact head 变化才重新运行该新 head 对应的
required plan；PR body、comment、Review、Draft/Ready 等 metadata 变化只重触发
trusted PRE，不重跑代码 CI。

### 9. 任务门禁

必须核对：

- 当前任务未在合并前标成 `DONE`；
- 合并项未提前勾选；
- `next_task` 未提前推进；
- 后续任务未开始；
- 真实 canary、Provider、Formal、Lock、OFFICIAL、Production 等边界保持既定状态。

## 四、执行与验收节奏

1. 子步骤执行中只跑与当前改动直接相关的 focused tests，不重复跑完整 CI。
2. 单项任务的最终 exact head 必须一次性完成全部范围项、业务语义对账、静态守卫、
   临时/生成资产清理、资产账本和 trusted PRE 要求的同一 exact-head CI receipt。
3. 最终门禁固定要求：
   `SCOPE_ITEMS_COMPLETE=YES`、`BUSINESS_DELTA=0`、`UNTRACKED_FILES=0`、
   `UNREFERENCED_NEW_FILES=0`、`WORKTREE_CLEAN=YES`、
   `TRUSTED_PRE_REQUIRED_PLAN_RECEIPT=PASS`、`EXTERNAL_ACCEPTANCE=PASS`。
4. 外部验收后若 exact head 未变化，不重复跑 CI；exact head 变化则重新运行新 head
   对应的 required plan 并重新验收。
5. 数据库 drop、数据迁移、部署、兼容链物理删除、安全开关和模型数学变更仍按逐项
   高风险门禁执行，不得简化。

## 五、禁止碎片化验收

在向 Codex发送整改意见前，必须先完成第三节全部适用项，并把本轮可发现的问题合并成**一份完整审查意见**。

同一 PR 的后续复验必须：

1. 验证上一轮全部整改；
2. 从零重新执行完整闭环矩阵；
3. 不只检查上一轮列出的差异；
4. 一次性汇总所有当前阻塞；
5. 后续 Codex 指令采用增量格式，不重复无变化的历史红线。

若后来发现的问题在上一轮 exact diff 中已经可见，应视为验收漏项，并在继续下一轮前修订本协议或对应检查矩阵。

## 六、验收输出格式

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

## 七、合并动作

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
