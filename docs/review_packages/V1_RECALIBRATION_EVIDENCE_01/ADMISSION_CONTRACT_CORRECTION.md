# V1 准入合同验收更正

状态：`IMPLEMENTED_PENDING_ACCEPTANCE`（本地提交，未部署）

## 生产影响结论更正

此前“不会改变当前生产行为”的说法错误。已部署合同为 `EV > 0 AND delta >= 0.05 AND EV-SE > 0`；本地实现改为 `EV > 0 AND cashflow_price_edge >= 0.05 AND EV-SE > 0`，与 calibration ledger 无关。

2026-08-30T14:27Z 之后生产只读抽取共 530 条评价，其中旧合同候选 216 条；76 条仅因 `DELTA_BELOW_THRESHOLD` 被拦截，占 76/216 = 35.19%。对这 76 条按 payload 五态分布与当时 decimal odds 重算 cashflow edge，76/76 均达到 0.05，因此新合同理论上会新增 76 条候选。

| market | 仅 delta 拦截 | cashflow edge ≥ 0.05 | EV min / p25 / median / p75 / max / mean | edge min / p25 / median / p75 / max / mean |
|---|---:|---:|---|---|
| AH | 30 | 30 | 0.050485 / 0.124109 / 0.172245 / 0.187089 / 0.187089 / 0.147433 | 0.058260 / 0.143364 / 0.198789 / 0.216145 / 0.216145 / 0.169859 |
| TOTALS | 46 | 46 | 0.037347 / 0.060759 / 0.111315 / 0.122146 / 0.146339 / 0.093366 | 0.050637 / 0.070109 / 0.124738 / 0.139473 / 0.169205 / 0.107057 |
| 合计 | 76 | 76 | 0.037347 / 0.060759 / 0.111315 / 0.153252 / 0.187089 / 0.114708 | 0.050637 / 0.070109 / 0.124738 / 0.175780 / 0.216145 / 0.131847 |

统计只读、不读赛果、不调用 Provider；原始 CSV 不入库，摘要可由下述 SQL 与脚本复核。抽取时刻固定为 `2026-08-31T03:22:53Z`，SQL SHA-256=`0fa167ed0738657ec039f67ad6cbdfc411dbbb8dc01b9e0f9dc7709fafb91e03`，CSV SHA-256=`4842f9b33de6af217c045c8a57ed1aae31184a9cd018a619080e79b4d7a8c74a`。服务端 COPY 完成后进程已退出，生产 `pg_stat_activity` active COPY=0。

## 测试与宿主限制

全量命令：`PYTHONPATH=src .venv/bin/pytest -q`。结果：`2945 passed, 9 skipped, 5 failed, 5 warnings`，耗时约 425.82s。

失败归因：

- `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`、`[path1]`：宿主 Docker 只有 engine，`docker compose` 插件缺失（`unknown shorthand flag: 'f'`）；不可通过产品代码修复。
- `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`：测试启动裸 `python`，宿主仅有 `python3`/`.venv/bin/python`，在脚本启动前 `FileNotFoundError`；不可通过产品代码修复。
- `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`、`test_preflight_passes_worker_owned_0750_runtime`：依赖 Docker 容器创建 UID/GID fixture；当前宿主测试表现为 fixture 目录未生成，返回 `MISSING`，属于宿主运行时限制，非本次准入合同改动。

`test_secret_patterns_are_guarded` 的既有文本误报已修复为无凭据表述，当前通过；它并非裸 python 失败。

## 部署边界

本变更不得在 AH 斜率修复落地前单独部署。它会在已量化亏损模型（110 注、-17.045 单位、胜率约 40%）上放宽约 35% 的准入。若 Owner 决定先部署，必须明确记录为“已知模型有缺陷情况下的主动放宽”风险决定，不得描述为清理或中性变更。
