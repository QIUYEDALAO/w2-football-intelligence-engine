# SCHED-DEDUP-01 复现

本包包含：

- `SCHED_DEDUP_01_REPORT_20260824.md`
- `SCHED_DEDUP_01_PROFILE_BASELINE_20260824.json`
- `SCHED_DEDUP_01_PROFILE_OPTIMIZED_20260824.json`
- `SCHED_DEDUP_01_EVIDENCE_20260824.json`

执行脚本为仓库根目录 `scripts/audit_sched_dedup_01.py`；冻结事件 manifest 复用 `docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json`。

## 前提

使用同一个批准的 PostgreSQL 隔离快照，禁止连接可写生产库：

```bash
export W2_DATABASE_URL='postgresql+psycopg://postgres@isolated-clone:5432/postgres'
export W2_ENVIRONMENT='staging'
export PGOPTIONS='-c default_transaction_read_only=on'
```

基线代码树必须是 `d3f877dd`；优化代码树必须是本分支当前提交。脚本会拒绝用优化代码树伪装 baseline，也会拒绝缺少增量实现的 optimized 运行。

## 生成 profile

从最终分支调用脚本，但分别把 `PYTHONPATH` 指向两个源码树：

```bash
PYTHONPATH=/path/to/baseline/src python scripts/audit_sched_dedup_01.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --profile baseline \
  --output /tmp/SCHED_DEDUP_01_BASELINE.json

PYTHONPATH=/path/to/optimized/src python scripts/audit_sched_dedup_01.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --profile optimized \
  --output /tmp/SCHED_DEDUP_01_OPTIMIZED.json
```

两个 profile 必须在同一静态 clone 上顺序执行；不要在中间重新从生产恢复。

## 组装与检查

```bash
python scripts/audit_sched_dedup_01.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --baseline docs/review_packages/SCHED_DEDUP_01/SCHED_DEDUP_01_PROFILE_BASELINE_20260824.json \
  --optimized docs/review_packages/SCHED_DEDUP_01/SCHED_DEDUP_01_PROFILE_OPTIMIZED_20260824.json \
  --assemble \
  --output /tmp/SCHED_DEDUP_01_EVIDENCE.json

python scripts/audit_sched_dedup_01.py \
  --manifest docs/review_packages/SCHED_PEAK_02/SCHED_PEAK_02_FROZEN_MANIFEST_20260824.json \
  --baseline docs/review_packages/SCHED_DEDUP_01/SCHED_DEDUP_01_PROFILE_BASELINE_20260824.json \
  --optimized docs/review_packages/SCHED_DEDUP_01/SCHED_DEDUP_01_PROFILE_OPTIMIZED_20260824.json \
  --check docs/review_packages/SCHED_DEDUP_01/SCHED_DEDUP_01_EVIDENCE_20260824.json
```

成功输出：`SCHED_DEDUP_01_CHECK_OK`。

检查不只依赖总 digest：即使修改 evidence 单字段后重算 digest，profile 交叉校验仍会失败。本轮 `+1e-6 wall_seconds.after` 变异实测以 `COMPARISON_MISMATCH:wall_seconds` 被拒绝。
