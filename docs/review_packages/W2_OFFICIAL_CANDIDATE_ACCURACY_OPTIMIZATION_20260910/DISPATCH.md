# 任务 2 执行令（逐字副本）

本文件是 Owner 下发的任务 2 执行令原文副本，用于交付包自证输入身份。
执行方：Claude Code；验收方：Codex。

原文见会话记录；关键约束在此复述，不改写、不解释：

```text
TASK_ID = W2_OFFICIAL_CANDIDATE_ACCURACY_OPTIMIZATION_02
WORKTREE = /Users/liudehua/Documents/Projects/W2-workspaces/w2-official-candidate-accuracy-20260909
EXPECTED_HEAD = 82b4b54f548627a7690f6400e9f8de7c0575bcf7
EXPECTED_BRANCH = codex/w2-official-candidate-accuracy-20260909
CANDIDATE_ID = GLOBAL_ROLLING_CONFIDENCE_SHRINKAGE_V1
唯一输入 = docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/
终态 = MODEL_CANDIDATE_READY | NO_SAFE_CANDIDATE | FAILED_DETERMINISM
```

开工核对结果：

```text
git status --porcelain=v1   （空，工作树干净）
git rev-parse HEAD          82b4b54f548627a7690f6400e9f8de7c0575bcf7   一致
git branch --show-current   codex/w2-official-candidate-accuracy-20260909   一致
shasum -c HASHES.sha256     13 / 13 OK
```

本任务不做：修复因子链、PIT 治理、C1 / rho / F5 / task3bis、
读取 5,818 / 8,659 / 858 / 280 或任何未正式推荐比赛、采集 Provider 数据、
修改生产推荐链、部署或开启正式推荐。
