# W2 stable_hash 迁移方案与 retry 调用点补证据

状态：DESIGN_ONLY / OWNER_DECISION_REQUIRED
日期：2026-09-24
工作树：`codex/w2-authority-20260916`，基线 `884341a72f3495492d79ad5a99f2c68fa6d9b443`

本文件只记录冻结、版本化和过渡设计；不切换任何哈希实现，不执行迁移，不改变生产读写。

## 1. 核实范围与总原则

全仓定义普查得到 9 个模块级 `stable_hash` 定义，另有 1 个脚本私有 `_stable_hash`：

| 定义位置 | 现状预映像（必须逐字节冻结） | 主要消费 | 分类 |
|---|---|---|---|
| `src/w2/markets/quote_identity.py:199-201` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` | `quote_identity_hash` | 落盘 |
| `src/w2/data_assets/registry.py:216-219` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)`；`ensure_ascii` 默认 `True` | `registry_hash`、数据集 manifest 路径/字段 | 落盘 |
| `src/w2/matchday/intake_v2.py:900-903` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)`；`ensure_ascii` 默认 `True` | capture/observation/identity/manifest/params/link/claim 等 | 落盘（claim 是短期租约值） |
| `src/w2/historical/formal_ah.py:121-123` | `json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))` | `canonical_key`、`fact_id`、`fact_hash`、quote/result 身份 | 落盘 |
| `src/w2/historical/football_data_co_uk.py:1797-1799` | `json.dumps(payload, sort_keys=True, default=str)`；默认 separators、`ensure_ascii=True` | source/row/fact/manifest/报告哈希 | 落盘 |
| `src/w2/backtest/replay.py:151-153` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)`；`ensure_ascii=True` | replay manifest/ledger/checkpoint/artifact 文件 | 落盘 |
| `src/w2/historical/existing_data_inventory.py:596-598` | 先 `_jsonable`，再 `json.dumps(..., sort_keys=True)`；默认 separators、`ensure_ascii=True` | `inventory_hash` 报告 | 落盘 |
| `src/w2/tracking/formal_results.py:62-64` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` | `snapshot_id`、`prediction_hash`、`settlement_id`、缺 ID 时的回退键 | 落盘 |
| `src/w2/settlement/settle.py:231-233` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` | `SettlementEvaluation.replay_hash` | 进程内/返回对象 |
| `scripts/build_fah_approval_package.py:244-247` | `json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)`；`ensure_ascii=True` | approval package JSON 内 `sha256` | 脚本产物 |

证据命令：

```text
rg -n '(stable_hash|_stable_hash)\(' src/w2 scripts/build_fah_approval_package.py
```

旧值必须作为不可变历史契约保留。特别是“v1”不是单一算法：紧凑/非紧凑 JSON、`ensure_ascii`、`default=str`、`_jsonable` 都是哈希预映像的一部分。既有 `src/w2/domain/canonical_serialization.py` 的 legacy profile 不能未经逐字节向量核对就充当所有旧实现的验证器。

## 2. 统一的新版本契约

### 2.1 v1 冻结

为每个消费域登记 `legacy_contract_id`，包括：模块、字段、完整 JSON 参数、UTF-8 编码、SHA-256、是否允许非有限数、类型 fallback 和历史版本。旧读路径只能按该登记的 profile 验证，不再调用“当前 stable_hash”。

### 2.2 v2 计算

新哈希统一使用 `w2.canonical-json.v2`（复用 `src/w2/domain/canonical_serialization.py` 的 `canonical_sha256`），按消费域使用不同的 `HashDomain`，并把 domain、serializer version、preimage schema 一并写入产物元数据。v2 必须：UTF-8、排序紧凑 JSON、NFC 字符串规范化、`allow_nan=False`，不使用隐式 `default=str`。现有 serializer 的 domain/version **不进入预映像**（`HASH_DOMAIN_IN_PREIMAGE=False`、`SERIALIZER_VERSION_IN_PREIMAGE=False`）；版本识别依赖独立元数据，若 Owner 要求密码学意义的域隔离，还需另立预映像 envelope 合同。

推荐存储形式是“64 位十六进制摘要 + 独立版本列/字段”，例如：

```json
{"hash_version":"w2.canonical-json.v2","hash_domain":"...","hash":"<64 hex>"}
```

不建议把 `v2:` 直接拼进现有 64 字符列：`capture_id`、`observation_id`、`link_hash`、`claim_token`、`params_hash`、`raw_payload_sha256`、`identity_hash`、`manifest_hash` 等现有列多为 `String(64)`，且有主键、外键或唯一约束。若 Owner 要求可见前缀，必须先把整条引用链扩成至少 67 字符并做约束迁移；不能截断前缀或覆盖旧值。

### 2.3 通用双读/双写窗口

1. **准备期**：增加域级 v1 verifier、v2 计算器、`hash_version`/v2 companion 字段或版本映射表；加入旧样本逐字节 golden vectors。此期不改变旧列值。
2. **双写期**：新写入同时产生 v1（兼容列）和 v2（新列/元数据）；新读优先验证 v2，缺失时按声明的 v1 profile 读取；若 v1/v2 对同一 payload 不一致，拒绝静默覆盖并记录 `HASH_VERSION_CONFLICT`。
3. **切读期**：所有消费者完成 v2 优先、v1 回退并观测一个完整留存周期后，Owner 才能批准新记录只生成 v2。历史记录仍只读 v1。
4. **收口期**：确认无旧客户端、无未迁移 FK、无 v1-only artifact 后，才可把 v2 提升为唯一写入契约；v1 字段仍保留只读，禁止重算覆盖。

回滚：停止 v2 写入，恢复 v1 写入；读路径继续接受 v2 已写记录但以 v1 为权威；不得删除 v2 行或重写历史 v1 值。若出现重复插入、唯一键冲突、FK 断裂、同 payload 双摘要分歧或读不到历史 artifact，立即回到双写期并暂停收口。

## 3. 8 个落盘消费域的迁移设计

### 3.1 quote identity（`quote_identity_hash`）

写入证据：`quote_identity.py:195`。此值经推荐决策/锁快照进入 JSON 投影，相关 quote hash 字段还见于 `dynamic_prematch_evaluations.quote_identity_hash`（`String(64)`）。`canonical_historical_ah_facts.quote_identity_hash`、`runtime_ah_settlement_facts.quote_identity_hash` 是同名的其他生成路径，不能仅凭字段名视作本实现的哈希；迁移前必须逐一核对来源。后者参与运行时 AH 事实自然唯一约束（quote identity + settlement capture）。

迁移：保留旧 `quote_identity_hash` 为 `v1`，增加 `quote_identity_hash_v2` 与版本/domain 元数据；历史读取按 v1 verifier，新增读取 v2 优先。双写期内不能按 v2 单独做 join；join 需要同一版本，或通过 `(domain, version, digest)` 映射表解析。

影响：直接覆盖可能令动态评估与推荐快照无法匹配；如查证运行时 AH 的同名字段消费此实现，唯一约束还可能把旧事实误判为新事实（重复写入）或把不同事实判为冲突。跨路径等价性尚未证明，不能直接重算历史 AH 字段。

### 3.2 data asset registry（`registry_hash` / `dataset_manifest_hash`）

写入证据：`registry.py:68-70`、`:118`；manifest hash 被拼入 `$W2_DESKTOP_BACKUP_ROOT/football-data-co-uk/<hash>` 路径。JSON registry 的 `registry_hash` 也是自校验字段。

迁移：旧 registry 文件和备份目录永久按 v1 保留；新 registry 增加 `hash_version/hash_domain/registry_hash_v2`，新备份目录采用版本化路径（如 `.../v2/<digest>`），同时保留 v1 路径别名。读取先按声明版本，未声明的历史文件固定 v1。

影响：直接改 manifest hash 会造成备份目录失联、恢复演练找不到旧备份，或把同一数据误当成新数据再次备份；registry 自校验也会全部失败。

### 3.3 matchday intake（capture/observation/identity/manifest/params/link/claim）

写入证据：`intake_v2.py:316,412,425,433,544,563,587,667,781,798,900`；schema 证据在 `matchday_intake_models.py`：`capture_id` PK、`observation_id` PK、`link_hash` PK，`capture_id` 外键链，`manifest_hash` 唯一约束，另有 `params_hash/raw_payload_sha256/identity_hash/plan_hash/claim_token` 等 64 字段。

迁移：这是最高风险域。先增加域版本映射表，至少覆盖：

- endpoint capture：`capture_id`、`params_hash`、`raw_payload_sha256`；
- market observation：`observation_id` 及其 capture FK；
- fixture identity：`identity_hash` 及 raw payload 关联；
- checkpoint plan：`plan_hash`、短期 `claim_token`；
- capture-plan link：`link_hash` 及 capture/plan FK；
- evidence manifest：`manifest_hash`、`input_manifest_hash` 及 `(fixture_id, as_of, manifest_hash)` 唯一键。

双写期物理主外键仍使用既有 v1 值，同时写 v2 companion；切读期需先部署所有 producer/consumer，再将新记录主键切到带版本的逻辑 ID。若采用 `v2:<64>`，所有上述列、外键和索引必须一次性扩容并验证；否则使用独立 `(hash_version, digest)` 身份表，禁止仅靠同一 64 字符列区分版本。

影响：直接替换会断掉 capture → observation → plan → manifest 的 FK 链；重复抓取可能绕过 `uq_matchday_endpoint_capture_identity`，同一计划可能产生重复 link；checkpoint claim 可能被旧 worker 判定为无效或错误释放。

### 3.4 formal AH（历史盘口事实）

写入证据：`formal_ah.py:554,564,577,647`；`fah_repository.py` 把 `fact_hash` 写入 `CanonicalHistoricalAhFactModel`。模型约束包括 `canonical_key/fact_id/fact_hash` 唯一，`source_snapshot_id + canonical_key` 唯一；字段还有 `quote_identity_hash/result_identity_hash`。

迁移：source snapshot、canonical key、fact id/hash、quote/result identity 各自登记版本；保留 v1 JSONL/DB 行，新增 v2 companion 或版本化事实表。新读按 artifact 声明版本，训练/回测不得把 v1/v2 事实混成同一集合。

影响：`fact_hash` 变化会绕过 `uq_canonical_historical_ah_fact_hash` 产生重复事实；`canonical_key` 变化会破坏 source snapshot 关联；`fact_id` 变化会使下游 F5/F8 的事实引用失效。

### 3.5 football-data.co.uk adapter artifacts

写入证据：`football_data_co_uk.py:357,408,558,561` 以及 `:249` manifest；产物写入 JSON/JSONL（`:238-250`）。是否进入 FAH repository 取决于后续导入流程，不能把写 artifact 与 DB 落盘混为一步。

迁移：保留既有 source/row/fact/manifest artifact 原文件及其 v1 哈希；新运行输出使用 `hash_version=v2`、独立 manifest 和目录，导入器按 manifest 版本选择 verifier。源文件原始字节 `_file_hash` 不变，不得用 stable_hash v2 替代文件 SHA-256。

影响：source_id、row_hash、fact_id/fact_hash、manifest_hash 任一变化都会改变去重和审计 lineage；重跑可能重复导入或把同一源文件识别成不同快照。

### 3.6 backtest replay

写入证据：`backtest/replay.py:62-63,113,117,126,142`；`scripts/run_stage8_replay.py:140-153` 将 manifest/ledger/checkpoint 汇总写入 `runtime/.../stage8-replay-<hash前12位>.json`。

迁移：新 replay artifact 使用 v2 manifest 元数据和新的文件名；读取器同时发现 v1/v2，按 artifact 声明版本验证。checkpoint 的 `ledger_hash` 在双读窗口不能跨版本比较；恢复必须使用与 checkpoint 相同版本。

影响：直接切换会找不到旧 artifact、恢复到不匹配的 ledger，或把同一回放误认为不同回放；文件名截断摘要还会放大碰撞排查难度。

### 3.7 existing data inventory

写入证据：`existing_data_inventory.py:79` 写 `inventory_hash`，`:596-598` 使用 `_jsonable` 后的默认空格 JSON；脚本 `scripts/inventory_existing_football_data.py` 和 `scripts/run_fah_master_pipeline.py` 写出 JSON/MD 报告。

迁移：历史报告声明为 inventory-v1 并只读；新报告写 `inventory_hash_v2`、版本和 domain，报告文件名可追加版本但保留旧路径读取。比较器必须先按版本校验，不能把 v1/v2 摘要直接作相等判断。

影响：报告被误判为“数据发生变化”，会触发重复盘点、审计差异或错误阻断；不会直接改变业务表，但会影响 FAH 门禁证据。

### 3.8 formal results / outcome ledger payloads

写入证据：`formal_results.py:137,229,476,555`。`snapshot_id`（截断 24 位）、`prediction_hash`、`settlement_id` 进入 formal snapshot/settlement JSON，并通过 `OutcomeLedgerRepository.business_key` 参与 `outcome_ledger.business_key`（PK）；完整 payload 另存 `payload_sha256`。

迁移：新增记录使用 v2 IDs 并在 payload 写明版本；历史 snapshot/settlement 仍按 v1 ID 读取。对缺 `snapshot_id` 的 `stable_hash(payload)` 回退必须永久固定 v1，不能随着默认实现变化。业务键和 payload 摘要的 v1/v2 必须分别声明，不能把同一结算作为两条记录导入。

影响：snapshot/prediction/settlement ID 变化会改变 `outcome_ledger.business_key`，造成重复账本行或 `LEDGER_IMPORT_IDENTITY_CONFLICT`；`payload_sha256` 不一致还会阻止幂等重导入。注意 repository 的 `payload_sha256/business_key` 已使用 canonical serializer legacy profile，不能与本节 stable_hash 迁移混为一谈。

## 4. `settle.replay_hash` 是否可立即统一

结论：**可以在独立小变更中立即统一，但本任务不实施。** `settle.py:196` 只生成 `SettlementEvaluation.replay_hash`，`:133` 只在 `as_dict()` 返回；全仓 `rg -n 'replay_hash' src scripts apps tests --glob '*.py'` 仅命中实现、字段、返回投影和单元测试，未发现数据库列、文件写入、外部 API 或下游比较器。

建议：先为 settlement replay 注册独立 `HashDomain`，再显式使用 `canonical_sha256(..., domain=HashDomain.SETTLEMENT_REPLAY, version=V2)`；保留字段名但附 serializer version，并更新固定测试向量。若未来把该字段写入账本或导出，必须先把它纳入落盘域清单，不能沿用“瞬时可统一”的判断。这里的 `SETTLEMENT_REPLAY` 是拟新增的枚举成员，现有代码尚无此成员。

## 5. retry 自动重试的补证据

结论：**未找到具体的生产非幂等调用点，当前不定级。**

证据：

```text
rg -n 'call_with_retry|ingestion\.retry' src scripts apps tests --glob '*.py'
src/w2/ingestion/retry.py:53:def call_with_retry[T]
tests/unit/test_stage4_ingestion.py:57:    result = call_with_retry(flaky, ...)
tests/unit/test_stage4_ingestion.py:68:    call_with_retry(lambda: ... TimeoutError(), ...)
```

生产目录没有 `from w2.ingestion.retry ...`、别名导入或 `call_with_retry(` 调用。测试中的 `flaky`/lambda 是合成函数，不产生业务副作用。`future_refresh.py`、`candidate_notifications.py` 等其他 retry loop 不调用这个通用函数，不能作为该问题的调用点证据。

因此不提出“修 retry.py”的结论。若后续发现调用点，必须补齐：文件/行、operation 的外部副作用（DB 写、Provider 请求、通知发送等）、失败后是否可能已生效、调用点幂等键/唯一约束以及自动重试边界；在此之前保持风险等级“不定级”。

## 6. Owner 拍板项与执行前门禁

Owner 需要明确：

1. v2 是否接受“64 位摘要 + 独立版本元数据”，还是要求 `v2:` 前缀并批准整条 FK/索引扩容；
2. 8 个域是否分别迁移，还是按 matchday intake → quote/formal → artifacts → ledger 的顺序分批；
3. 双写窗口长度、历史只读保留期限和 v1 artifact 归档位置；
4. 是否允许新的物理表/映射表，及其 Alembic 迁移边界；
5. `settle.replay_hash` 是否单独批准立即切换。

执行前必须有：逐域 golden vectors、现存行数/键冲突扫描、所有读写方清单、迁移与回滚演练、双读观测指标、无 Provider/生产写入的离线验证。Owner 未拍板前不得改哈希实现、数据库列、迁移或生产配置。
