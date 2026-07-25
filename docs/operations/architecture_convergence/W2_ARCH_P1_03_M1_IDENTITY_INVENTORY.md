# ARCH-P1-03 M1 — 身份/Crosswalk 只读盘点证据

> 只读盘点，未调用 provider、未写数据库、未改 staging/生产数据。
> captured_at 2026-07-26（UTC），staging `w2` DB（只读 SSH → psql）。

## 冻结的 canonical authority

- 团队唯一权威：`canonical_teams` + `provider_team_identity_crosswalks`。
- 球员唯一权威：`player_identity_mappings`（仅 REVIEWED + 非空
  `canonical_player_id` + 完整复核来源 + 时间有效方可被模型消费）。
- `w2_team_id` 作 opaque ID，禁止代码解析其中 provider 信息；未知 provider
  identity fail-closed，禁止运行时 `stable_w2_team_id(provider_id)` 建身份。
- 不新增身份表。

## 逐表盘点

| 表 | TOTAL | ACTIVE/有效 | APPROVED/REVIEWED | CANDIDATE | CONFLICT | DISTINCT_PROVIDER_ID | DISTINCT_CANONICAL_ID | NULL_CANONICAL | OVERLAP_VALIDITY |
|---|---|---|---|---|---|---|---|---|---|
| canonical_teams | 16 | 16 | n/a | 0 | 0 | n/a | 16 | 0 | 0 |
| provider_team_identity_crosswalks（团队权威） | 16 | 16 | 16 (PROVIDER_PRIMARY_READY) | 0 | 0 | 16 (api_football) | 16 | 0 | 0 |
| team_identity_crosswalks（legacy） | 16 | 16 | 16 (APPROVED) | 0 | 0 | 16 (api_football↔tm) | n/a(无w2列) | n/a | 0 |
| football_data_team_crosswalks（legacy） | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| player_identity_crosswalks（legacy） | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| player_identity_mappings（球员权威） | **0** | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

### READERS / WRITERS / JOBS / REPORT_READERS / FOREIGN_KEYS（运行面，src+apps，排除 migrations/tests）

```text
football_data_team_crosswalks   READERS = src/w2/historical/fah_repository.py (F5 historical AH), models.py(ORM)
team_identity_crosswalks        READERS = models.py(ORM), factor_model_models.py(ORM)
provider_team_identity_crosswalks READERS = factor_model_models.py(ORM)   [authority]
player_identity_crosswalks      READERS = models.py(ORM)
player_identity_mappings        READERS = src/w2/ingestion/future_refresh_repository.py, models.py(ORM)  [authority]
JOBS / REPORT_READERS           = 0 专用 job / report 引用（仅上述 repository/ORM）
FOREIGN_KEYS:
  provider_team_identity_crosswalks.w2_team_id -> canonical_teams
  canonical_team_match_history.team_w2_id / opponent_w2_id -> canonical_teams
  team_rating_snapshots.w2_team_id -> canonical_teams
  structured_lineup_players.identity_mapping_id -> player_identity_mappings
  三张待删 legacy 表（team_identity_crosswalks / football_data_team_crosswalks /
  player_identity_crosswalks）无任何 inbound FK → 无 FK blocker。
```

## 逐行迁移预演（团队，team_identity_crosswalks 16 行）

全部 `review_status = APPROVED`，`competition = allsvenskan`，api_football ID 与
`canonical_teams` 16/16 对齐（`w2:team:api_football:<api_id>`）。迁移决策：向权威
`provider_team_identity_crosswalks` **新增 transfermarkt provider 行**（
`provider=transfermarkt`、`provider_team_id=transfermarkt_club_id` → 同一
`w2_team_id`），并迁移 review provenance；api_football 行权威中已存在。

```text
LEGACY_ROW_ID → TARGET_CANONICAL_ID → MIGRATION_DECISION
e09b7107… → w2:team:api_football:2166 → ADD_TRANSFERMARKT_PROVIDER_ROW+MIGRATE_REVIEW_PROVENANCE
de2e97a6… → w2:team:api_football:2170 → ADD_TRANSFERMARKT_PROVIDER_ROW+MIGRATE_REVIEW_PROVENANCE
13bd5276… → w2:team:api_football:2172 → …
f529df45… → w2:team:api_football:2240 → …
4c0d0f06… → w2:team:api_football:2241 → …
e1ff7f19… → w2:team:api_football:363  → …
98e1ddd9… → w2:team:api_football:364  → …
02d6d842… → w2:team:api_football:366  → …
d17a37c0… → w2:team:api_football:367  → …
63a37572… → w2:team:api_football:370  → …
c233c047… → w2:team:api_football:371  → …
f8ad7345… → w2:team:api_football:372  → …
3ff746b1… → w2:team:api_football:374  → …
b3e55aed… → w2:team:api_football:375  → …
dbf3ce7c… → w2:team:api_football:377  → …
5c8c8600… → w2:team:api_football:766  → ADD_TRANSFERMARKT_PROVIDER_ROW+MIGRATE_REVIEW_PROVENANCE
```

```text
TEAM_APPROVED_MIGRATABLE     = 16
TEAM_BLOCKED                 = 0
TEAM_MIGRATION_SUMMARY_HASH  = 2c753bec3bb22841fecf70f3d570d76d28b15bb1ded504f81d3be9f42f9a915b
```

（deterministic per-row hash 见 scratchpad `team_migration_preview.json`，逐行
`row_hash = sha256(canonical row json)`，总摘要为有序拼接后再 sha256。）

## 球员侧 / lineup 侧

```text
player_identity_crosswalks   = 0
player_identity_mappings     = 0   (球员唯一权威为空)
structured_lineup_snapshots  = 0
structured_lineup_players    = 0
```

球员身份数据与已保存 lineup **完全为空**。球员迁移为**空操作**（无可迁移行）。

## 决定性结论

- **团队侧**：迁移真实且可行（16 APPROVED legacy 行 → 补 transfermarkt provider
  行 + review provenance；权威表需先补 `review_status/reviewed_by/reviewed_at/
  source_hashes/payload` 列，不新增表）。
- **球员侧**：`player_identity_mappings`、`player_identity_crosswalks` 全空 →
  球员迁移空操作；无任何 canonical 球员身份可被模型消费。
- **M3 真实比赛验收结构性受阻**：staging `structured_lineup_snapshots = 0`、
  `structured_lineup_players = 0`、`player_identity_mappings = 0`，无法选出 3 场
  含 confirmed lineup + 22 canonical 球员的真实比赛。按指令 step 7：

```text
REAL_MATCH_EVIDENCE = BLOCKED_INSUFFICIENT_REAL_SAVED_LINEUPS
```

  不构造 synthetic staging 证据，不授权 M4。
- **M4 无 FK blocker**：3 张待删 legacy 表无 inbound FK（player 权威被
  `structured_lineup_players` FK 引用，但该表为空）。
