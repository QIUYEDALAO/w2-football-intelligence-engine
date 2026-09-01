# V1 AH goal-share calibration 自验收

状态：`CANDIDATE_REJECTED_PENDING_INDEPENDENT_ACCEPTANCE`。

## 冻结顺序

```text
ae82d534  docs: freeze V1 AH goal-share calibration
d624f65b  docs: clarify V1 AH fold metric before fit
ba621518  test: freeze V1 AH goal-share fit runner
804c4c05  audit: reject V1 AH goal-share candidate
```

预注册 SHA-256：
`a078948196ff014180bf64dcbaae48a8304a4367d187fae60c43c475794ffb18`。

结果前 runner 对输入执行 fail-closed SHA-256 校验。唯一一次拟合使用：

```text
home-away  709050b581b569c874c6a8d1363ba1a6612503489d175da8b644c5df05294a02
xg         16fcaaad812e8007c7e828c964d7029bc223e361cdac87b122c56eba9e8e3522
```

## 冻结裁决

- full fit：`share_intercept=-0.004697 / share_logit_scale=1.139814`；
- OOF：`7,159` 场，7/10 folds、11/13 lines 改善；
- margin regression：slope `1.173055→0.997040`，intercept
  `-0.020455→+0.007119`；
- TOTALS 不变量：最大 lambda-total 差 `1e-15`、total-NLL 差 `2e-15`；
- clamp：`0`。

三项强制门失败：

```text
AH Brier candidate-minus-TOTALS-only upper95       +0.000080926
scoreline NLL candidate-minus-TOTALS-only upper95  +0.000973714
AH Brier candidate-minus-production upper95        +0.000115516
required                                            <= 0
```

因此裁决为 `REJECTED`。未修改门槛、未重跑、未接入生产参数。

结果 artifact SHA-256：

```text
JSON  746da142733148eed1780f10546297c31f9747e6617923e28ba4f7647e6b51e4
MD    7a7e4f461a8e9635d6bf7c1b73857b246b3823bb39d24e42bd26cbd0d2db859d
```

## 自验收

定向命令：

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src:. .venv/bin/pytest -q \
  tests/unit/test_v1_ah_goal_share_calibration.py \
  tests/unit/test_v1_market_axis_calibration.py \
  tests/unit/test_calibration_validation_registry.py \
  tests/unit/test_point_ev_calibration_authority.py \
  tests/unit/test_simulation_engine.py \
  tests/unit/test_point_ev_calibration_identity.py \
  tests/contract/test_api_projection_read_authority.py \
  tests/contract/test_src_w2_package_matrix.py
```

结果：`134 passed`。

全量命令：

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src:. .venv/bin/pytest -q
```

结果：`2957 passed / 9 skipped / 4 failed / 5 warnings`。四个失败与改动前宿主基线
一致且本轮未触及相应文件：

- `tests/contract/test_compose_env_dedup.py` 两个参数实例：本机 Docker CLI 缺 Compose
  插件，`docker compose -f` 返回 exit 125；
- `tests/integration/test_future_refresh_staging_parity.py` 两项：Docker Desktop bind mount
  无法在 macOS 临时目录构造 Linux UID/GID 权限夹具，返回 `MISSING`。

Ruff check 与 format check 均通过。结果 JSON 的输入摘要、`8,659/7,159` 计数、三项失败门
及全部 safety=0 已用独立 `jq -e` 断言复核。

## 边界

`src/`、模型参数、calibration identity、ledger、白名单、V2、migration、Provider、生产读写
与部署均未改变。121 注与 259 场市场 artifact 未加载，`raw_delta_scale` 未使用。

本结果不能表述为 AH 或整体 EV 已修复。TOTALS 本地候选仍是独立的未授权候选；不得与本次
被拒绝的 AH 参数组合发布。
