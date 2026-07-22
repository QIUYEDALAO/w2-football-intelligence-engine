# W2 V3-08 LMM 离线增量验证协议

该协议只使用冻结、可审计资料：官方首发与公告时点、历史常用 XI、API-Football 到 Transfermarkt 的团队范围身份映射、当时估值、阵型/位置/替补/缺席/连续性，以及同一比赛的 as-of 市场快照、收盘快照和结算。不得网页搜索、直接抓 Transfermarkt，或使用赛后/未来估值。

固定比较 baseline（无 LMM）、gate only、explanation only、LMM-AH、LMM-OU、combined；按固定时间切分（2024 train、2025 validation、2026 holdout），holdout 不参与调参。AH 检查 log loss、Brier、五态结算分布、校准、CLV；OU 检查 total-goal log loss、Brier、RPS、校准、CLV。所有差异使用 2,000 次 seed=20260719 配对 percentile bootstrap。

每个总体至少 500 条、联赛与 coverage A/B/C 分层至少 50 条，并报告身份缺失敏感性与公告后前向 shadow。任何 holdout CI 上界大于零或 coverage 下降超过 2pp 均不通过 no-harm。即使未来离线通过，也只能将验证状态改为 `PASS_FOR_SHADOW`；数值调整始终为零，必须另获人工批准才可开启。

本次冻结资料的团队范围 identity 映射和已物化估值均为 0，不能构成 canonical 的 AH/OU outcome join。因此这是诚实的 `INSUFFICIENT_EVIDENCE`，不是对 LMM 效果的正/负判断。
