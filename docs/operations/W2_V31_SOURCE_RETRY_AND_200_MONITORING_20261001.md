# v3.1 来源重试与累计监测整改

本轮起点为 `bedeea82dfbe17e725964464a767a433707ff257`，权威分支为
`codex/w2-authority-20260916`。原始上线证据不改写。

2026-10-01 02:18 UTC 生产只读基线：13 个 future refresh 任务被持久栅栏阻断，
其中 10 个 XG 阶段冲突为 `first_captured_at`，3 个 H2H 阶段冲突为
`endpoint_capture_id`。当时 v3.1 AH/OU 决策均为零，已安装巡检仍返回 `issues=[]`。

## 不变合同

两份模型 JSON、评分公式、门槛和推荐权威不变。首次冻结的来源与时间证明不改写，
历史缺 PIT 不升级。旧推荐的写入、发送和当前展示继续关闭。727 场仅是冻结公式研究证据。

残留 `SIDE_EFFECT_UNCERTAIN` 保留隔离；本轮不清 claim、不重发可能已发生的 Provider
调用、不将未知调用数改为零。修复用于后续正常计划窗口。历史失败记录须保留并由巡检显示，
不能因新窗口成功而冒称旧任务已完成。

## 真实调用点

- XG：`future_fixture_refresh` 的拥有者阶段 → `XgHistoryBackfillService.run` →
  持久 match 读回 → 首次未冻结 target 写入。`run_saved_raw` 使用同一冻结选择，零 Provider。
  已有 target 不再以新采集时间重新提交；显露 `frozen_snapshot_no_ops` 与
  `unproven_snapshot_no_ops`。显式冻结 writer 仍逐字段拒绝冲突。
- H2H：自然 worker → `capture_h2h_for_pair` → raw/capture →
  `_record_h2h_observation`。同一 FT 事实的后续 capture 保留为观测，canonical 原始行不变；
  fixture/team/比分等业务字段改变仍拒绝。严格冻结对象重试接口保持完整字段比较。
- 赛前：唯一公开计算入口自动 forward，在决策原事务中追加用于监测的原报价、两价、
  特征和冻结模型概率。未入选项仍为 `selected=false`、`direction=NULL`、无推荐入场条款。
- 赛后：`result_materialize` 与 `forward_outcome_ledger` → `_settle_v3_postmatch` →
  可信 FT 核验 → 推荐结算/样本与累计监测事实同事务；任一失败不得 PASS。
- 巡检：`ops/host/w2-v3-readonly-monitor.py`。检查持久不确定阶段、陈旧 ATTEMPTING、
  任务 DONE 缺 refresh_forward、近期 FAILED checkpoint；无推荐不能遮蔽故障。

## 每市场每版本每新增 200 场

原研究实施计划 2026-09-28 第 70 行的设置落实为 `REPORT_INTERVAL=200`。
计数对象是已完成可信 FT、来源和报价合格的 fixture；AH/OU、model/calibration 版本各自计数。
合格但低于推荐门槛的 fixture 也计数；SKIP、来源不合格、无 FT、AET/PEN 不计入分母。
不得将两个市场合并为 200，也不是 200 条 selected 推荐。

`0089_ahou_v3_monitoring` 新增不可变事实与累计报告。到 200/400/600… 自动持久化报告；
报告保留 decision_id、输入/报价/模型/可信 FT 引用、五态、净单位、RPS、报价年龄及联赛/月分层。
纯市场对照来自同一合格 fixture 集合，按原两价的去水优势排序，同推荐覆盖数，fixture_id 稳定打破平局。
每次事件即时保留事实，报告失败回滚结算事务；重试比对内容与哈希且不重复。

这是只读描述报告，不会自动拟合、重训、改参数、切模型或发送新推荐。
后续模型变更仍须单独研究合同与所有者决定。

## 发布和老板总验收

最终固定 SHA 的 FULL 质量门通过后，使用现有 `w2-release` 停调度、等待有效 lease
自然排空、停推荐出口、备份/迁移、同 SHA 激活；旧栅栏在失败和回滚中保留。
有监测审计事实时拒绝 schema 降级，代码回滚保留事实。空表的隔离 down/up 可重新构建；
既存表的升级重新核对字段类型、主键、唯一键及外键。
`w2-update-v3-monitor` 仅更新原有只读 timer 的版本化脚本，不修改历史报告与采集配置。

上线回执必须区分隔离链通过、代码已部署、生产新窗口结果，以及首批真实推荐/FT/page/daily
对账。隔离 200 场或 +1.15 单位不得称生产收益；实现方不代签独立验收。
