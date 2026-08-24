# ALLSV-RESTORE-01

Owner 已批准“恢复瑞超、保持中超关闭”的范围，但当前生产 Gate **未通过**：瑞超近 30 日 xG 覆盖仅 `2/16=12.5%`，SCHED-DEDUP-01 容量证据也未完成。因此本包只交付实现与三份独立生产决策单，没有部署、Provider 调用或数据库写入。

本地实现把原通用恢复脚本收紧为瑞超专用执行器：拒绝中超、要求中超仍 disabled、精确匹配单一 blocker、冻结计划数与集合哈希，并强制引用部署、回补、容量三份 SHA256 证据。当前 1296 条集合哈希为 `8998f5e00892a178ff29e3bbc9926267a616a5adaea1d73ce38c22f210bfd7de`；28 条已过期计划不在集合中。

验证：

```bash
uv run pytest -q tests/unit/test_reenable_competition_after_xg_recovery.py
uv run python scripts/check_allsv_restore_01.py --check
```

`--check` 对 evidence 全文做规范化 SHA256；任一字段发生 `1e-6` 变异都会失败。
