# W2 V3 Gate C（非 UI）验收

**时间：** 2026-07-20（Asia/Shanghai）  
**结果：** PASS，进入人工审批停止点  
**本地分支：** `codex/w2-v3-gate-c-readonly`  
**代码 / staging release：** `dbff72bd97764bfe6712527447f0459403e3e6a7`

本验收只验证已部署 release；没有访问 GitHub、没有部署、没有修改
Dashboard 组件、文案、CSS、布局、路由或信息架构。

## 本地 Gate

| 检查 | 结果 |
| --- | --- |
| Ruff | PASS |
| Mypy | PASS（243 source files） |
| pytest | PASS：1263 passed、4 skipped、1042 warnings |
| Web typecheck / production build | PASS |
| Playwright | PASS：9 passed |

4 个 pytest skip 均为既有环境限定：3 个 staging-parity fixture 需要 Docker，
1 个 migration fixture 需要 `W2_TEST_POSTGRES_URL`。本轮没有新增 skip。

## staging 基线与运行状态

- `/health`、`/ready` 均为 200；Alembic current/head 均为
  `0024_create_lineup_intelligence`。
- API、Web、release SHA 均为 `dbff72b`；API、Web、worker、scheduler、
  postgres、redis 六服务最终均为 healthy。
- 运行镜像 ID：API `sha256:869ba2ba7c03…`、Web
  `sha256:6c71867994e5…`、worker `sha256:39202fd36248…`、scheduler
  `sha256:8745f6c4e34c…`。公开 release identity 的 OCI digest 为
  `UNAVAILABLE`，因此以容器 image ID 与 API/Web SHA 共同冻结。
- RSS：API 292.4 MiB、worker 298 MiB、scheduler 145 MiB、Web 4.6 MiB、
  postgres 149.5 MiB、redis 4.6 MiB；所有服务 restart=0、OOM=false。
- 磁盘 118 GiB 中已用 96 GiB（85%）；这是既有运行风险，不在本 Gate 修改。
- 真实 analysis-card 公共读取 20 次：p95=2.606s、max=2.609s，低于既有
  3.706s 门槛。

## 证据、能力与 cohort

三场瑞典超样本 `1494210`、`1494212`、`1494213` 均满足：

- `competition_id=allsvenskan`，`frozen_artifact_provenance.status=VERIFIED`；
  artifact hash 依次为 `7ad92f19…526364`、`fe12b213…6823b2`、
  `19997fb1…cd45b1`。
- 首发要求为 `ADVISORY`；AH 与 OU 均为同一 provider/bookmaker/capture 的
  完整、新鲜 quote pair。
- 三场实际语义均为 `WATCH`：模型状态 `NOT_READY`，没有市场概率、方向、
  settlement contract、candidate、formal recommendation 或 lock。这是如实的
  fail-closed 状态，不是“已形成推荐”。

canonical performance cohort hash：
`b234fc5983a38e9264191ffdc3be26568856059a661c49edaf0e0ce04bc7ff84`。
值保持 validation=23、processed=23、eligible=16、excluded=7、pending=0；
命中/未中/走水/作废为 11/3/2/0，所有 cohort 与 CLV 不变量为 PASS。

`formal_ah`、`formal_ou`、`lineup_numeric_adjustment_ah`、
`lineup_numeric_adjustment_ou`、`production_recommendation` 与
`recommendation_lock` 均保持 `feature_enabled=false` 且
`production_enabled=false`。

## 受控只读窗口

为消除 scheduler 干扰，短暂停止 scheduler 后仅访问公共 API 和现有 Dashboard：

- 1440px 与 824px 均无横向溢出，Tab 首焦点为“全部赛程”按钮；页面显示
  Web/API 同一 `dbff72b` 与 canonical 16 场 cohort。
- API、Dashboard、三个 analysis-card 请求均为 200；公共响应声明
  `provider_calls=0`、`db_writes=0`。
- 窗口前后：`provider_request_logs=805`；odds observation、forward
  market snapshot、forward prediction lock、recommendation lock、
  recommendations、forward evaluation 均为 0；Celery queue=0，Redis
  result DB=336。没有 provider、业务 DB、ledger、queue 或 lock 增量。
- scheduler 随后恢复为 healthy。为执行受控窗口发生一次预期的 scheduler
  容器 recreate；该容器 restart count=0、OOM=false，非故障重启。

## 边界与下一步

原版 Gate C 的 Owner/Analyst/Ops 三层视图、role-view E2E 与 V3-09 Dashboard
语义切换未执行，仍需用户单独授权；本次没有改变现有 Dashboard。

Gate C（非 UI）到此停止。不得自行开启 AH/OU 正式推荐、LMM 数值调整、
锁单或 production；后续只能在人工审批后进入相应条件性阶段。
