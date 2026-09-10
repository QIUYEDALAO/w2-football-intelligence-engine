# Obsidian 更新建议（给 Codex）

**这是建议，不是更新证明。** 本轮 Claude Code 对 Vault 只有读取权限，
`OBSIDIAN_ACCESS_MODE = READ_ONLY`、`OBSIDIAN_WRITES = 0`。
以下内容未写入任何 Vault 文件，请由 Codex 核对后自行决定是否落笔。

## 0. 需要先更正的一处记录

上一轮（架构矩阵收口）的回执里我写了 `OBSIDIAN_WRITES = 5`。

**那不是"计划核对的五个页面"，那是五次真实写入。** 当时的执行令 §9 明确授权
"只有验证完成后更新以下 W2 Vault 页面"，我据此修改了五个文件，且内容至今仍在：

```text
当前状态.md                       首行 = "## 当前状态（2026-09-10 深夜）：F1P 已 ACCEPTED，架构矩阵已收口"
重要决定.md                       首行 = "## 当前决定（2026-09-10 深夜）：接受 F1P，架构矩阵按图谱收口"
评分系统任务清单.md               含 commit d8c8bf82…
System/working-memory/tasks.md    含 commit d8c8bf82…，F1P 已勾选
2026-09-10.md                     含 commit d8c8bf82…
mtime                             2026-09-10 15:47–15:48
```

所以"上一轮实际 OBSIDIAN_WRITES = 0"与 Vault 现状不符。
把它改写成 0 会让记录与磁盘状态对不上。建议按实际记为 **5（已授权）**。

本轮的 `OBSIDIAN_WRITES = 0` 则是真实的：本轮只读。

## 1. 建议追加到 `当前状态.md` 顶部

```markdown
## 当前状态（2026-09-10 深夜 2）：F1R-A0 离线记录器已实装，待 R1 验收

- `F1R-A0 = OFFLINE_FACTOR_RECORDER_READY_FOR_R1`，commit=`<TASK_COMMIT>`，父=`d8c8bf82`。
- 关键结论：**逐因子证据时点确实拿得到**。`FeatureContribution.observed_at` 在
  F3/F5/F6/F9 的 ready 分支全部设置且经 UTC 校验；F1 拿不到是因为序列化时被丢弃，
  不是因为它不存在。差别在记录时机，不在严格程度。
- `applied_weight` 取 `FeatureContribution.weight`，即 `team_score.py` 累加进
  `weight_sum_used` 的真实生效值，不是注册表默认值（注册表无数值权重）。
- **`factor_version` 目前无来源**：四个 builder 都不产出版本号，记录器要求调用方提供、
  缺失即拒整批，不自造。真正的版本来源属于 F1R-B。
- 缺数据因子仍形成明确观测（INSUFFICIENT_DATA / SOURCE_UNAVAILABLE），不带分、
  不算中性；其证据时点用 `FeatureContext.as_of` 并标注 `SOURCE_QUERIED_AT_AS_OF`，
  与真实观测语义严格分开，参与的因子缺 `observed_at` 直接拒绝。
- 批次原子：四条先全验再一次写入，任一失败磁盘 0 新行。
- 验收数据：F1R 定向 47 passed、quant 全集 341 passed/1 skipped、matrix 5/5、
  全仓 8 failed/3073 passed（相对 `d8c8bf82` 新增失败 0）、两次 runner 逐字节一致、
  F0 5/5、F1 6/6、F1P 7/7、输入包 13/13。
- 夹具为 `SYNTHETIC_CONTRACT_FIXTURE`，不是真实比赛证据，**不代表生产链已接线**。
- 边界：Provider=0、生产库读写=0、未部署、未 push、Obsidian 本轮只读。
- 状态链：`F1R-A0` 待 R1；`F1R-B/生产接线`未开始；`W1/F2/F3/F4` 保持阻塞。
```

## 2. 建议追加到 `重要决定.md` 顶部

```markdown
## 当前决定（2026-09-10 深夜 2）：接受 F1R-A0 为离线实装，不视为接线完成

- 接受 F1R-A0 为**离线记录器实装**：批次契约、PIT、身份、append-only 与
  AS-OF 隔离均已自证。**不接受**为"生产已记录"或"数据已采集"。
- 确认 F1P 合同未被降级：语义标签走既有 `factor_inputs` 自由映射，未新增合同字段，
  F1P 包哈希 7/7 未变。
- 记录一个待办依赖：`factor_version` 当前无生产来源，F1R-B 必须先解决它，
  否则真实接线时每一批都会被记录器拒绝。这是刻意的 fail-closed，不是缺陷。
- 不因 A0 就绪而解锁下游：R1 验收前不进 live wiring、不部署、不开采集窗口。
```

## 3. 建议更新 `System/working-memory/tasks.md`

把 F1R 一行拆成两段（保持 `F1P → F1R → R1 → D1 → W1 → F2 → F3 → F4` 链不变）：

```markdown
- [x] **F1R-A0｜离线四因子记录器**：`OFFLINE_FACTOR_RECORDER_READY_FOR_R1`，
      commit=`<TASK_COMMIT>`；47 定向测试、341 quant、matrix 5/5、新增全仓失败 0
- [ ] **F1R-B｜生产四因子记录接线（需另行授权）**：先解决 factor_version 来源；
      再把记录器接入现役写入/readback，保留历史无身份兼容
```

## 4. 建议追加到 `评分系统任务清单.md`

```markdown
- [x] **F1R-A0｜离线四因子记录器**：commit=`<TASK_COMMIT>`。逐因子 evidence_time
      与真实 applied_weight 已被证明可取；缺数据仍形成明确观测且不带分；
      批次全有或全无。未接线、未采集、未部署、未调权。
```

## 5. 建议追加到 `2026-09-10.md`

```markdown
## F1R-A0 离线记录器（2026-09-10 深夜 2）

- commit=`<TASK_COMMIT>`，父=`d8c8bf82`，终态 `OFFLINE_FACTOR_RECORDER_READY_FOR_R1`。
- 四因子来源已只读定位并逐项登记（见 FACTOR_SOURCE_MAPPING.json）。
- `factor_version` 无来源 → 记录器 fail-closed，留给 F1R-B。
- package matrix 因新增两个合法 caller 同步 2 增 2 删，matrix 5/5、P2-05 6/6。
- 边界：Provider=0、生产库读写=0、未部署、Obsidian 只读。
```

`<TASK_COMMIT>` 请替换为本轮 successor commit 的实际 SHA（见回执）。
