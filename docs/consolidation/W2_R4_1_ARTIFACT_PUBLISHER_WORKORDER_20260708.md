# W2 工单 · R4.1 artifact 发布器 · 2026-07-08

来源:#214(FIX-D)验收备注——divergence champion 插座已在,但全库无生产路径填充 `r4_1_calibrated`,三联赛恒走 fallback。本工单让插座通电。
**红线**:纯离线产物,零 provider calls;不放行 `direction_allowed`;EV/RECOMMEND 保持关;不 enable、不碰 production;artifact 不含任何 raw payload/key。

## 0. 范围与非目标

- 目标联赛:`bundesliga`、`chinese_super_league`、`allsvenskan`(与 `R4_1_DIVERGENCE_MODEL_COMPETITIONS` 一致)。
- **巴甲明确禁用**:R4.1 eval 判 FAIL(gap +0.0538→+0.0550)。`divergence_champion.py` 的联赛集不得扩;加一条守卫测试:`brasileirao_serie_a` 永不选中 R4_1,注释链接 `W2_R4_1_MODEL_GAP_REDUCTION_EVAL_20260708.md`。
- 非目标:不改展示门、不改档位逻辑、不动 EV。

## 1. 特征同源(本工单的真正难点,先做)

R4.1 特征(8 场窗口、对手强度调整 xG、365 天半衰期时间衰减、联赛主场系数)目前只存在于 `scripts/run_w2_market_baseline_eval.py` 的 eval 实现里。**禁止在 read-model 里重写一份**——两份实现必然漂移,divergence 将变成"特征漂移检测器"。

指令:抽取 `src/w2/models/r4_1_features.py`(纯函数、stdlib):窗口/衰减/对手调整特征构建 + `_fit_r4_1_lambda_model` 所需的行构造,**eval 脚本与 read-model 共同 import 这一份**。eval 脚本改为薄封装;加特征奇偶性单测:同一 fixture 输入,eval 路径与 serving 路径特征逐值相等(±1e-9)。

## 2. 发布器脚本

`scripts/publish_w2_r4_1_artifacts.py`,离线运行:

1. 数据源:`runtime/w2_pro_day1_provider_data` 缓存(与 eval 同源)。
2. **协议同一性自检**:先按 eval 原协议(train=2024)重拟合,系数必须与 eval 报告记录值逐项一致(±1e-9),记 `protocol_identity_check: PASS`;不一致即 FAIL 退出,不产 artifact。
3. 正式拟合:全窗口(缓存内 ≤ cutoff 的全部赛季)重拟合,`train_cutoff_utc` = 缓存中最后一场已完赛 kickoff。
4. 产物:`runtime/model_artifacts/r4_1/{competition_id}.v1.json`,字段:`schema_version, competition_id, coefficients{...}, temperature, rho, home_coefficients, feature_spec{window=8, half_life_days=365, opponent_adjusted=true}, train_cutoff_utc, fit_sample_count, protocol_identity_check, source_eval_doc, artifact_hash`(hash=除 hash 外全字段的 sha256,复用 `artifact_hash()`)。
5. 团队状态:artifact **不存**每队状态快照;serving 端用 §1 的同源特征构建器从 read-model 已摄入的赛果/统计现算(as-of 纪律沿用)。若 read-model 历史深度不足 8 场窗口 → 该卡 fallback `FITTED_CALIBRATED` + reason `R4_1_FEATURE_HISTORY_INSUFFICIENT`。

## 3. 加载与写入(read-model)

1. 加载器:启动时读 `runtime/model_artifacts/r4_1/`,校验 schema + hash + `train_cutoff_utc < now`(时钟哨兵);校验失败 → 该联赛 fallback + reason `R4_1_ARTIFACT_INVALID`。
2. 写入**规范 key(唯一)**:`pricing_shadow.r4_1_calibrated = {"probabilities": {...}, "fair_ah": float, "artifact_hash": str, "artifact_version": str}`。
3. **清理 #214 的防御性 key 蔓延**:`_r4_1_model_payload` 只认 `r4_1_calibrated`,删除 `r4_1_model / r4_1_divergence_model / probabilities_r4_1_calibrated` 三种拼法及其分支。
4. provenance:卡片 `model_market_divergence` 已带 `model_family`;再透传 `artifact_hash`(审计可回指参数版本)。

## 4. 刷新策略(写进文档,不写死代码)

artifact 为版本化只增文件;月度 `market_baseline_eval` 重跑(路线图 R4 既有节奏)出新 eval → 若 gap 结论维持 → 发布 `.v2` 并在台账留痕。代码只认"目录里 hash 校验通过的最新版本"。

## 5. 验收(硬)

1. 特征奇偶性测试过(§1)。
2. 发布器跑通:三联赛 artifact 落地,`protocol_identity_check: PASS`。
3. 单测:CSL 卡(构造 read-model 历史充足)→ `model_family=R4_1_CALIBRATED`、无 fallback_reason、probabilities 和为 1、`fair_ah` 有值;历史不足 → fallback + `R4_1_FEATURE_HISTORY_INSUFFICIENT`;artifact hash 篡改 → fallback + `R4_1_ARTIFACT_INVALID`;PL 恒 FITTED;**巴甲守卫测试**(§0)。
4. `rg "r4_1_model|r4_1_divergence_model|probabilities_r4_1_calibrated" src/` 零命中。
5. 合入+下次 staging 部署后抽查:CSL/瑞典超当日卡 `model_family=R4_1_CALIBRATED`(德甲歇夏无卡,单测覆盖即可);ledger 记录透传 artifact_hash。
6. 常规:零 provider calls、零 enable、CI 绿、runtime 产物不进 git(artifact 目录加 .gitignore 确认——它是部署产物,不是源码)。

## 6. 一个开放决策(交老板,不阻塞本 PR)

artifact 是 runtime 产物不进 git,那 staging 机器上谁来生成?两个选项:①部署流程加一步"部署后跑 publisher"(数据源需在 staging 机器同步 pro-day1 缓存,或改为从 read-model DB 拟合);②artifact 作为发布工件随部署包分发(CI 产出、hash 校验)。建议 ②(可复现、可审计),但涉及部署流水线改动,单独审批。本 PR 先交付脚本+加载器+测试,artifact 分发方式由该决策定。
