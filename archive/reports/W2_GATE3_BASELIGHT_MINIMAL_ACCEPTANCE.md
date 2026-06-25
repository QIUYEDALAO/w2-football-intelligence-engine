# W2 Gate 3 — Baselight 最小验收报告（纠正版）

**检查日期**: 2026-06-23 19:38 UTC  
**写报告日期**: 2026-06-24 03:48 CST

**BASELIGHT_STATUS**: `NOT_EVALUATED_SOURCE_MISMATCH`

**状态说明**: 原始报告误将 API-Sports 本地 JSON 数据称为 Baselight 数据集。
实际 Baselight 数据未被读取、未被接入。Settlement 验证逻辑本身通过，
但所验证的数据源与 Baselight 无关。因此 Baselight 状态从 LICENSE_UNVERIFIED
纠正为 NOT_EVALUATED_SOURCE_MISMATCH。

---

## 数据源声明

| 字段 | 数值 |
|------|------|
| 检查使用的来源 | API-Sports 本地 JSON (312 文件, 54 MB) |
| 是否读取 Baselight 数据集 | ❌ 否 |
| 是否接入 Baselight 数据 | ❌ 否 |
| Settlement 验证的对象 | API-Sports 赔率数据 |
| 经济报价键来源 | API-Sports 单次快照 JSON |

---

## 1. 经济报价键跨日期检查

**⚠️ 此检查针对 API-Sports 数据执行，无法外推至 Baselight 数据集。**

| 指标 | 数值 |
|------|------|
| 总报价条目 | 652,841 |
| 总报价键数 | 652,841 |
| 跨2+日期报价键 | **0** |
| 单日期报价键 | 652,841 |
| Exact duplicate | 0 |
| distinct 收集日期 | 2026-04-27 至 2026-05-04 (8 日) |

跨日期报价键为 0 是因为每条 (fixture_id, bookmaker, market, selection, line) 组合
在每个 JSON 文件中仅出现一次（单次快照布局）。该特征不提供时序变动验证能力，
不能证明任何数据集具备 historical timeline 特性。

---

## 2. Settlement 核对

**Settlement 逻辑验证通过，但验证对象为 API-Sports 数据，非 Baselight。**

使用 W2 现有 `asian_over_settlement.py` 的镜像实现与纯手工公式核对。

| 分类 | 检查数 | 匹配 | 不匹配 |
|------|--------|------|--------|
| 整盘(整数盘) | 10 | 10 | 0 |
| 半盘(±0.5) | 10 | 10 | 0 |
| ±0.25 | 10 | 10 | 0 |
| ±0.75 | 10 | 10 | 0 |
| ±1.25 | 5 | 5 | 0 |

**结果**: Settlement 逻辑 55/55 PASS ✅  
**注意**: 此结果仅证明 W2 settlement library 正确性，不构成对 Baselight 数据集的评估。

---

## 3. License / Provenance

| 字段 | 数值 |
|------|------|
| 状态 | `UNVERIFIED` |
| 实际评估对象 | API-Sports (api-sports.io) |
| 实际 license 元数据 | 未找到 |
| Baselight 数据集 license | 未查阅、未确认 |

**license 未确认，且 Baselight 数据本身未被读取。**  
如需评估 Baselight 数据集，必须在数据源接入后重新执行验收。

---

## 4. 最终 Baselight 分类

| 维度 | 数值 |
|------|------|
| Baselight 数据是否被读取 | ❌ 否 |
| Settlement 逻辑 | ✅ PASS |
| 跨日期报价键 | ❌ 0（数据布局特征） |
| License | UNVERIFIED |
| Historical timeline 证明 | ❌ 无 |
| **综合分类** | **NOT_EVALUATED_SOURCE_MISMATCH** |

---

## 约束确认

- ✅ 未下载全量 5.22 亿行
- ✅ 未构建 adapter
- ✅ 未构建 walk-forward
- ✅ 未修改 Gate3 为 CLOSED
- ✅ 未修改 master roadmap
- ✅ 未修改 W1 或 Stage7I runtime
- ✅ 未查询 provider
- ✅ 未重新分析 652,841 条数据

---

_报告由 w2-football-intelligence-engine 生成的纠正版本_
_Baselight 数据接入后方可重新评估。_
