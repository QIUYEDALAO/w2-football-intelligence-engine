# Obsidian 更新建议（给 Codex）

**这是建议，不是更新证明。** 本轮 Claude Code 对 Vault 只读：
`OBSIDIAN_ACCESS_MODE = READ_ONLY`、`OBSIDIAN_WRITES = 0`。

只读核对时发现 Vault 已由 Codex 在 2026-09-10 19:19 更新（`当前状态.md` 首行为
"F1R-A0 R1 独立验收未通过，进入窄整改"）。那不是本轮写入；本轮未触碰任何 Vault 文件。

## 建议追加到 `当前状态.md` 顶部

```markdown
## 当前状态（2026-09-10 深夜 3）：F1R-A0 窄整改完成，终态仍为阻塞

- `F1R_A0_FINAL_STATE = BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`，commit=`<TASK_COMMIT>`，
  父=`0821f472`。R1 指出的三个问题全部修复，但修完的结论不是放行，而是把阻塞点
  从"没被发现"变成"被机器强制"。
- **P0**：`TeamMatchHistory.observed_at` 的实现就是 `return self.kickoff_at`。
  F5 读已结算 AH 结果、F6 读历史进球，这两类事实在开球时都不存在。现按因子分三种
  证据规则：F3 用事件时点、F9 用来源快照时点，F5/F6 必须由调用方显式传入真实来源
  观测时点，且传入值等于 kickoff 会被识别并拒绝。
- **生产中该时点不存在**：`results.confirmed_at` 在库里有，但从未被带到因子 builder
  消费的对象上，`TeamMatchHistory` 也没有承载它的字段。接通需改 `src/w2/features/`
  与 `src/w2/prematch/`，均不在 A0 授权范围内 → 终态保持阻塞。
- **P1 参与与权重**：不再把 `READY` 当作参与。直接复用
  `w2.pricing.team_score.independent_team_scores_from_contributions`，
  participated 与 applied_weight 均以该权威为准，不一致即整批拒绝；READY 但被权威
  排除的因子记为 `FACTOR_ADMISSION_FAILED`、score=null。参考账本里就有一例。
- **P1 原子性**：改为同目录临时文件 → 写入旧内容+完整新批次 → flush → fsync →
  `os.replace` 单一提交点。四类故障注入（首行写失败／中途失败／fsync 失败／提交点失败）
  均验证账本新增 0 行且不留临时文件。
- 验收数据：F1R-A0 定向 73 passed、F1P 72 passed/1 skipped、quant 全集 367 passed/
  1 skipped、matrix 5/5、ARCH-P2-05 6/6、全仓 8 failed/3073 passed（相对 `d8c8bf82`
  新增失败 0）、两次 runner 逐字节一致、F0 5/5、F1 6/6、F1P 7/7、输入包 13/13。
- `ruff check .` 报 10 errors，**不是 exit 0**；但与干净生产基线 `3ac86c14` 的 10 条
  逐条相同，本轮未引入任何新 lint。
- 夹具为 `SYNTHETIC_CONTRACT_FIXTURE`，`SYNTHETIC_FIXTURE_v1` 是夹具值不是生产版本号；
  不代表生产链已接线。
- 边界：Provider=0、生产库读写=0、未部署、未 push、Obsidian 本轮只读。
```

## 建议追加到 `重要决定.md` 顶部

```markdown
## 当前决定（2026-09-10 深夜 3）：接受窄整改，维持 F1R-A0 阻塞

- 三个问题已修，接受修复本身；**不接受**把终态改成 READY。F5/F6 在生产中确实没有
  可绑定的逐因子来源观测时点，写成 READY 就是为了过测试而降级合同。
- 确认修复方向正确：阻塞现在由记录器强制（缺来源时点或用 kickoff 冒充都整批拒绝），
  而不是靠人记得。
- 记录 F1R-B 的前置条件：把 `results.confirmed_at` 一类真实来源观测时点接到
  `TeamMatchHistory`（改 `src/w2/features/` 与 `src/w2/prematch/`），
  并解决真实 `factor_version` 与逐因子 source capture identity。两者都需单独授权。
- 不因窄整改完成而解锁下游：R1-A0 复验前不进 live wiring、不部署、不开采集窗口。
```

## 建议更新 `System/working-memory/tasks.md`

```markdown
- [ ] **F1R-A0｜离线四因子记录器（阻塞）**：`BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`，
      commit=`<TASK_COMMIT>`；端口、批次契约与原子提交已实装并自证，
      F5/F6 缺生产来源观测时点故 fail closed，待 R1-A0 复验
- [ ] **F1R-B｜真实来源时点与生产接线（需另行授权）**：先把 results.confirmed_at
      一类时点接到 TeamMatchHistory，并解决 factor_version 与 source capture identity
```

## 建议追加到 `评分系统任务清单.md`

```markdown
- [ ] **F1R-A0｜离线四因子记录器（阻塞）**：commit=`<TASK_COMMIT>`。kickoff 不再冒充
      赛果观测时点；参与与权重以 team_score 权威为准；批次单点原子提交并有故障注入验证。
      F5/F6 无生产来源时点 → `BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`。
```

## 建议追加到 `2026-09-10.md`

```markdown
## F1R-A0 窄整改（2026-09-10 深夜 3）

- commit=`<TASK_COMMIT>`，父=`0821f472`，终态 `BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`。
- P0 kickoff 冒充证据时点、P1 READY≠参与、P1 逐行写入非原子 —— 三项全部修复。
- 阻塞原因已定位到具体字段：`TeamMatchHistory` 没有承载来源观测时点的字段，
  `results.confirmed_at` 从未被带过来。
- package matrix 因新增 `w2.pricing` caller 同步 1 增 1 删，matrix 5/5、P2-05 6/6。
```

`<TASK_COMMIT>` 请替换为本轮 successor commit 的实际 SHA（见回执）。
