# Candidate C R0 前向时钟启动回执 · 2026-09-25

## 授权、版本与启动

Owner 于本任务明确授权前向时钟启动与 R1 生产补采集；不授权推荐公式/因子门/结算切换，也不开放独立 quant Freeze A1 Provider 采集。权威分支：`codex/w2-authority-20260916`。

| 项目 | 实际值 |
|---|---|
| R0 预注册 T0 | `2026-09-25T08:46:32Z` |
| R0 预注册 SHA-256 | `13b897871a37011b3647f860b819a9299a76f81d5af00be5eb2acf2142671a0f` |
| 发布目标 / 生产实现 | `d4ef36edebe66e4e3c7f279adbf37c9b51d947a9` |
| Alembic 前 → 后 | `0075_validation_samples_calibrated` → `0076_forward_review_evidence` |
| clock_id | `candidate-c-r0-forward-v1` |
| **数据库实际 started_at** | **`2026-09-25T09:43:11.620864Z`** |
| 模型 / 输入身份 | `candidate-eval.v2` / `w2.forward_evidence_input.v1` |
| 启动时 R1 event / 密封 validation / test | `0 / 0 / 0` |

启动前只读 SQL 返回 schema `0076`、`forward_clock_registry=0`、`recommendation_review_ledger=0`，`/list.forward_wait_monitor.clock.status=NOT_STARTED`。发布成功后在已部署 API 容器内**一次**执行：

```text
python -m w2.tracking.start_forward_clock --revision d4ef36edebe66e4e3c7f279adbf37c9b51d947a9
candidate-c-r0-forward-v1 2026-09-25T09:43:11.620864+00:00 d4ef36edebe66e4e3c7f279adbf37c9b51d947a9
```

随后独立回读 `forward_clock_registry` 的 `clock_id/started_at/code_revision/model_identity/preregistration_sha256/input_version` 全字段吻合；`started_at>T0`。`recommendation_review_ledger=0`，因为开钟后尚未出现新评估，不得以 T0 后至启动前的旧行补齐。前向密封样本仍未开始，F1 shadow 运行尚无正式登记，AH 100 场 DC/Skellam 误差仍未就绪；**开钟不等于 Gate 通过或生产推荐切换**。

## 发布与回读

发布使用 `ops/host/w2-release --target d4ef36edebe66e4e3c7f279adbf37c9b51d947a9`，仅执行一次，耗时 367 秒。备份 `/opt/w2/backups/predeploy-d4ef36edebe66e4e3c7f279adbf37c9b51d947a9-20260925T093633Z.dump`，大小 505,748,767 bytes，`pg_restore --list` 通过。release_id 与 API/Web SHA 一致，远端分支 SHA 同目标。发布日志：`/opt/w2/shared/runtime/reports/release-20260925T093959Z.log`；本地发布回执：`~/Desktop/W2文档/W2_发布_d4ef36edebe66e4e3c7f279adbf37c9b51d947a9_20260925.md`。

| 回读 | 结果 | 证据摘要 |
|---|---|---|
| a | PASS | 六接口 200，`/ready=200` |
| b | PASS | release_id / API / Web SHA 均为 `d4ef36ed…` |
| c | PASS | 248 推荐，倒序一致 |
| d | PASS | 所选足球日 2 场，抽样盘口 radar 可读 |
| e | PASS | API、Web、worker、worker-heavy、scheduler、Postgres、Redis 七容器 healthy；postmatch cap 800 |
| f | PASS | 四业务容器稳定窗口 Traceback=0 |
| g | PASS | 过期验证样本推送=0 |
| h | PASS | 逾期 DUE N0=0、N1=0 |

## 采集字段落盘与回退

R1 的新 `EVALUATION_SNAPSHOT` 事件在评估落库后经 savepoint 追加，字段包括：`evaluation_id/evaluated_at`，forecast capture identity 与 `captured_at`，同 capture/bookmaker/line 的双侧 quote observation identity 与各自 `captured_at`，`kickoff_utc`，模型 `lambda_home/lambda_away/rho`、simulation input hash 与 manifest hash，原选边、候选/展示/因子门状态及校准身份。缺证据保留事件并标 `PIT_UNPROVABLE`；写入异常记日志 `FORWARD_EVIDENCE_WRITE_FAILED`，Dashboard 计数缺口。当前没有新评估事件，因此字段**结构已部署、逐笔真实样本待首个新增事件核验**。

回退仅切回上一已知健康应用镜像以停 R1 writer；clock 和已追加 ledger 不删除、不覆盖，schema 在非空时拒绝 downgrade。停写区间不补入密封样本。`validation_samples` 保持兼容事实投影，推荐、结算、EV 与因子门逻辑未改。
