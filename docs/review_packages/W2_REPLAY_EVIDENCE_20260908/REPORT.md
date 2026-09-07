# 完整捕获重放证据：本地执行交付

状态：LOCAL_IMPLEMENTED_AND_TESTED_PENDING_INDEPENDENT_REVIEW。未部署。

工作区：/Users/liudehua/Documents/Projects/w2-replay-evidence-20260908
基线：f0eab4a5；包含已交付任务3 v3的四文件修复。当前包是执行方交付，不能作为独立验收。

## 已实施

- simulation 保存完整 dataclass 输入、实际校准参数、输入权重、原始未舍入矩阵、运行选项和既有模型/校准身份。原先12位矩阵及其 hash保留。
- 所有新 capture 保存比分矩阵、输入 manifest、完整 simulation 快照及可得的因子贡献。缺失贡献显式 NOT_AVAILABLE，不虚构因子或把贡献解释成因果。
- 新证据 schema为 w2.capture_replay_evidence.v1。新增字段进入新 capture hash core；旧捕获不重写、不回填，不改变唯一键或冻结规则。新捕获 hash会变化。
- replay_simulation 只接受完整字段和匹配模型版本，重新计算并比较所有模型输出、参数、矩阵和概率；缺字段/篡改拒绝。analysis card后补的 point_estimate_component_fixture_ids 单独保留为 provenance，不冒充 simulation可计算输出。
- 捕获只写 RECORDED_PENDING_REPLAY，不预先宣称通过；旧式手工或不完整输入仍 NOT_REPLAYABLE_EXACTLY。缺证据不会通过审计，但本任务不改变现有推荐准入。
- T30现有报价引用保留。FIRST_ELIGIBLE是模型捕获，仍非每条evaluation的原始报价证明；本包不补历史89条 observation，不宣称全报价绑定已解决。

## 本地验证

最终定向测试：192 passed in 2.59s。包含实际 ReadModel/uncertainty/simulation/selector/SQLite落盘后精确概率重放、旧捕获兼容与幂等、缺字段和篡改拒绝、独立分半注结算oracle、canonical EV测试。
独立分半注 oracle覆盖比分0–7、AH双方 -4到+4每0.25、大小双方0到4每0.25，共6400个盘口/比分/方向组合。
20组合成输入与f0eab4a5旧simulation对照：去除新增证据字段后所有旧输出完全一致，涵盖neutral_site与非零sigma。真实比赛影响NOT_MEASURED。
Ruff与git diff --check通过。未跑完整Linux/PostgreSQL发布门，待老K执行。

复测命令见 DEPLOY_ORDER.md。不读取Provider、生产或秘密，不调用GitHub/GHCR，不改门禁。未启动任务3/4科学时钟，未授权正式推荐或真钱。

## 部署风险

simulation和capture JSON新增未舍入矩阵及输入，载荷增加；需独立检查API/schema兼容和线上存储增长。历史已有capture按原规则跳过，不能用旧记录证明上线新增功能未生效。记录数为0时只能报告等待新eligible捕获，不能伪造一次成功。
Git共享packed-refs.lock已存在；本轮没有删除锁。部署前需确认本地commit/基线及生产版本，禁止直接覆盖未知生产树。
