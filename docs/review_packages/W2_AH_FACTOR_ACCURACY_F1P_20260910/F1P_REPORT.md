# F1P 验收报告 —— 前瞻 AH 因子数据合同

```text
TASK_ID          W2_AH_FACTOR_ACCURACY_F1P_FORWARD_CONTRACT_20260910
PARENT_COMMIT    71cffa8d4ab8e7a7d4a779cc91951c97f594a261
F1P_FINAL_STATE  FORWARD_CONTRACT_READY
F2_ALLOWED       false        F3_ALLOWED  false
```

## 1. 必须先说清的四件事

1. **这是前瞻数据合同，不是历史 148 场补全。** F1 已确认 336 个单元的
   exact PIT 为 0，本任务不改变、不触碰、也不试图绕过那个结论。
   F0/F1 的产物哈希在本轮前后完全不变。
2. **不产生任何模型权重。** 模块源码里不存在任何默认权重常量，有测试扫描；
   缺 `applied_weight` 直接拒绝，绝不回填注册表默认值。
3. **不产生任何推荐方向。** 合同只记录逐因子的观测事实，没有聚合、没有 margin、
   没有 direction。
4. **不改变现役推荐链。** `src/w2/` 下未新增或修改任何文件；
   本合同只被 `scripts/quant/` 引用，生产侧无法 import 它。

**即使终态是 `FORWARD_CONTRACT_READY`，也不自动解锁 F2、F3、Provider 或 Shadow。**
F2 仍然需要未来真实、逐场、PIT 可证明的数据 cohort，以及 Owner/Codex 的单独授权。

## 2. 合同要点

完整规格见 `F1P_DATA_CONTRACT.md`，机器可读版见 `F1P_SCHEMA_CONTRACT.json`。

```text
PIT        evidence_time_utc < evaluated_at_utc，严格早于；相等/晚于/缺失/
           naive/不可解析全部 fail closed；一律解析为 aware UTC 再比较；
           created_at_utc 不在身份内，不能证明 PIT
身份       复用 w2.canonical-json.v2；三个 hash 各有明确 preimage；
           17 个受保护字段任一变化即换身份；小写 64 hex，否则拒绝
append-only 不 UPDATE 不 DELETE；同内容重写是幂等 no-op（逐字段比对后）；
           同 id 异内容报冲突；修订新建 id 并链接旧 id，必须给理由；成环拒绝
隔离       AS_OF_FACTOR_OBSERVATION 与 POST_EVENT_ENRICHMENT 分账本、单向
状态       PARTICIPATED / INSUFFICIENT_DATA / SOURCE_UNAVAILABLE /
           FACTOR_ADMISSION_FAILED / HISTORICAL_NO_FACTOR_VERDICT_IDENTITY
```

## 3. 参考账本（合成夹具，非真实比赛）

运行器用固定的合成数据演示合同，因此两次运行逐字节一致：

```text
F3_REST_FITNESS      PARTICIPATED         w=0.10  score=0.25
F9_TRUE_XG           PARTICIPATED         w=0.10  score=-0.12
F5_RECENT_AH_COVER   INSUFFICIENT_DATA    w=0.05  score=null      ← 不是 0
F6_H2H               SOURCE_UNAVAILABLE   w=0.05  score=null      ← 不是中性
F3_REST_FITNESS      PARTICIPATED         w=0.12  score=0.25   supersedes 第 1 行
```

实测行为：

```text
完全相同的重写            created=false，reason=IDEMPOTENT_NO_OP，账本仍 5 行
修订                      新建 observation_id，旧行原样保留在文件前缀
赛后 enrichment 写入后    观测账本逐字节不变
5 行全部 readback         重算 canonical hash 并逐字段核对通过
AS-OF 视图                不含任何赛后字段
```

这 5 行是**合同的用法示例**，不是任何真实比赛的证据。fixture id 用的是
明显合成的 `9000001`。

## 4. 测试

`scripts/quant/tests/test_f1p_forward_factor_contract.py`：**72 passed / 1 skipped**。

强制矩阵逐条对应：

```text
合法完整记录写入并 readback                      ✓
evidence_time 缺失 / 非法 / naive 失败            ✓（6 条参数化）
evidence_time == evaluated_at 失败                ✓
evidence_time > evaluated_at 失败                 ✓
不同 timezone 同一 UTC 瞬间归一正确                ✓（并另测 +09:00 换算后过晚仍失败）
字符串时间不能绕过 PIT                            ✓（用 ' ' < 'T' 那对时间戳锁死方向）
缺 applied_weight 失败                            ✓
默认权重不能被自动填充                            ✓（源码扫描无默认权重常量）
缺 / 非法 / 大写 hash 失败                        ✓（5 条参数化 + source_capture_sha256）
factor_input_hash 与 preimage 不一致失败          ✓
factor_verdict_hash 与 verdict 不一致失败         ✓
完全相同重复写入是幂等 no-op                      ✓
同 observation_id 不同业务字段冲突失败            ✓
supersedes 可追加且旧行不变                       ✓
supersedes 循环失败                               ✓
赛后 enrichment 不改变 AS-OF observation          ✓
历史 payload 返回 HISTORICAL_NO_FACTOR_VERDICT_IDENTITY  ✓
历史 payload 不得被解释为 ADMITTED                ✓
F3/F5/F6/F9 之外的 factor_id 失败                 ✓（6 条参数化，含大小写变体）
TOTALS 不进入 AH 因子合同                         ✓（报 MARKET_OUT_OF_CONTRACT，非因子失败）
运行器两次生成 byte-identical                     ✓
Provider / 生产库读写全程为 0                     ✓（AST 断言 + 无网络无 DB 依赖）
```

被 skip 的 1 条是 `market` 的受保护字段变异用例：`market` 由合同硬钉为
`ASIAN_HANDICAP`，任何其他值在到达身份计算前就已被拒绝，因此无法构造
"同记录不同 market"的身份对比。已在测试里写明 skip 理由，不是覆盖缺口。

## 5. 过程中修掉的一处真实设计缺陷

第一版把身份按解析后的 UTC 瞬间计算，但**存储时保留原始文本**。
后果：同一瞬间写成 `+09:00` 和 `Z` 两次，会得到相同的 `observation_id`，
却因 `evidence_time_utc` 文本不同被判成 `OBSERVATION_ID_BUSINESS_CONFLICT`——
一次合法的幂等重写被当成了伪造。

修法：存储也按解析后的瞬间归一。身份按瞬间判定，存储就必须按瞬间存。
这是"不同 timezone 同一瞬间归一正确"这条测试逼出来的，不是事后补的说明。

## 6. 边界

```text
PROVIDER_CALLS = 0            PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0       PRODUCTION_DB_WRITES = 0
DEPLOYMENT_EXECUTED = false   OBSIDIAN_WRITES = 0
F2_ALLOWED = false            F3_ALLOWED = false
```

未调用 Provider、未抓捷报、未开 live adapter / collector / capture schedule /
Track 1 forward clock、未访问生产 PostgreSQL、未部署、未 push、未开 PR、
未新建 worktree、未修改 Obsidian。

`src/w2/` 整棵树变更 0 字节（含 `prematch`、`strategy`、`api`、`dashboard`、
RecommendationDecisionV4、Scheduler、Provider allowlist、`migrations`、
`config/factors`）。F0、F1 与输入包的哈希全部不变。

**未编写迁移文件**：本任务允许写迁移草案，但落库形状需要单独授权与评审，
把它塞进本轮只会制造一个没人验收过的生产变更面。表形状建议写在
`F1P_DATA_CONTRACT.md` §7，作为将来授权时的起点。

## 7. 下一步

合同就绪不等于数据就绪。要让 F2 有真实输入，还需要：

1. 生产侧在写评估时**同时**写出这四个因子的逐场观测（含逐因子 `evidence_time`
   与 `applied_weight`）——这需要改现役写入路径，属于另一次授权；
2. 累积到足以做全局权重搜索的 AH 样本量；
3. Owner/Codex 对该 cohort 的 PIT 与身份做独立验收。

在这三件事完成之前，F2 仍然不可启动，本任务也不主张启动。
