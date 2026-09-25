# R5 · 每周只读 Markdown 报告设计

状态：`LOCAL_GENERATOR_READY`，不定时、不发送 Bark，不作为自动调参指令。

实现：`scripts/quant/r5_weekly_report.py`。调用者显式提供 `--week`、`--shadow`、`--forward`、`--drift` 三份冻结 JSON 导出及 `--output`。脚本不连数据库、不访问 Provider、不读取赛果以外的新源、不发送任何通知。输入若不完整，字段写“证据不足”，不把空值算 0 或通过。

输入契约：

- shadow：`metrics` 映射，键为市场/轨道，值含 `n/logloss/brier/rps/bias/status`；
- forward：`calibration_identity/eligible_count/validation_count/test_count/fixture_count/exclusions`；eligible 应来自正式 PIT/双侧/参数资格 manifest，技术可证明评估数不得混入；
- drift：`windows` 数组，逐项 `window_days/n/bias/cusum_zero_reference/evidence`；
- 每份导出需由上游另附提取时点、数据快照身份和 SHA，报告生成器只格式化输入，不代替上游证据冻结。

报告顺序固定为 shadow 指标、前向样本进度、排除计数、漂移观测。R1 追加式账本及正式密封 manifest 上线后才可填正式进度；未上线时不得把 Gate 2 历史 399 行写成前向样本。R5 如需自动调度或 Bark 推送，另行变更通知范围与权限。
