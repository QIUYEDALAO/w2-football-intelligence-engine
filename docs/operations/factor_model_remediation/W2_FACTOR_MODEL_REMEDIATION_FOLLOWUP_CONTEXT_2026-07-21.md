# W2 Factor Model Remediation Follow-up Context - 2026-07-21

## User Question

用户追问：这么说，这几个缺的因子还没有解决吗？

## Context Sync Answer

结论：缺因子问题只完成了代码与 schema foundation，尚未完成真实 staging/provider 数据闭环。

已解决的是：

- canonical provider-primary team identity schema and service path
- provider team identity crosswalk schema
- canonical team match history schema and service path
- internal rating snapshot materialization from canonical match history
- controlled provider capture CLI using `request_live()`
- no-live artifacts proving `MANUAL_APPROVAL_REQUIRED`

尚未解决的是：

- staging runtime has not executed the live provider capture on the runtime DB
- Allsvenskan fixture identities are not visible in the local no-live DB
- F3/F6/F7/F9 are not yet populated with real staging rows for the smoke fixtures
- F5 remains dependent on reviewed historical AH/Foootball-Data crosswalk coverage
- F8 remains dependent on reviewed as-of squad value artifact/crosswalk coverage
- xG is not proven unavailable; it is currently `NOT_PROBED_PROVIDER_CALLS_DISABLED`

Current GitHub PR: #370.

Current source SHA: `97a0967119468d4961da1356dc276edcaef50f21`.

Final state remains `MANUAL_APPROVAL_REQUIRED`.
