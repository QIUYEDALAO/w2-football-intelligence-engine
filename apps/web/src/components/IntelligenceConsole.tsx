import { useEffect, useMemo, useState, type ReactNode } from "react";
import { translateCompetition, translateReason, translateTeam } from "../lib/formatters";
import type {
  IntelligenceState,
  IntelligenceWorkspace,
  RiskAxisName,
  WorkspaceAttentionItem,
  WorkspaceMarket,
  WorkspaceMatch,
} from "../types/intelligenceWorkspace";

const STATE_LABELS: Record<IntelligenceState, string> = {
  COLLECTION_INCIDENT: "采集异常",
  DATA_INCOMPLETE: "数据不完整",
  MODEL_DIAGNOSTIC_WARNING: "模型诊断警告",
  MARKET_ANOMALY: "市场异常",
  MODEL_MARKET_DISAGREEMENT: "模型与市场分歧",
  MARKET_MOVEMENT: "盘口变化",
  MARKET_STABLE: "市场稳定",
};

const RISK_LABELS: Record<RiskAxisName, string> = {
  EVENT_RISK: "事件风险",
  DATA_RISK: "数据风险",
  MODEL_RISK: "模型风险",
  COLLECTION_RISK: "采集风险",
};

const NAVIGATION = [
  ["attention", "关注情报"],
  ["matches", "今日比赛"],
  ["market-radar", "市场雷达"],
  ["model-lab", "模型实验室"],
  ["validation", "赛后验证"],
  ["history", "前向记录 / 回放"],
  ["external", "外部情报"],
  ["operations", "数据与系统"],
] as const;

const STATUS_LABELS: Record<string, string> = {
  ANALYSIS_REFERENCE: "分析参考",
  ADVISORY: "提示模式",
  ATTENTION: "需关注",
  AVAILABLE: "可用",
  AVAILABLE_WITH_GAPS: "可用（有缺口）",
  BLOCKED_DAY: "当日阻塞",
  BLOCKED: "阻塞",
  COLLECTION: "采集",
  DATA: "数据",
  DEGRADED: "降级",
  DISCRETE_REAL_PATH: "真实离散轨迹",
  EMPTY_DAY: "空比赛日",
  EXPECTED: "预计应提供",
  EXPECTED_NEAR_KICKOFF: "临近开赛预计提供",
  FAIL: "未通过",
  FRESH: "新鲜",
  HEALTHY: "健康",
  INSUFFICIENT: "证据不足",
  IDENTITY_NOT_READY: "身份映射未就绪",
  INCIDENT: "异常",
  MARKET_OUTSIDE_MODEL_RANGE: "市场超出模型区间",
  MARKET_NOT_READY: "市场证据未就绪",
  MARKET: "市场",
  MISSING_OUTCOMES: "缺少部分赛果",
  MODEL: "模型",
  MODEL_OUTSIDE_MARKET_RANGE: "模型超出市场区间",
  COMPARABLE_WITHIN_MARKET_RANGE: "模型与市场处于可比区间",
  NOT_AVAILABLE: "暂不可用",
  NOT_READY: "尚未就绪",
  NOT_CONNECTED: "尚未连接",
  NOT_DEFINED: "尚未定义",
  NOT_PROVEN: "尚未证实",
  NOT_EXPECTED_YET: "当前尚不应提供",
  NO_EDGE: "未证明增量能力",
  OFF: "关闭",
  OK: "正常",
  ONE_OBSERVATION_NOT_A_TREND: "单次观测，不构成趋势",
  NO_TIMELINE_EVIDENCE: "暂无时间线证据",
  PROTECTED: "额度受保护",
  PROTECTED_DEGRADED: "额度受保护（降级）",
  PRICE_MOVEMENT: "盘口变化",
  PROVIDER_EMPTY: "来源数据为空",
  READY: "就绪",
  SAMPLE_BUILDING: "样本积累中",
  STABLE: "稳定",
  STALE: "已过期",
  TOO_EARLY: "时间尚早",
  UNAVAILABLE: "不可用",
  UNKNOWN: "状态未读取",
};

const MARKET_LABELS: Record<string, string> = {
  ASIAN_HANDICAP: "让球",
  TOTALS: "大小球",
};

const SIDE_LABELS: Record<string, string> = {
  HOME: "主队",
  AWAY: "客队",
  OVER: "大",
  UNDER: "小",
};

const EXTERNAL_LABELS: Record<string, string> = {
  weather: "天气",
  news: "新闻",
  sentiment: "舆情",
  advanced_xg: "高级 xG",
};

const EXCLUSION_REASON_LABELS: Record<string, string> = {
  MARKET_IDENTITY_NOT_READY: "市场身份未就绪",
  SCORELINE_NOT_READY: "比分证据未就绪",
  RESULT_MISSING: "缺少赛果",
};

function text(value: unknown, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function label(value: unknown, fallback = "暂无"): string {
  const raw = text(value, "");
  return raw ? STATUS_LABELS[raw] || translateReason(raw) : fallback;
}

function percent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function decimal(value: number | null): string {
  return value === null ? "—" : value.toFixed(4);
}

function marketPrice(value: unknown): string {
  const candidate = value && typeof value === "object" && "median" in value ? value.median : value;
  if (typeof candidate === "number" && Number.isFinite(candidate)) return candidate.toFixed(2);
  return typeof candidate === "string" && candidate ? candidate : "暂无";
}

function localTime(value: string | null): string {
  if (!value) return "时间待确认";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date).replaceAll("/", "-");
}

function nextEvaluation(value: string | null, generatedAt: string | null): string {
  if (!value) return "暂无未来评估时间";
  const next = new Date(value).valueOf();
  const generated = generatedAt ? new Date(generatedAt).valueOf() : Number.NaN;
  if (!Number.isNaN(next) && !Number.isNaN(generated) && next <= generated) return "评估时间已过期";
  return `下次评估 ${localTime(value)}`;
}

function providerBudgetLabel(value: string): string {
  return value === "UNKNOWN" ? "额度未读取（只读页面不查询 Provider）" : label(value);
}

function leagueName(league: IntelligenceWorkspace["validation"]["league_performance"][number]): string {
  if (league.identity_status === "RESOLVED" && league.competition_name) return translateCompetition(league.competition_name);
  return `联赛名称待解析（ID: ${league.source_league}）`;
}

function matchName(match: WorkspaceMatch): string {
  return `${translateTeam(match.home_team_name)} vs ${translateTeam(match.away_team_name)}`;
}

function marketFactLabel(match: WorkspaceMatch): string {
  const market = Object.values(match.market_radar.markets).find((item) => item.main_line === match.market_fact.main_line);
  if (!market || !match.market_fact.main_line) return "盘口暂不可用";
  return `${MARKET_LABELS[market.market] || market.market} ${match.market_fact.main_line}`;
}

function StateBadge({ state }: { state: IntelligenceState }) {
  return <span className={`workspace-state workspace-state--${state.toLowerCase()}`} data-code={state} title={state}>{STATE_LABELS[state]}</span>;
}

function SectionHeading({ eyebrow, title, detail }: { eyebrow: string; title: string; detail?: string }) {
  return <header className="workspace-section-heading"><div><span>{eyebrow}</span><h2>{title}</h2></div>{detail ? <p>{detail}</p> : null}</header>;
}

function KeyValue({ label: title, value, mono = false }: { label: string; value: unknown; mono?: boolean }) {
  return <div className="workspace-key-value"><span>{title}</span><strong className={mono ? "is-mono" : undefined}>{text(value)}</strong></div>;
}

function TechnicalDetails({ children }: { children: ReactNode }) {
  return <details className="technical-details"><summary>技术详情</summary><div>{children}</div></details>;
}

function RiskGrid({ match }: { match: WorkspaceMatch }) {
  return (
    <div className="workspace-risk-grid" aria-label="四轴风险">
      {(Object.keys(RISK_LABELS) as RiskAxisName[]).map((axis) => {
        const risk = match.risks[axis];
        const summary = risk.status === "OK" ? "当前未见风险证据" : "需要复核相关证据";
        return <div className={`workspace-risk workspace-risk--${risk.status.toLowerCase()}`} data-risk-axis={axis} key={axis} title={`${axis}: ${risk.explanation}`}><span>{RISK_LABELS[axis]}</span><strong>{label(risk.status)}</strong><small>{summary}</small></div>;
      })}
    </div>
  );
}

function Attention({ generatedAt, items, matches, onSelect }: { generatedAt: string | null; items: WorkspaceAttentionItem[]; matches: WorkspaceMatch[]; onSelect: (id: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const nameById = new Map(matches.map((match) => [match.fixture_id, matchName(match)]));
  const visible = expanded ? items : items.slice(0, 5);
  return (
    <section className="workspace-panel attention-panel" id="attention" data-ui="attention">
      <SectionHeading eyebrow="优先级情报流" title="关注情报" detail={`${items.length} 条`} />
      <div className="attention-table" data-ui="attention-feed" role="list">
        {visible.length ? visible.map((item) => (
          <button className="attention-row" data-intelligence-state={item.intelligence_state} key={item.fixture_id} onClick={() => onSelect(item.fixture_id)} role="listitem" title={`${item.factual_summary} · 影响 ${item.affected_domains.join(" · ")} · ${item.reason_codes.join(" · ")} · ${item.readiness_context.reason_code || "NO_REASON_CODE"} · next_eval_at=${item.next_eval_at || "TIME_NOT_AVAILABLE"}`} type="button">
            <div><StateBadge state={item.intelligence_state} /><strong>{nameById.get(item.fixture_id) || item.fixture_id}</strong><time>{localTime(item.kickoff_utc)}</time></div>
            <p>{STATE_LABELS[item.intelligence_state]} · {item.reason_codes.slice(0, 1).map(translateReason).join("；") || label(item.readiness_status)}</p>
            <small>影响：{item.affected_domains.map((domain) => label(domain)).join(" · ") || "待确认"} · {nextEvaluation(item.next_eval_at, generatedAt)}</small>
          </button>
        )) : <div className="workspace-empty"><strong>暂无关注项</strong><span>读取模型明确返回空比赛日。</span></div>}
      </div>
      {items.length > 5 ? <button className="text-action" onClick={() => setExpanded((value) => !value)} type="button">{expanded ? "收起" : `查看全部（${items.length}）`}</button> : null}
    </section>
  );
}

function MatchBoard({ matches, selectedId, onSelect }: { matches: WorkspaceMatch[]; selectedId: string | null; onSelect: (id: string) => void }) {
  return (
    <section className="workspace-panel match-board-panel" id="matches" data-ui="match-board">
      <SectionHeading eyebrow="13 联赛观察池" title="今日比赛" detail={`${matches.length} 场`} />
      {matches.length ? <div className="match-board-table"><div className="match-board-head"><span>时间 / 联赛</span><span>比赛</span><span>状态</span><span>主盘口</span></div><div className="match-board-body">{matches.map((match) => (
        <button aria-pressed={match.fixture_id === selectedId} className={match.fixture_id === selectedId ? "match-board-row is-selected" : "match-board-row"} data-fixture-id={match.fixture_id} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} type="button">
          <span><time>{localTime(match.kickoff_utc)}</time><small>{translateCompetition(match.competition_name || match.competition_id)}</small></span>
          <strong>{matchName(match)}</strong>
          <span><StateBadge state={match.intelligence_state} /><small>{label(match.readiness.status)}</small></span>
          <b className="match-board-market">{marketFactLabel(match)}</b>
        </button>
      ))}</div></div> : <div className="workspace-empty"><strong>今日暂无比赛</strong><span>未生成任何合成比赛或替代数据。</span></div>}
    </section>
  );
}

function Inspector({ generatedAt, match }: { generatedAt: string | null; match: WorkspaceMatch | null }) {
  if (!match) return <section className="workspace-panel workspace-empty inspector-panel" data-ui="match-inspector"><strong>尚未选择比赛</strong><span>只有真实比赛存在时才会显示分析。</span></section>;
  return (
    <section className="workspace-panel inspector-panel" data-ui="match-inspector">
      <SectionHeading eyebrow={`比赛 ${match.fixture_id}`} title={matchName(match)} detail={`${translateCompetition(match.competition_name || match.competition_id)} · ${localTime(match.kickoff_utc)}`} />
      <div className="selected-summary"><div><StateBadge state={match.intelligence_state} /><span>{label(match.readiness.status)}</span></div><strong>{marketFactLabel(match)}</strong><small>当前主盘口事实</small></div>
      <div className="inspector-grid">
        <div><span>W2 分析</span><strong>{label(match.w2_analysis.status)}</strong><small>{label(match.w2_analysis.proof_status)}</small></div>
        <div><span>模型视图</span><strong>{label(match.w2_analysis.model_view.status)}</strong><small>{label(match.w2_analysis.model_view.calibration_status)}</small></div>
        <div><span>市场视图</span><strong>{label(match.market_fact.status)}</strong><small>{marketFactLabel(match)}</small></div>
        <div><span>正式建议</span><strong className="is-off">保持关闭</strong><small>候选 / 锁定 / 生产均关闭</small></div>
      </div>
      <div className="relation-grid">{Object.values(match.w2_analysis.model_market_relation).map((relation) => <div key={relation.market}><span>{MARKET_LABELS[relation.market] || relation.market}</span><strong>{label(relation.status)}</strong><small>盘口 {relation.canonical_line || "待确认"} · {relation.bookmaker_count} 家 · {label(relation.freshness_status)}</small></div>)}</div>
      <RiskGrid match={match} />
      <div className="readiness-strip"><KeyValue label="就绪状态" value={label(match.readiness.status)} /><KeyValue label="阵容预期" value={label(match.readiness.lineup_expectation)} /><KeyValue label="阵容状态" value={label(match.readiness.lineup_status)} /><KeyValue label="评估时间" value={nextEvaluation(match.readiness.next_eval_at, generatedAt)} /></div>
      <div className="reason-summary">{match.intelligence_reason_codes.slice(0, 2).map((reason) => <span key={reason}>{translateReason(reason)}</span>)}</div>
      <TechnicalDetails><code>{match.intelligence_state}</code><code>{match.w2_analysis.status}</code><code>{match.w2_analysis.proof_status}</code><code>{match.formal_recommendation.reason}</code><code>{match.readiness.reason_code || "NO_REASON_CODE"}</code><code>next_eval_at={match.readiness.next_eval_at || "NOT_AVAILABLE"}</code><code>{match.readiness.lineup_expectation || "NOT_AVAILABLE"}</code><code>{match.readiness.lineup_status || "NOT_AVAILABLE"}</code>{match.intelligence_reason_codes.map((reason) => <code key={reason}>{reason}</code>)}</TechnicalDetails>
    </section>
  );
}

function MarketTimeline({ market }: { market: WorkspaceMarket }) {
  return (
    <div className="discrete-timeline" data-real-point-count={market.timeline_points.length} data-snapshot-state={market.snapshot_state}>
      <div><span>{label(market.snapshot_state)}</span><small>{market.snapshot_count} 个快照 · {market.observation_count} 次观测</small></div>
      {market.timeline_points.length < 2 ? <p>{market.timeline_points.length === 0 ? "暂无时间线证据，不推断走势。" : "仅一次观测，不构成趋势。"}</p> : <ol>{market.timeline_points.map((point, index) => <li key={point.capture_id || `${point.captured_at}-${index}`}><time>{localTime(point.captured_at)}</time><strong>{point.canonical_line || "无盘口"}</strong><span>{point.bookmaker_count} 家</span></li>)}</ol>}
    </div>
  );
}

function MarketPrices({ market }: { market: WorkspaceMarket }) {
  if (!Object.keys(market.prices).length) return <div className="market-prices" data-ui="market-prices"><p>暂无价格证据</p></div>;
  const sides = market.market === "ASIAN_HANDICAP" ? ["HOME", "AWAY"] : ["OVER", "UNDER"];
  return <div className="market-prices" data-ui="market-prices">{sides.map((side) => {
    const available = Object.prototype.hasOwnProperty.call(market.prices, side);
    return <span data-price-side={side} key={side}><small>{SIDE_LABELS[side]}</small><strong>{available ? marketPrice(market.prices[side]) : "暂无"}</strong></span>;
  })}</div>;
}

function MarketRadar({ match }: { match: WorkspaceMatch | null }) {
  return (
    <section className="workspace-panel market-radar-panel" id="market-radar" data-ui="market-radar">
      <SectionHeading eyebrow="持久化真实证据" title="市场雷达" detail="0 / 1 / 2+ 快照" />
      {match ? <div className="market-grid">{Object.values(match.market_radar.markets).map((market) => <article className="market-card" data-market={market.market} key={market.market}><header><div><span>{MARKET_LABELS[market.market] || market.market}</span><small>{label(market.status)}</small></div><b>{market.main_line || "—"}</b></header><div className="market-metrics"><KeyValue label="机构" value={`${market.bookmaker_count} 家`} /><KeyValue label="新鲜度" value={label(market.freshness.status)} /><KeyValue label="变化" value={label(market.movement.status)} /></div><MarketPrices market={market} /><MarketTimeline market={market} /><TechnicalDetails><code>{market.market}</code><code>{market.snapshot_state}</code><code>{market.status}</code><code>{text(market.freshness.status, "NOT_AVAILABLE")}</code></TechnicalDetails></article>)}</div> : <div className="workspace-empty"><span>尚未选择市场证据。</span></div>}
    </section>
  );
}

function ModelLab({ match }: { match: WorkspaceMatch | null }) {
  const history = match?.model_lab.historical_validation || {};
  const marketStatuses = match ? [...new Set(Object.values(match.model_lab.market).map((market) => label(market.status)))] : [];
  return (
    <section className="workspace-panel model-lab-panel" id="model-lab" data-ui="model-lab">
      <SectionHeading eyebrow="诊断对比" title="模型实验室" detail="模型 / 市场 / 外部基准" />
      {match ? <><div className="model-lab-grid"><div><span>W2 模型</span><strong>{label(match.model_lab.w2_model.status)}</strong><small>{match.model_lab.w2_model.model_version || "版本待确认"}</small></div><div><span>市场</span><strong>{marketStatuses.join(" · ")}</strong><small>{Object.entries(match.model_lab.market).map(([name, market]) => `${MARKET_LABELS[name] || name}：${label(market.status)}`).join("；")}</small></div><div><span>外部模型</span><strong>{label(match.model_lab.api_football_prediction.status)}</strong><small>仅作独立基准</small></div></div><div className="model-relations">{Object.values(match.model_lab.relation).map((relation) => <article key={relation.market}><header><span>{MARKET_LABELS[relation.market] || relation.market}</span><strong>{label(relation.status)}</strong></header><small>模型与市场差异仅用于诊断；优先检查模型校准、特征时效、盘口身份和数据质量。</small><TechnicalDetails>{relation.diagnostics.map((row, index) => <code key={`${relation.market}-${index}`}>{JSON.stringify(row)}</code>)}<code>{relation.status}</code></TechnicalDetails></article>)}</div><div className="phase-context" data-ui="phase-0-5-context" title={`HISTORICAL_INCREMENTAL_EDGE=${text(history.historical_incremental_edge, "NOT_PROVEN")}`}><span>历史结论复用</span><strong>{label(history.final_verdict)} · V 门槛 {label(history.v_continuation_gate)} · 增量能力 {label(history.historical_incremental_edge)}</strong><small>Phase 0.5 未重新执行</small></div></> : <div className="workspace-empty"><span>尚无所选模型证据。</span></div>}
    </section>
  );
}

function Scoreline({ match }: { match: WorkspaceMatch | null }) {
  const scoreline = match?.scoreline_reference;
  const ready = scoreline?.status === "READY" && scoreline.simulations_completed === 10_000;
  return (
    <section className="workspace-panel scoreline-panel" data-ui="scoreline-top3">
      <SectionHeading eyebrow={ready ? "10,000 次既有模拟" : "比分参考"} title="比分 Top 3" detail="读取时不重新模拟" />
      <div className="scoreline-context" data-ui="scoreline-context"><span>模型 {label(match?.w2_analysis.model_view.status)}</span><span>就绪 {label(match?.readiness.status)}</span><span>{label(match?.readiness.reason_code)}</span></div>
      {ready && scoreline ? <div className="scoreline-grid">{scoreline.top3.map((row, index) => <article key={`${row.scoreline}-${index}`}><span>#{index + 1}</span><strong>{row.scoreline}</strong><b>{percent(row.unconditional_probability)}</b><small>无条件概率 · 样本 {row.sample_count}</small></article>)}</div> : <div className="workspace-empty"><strong>{label(scoreline?.status || "UNAVAILABLE")}</strong><span>{scoreline?.status === "READY" ? "就绪状态必须精确对应 10,000 次模拟。" : "尚无比分参考。"}</span></div>}
      <TechnicalDetails><code>simulations_completed={scoreline?.simulations_completed ?? "NOT_AVAILABLE"}</code><code>unconditional_probability</code>{scoreline?.top3.map((row, index) => <code key={index}>sample_count={row.sample_count}</code>)}<code>{scoreline?.proof_status || "NOT_PROVEN"}</code><code>{match?.readiness.reason_code || "NO_REASON_CODE"}</code></TechnicalDetails>
    </section>
  );
}

function Validation({ workspace }: { workspace: IntelligenceWorkspace }) {
  const { probability, directional } = workspace.validation;
  const forward = workspace.validation.forward_validation_records;
  const excludedReasons = Object.entries(forward.excluded_by_reason).sort((left, right) => right[1] - left[1]).slice(0, 3);
  const directionReady = directional.status === "AVAILABLE" && directional.probability_evidence_ready;
  return (
    <section className="workspace-panel validation-panel" id="validation" data-ui="validation">
      <SectionHeading eyebrow="概率质量优先" title="赛后验证 / 前向验证" detail={label(probability.status)} />
      <div className="validation-summary"><KeyValue label="W2 Brier" value={decimal(probability.model_brier)} /><KeyValue label="市场 Brier" value={decimal(probability.market_brier)} /><KeyValue label="W2 LogLoss" value={decimal(probability.model_log_loss)} /><KeyValue label="校准误差" value={decimal(probability.model_calibration_error)} /><KeyValue label="方向记录" value={directionReady ? percent(directional.direction_accuracy) : "仅作样本记录"} /><KeyValue label="有效样本" value={directional.effective_n} /></div>
      {!directionReady ? <p className="probability-warning">概率质量证据不足，方向指标仅作样本记录</p> : null}
      <div className="forward-strip"><span>前向记录</span><strong>{label(forward.status)}</strong><small>验证 {forward.validation_count} · 可纳入 {forward.eligible_count} · 排除 {forward.excluded_count}（{percent(forward.excluded_share)}）· 待定 {forward.pending_count}</small><span>命中 {text(forward.outcomes.hit_count)} / 未命中 {text(forward.outcomes.miss_count)} / 走盘 {text(forward.outcomes.push_count)} / 无效 {text(forward.outcomes.void_count)}</span></div>
      {forward.excluded_count ? <div className="exclusion-reasons" data-ui="exclusion-reasons"><strong>排除原因</strong>{excludedReasons.length ? excludedReasons.map(([reason, count]) => <span key={reason}>{EXCLUSION_REASON_LABELS[reason] || "其他已记录原因"} <b>{count}</b></span>) : <span>排除原因尚未投影</span>}</div> : null}
      <TechnicalDetails><div data-ui="validation-checkpoint">{Object.entries(probability.checkpoint_metadata).length ? Object.entries(probability.checkpoint_metadata).map(([key, value]) => <code key={key}>{key}={text(value)}</code>) : <code>CHECKPOINT_METADATA_NOT_AVAILABLE</code>}</div><code>{probability.status}</code><code>source_directional_status={directional.source_status}</code><code>probability_evidence_ready={String(directional.probability_evidence_ready)}</code><code>{directional.market_direction_benchmark}</code>{Object.entries(forward.excluded_by_reason).map(([reason, count]) => <code key={reason}>{reason}={count}</code>)}</TechnicalDetails>
    </section>
  );
}

function LeaguePerformance({ workspace }: { workspace: IntelligenceWorkspace }) {
  const leagues = workspace.validation.league_performance;
  return (
    <section className="workspace-panel league-panel" data-ui="league-performance">
      <SectionHeading eyebrow="分联赛样本" title="联赛表现" detail={`有验证样本的联赛 ${leagues.length}（运行白名单 13）`} />
      <div className="league-table"><div className="league-table-head"><span>联赛</span><span>验证 N</span><span>有效 N</span><span>方向记录</span><span>Brier</span><span>状态</span></div>{leagues.length ? leagues.map((league) => <div className="league-table-row" key={`${league.source_league}-${league.league}`}><strong>{leagueName(league)}</strong><span>{league.validation_n}</span><span>{league.decisive_n}</span><span>{league.probability_evidence_ready ? percent(league.direction_accuracy) : "仅记录"}</span><span>{decimal(league.brier)}</span><span title={league.statistical_status}>{label(league.statistical_status)}</span><TechnicalDetails><code>source_league={league.source_league}</code><code>canonical_competition_id={league.canonical_competition_id || "UNRESOLVED"}</code><code>identity_status={league.identity_status}</code><code>source_status={league.source_statistical_status}</code><code>log_loss={league.log_loss ?? "NOT_AVAILABLE"}</code><code>calibration={league.calibration ?? "NOT_AVAILABLE"}</code></TechnicalDetails></div>) : <div className="workspace-empty"><span>联赛样本仍在积累。</span></div>}</div>
    </section>
  );
}

function History({ workspace }: { workspace: IntelligenceWorkspace }) {
  const forward = workspace.validation.forward_validation_records;
  const replay = workspace.validation.history_replay;
  return (
    <section className="workspace-panel" id="history" data-ui="history-replay">
      <SectionHeading eyebrow="已知时点证据" title="前向记录 / 回放" detail="决策摘要、结果、哈希与缺口" />
      <div className="history-grid"><KeyValue label="前向状态" value={label(forward.status)} /><KeyValue label="回放状态" value={label(replay.status)} /><KeyValue label="卡片总数" value={replay.decision_summary.total_cards} /><KeyValue label="哈希检查" value={replay.card_hash_checks.length} /></div>
      <TechnicalDetails><code>{forward.status}</code><code>{replay.status}</code>{Object.entries(replay.known_at).map(([key, value]) => <code key={key}>{key}={text(value)}</code>)}<code>{JSON.stringify(replay.decision_summary)}</code>{replay.replay_gaps.map((gap) => <code key={gap}>{gap}</code>)}</TechnicalDetails>
    </section>
  );
}

function External({ workspace }: { workspace: IntelligenceWorkspace }) {
  return (
    <section className="workspace-panel external-panel" id="external" data-ui="external-intelligence">
      <SectionHeading eyebrow="非阻塞来源" title="外部情报" detail="不影响当前比赛就绪" />
      <div className="external-grid">{Object.entries(workspace.external_intelligence).map(([name, source]) => <article data-affects-match-readiness={String(source.affects_match_readiness)} data-status={source.status} key={name}><span>{EXTERNAL_LABELS[name] || name}</span><strong>{label(source.status)}</strong><small>不影响比赛就绪</small><TechnicalDetails><code>{source.status}</code><code>affects_match_readiness={String(source.affects_match_readiness)}</code></TechnicalDetails></article>)}</div>
    </section>
  );
}

function Operations({ workspace }: { workspace: IntelligenceWorkspace }) {
  const degradation = typeof workspace.data_operations.degradation === "object" && workspace.data_operations.degradation !== null
    ? (workspace.data_operations.degradation as Record<string, unknown>).state
    : workspace.data_operations.degradation;
  return (
    <section className="workspace-panel" id="operations" data-ui="data-operations">
      <SectionHeading eyebrow="只读事实" title="数据与系统" detail="来源、新鲜度、降级与读取合同" />
      <div className="operations-grid"><KeyValue label="读取来源" value={workspace.data_operations.read_model_source} mono /><KeyValue label="检查点" value={workspace.data_operations.checkpoint_key} mono /><KeyValue label="系统 / 数据健康" value={label(workspace.data_operations.system_health)} /><KeyValue label="Provider 额度读取" value={providerBudgetLabel(workspace.data_operations.provider_budget_status)} /><KeyValue label="生成时间" value={localTime(workspace.generated_at)} /><KeyValue label="降级状态" value={label(degradation)} /></div>
      <div className="read-contract"><strong>读取零调用 / 零写入</strong><code>provider_calls={workspace.read_contract.provider_calls}</code><code>db_writes={workspace.read_contract.db_writes}</code><code>would_write_checkpoint={String(workspace.read_contract.would_write_checkpoint)}</code><code>no_call_on_read={String(workspace.read_contract.no_call_on_read)}</code></div>
      <details className="freshness-contract"><summary>新鲜度域技术详情</summary><div>{Object.values(workspace.freshness.domains).map((domain) => <article key={domain.domain}><header><strong>{domain.domain}</strong><code>{domain.status}</code></header><span>{domain.source} · {domain.source_as_of || "未投影"}</span><small>{domain.availability} · {domain.readiness_semantics} · no_call_on_read={String(domain.no_call_on_read)}</small></article>)}</div></details>
    </section>
  );
}

export function IntelligenceConsole({ date, loading, onDateChange, onRefresh, workspace }: { date: string; loading: boolean; onDateChange: (date: string) => void; onRefresh: () => void; workspace: IntelligenceWorkspace }) {
  const initialId = workspace.selected_fixture_id || workspace.matches[0]?.fixture_id || null;
  const [selectedId, setSelectedId] = useState<string | null>(initialId);
  const [dateDraft, setDateDraft] = useState(date);
  useEffect(() => setDateDraft(date), [date]);
  const selected = useMemo(() => workspace.matches.find((match) => match.fixture_id === selectedId) || workspace.matches[0] || null, [selectedId, workspace.matches]);
  const select = (id: string) => {
    setSelectedId(id);
    document.querySelector("[data-ui='match-inspector']")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const commitDate = () => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(dateDraft)) onDateChange(dateDraft);
    else setDateDraft(date);
  };
  return (
    <div className="unified-workspace" data-public-authority={workspace.runtime.public_dashboard_authority} data-schema-version={workspace.schema_version}>
      <aside className="workspace-sidebar"><a className="workspace-brand" href="#top"><span>W2</span><strong>INTELLIGENCE</strong><small>统一情报工作台</small></a><nav aria-label="工作台导航">{NAVIGATION.map(([target, item]) => <a href={`#${target}`} key={target}>{item}</a>)}</nav><div className="sidebar-health"><span>系统 / 数据健康</span><strong>{label(workspace.data_operations.system_health)}</strong><span>Provider 额度读取</span><small>{providerBudgetLabel(workspace.data_operations.provider_budget_status)}</small></div><div className="sidebar-contract"><strong>只读模式</strong><span>影子运行</span><span>{workspace.runtime.active_whitelist_count} 个联赛</span></div></aside>
      <main className="workspace-main" id="top">
        <header className="workspace-topbar"><div className="topbar-title"><span>W2 INTELLIGENCE</span><strong>{workspace.date}</strong><small data-ui="header-context">{workspace.timezone} · {workspace.window === "today" ? "今日窗口" : workspace.window} · 更新 {localTime(workspace.generated_at)} · 系统 {label(workspace.data_operations.system_health)}</small></div><div className="topbar-status"><span>13 联赛</span><span>影子模式<small>SHADOW_ONLY</small></span><span>候选关闭<small>CANDIDATE OFF</small></span><span>正式关闭<small>FORMAL OFF</small></span><span>锁定关闭<small>LOCK OFF</small></span><span>生产关闭<small>PRODUCTION OFF</small></span></div><div className="topbar-actions"><label><span>日期（YYYY-MM-DD）</span><input aria-label="工作台日期" inputMode="numeric" onBlur={commitDate} onChange={(event) => setDateDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") commitDate(); }} pattern="\d{4}-\d{2}-\d{2}" type="text" value={dateDraft} /></label><button disabled={loading} onClick={onRefresh} type="button">{loading ? "读取中…" : "刷新"}</button></div></header>
        <div className="workspace-authority"><span>唯一统一情报工作台</span><code>{workspace.schema_version}</code><strong>Provider 额度读取：{providerBudgetLabel(workspace.data_operations.provider_budget_status)}</strong></div>
        <div className="workspace-grid">
          <Attention generatedAt={workspace.generated_at} items={workspace.attention} matches={workspace.matches} onSelect={select} />
          <MarketRadar match={selected} />
          <External workspace={workspace} />
          <MatchBoard matches={workspace.matches} onSelect={select} selectedId={selected?.fixture_id || null} />
          <div className="selected-column"><Inspector generatedAt={workspace.generated_at} match={selected} /><Scoreline match={selected} /></div>
          <ModelLab match={selected} />
          <Validation workspace={workspace} />
          <LeaguePerformance workspace={workspace} />
        </div>
        <footer className="workspace-footer"><span>{workspace.source}</span><span>{workspace.timezone} · 市场参考：最后可用赛前快照</span><code>{workspace.schema_version}</code></footer>
        <div className="workspace-secondary-grid"><History workspace={workspace} /><Operations workspace={workspace} /></div>
      </main>
    </div>
  );
}
