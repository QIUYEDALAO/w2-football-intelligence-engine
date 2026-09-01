# V1 TOTALS 轴本地候选实现回执

状态：`LOCAL_IMPLEMENTED_PENDING_INDEPENDENT_ACCEPTANCE`。本回执不是 calibration grant、部署授权、盈利证明或生产有效性证明。

## 证据与决定

- 冻结预注册：`docs/operations/V1_MARKET_AXIS_CALIBRATION_PREREGISTRATION_20260901.json`，SHA-256 `a8a4f0ddc55e1d30ed69c8ee3ec8697346968c3a427f1bcba588b4aca4309bbd`，commit `303ba7bc73504f3943c45df113ff2a63634036c3`。
- 冻结结果：`V1_MARKET_AXIS_CALIBRATION_FIT.json`，SHA-256 `93f8bcf56aa4cf5ef94a225e8f3349676ef819ac3ac54374a442c7f10442b2a2`，commit `83f19de4ace76a4556086ce31de295b53882efda`。
- TOTALS 通过全部冻结开发门：`total_goals_intercept=0.885958`、`total_goals_scale=0.701191`；8/10 rolling-origin OOF folds、7/7 lines 改善，Brier 差 95% 上界 `-0.000518059`，TOTALS NLL 差 95% 上界 `-0.002243568`，总量 slope `0.670546→0.922157`，均值偏差 `-0.057321→+0.004464`，clamp 数为 0。
- TOTALS-only arm 保持净胜球回归完全不变，但因共享比分矩阵，AH mean Brier 从 `0.161094291` 变为 `0.161124982`（`+0.000030691`）。这不是 AH 修复，后续独立验收与发布决策必须保留该影响披露。
- AH 候选被拒绝：Brier 差 95% 上界 `+0.000044216`，scoreline NLL 非劣上界 `+0.002243618 > 0.001`。本实现没有加入 AH 参数。
- 已结算 121 注和 259 场市场 artifact 均未加载，未用于选参、改门或决定通过。

## 最小实现

- `CALIBRATION_VERSION` 提升为 `w2.formal.lambda_totals_axis.v2`。
- `LambdaCalibrationParams` 追加上述两个 TOTALS 参数；生产公式候选为 `clamp(0.885958 + 0.701191 * raw_total, 1.35, 4.40)`。
- 主客差轴、`home_advantage_goals=0.30`、Dixon-Coles、Elo/身价/首发权重、EV/EV-SE、准入阈值、白名单与 ledger 均未修改。
- 新 identity 为 `f98d4ef0c2b158a80eeba60ca979250736831583612ad126b6ae9010262dbc91`；旧授权 identity `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` 不匹配。默认 ledger 查询返回 `None`，运行状态为 `BASELINE_PRIOR`，因此本地候选不会形成正式推荐。

## 本地验收

- 定向命令：`.venv/bin/pytest -q tests/unit/test_calibration_validation_registry.py tests/unit/test_point_ev_calibration_authority.py tests/unit/test_simulation_engine.py tests/unit/test_point_ev_calibration_identity.py tests/contract/test_api_projection_read_authority.py tests/contract/test_src_w2_package_matrix.py`
- 结果：`129 passed`。
- 直接守卫：TOTALS 仿射总量、未夹断时 AH 主客差保持不变、完整参数变化导致 identity 变化、旧 grant 不顺延、未授权候选 fail closed。
- 全量首次运行：`.venv/bin/pytest -q`，`2952 passed / 9 skipped / 6 failed / 5 warnings`。其中唯一代码回归是旧测试仍要求新 identity 沿用旧授权，已改为断言 `BASELINE_PRIOR + MODEL_CALIBRATION_NOT_VALIDATED`；其余为当前 macOS 宿主限制：Docker Compose 插件缺失 2、裸 `python` 缺失 1、Docker Desktop bind mount 无法构造 Linux UID/GID fixture 2。
- 修正后全量命令：`PATH="$PWD/.venv/bin:$PATH" .venv/bin/pytest -q`；结果 `2954 passed / 9 skipped / 4 failed / 5 warnings`。4 个失败仅为 Docker Compose 插件缺失 2 与 Docker Desktop bind mount 无法构造 Linux UID/GID fixture 2；校准相关失败 0，SC18 在显式虚拟环境 PATH 下通过。
- `ruff check .` 通过；本次触达 Python 文件 `ruff format --check` 通过。仓库级 `ruff format --check .` 报 311 个历史文件需重排，与本次 diff 无关，未机械改写全仓。

## Stop line

Provider 调用 0、生产读 0、生产写 0、migration 0、ledger 新记录 0、部署 0、GitHub 操作 0。独立验收和 Owner 的新授权之前不得登记状态或部署。
