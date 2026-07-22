# W2_SYSTEM_TRUTH_MATRIX_V1

- Generated at: `2026-07-20T12:51:47.425145Z`
- Audit SHA: `94ba834559c0beba5b38075bd358a8e92a434a51`
- Provider calls: `0`
- DB writes: `0`
- Final state: `MANUAL_APPROVAL_REQUIRED`

只读全系统审计矩阵。此文件冻结 source review SHA，并列出 calibration/formal/lock/provider canary 之前必须关闭的 P0/P1。

## Findings

| id | severity | title | required_before_unlock |
| --- | --- | --- | --- |
| P0-DATA-ASSET-REGISTRY-MISSING | P0 | Historical data assets are not governed by durable W2DataAssetRegistryV1 | Create registry, backup copy, restore drill, and code/data compatibility binding. |
| P0-PROVIDER-INTAKE-SPLIT | P0 | Provider intake has two competing chains | All provider paths must go through endpoint capture contract or be explicitly compatibility-only. |
| P0-CHECKPOINT-AUTHORITY-SPLIT | P0 | Checkpoint policy is not yet singular across scheduler/runtime/config | Remove or demote older checkpoint authority after zero-caller proof. |
| P0-RECOMMENDATION-STATE-SPLIT | P0 | Recommendation states remain distributed across legacy, analysis, V3, reporting and Dashboard projection | Single canonical V3 decision_hash must feed API, Dashboard, tracking, lock, settlement and cohort. |
| P0-F5-F8-RUNTIME-DATA-MISSING | P0 | F5/F8 are not proven runtime-ready despite local/private artifacts | Import F5 canonical DB/query path and declare one reviewed F8 as-of authority. |
| P1-RUNTIME-DEPLOYMENT-TRUTH-UNVERIFIED | P1 | Staging running SHA and DB state were not verified in this audit turn | Run read-only runtime evidence capture with approved access and bind it to this matrix. |
