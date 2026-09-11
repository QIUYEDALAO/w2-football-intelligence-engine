# Decision C — 启用瑞超并精确重开计划

Status: `BLOCKED_BY_A_B_HEALTH_AND_CAPACITY`

只有 Decision A、Decision B、30 日健康 Gate 和 SCHED-DEDUP-01 容量 Gate 全部通过后，Owner 才能批准本决策。

批准对象必须绑定当时重新读取的精确计划集合。当前冻结基线为 1296 条、SHA256 `8998f5e00892a178ff29e3bbc9926267a616a5adaea1d73ce38c22f210bfd7de`；若执行时任何一条已过期、状态变化或 blocker 变化，执行器会失败，必须刷新证据后重新决策。

执行器在一个事务内：确认瑞超 disabled、中超 disabled、覆盖/新鲜度通过、证据哈希齐备、计划集合完全一致；然后启用瑞超并只把该集合改回 PLANNED，清除禁用 blocker 和旧 claim 字段，重算 plan hash，写入含完整 plan IDs 的 readiness audit。

本决策不包含部署、回补、模型参数、SE 公式或中超状态变更。
