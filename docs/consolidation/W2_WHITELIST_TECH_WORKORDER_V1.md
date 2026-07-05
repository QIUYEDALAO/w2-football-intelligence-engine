# W2 联赛白名单 · 技术员工单与验收清单 V1

面向:技术员执行 + 负责人验收。目标:把新联赛白名单从"配置就位"推进到"审计通过、staging 启用",全程受控、可验收。

## 0. 这批文件是什么

`config/competitions/national_leagues/` 下 8 个联赛档案 + 1 个 README。它们是**白名单登记**,不是启用:

| 档案 | 联赛 | 现在在赛 | enabled |
|---|---|---|---|
| brasileirao_serie_a.v1.json | 巴西甲 | 是 | false |
| argentina_primera.v1.json | 阿甲 | 是 | false |
| allsvenskan.v1.json | 瑞典超 | 是 | false |
| eliteserien.v1.json | 挪超 | 是 | false |
| mls.v1.json | 美职联 | 是 | false |
| chinese_super_league.v1.json | 中超 | 是 | false |
| eredivisie.v1.json | 荷甲 | 否(8月) | false |
| primeira_liga.v1.json | 葡超 | 否(8月) | false |

五大联赛档案已在 `config/competitions/top_five/`;世界杯 `world_cup_2026.v1.json` 已 enabled。

## 1. 关键前提(技术员必读)

- API key 环境变量:`W2_API_FOOTBALL_API_KEY`(适配器 `src/w2/providers/api_football.py`)。
- 纪律:把任何 `enabled` 从 false 翻 true,必须**覆盖审计通过 + 单独 PR(带配额/回滚/staging 证据)**,且**只在 staging 先开**。见 `config/competitions/README.md`。
- ⚠ 已知坑:现有 `scripts/run_stage14a_league_audit.py` 调 `run_top_five_audit()`,**只审 top_five 且不打 API**("No API calls were made")。它不能审新联赛,别拿它的 PASS 当数。

## 2. 工单(按顺序执行)

### 步骤 1 — 档案就位校验(离线,现在可做)
- 确认 8 个 `national_leagues/*.json` 存在、`enabled=false`、schema 与 `top_five` 一致(已预校验通过)。
- **改代码点**:确认竞赛 registry(`src/w2/competitions/registry.py`)会**扫描 `national_leagues/` 子目录**。若现在只扫 `top_five` + `world_cup`,需扩展加载路径,否则新档案不被系统发现。
- 交付:`registry` 能列出 8 个新 `competition_id`,且都 `enabled=false`。

### 步骤 2 — 逐联赛覆盖审计(在赛 6 个:巴西/阿甲/瑞典/挪威/美职联/中超)
- **改代码点**:把审计从 top_five-only、离线,扩展为对 `national_leagues` 逐联赛、用 `W2_API_FOOTBALL_API_KEY` **实拉**验证(复用 `src/w2/operations/leagues.py` 的审计逻辑 + `providers/api_football.py`)。
- 受控:走 endpoint allowlist + 每 tick hard cap + ledger,别全量狂拉。
- 每个联赛核 7 项,逐项记 PASS/FAIL(见第 3 节)。
- 交付:一份 `reports/W2_WHITELIST_AUDIT_<league>.json`,每项 PASS/FAIL + 证据(样本 fixture id)。

### 步骤 3 — 启用(仅审计全过的联赛,仅 staging)
- 该联赛 `coverage_profile` 各项从 `NOT_AUDITED_STAGE14_REQUIRED` 改为实测结论(`AUDITED_OK` / `AUDITED_THIN`)。
- `enabled` 改 true,**仅 staging 环境**;production 不动。
- 未过审的联赛保持 `enabled=false`,系统按契约降级 `SKIP / COVERAGE_NONE`,不硬出。

### 步骤 4 — 端到端确认
- 对已启用联赛跑当日比赛日流程(`w2-matchday --date today` 或现有等价入口),确认每场产出一张 DecisionCard(pick 或带 reason_code 的非推荐),非空、非崩。

## 3. 每个联赛的覆盖审计项(步骤 2 的 7 项)

| 项 | 判定标准 | 来源 |
|---|---|---|
| provider_mapping | `api_football_league_id` 实拉确认 = 正确联赛/赛季(名称、国家、队数匹配) | API-Football `/leagues` |
| fixtures | 能取到该联赛未来赛程 | `/fixtures` |
| results | 能取到已完赛比分 | `/fixtures` |
| xg | `/fixtures/statistics` 有 xG 覆盖 | API-Football |
| lineups_injuries | 首发/伤停可得 | API-Football |
| bookmaker_depth | 盘口达标(≥ 约定 bookmaker 数,AH/OU 有线) | 盘口源 |
| squad_value | Transfermarkt 身价映射就位 | 内部数据集 |

必须全过才可翻 `enabled`(阿甲额外确认:28 队、按平均分降级、多赛事同名要选对 id)。

## 4. 验收清单(负责人勾选)

按联赛逐个验收:

- [ ] registry 能发现并加载 `national_leagues/` 全部 8 档,均 `enabled=false`
- [ ] 审计对**在赛 6 个联赛实打了 API**(ledger 有请求记录,非离线 PASS)
- [ ] 每联赛 7 项覆盖有 PASS/FAIL 报告 + 证据 fixture id
- [ ] 仅"7 项全过"的联赛被翻 `enabled=true`,且**仅 staging**
- [ ] 未过审联赛保持 `enabled=false`,当日跑流程时降级为 `SKIP/COVERAGE_NONE`(不硬出)
- [ ] 单日 provider 用量在 hard cap 内,未触发配额告警
- [ ] 已启用联赛 `w2-matchday` 当日出卡,pick/非推荐都带完整字段(含 reason_code)
- [ ] 中超:启用前确认已挂逐场完整性闸(异常赔率/死局);美职联:已核世界杯期间赛程扰动
- [ ] production 环境 `enabled` 全程未被改动

## 5. 一句话交代

技术员先解决两个"改代码点"(registry 扫新目录、审计改实拉),再对在赛 6 个联赛跑实拉审计,过审的只在 staging 开。负责人按第 4 节逐项验收。全程 production 不动、配额受控。
