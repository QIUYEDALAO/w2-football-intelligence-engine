# W2 Recommendation Capabilities V1

`config/capabilities/recommendation_capabilities.v1.json` 是对外能力状态的唯一权威。它将代码存在、契约/本地/隔离/staging 验证、功能启用、公开可用和 production 启用分离表达。

`/v1/version.capability_manifest` 公开同一份 manifest 的 schema、SHA-256 和能力摘要。Web 与产品端不得从环境变量、代码字段存在或 staging 历史通过推断能力是否可用。

旧 `W2_FORMAL_RECOMMENDATION_ENABLED` 保留为 legacy admission 输入：只有 `formal_ah.feature_enabled=true` 时它才可能允许 formal AH；它不能单独开放功能。默认 manifest 保持 formal AH/OU、LMM 数值调整、recommendation lock 和 production recommendation 关闭。

manifest 缺失、schema 不兼容、缺少能力、public 但 feature disabled、或 production 但 non-public 时会 fail closed。
