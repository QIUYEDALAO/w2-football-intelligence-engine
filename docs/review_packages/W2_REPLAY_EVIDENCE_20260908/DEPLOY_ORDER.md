# 给老K：独立复核并部署捕获重放证据补丁

Owner已要求Codex实施并交由老K部署。你负责独立复核、部署和线上技术验收。无需再向Owner询问普通技术选择；发现本包范围内缺陷，自主最小修复并重跑，将修复diff和证据回交Codex。未满足发布标准不得切换生产。

## 目标与范围

工作区 /Users/liudehua/Documents/Projects/w2-replay-evidence-20260908
交付包 docs/review_packages/W2_REPLAY_EVIDENCE_20260908/
先读本项目AGENTS、W2三个Obsidian必读页、最新任务计划、REPORT.md和manifest.json。以当前Owner授权覆盖历史已过期的GitHub发布指引。
目标是新捕获具备本地重放证据并在VPS真实保存；不是开启推荐或验证模型盈利。包含基线f0eab4a5上的任务3 v3前置修复，新增文件也在manifest，不得漏带。

## 一、独立复核

1. 校验manifest全部文件hash，记录实际本地HEAD、diff、生产release/digest/schema及UTC时间。不得打印环境变量、密钥或读取.env内容。
2. 先确认源码基线与生产的关系。严禁把主仓库旧分支或整个脏worktree直接覆盖VPS。用明确生产基线构建干净本地候选，只整合此包和必要的已验收v3前置；不夹带phase1治理补丁。若Git锁仍在，查明进程所有权，不能盲删锁；必要时在独立本地仓库构建可提交候选。
3. 独立核对矩阵→AH/TOTALS五态→Decimal EV，盘口是所选球队视角。正负四分之一盘口、双方、走盘及半输半赢必须有独立oracle。核对保存输入/参数/未舍入矩阵和hash关系，缺失不得补默认值。补充同身份matrix篡改/参数篡改/JSON持久化往返和旧捕获不重写检查。
4. 执行：

```sh
cd /Users/liudehua/Documents/Projects/w2-replay-evidence-20260908
PYTHONPATH=src /Users/liudehua/Documents/Projects/w2-football-intelligence-engine-phase1-37543b3c/.venv/bin/python -m pytest tests/unit/test_task3_t30_checkpoint.py tests/unit/test_task3_t30_freeze.py tests/unit/test_model_forecast_ledger.py tests/unit/test_analysis_card_xg_materialized.py tests/unit/test_runtime.py tests/unit/test_market_timeline_snapshots.py tests/unit/test_simulation_slim_inputs.py tests/unit/test_simulation_engine.py tests/unit/test_five_state_cashflow_oracle.py tests/unit/test_capture_replay_evidence.py -q
/Users/liudehua/Documents/Projects/w2-football-intelligence-engine-phase1-37543b3c/.venv/bin/ruff check apps/worker/celery_app.py src/w2/strategy/simulate.py src/w2/tracking/model_forecast_ledger.py tests/unit/test_model_forecast_ledger.py tests/unit/test_task3_t30_freeze.py tests/unit/test_task3_t30_checkpoint.py tests/unit/test_capture_replay_evidence.py
git diff --check
```

5. 在隔离Linux/PostgreSQL环境执行项目适用发布回归、capture JSON持久化重放、API响应契约、旧版本兼容、幂等与migration检查。本包无migration；检查完成后形成独立PASS回执及精确候选commit/hash。当前192条通过不代替发布门。

## 二、部署

- 使用项目既有本地构建→OCI文件传输→VPS流程。禁止GitHub/GHCR、拉取未知远端代码或任意升级依赖。先固定旧release/digest/schema，准备可恢复备份和旧镜像，保存配置指纹而不导出秘密。
- 避开已有临场任务，按既有runbook切换与最小必要重启；先检查部署窗口内任务负载。禁止新增Provider探针/回填、扩联赛、修改策略参数、阈值和数据库历史行。
- 保持既有开关原值。尤其不得启动W2_TASK3_T30_CAPTURE_ENABLED、shadow或前瞻确认时钟；若发现其原值与报告不同，记录并先核实，不擅自切换。正式推荐/自动下注/真钱保持关闭。
- 本次允许既有正常捕获流程在新eligible样本上保存新增JSON证据；不手工制造新evaluation，不给旧capture补字段。

## 三、线上验收与回滚

- 记录各节点实际UTC、exact release/digest/schema、容器健康、ready、错误日志与任务运行状态；验证API JSON载荷增长未破坏既有消费者。
- 对部署后自然产生的新eligible捕获，以BEGIN READ ONLY导出最小证据，结束ROLLBACK；封存capture payload、关联id/hash、执行回执并校验两端SHA。不调用Provider，不导出秘密。
- 下载后在相同发布版本的隔离环境对simulation_replay.simulation运行replay_simulation，比较矩阵/五态/参数；核对capture身份与hash。T30没有开启则不要求产生T30记录；普通捕获不是报价绑定证明。
- 尚无新记录：明确DEPLOYED_HEALTHY_CAPTURE_PENDING，不能写线上捕获验收PASS或启动计时。交接等待后续自然样本，禁止为通过而启动采集开关。
- ready失败、版本不一致、捕获崩溃或消费者回归：按已备份旧release/digest回滚，保留新增append-only证据，复核健康，提交失败与回滚日志。

## 四、一次性交付

提交独立验收报告、候选diff/commit/hash、构建与传输digest、备份与回滚位置、部署时间/版本/健康证据、捕获只读回执及离线重放结果、未完成项。Obsidian仅记录已核实事实；分开写本地实现、独立验收、已部署、线上捕获是否通过。任务3科学结论与任务4门禁保持不变。
