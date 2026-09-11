# Decision B — 瑞超受控 xG 回补

Status: `OWNER_DECISION_REQUIRED_AFTER_DECISION_A_PASS`

仅允许 `W2_XG_REFRESH_COMPETITIONS=allsvenskan` 的单次显式回补。执行前复查临场档位、记录 Provider 剩余额度并设调用上限；执行后记录调用数、numeric/null、成功物化与失败 fixture，生产写入只限 xG 原始证据与既有物化表。

回补后以只读查询给出瑞超近 30 日：已完赛数、两队 xG 完整场数、覆盖率、最新 xG kickoff。覆盖低于 70% 或最新证据超过 7 天，停止在 Decision B，不得进入启用。证据形成 SHA256，供 Decision C 强制引用。

本决策不授权启用联赛或重开任何计划。
