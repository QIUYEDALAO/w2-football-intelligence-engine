# R0 前向时钟与 R1 补采集 · 激活/回退手册

状态：已执行；本文件记录激活步骤，实际数据库回读见 `W2_CANDIDATE_C_R0_FORWARD_CLOCK_ACTIVATION_20260925.md`。T0 固定为 `2026-09-25T08:46:32Z`。正式时钟是数据库 `forward_clock_registry` 中一次性追加的 `started_at`，不能使用文档编辑时间或发布开始时间冒充。

## 激活顺序

1. 校验权威分支、目标 SHA、R0 预注册 SHA `13b897…1a0f`、生产当前 schema `0075_validation_samples_calibrated`。冻结代码与输入版本；无独立复算和 Owner 授权不得开钟。本任务 Owner 已明确授权前向时钟/R1 生产写入，不涉及推荐切换。
2. 运行全量测试、API/前端契约与发布 dry-run。发布目标 SHA（含 `0076_forward_review_evidence`）；先备份与迁移，再部署并完成发布 a–h 回读。新表迁移只追加，`validation_samples` 和旧 evaluation identity 不变。
3. 发布成功**之后**，在当前生产镜像内执行 `python -m w2.tracking.start_forward_clock --revision <40位已部署SHA>`。命令从 PostgreSQL `clock_timestamp()` 取实际时钟，将 SHA、`candidate-eval.v2`、R0 预注册 SHA、`w2.forward_evidence_input.v1` 同事务落盘。重复调用只有完全相同字段才是 no-op；不得重设启动时间。
4. 回读数据库登记值，确认 `started_at≥T0`；随后回读新评估的 `EVALUATION_SNAPSHOT` 与双侧 observation、forecast capture、λ/rho/input hash。无新评估时，封存 0 行初始回执，不伪造样本。
5. 用真实登记值更新 `NEXT_ACTION.md`、`QUANT_PROJECT_STATE.yaml` 等当前状态文件，并单独提交。T0 至启动时刻的行全部排除，不回填。

## 证据规则

现有评估事务新增一条不可变 `recommendation_review_ledger` 事件；事件带 evaluation_id、决策/校准版本、原选边、展示状态、因子门、模型/报价身份、evaluated_at、forecast 与双侧报价 captured_at、kickoff、lambda_home/away/rho 和输入哈希。双侧仅接受同 capture、bookmaker=4、同线的合法组合；AH 对侧线符号相反。缺任一时间/参数/双侧身份保留事件并标 `PIT_UNPROVABLE` 及原因，不参与前向密封。旧行从不重放写入。

## 回退

- 开钟前发布失败：发布脚本回滚旧镜像/旧 schema；新表为空才允许 downgrade。
- 开钟后写入异常：立刻回退到上一已知健康的应用镜像以停止 R1 writer；保留 clock 与 ledger 原始行，**不降级 schema、不删除时钟或证据**。记录停写区间与失败事件，后续恢复需新的 writer revision/排除清单；不能追写停写期间评估为密封样本。
- R1 只追加诊断，不修改推荐、结算、EV 或因子门。Dashboard 监测为只读；F1 shadow 运行尚无持久化调度登记时明确显示“尚无 F1 运行登记”。
- R1 写入使用评估事务内 savepoint；证据写入失败会记录 `FORWARD_EVIDENCE_WRITE_FAILED`，评估事务继续。Dashboard 以新评估数减 ledger 事件数显示“证据写入缺口”，缺口不得进入密封样本。
