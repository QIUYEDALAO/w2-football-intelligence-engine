# V1 AH component-share calibration 自验收

状态：`CANDIDATE_REJECTED_FINAL_AH_FAMILY_ON_FROZEN_DEVELOPMENT_COHORT`。

提交顺序：`d2afa36c`（预注册）→ `a1b818a7`（单调性前提）→ `f04bf05a`
（runner/测试）→ `8e7d654b`（唯一一次结果）。

预注册 SHA-256：`c343b14e3c0be82a2595d799347ae96edd443e206f999234f2c87c9b73c1bf93`。
输入摘要：home-away `709050b581b569c874c6a8d1363ba1a6612503489d175da8b644c5df05294a02`；
xg `16fcaaad812e8007c7e828c964d7029bc223e361cdac87b122c56eba9e8e3522`。

## 结果

- full fit：`home=0.208545 / attack=0.663475 / defence=-0.112027`；
- OOF：`7,159` 场，7/10 folds、12/13 lines 改善；margin slope
  `1.173055→0.995275`；
- Bonferroni 修正后强制门仍失败：AH Brier 相对 TOTALS-only 上界
  `+0.000080417`，scoreline NLL 上界 `+0.000879910`，AH Brier 相对现役上界
  `+0.000094281`；
- TOTALS invariance：lambda 差 `1e-15`，NLL 差 `2e-15`；current share clamp 与
  candidate clamp 均为 `0`。

结果 artifact SHA-256：JSON `74c7e8830e395f871e225912cd9055023a7af885644340100ae12d8e0ab48f2`；
MD `95c5b470739fe9a4b8d02ec58bf0ffe372c76f0dfac878b7452c5c9fdf2cdce9`。

## 验证

```bash
PYTHONPATH=src:. .venv/bin/pytest -q tests/unit/test_v1_ah_component_share_calibration.py
# 4 passed

PATH="$PWD/.venv/bin:$PATH" PYTHONPATH=src:. .venv/bin/pytest -q
# 2957 passed / 9 skipped / 4 failed / 5 warnings
```

全量 4 个失败均为本轮前已存在的宿主限制：Docker Compose 插件缺失 2；macOS Docker
bind-mount 无法构造 Linux UID/GID 权限夹具 2。校准相关失败为 0。

## 结论与边界

该模型族拒绝；按协议停止在这批 8,659 场上的 AH 家族搜索。未改 V1 参数、calibration
identity、ledger、白名单、V2、migration、Provider、生产读写或部署；121 注与 259 场市场
artifact 未加载，`raw_delta_scale` 未使用。AH 与整体 EV 不能宣称已修复。

后续若继续，必须使用新的非重叠数据和新的预注册，不能改门或重跑本 cohort。
