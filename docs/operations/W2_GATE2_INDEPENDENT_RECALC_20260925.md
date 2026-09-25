# Gate 2 独立复算报告

本报告的算例只使用手写 Poisson PMF、五态现金流和赔率算术；没有把被审计函数当作 oracle。复算日期为 2026-09-25，代码基线为 `ebe027234eff7dabae805ec8c79b1d7d783ed1a0`。

## 五态返水算例

取赔率 `o=2.0`，分布：

```text
WIN=.30, HALF_WIN=.20, PUSH=.10, HALF_LOSS=.15, LOSS=.25
```

独立算术：成功暴露 `.30 + .5*.20 = .40`，亏损暴露 `.25 + .5*.15 = .325`；纯现金流 `1*.40 - .25 - .5*.15 = .075`；绝对盈亏暴露 `.40 + .325 = .725`，返水 `0.025*.725 = .018125`，含返水现金流 `0.093125`。离线实现的单测结果与这三个数一致。

单态边界（`o=2`）：`WIN=.025`、`HALF_WIN=.0125`、`PUSH=0`、`HALF_LOSS=.0125`、`LOSS=.025`。

## 四分之一线逐点复算

- TOTALS 2.25：总进球 2 是 UNDER 的 HALF_WIN、OVER 的 HALF_LOSS。
- TOTALS 2.75：总进球 3 是 UNDER 的 HALF_LOSS、OVER 的 HALF_WIN。
- AH -0.25：主队 0-0 是 HOME 的 HALF_LOSS。
- AH -0.75：主队赢 1 球是 HOME 的 HALF_WIN。

这些是由盘口拆分规则直接计算的点质量，不依赖概率矩阵的聚合实现。

## 反解与极端赔率

对称赔率 `OVER=UNDER=2.0` 的目标去水概率为 0.5。用独立 Poisson PMF 复算当前返回的 `lambda_total_market` 后，整数线、2.25、2.5、2.75 的 UNDER 有效概率均回到 0.5（矩阵 12 球截断造成的尾部误差小于 `1e-8`）。

极端但合法赔率 `OVER=1.01, UNDER=1000` 的目标 UNDER 概率约 `0.001009`；当前实现返回 `lambda_total_market=10.0` 的上界，2.5 线有效概率约 `0.002781`，残差约 `0.001772`。这证明当前实现没有检测“目标超出反解 bracket/截断可达域”，属于审计发现，不在本 Gate 擅改。

## Track D 近似边界

`p_fade=.4, o=2.5`：纯 EV 为 `0.4*2.5-1=0`；ABS_PROFIT_V2 二元返水为 `0.025*(1.5*.4+.6)=.03`，所以近似 EV 为 `.03`。该计算把失败侧合并成全损，遇到 quarter-line 半态时不等于五态 EV；设计版本明确为 `w2.track_d.binary_abs_profit_v2.v1`，不能宣称五态等价。

## 可复现测试

新增 `tests/unit/test_gate2_fusion_audit.py`：四分之一线点质量、独立 Poisson 复算、零状态、非法/极端赔率均有断言。定向总计 `38 passed`。
