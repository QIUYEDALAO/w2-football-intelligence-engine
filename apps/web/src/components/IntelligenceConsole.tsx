import { useEffect, useMemo, useState } from "react";
import { footballDayShanghai, translateCompetition, translateReason, translateTeam } from "../lib/formatters";
import type {
  IntelligenceWorkspace,
  RiskAxisName,
  WorkspaceMarket,
  WorkspaceMatch,
} from "../types/intelligenceWorkspace";

type Props = {
  date: string;
  loading: boolean;
  onDateChange: (date: string) => void;
  onRefresh: () => void;
  workspace: IntelligenceWorkspace;
};

const MARKET_LABELS = {
  ASIAN_HANDICAP: "让球主盘",
  TOTALS: "大小球主盘",
} as const;

const RISK_LABELS: Record<RiskAxisName, string> = {
  EVENT_RISK: "事件风险",
  DATA_RISK: "数据风险",
  MODEL_RISK: "模型风险",
  COLLECTION_RISK: "采集风险",
};

const REASON_LABELS: Record<string, string> = {
  COLLECTION_INCIDENT: "采集异常",
  MARKET_MOVEMENT: "盘口或赔率变化",
  FRESH_MARKET_EVIDENCE: "市场证据完整",
  MODEL_DIAGNOSTIC: "模型诊断",
  STALE_MARKET_MEMORY: "证据已过期",
  DATA_INCOMPLETE: "数据不完整",
  LINEUP_PENDING: "首发等待",
  MISSING_AUDIT_MANIFEST: "审计清单缺失",
  MISSING_AUDIT_TABLES: "审计记录缺失",
  MISSING_OUTCOMES: "赛果缺失",
};

const PRIORITY_ORDER: Record<string, number> = {
  STALE_MARKET_MEMORY: 0,
  MARKET_MOVEMENT: 1,
  MODEL_DIAGNOSTIC: 2,
};

const DAY_MODE_LABELS: Record<IntelligenceWorkspace["day_mode"], string> = {
  NORMAL: "正常日",
  BLOCKED: "阻塞日",
  CALM: "平静日",
  EMPTY: "空比赛日",
};

const PUBLIC_SYSTEM_LABELS: Record<IntelligenceWorkspace["data_operations"]["public_system_health"], string> = {
  HEALTHY: "系统数据正常",
  PARTIAL_DEGRADATION: "系统数据部分降级",
  DAY_BLOCKED: "全日证据阻塞",
};

const STATUS_LABELS: Record<string, string> = {
  AVAILABLE: "可用",
  READY: "已就绪",
  STALE: "已过期",
  INSUFFICIENT: "证据不足",
  PAUSED_STALE: "证据过期，比较暂停",
  PRIOR_ONLY: "仅先验",
  UNAVAILABLE: "不可用",
  NOT_AVAILABLE: "暂不可用",
  MARKET_NOT_READY: "市场证据未就绪",
  MODEL_OUTSIDE_MARKET_RANGE: "模型区间外",
  MARKET_OUTSIDE_MODEL_RANGE: "市场区间外",
  COMPARABLE_WITHIN_MARKET_RANGE: "处于可比区间",
  OK: "正常",
  ATTENTION: "需关注",
  INCIDENT: "异常",
  UNASSESSED: "未评估",
};

function label(value: string | null | undefined, fallback = "暂无"): string {
  if (!value) return fallback;
  return STATUS_LABELS[value] || REASON_LABELS[value] || translateReason(value);
}

function matchName(match: WorkspaceMatch): string {
  return `${translateTeam(match.home_team_name)} vs ${translateTeam(match.away_team_name)}`;
}

function localDateTime(value: string | null): string {
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

function clock(value: string | null): string {
  const formatted = localDateTime(value);
  return formatted === "时间待确认" ? formatted : formatted.slice(-5);
}

function ageLabel(generatedAt: string | null, sourceAt: string | null): string {
  if (!generatedAt || !sourceAt) return "时间证据不足";
  const age = Math.max(0, new Date(generatedAt).valueOf() - new Date(sourceAt).valueOf());
  if (!Number.isFinite(age)) return "时间证据不足";
  const minutes = Math.floor(age / 60_000);
  return minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function nextEvaluation(next: string | null, generatedAt: string | null): string {
  if (!next) return "暂无未来评估时间";
  const nextAt = new Date(next).valueOf();
  const generated = generatedAt ? new Date(generatedAt).valueOf() : Number.NaN;
  if (!Number.isFinite(nextAt) || !Number.isFinite(generated) || nextAt <= generated) {
    return "评估时间已过期";
  }
  return `下次评估 ${localDateTime(next)}`;
}

function dateShift(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  date.setUTCDate(date.getUTCDate() + days);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(date);
}

function footballDayWindow(workspace: IntelligenceWorkspace): string {
  const start = localDateTime(workspace.football_day_start_utc).slice(5);
  const end = localDateTime(workspace.football_day_end_utc).slice(5);
  return `比赛日 ${start} → ${end}（不含）`;
}

function price(value: unknown): string {
  const raw = value && typeof value === "object" && "median" in value
    ? (value as { median?: unknown }).median
    : value;
  if (typeof raw === "number") return raw.toFixed(2);
  return raw === null || raw === undefined || raw === "" ? "—" : String(raw);
}

function comparisonSummary(market: WorkspaceMarket): string {
  if (market.cross_sectional_comparison_status === "PAUSED_STALE") return "历史证据可见，当前比较暂停";
  if (market.cross_sectional_comparison_status === "AVAILABLE") return "同一时刻机构双边报价可比较";
  return "当前横截面对比证据不足";
}

function Header({ date, loading, onDateChange, onRefresh, workspace }: Props) {
  return (
    <header className="v41-header">
      <a className="v41-brand" href="#top"><strong>W2</strong><span>情报工作台</span></a>
      <span className="v41-separator" />
      <nav className="v41-date-nav" aria-label="比赛日导航">
        <button aria-label="前一天" onClick={() => onDateChange(dateShift(date, -1))} type="button">‹</button>
        <input aria-label="选择比赛日" onChange={(event) => event.target.value && onDateChange(event.target.value)} type="date" value={date} />
        <button aria-label="后一天" onClick={() => onDateChange(dateShift(date, 1))} type="button">›</button>
        <button className="is-text" onClick={() => onDateChange(footballDayShanghai())} type="button">今天</button>
        <button aria-label="刷新" disabled={loading} onClick={onRefresh} type="button">⟳</button>
      </nav>
      <span className="v41-separator" />
      <span className="v41-pill v41-pill--read">影子只读</span>
      <span className={`v41-pill v41-pill--mode-${workspace.day_mode.toLowerCase()}`} data-day-mode-label={workspace.day_mode}>
        {DAY_MODE_LABELS[workspace.day_mode]}
      </span>
      <span className={`v41-pill ${workspace.data_operations.public_system_health === "HEALTHY" ? "v41-pill--ok" : "v41-pill--warn"}`} data-public-system-health={workspace.data_operations.public_system_health}>
        {PUBLIC_SYSTEM_LABELS[workspace.data_operations.public_system_health]}
      </span>
      <time className="v41-updated">更新 {clock(workspace.generated_at)}</time>
      <nav className="v41-secondary-nav" aria-label="辅助视图">
        <a href="#history">证据审计台</a>
        <a href="#secondary-validation">赛后验证</a>
        <a href="#system-status">系统状态</a>
      </nav>
    </header>
  );
}

function TodaySummary({ workspace }: { workspace: IntelligenceWorkspace }) {
  const counts = workspace.today_summary.primary_reason_counts;
  const blockedCount = workspace.day_mode === "BLOCKED" ? workspace.global_focus?.affected_fixture_count || 0 : 0;
  const calmCount = workspace.day_mode === "CALM" ? workspace.today_summary.match_count : 0;
  return (
    <section className="v41-today" aria-label="今日比赛摘要">
      <div className="v41-today-primary">
        <div><strong>{workspace.today_summary.priority_match_count}</strong><span>场优先查看</span></div>
        <p>
          {Object.entries(counts).slice(0, 2).map(([reason, count], index) => (
            <span className={reason.includes("INCIDENT") ? "is-critical" : index ? "is-warning" : "is-accent"} key={reason}>
              <b>{count}</b> 场{REASON_LABELS[reason] || label(reason)}
            </span>
          ))}
        </p>
      </div>
      {blockedCount ? <div className="v41-today-other"><span>全局事件</span><p><b>{blockedCount} 场缺少市场证据</b></p></div> : calmCount ? <div className="v41-today-other"><span>其他关注</span><p><b>{calmCount} 场市场证据完整</b></p></div> : Object.keys(counts).length > 2 ? <div className="v41-today-other"><span>其他关注</span><p>{Object.entries(counts).slice(2).map(([reason, count]) => <b key={reason}>{count} 场{REASON_LABELS[reason] || label(reason)}</b>)}</p></div> : null}
      <div className="v41-today-day"><strong>共 {workspace.today_summary.match_count} 场 · {workspace.today_summary.competition_count || workspace.runtime.active_whitelist_count} 联赛</strong><small>{footballDayWindow(workspace)}</small></div>
    </section>
  );
}

function PriorityShortlist({ workspace, selectedId, onSelect }: { workspace: IntelligenceWorkspace; selectedId: string | null; onSelect: (id: string) => void }) {
  const matches = workspace.matches;
  const prioritized = matches.filter((match) => match.priority_reason_primary).slice().sort((left, right) => {
    const priority = (PRIORITY_ORDER[left.priority_reason_primary || ""] ?? 99) - (PRIORITY_ORDER[right.priority_reason_primary || ""] ?? 99);
    return priority || String(left.kickoff_utc || "").localeCompare(String(right.kickoff_utc || "")) || left.fixture_id.localeCompare(right.fixture_id);
  });
  const visible = prioritized.slice(0, 6);
  const otherAttention = matches.filter((match) => !match.priority_reason_primary && match.priority_reason_secondary.length);
  const visibleOtherAttention = otherAttention.slice(0, 3);
  const blocked = workspace.day_mode === "BLOCKED" && workspace.global_focus;
  const calm = workspace.day_mode === "CALM" && workspace.global_focus;
  const empty = workspace.day_mode === "EMPTY" && workspace.global_focus;
  const aggregate = blocked || calm;
  return (
    <aside className="v41-shortlist" aria-label="关注情报 / 今日优先查看" data-ui="attention-feed">
      <header><span>今日优先查看 · 按信息价值 · 主因归类</span><b>{prioritized.length} 场优先</b></header>
      <div className="v41-shortlist-group">优先查看 · {prioritized.length} 场</div>
      <div className="v41-shortlist-list">
        {empty ? <div className="v41-shortlist-empty">本比赛日观察池内没有比赛</div> : null}
        {aggregate ? <div className="v41-shortlist-empty">{blocked ? "今日没有具备可查看证据的比赛" : "今日无需优先排查；这是有效观测结果。"}</div> : null}
        {aggregate ? <div className="v41-shortlist-group">{blocked ? "其他需关注 · 1 组" : `全部比赛 · ${workspace.today_summary.match_count} 场`}</div> : null}
        {blocked ? (
          <div className="v41-shortlist-incident">
            <span className="v41-stripe v41-stripe--collection_incident" />
            <span className="v41-shortlist-copy">
              <small>{blocked.affected_competition_count} 个联赛受影响</small>
              <strong>采集异常 · {blocked.affected_fixture_count} 场</strong>
              <span><b>{label(blocked.reason_code)}</b> · 等待既有调度恢复</span>
            </span>
          </div>
        ) : calm ? (
          <div className="v41-shortlist-incident is-calm">
            <span className="v41-stripe v41-stripe--fresh_market_evidence" />
            <span className="v41-shortlist-copy">
              <small>{workspace.today_summary.competition_count} 个联赛</small>
              <strong>未发现需关注的市场变化 · {workspace.today_summary.match_count} 场</strong>
              <span><b>证据完整</b> · 盘口未移动 · 波动未达阈值</span>
            </span>
          </div>
        ) : visible.map((match) => (
          <button aria-pressed={selectedId === match.fixture_id} className={selectedId === match.fixture_id ? "is-selected" : undefined} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} type="button">
            <span className={`v41-stripe v41-stripe--${match.priority_reason_primary?.toLowerCase()}`} />
            <span className="v41-shortlist-copy">
              <small>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认")}</small>
              <strong>{matchName(match)}</strong>
              <span className="v41-reason-line"><b>主因：{REASON_LABELS[match.priority_reason_primary || ""] || label(match.priority_reason_primary)}</b>{match.priority_reason_secondary.length ? <small>次因：{match.priority_reason_secondary.map((reason) => REASON_LABELS[reason] || label(reason)).join("、")}</small> : null}</span>
            </span>
            <time>{clock(match.kickoff_utc)}</time>
          </button>
        ))}
        {!aggregate && !empty && !prioritized.length ? <div className="v41-shortlist-empty">当前没有优先复核比赛</div> : null}
        {!aggregate && !empty && otherAttention.length ? <div className="v41-shortlist-group">其他关注 · {otherAttention.length} 场（不计入优先）</div> : null}
        {!aggregate && !empty ? visibleOtherAttention.map((match) => (
          <button aria-pressed={selectedId === match.fixture_id} className={selectedId === match.fixture_id ? "is-selected" : undefined} key={`other-${match.fixture_id}`} onClick={() => onSelect(match.fixture_id)} type="button">
            <span className="v41-stripe v41-stripe--data_incomplete" />
            <span className="v41-shortlist-copy">
              <small>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认")}</small>
              <strong>{matchName(match)}</strong>
              <span className="v41-reason-line"><small>关注：{match.priority_reason_secondary.map((reason) => REASON_LABELS[reason] || label(reason)).join("、")}</small></span>
            </span>
            <time>{clock(match.kickoff_utc)}</time>
          </button>
        )) : null}
        {!aggregate && !empty && otherAttention.length > visibleOtherAttention.length ? <p className="v41-shortlist-more">另有 {otherAttention.length - visibleOtherAttention.length} 场其他关注</p> : null}
      </div>
      {prioritized.length > visible.length ? <p className="v41-shortlist-more">另有 {prioritized.length - visible.length} 场优先项</p> : null}
      <a className="v41-text-link" href="#all-matches">查看全部 {matches.length} 场</a>
    </aside>
  );
}

function Timeline({ market }: { market: WorkspaceMarket }) {
  if (!market.timeline_points.length) return <div className="v41-no-evidence">暂无已落盘时间线证据，不推断走势。</div>;
  return (
    <ol className="v41-snapshots" data-point-count={market.timeline_points.length}>
      {market.timeline_points.map((point, index) => (
        <li className={index === market.timeline_points.length - 1 ? "is-latest" : undefined} key={point.capture_id || `${point.captured_at}-${index}`}>
          <time>{clock(point.captured_at)}</time>
          <strong>{point.canonical_line || "—"}</strong>
          <span>{point.bookmaker_count} 家 {price(point.prices.HOME ?? point.prices.OVER)}/{price(point.prices.AWAY ?? point.prices.UNDER)}</span>
        </li>
      ))}
    </ol>
  );
}

function MarketEvidence({ market, generatedAt }: { market: WorkspaceMarket; generatedAt: string | null }) {
  const stale = market.status === "STALE";
  return (
    <section className={`v41-market ${stale ? "is-stale" : ""}`} data-market={market.market} data-status={market.status}>
      <header><span>市场雷达 · {MARKET_LABELS[market.market]} · 仅绘制已落盘快照</span>{stale ? <b>市场记忆</b> : null}</header>
      <div className="v41-market-line"><strong>{market.main_line || "—"}</strong><span className={`v41-status v41-status--${market.status.toLowerCase()}`}>{stale ? "证据已过期" : market.status === "READY" ? `已观测 · ${market.bookmaker_count} 家机构双边报价` : "证据不足"}</span></div>
      <Timeline market={market} />
      <p className="v41-market-foot">
        <span>{market.snapshot_count} 个真实快照 · 点间不插值、不推断缺失路径</span>
        <span>最新 {localDateTime(market.latest_snapshot_at)} · 距生成 {ageLabel(generatedAt, market.latest_snapshot_at)}</span>
      </p>
      <div className="v41-market-semantics"><b>走势证据：{label(market.trend_evidence_status)}</b><span>{comparisonSummary(market)}</span></div>
    </section>
  );
}

function RiskSummary({ match }: { match: WorkspaceMatch }) {
  return (
    <div className="v41-risk-list" aria-label="四轴风险">
      {(Object.keys(RISK_LABELS) as RiskAxisName[]).map((axis) => {
        const risk = match.risks[axis];
        return <div className={`is-${risk.status.toLowerCase()}`} key={axis}><span>{RISK_LABELS[axis]}</span><strong>{risk.assessment_status === "UNASSESSED" ? "未评估" : label(risk.status)}</strong><small>{risk.explanation || "没有可陈述的源证据"}</small>{risk.reason_codes.length ? <details className="v41-risk-codes"><summary>技术原因 {risk.reason_codes.length} 项</summary>{risk.reason_codes.map((reason) => <code key={reason}>{reason}</code>)}</details> : null}</div>;
      })}
    </div>
  );
}

function Scoreline({ match }: { match: WorkspaceMatch }) {
  if (match.scoreline_reference.status !== "READY" || match.scoreline_reference.simulations_completed !== 10_000) return null;
  return (
    <section className="v41-scoreline">
      <header><span>比分参考 · 10,000 次既有模拟</span><b>不在读取时重新模拟</b></header>
      <div>{match.scoreline_reference.top3.map((item) => <span key={item.scoreline}><strong>{item.scoreline}</strong><b>{(item.unconditional_probability * 100).toFixed(1)}%</b><small>样本 {item.sample_count}</small></span>)}</div>
    </section>
  );
}

function MatchFocus({ generatedAt, match }: { generatedAt: string | null; match: WorkspaceMatch }) {
  const markets = [match.market_radar.markets.ASIAN_HANDICAP, match.market_radar.markets.TOTALS];
  const primary = markets.find((market) => market.main_line) || markets[0];
  const model = match.w2_analysis.model_view;
  const primaryRelation = match.w2_analysis.model_market_relation[primary.market];
  const diagnosticRelation = Object.values(match.w2_analysis.model_market_relation).find((relation) => !["COMPARABLE_WITHIN_MARKET_RANGE", "MARKET_NOT_READY"].includes(relation.status)) || primaryRelation;
  const stale = markets.some((market) => market.status === "STALE");
  return (
    <article className="v41-focus" data-focus-type="MATCH" data-fixture-id={match.fixture_id}>
      <header className="v41-focus-header">
        <div><h1>{matchName(match)}</h1><p>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认")} · {localDateTime(match.kickoff_utc)} · 比赛 {match.fixture_id}</p></div>
        <div><span>开球时间</span><strong>{clock(match.kickoff_utc)}</strong></div>
      </header>
      <div className={`v41-focus-summary ${stale ? "is-warning" : ""}`}><b>{stale ? "市场记忆" : "本场摘要"}</b><span>{match.factual_summary}</span></div>
      <div className="v41-focus-body">
        <div className="v41-focus-markets">{markets.map((market) => <MarketEvidence generatedAt={generatedAt} key={market.market} market={market} />)}</div>
        <div className="v41-focus-meaning">
          <span className="v41-eyebrow">三层语义 · 互不等同</span>
          <div className="v41-three-layer">
            <div><span>市场主事实</span><strong>{MARKET_LABELS[primary.market]}</strong><b>{primary.main_line || "—"}</b></div>
            <div><span>W2 诊断</span><strong>{label(model.status)}</strong><b>{stale ? "比较暂停" : label(diagnosticRelation?.status)}</b></div>
            <div><span>正式推荐</span><strong>产品权限</strong><b>未启用</b></div>
          </div>
          <div className={`v41-diagnostic ${stale ? "is-stale" : ""}`}><span /><p><b>{stale ? "市场记忆不可作为当前比较权威" : `当前模型状态：${label(model.status)}`}</b>{stale ? "等待既有采集调度形成新快照后再比较。" : `${label(diagnosticRelation?.status)}。模型与市场差异仅用于诊断；优先检查模型校准、特征时效、盘口身份和数据质量。${diagnosticRelation?.blockers.map(translateReason).join("；") || ""}`}</p></div>
          <RiskSummary match={match} />
          <Scoreline match={match} />
          <div className="v41-next"><span>当前就绪</span><strong>{label(match.readiness.status)}</strong><b>{nextEvaluation(match.readiness.next_eval_at, generatedAt)}</b></div>
          <details className="v41-details"><summary>技术详情</summary><code>{match.intelligence_state}</code><code>{match.readiness.reason_code || "NO_REASON_CODE"}</code><code>model_source={model.source_status}</code></details>
        </div>
      </div>
    </article>
  );
}

function GlobalFocus({ date, onDateChange, workspace }: Pick<Props, "date" | "onDateChange" | "workspace">) {
  const focus = workspace.global_focus;
  if (!focus) return <article className="v41-focus v41-global" data-focus-type={workspace.default_focus_type}><div className="v41-global-copy"><span className="v41-eyebrow">当前焦点</span><h1>尚未选择比赛</h1><p>请选择具有已持久化证据的比赛；页面不会自动填充其他焦点。</p></div></article>;
  const blocked = workspace.day_mode === "BLOCKED";
  const calm = workspace.day_mode === "CALM";
  const title = blocked ? "当日市场采集阻塞" : calm ? "今日未发现需优先排查的比赛" : "本比赛日没有纳入观察池的比赛";
  const detail = blocked ? `影响 ${focus.affected_fixture_count} 场比赛 · ${focus.affected_competition_count} 个联赛 —— 本足球日全部比赛` : calm ? `${workspace.today_summary.match_count} 场比赛市场证据完整 —— 这是有效观测结果，不是系统未完成。` : `${workspace.runtime.active_whitelist_count} 个白名单联赛在本足球日均无赛程`;
  return (
    <article className={`v41-focus v41-global v41-global--${workspace.day_mode.toLowerCase()}`} data-focus-type={workspace.default_focus_type}>
      <div className="v41-global-copy"><span className="v41-eyebrow">{workspace.day_mode === "BLOCKED" ? "全局事件" : "当日摘要"}</span><h1>{title}</h1><p>{detail}</p></div>
      <div className="v41-global-grid">
        <section><span>{blocked ? "原因" : "今日判定"}</span><strong>{focus.factual_summary}</strong><small>来源截至 {localDateTime(focus.source_as_of)}</small></section>
        <section><span>{blocked ? "结果" : workspace.day_mode === "EMPTY" ? "说明" : "判定口径"}</span><strong>{blocked ? "无赛前市场报价；不计算模型—市场关系，不推断走势。" : workspace.day_mode === "EMPTY" ? "不会用其他日期的比赛填充本页；空比赛日不代表系统异常。" : "盘口未移动、双边赔率波动未达阈值，且当前持久化证据完整。"}</strong><small>{focus.reason_code}</small></section>
      </div>
      <div className="v41-global-stats">
        <div><span>{blocked ? "市场证据" : calm ? "优先复核" : "白名单联赛"}</span><strong>{blocked ? "让球与大小球均无持久化快照" : calm ? "0 场" : workspace.runtime.active_whitelist_count}</strong></div>
        <div><span>{blocked ? "受影响联赛" : calm ? "覆盖比赛" : "本日赛程"}</span><strong>{blocked ? `${focus.affected_competition_count} / ${workspace.today_summary.competition_count}` : calm ? `${workspace.today_summary.match_count} / ${workspace.today_summary.match_count}` : 0}</strong></div>
        <div><span>{workspace.day_mode === "EMPTY" ? "下一有赛日" : "下一计划评估"}</span><strong>{workspace.day_mode === "EMPTY" ? typeof workspace.navigation.next_available_date === "string" ? workspace.navigation.next_available_date : "尚未确认" : focus.next_eval_at ? clock(focus.next_eval_at) : "等待既有调度"}</strong></div>
      </div>
      {blocked ? <div className="v41-global-note"><span>恢复条件</span><strong>{focus.recovery_condition}</strong><small>系统状态页只显示已持久化证据，本页面不发起任何 Provider 请求。</small></div> : calm ? <div className="v41-global-note"><span>说明</span><strong>页面内容少不会改变既有关注阈值。</strong><small>继续等待既有调度形成下一次持久化评估。</small></div> : null}
      {blocked ? <div className="v41-global-guard"><b>读取保护</b><span>本页只读持久化证据；Provider 调用 0，业务写入 0。</span></div> : null}
      {workspace.day_mode === "EMPTY" ? <nav className="v41-adjacent-days"><button onClick={() => onDateChange(typeof workspace.navigation.previous_date === "string" ? workspace.navigation.previous_date : dateShift(date, -1))} type="button">‹ 前一天</button><button onClick={() => onDateChange(typeof workspace.navigation.next_date === "string" ? workspace.navigation.next_date : dateShift(date, 1))} type="button">后一天 ›</button></nav> : null}
    </article>
  );
}

function QualityRail({ workspace }: { workspace: IntelligenceWorkspace }) {
  const quality = workspace.global_model_quality;
  const available = quality.status === "AVAILABLE";
  const qualityCopy = available
    ? "仅展示当前有效验证证据"
    : quality.status === "STALE"
      ? `已过期（截至 ${localDateTime(quality.checkpoint_generated_at)}）`
      : quality.status === "INCOMPLETE"
        ? `checkpoint 指标不完整（截至 ${localDateTime(quality.checkpoint_generated_at)}）`
        : "尚无可用 checkpoint";
  return (
    <section className="v41-quality" id="validation">
      <header><span>全局模型质量 · 来源 checkpoint</span><p>整体表现：<b>{qualityCopy}</b></p></header>
      <div>
        <span><small>W2 LogLoss</small><strong>{available ? quality.model_log_loss?.toFixed(3) : "—"}</strong><b>市场 {available ? quality.market_log_loss?.toFixed(3) : "—"}</b></span>
        <span><small>W2 Brier</small><strong>{available ? quality.model_brier?.toFixed(3) : "—"}</strong><b>市场 {available ? quality.market_brier?.toFixed(3) : "—"}</b></span>
        <span><small>校准误差 ECE</small><strong>{available && quality.model_calibration_error !== null ? `${(quality.model_calibration_error * 100).toFixed(1)}%` : "—"}</strong><b>{label(quality.status)}</b></span>
        <span><small>前向有效样本</small><strong>{available ? quality.sample_count : "—"}</strong><b>{available && quality.checkpoint_generated_at ? `截至 ${localDateTime(quality.checkpoint_generated_at)}` : quality.status === "NOT_AVAILABLE" ? "checkpoint 缺失" : label(quality.status)}</b></span>
        <a href="#secondary-validation">赛后验证</a>
      </div>
    </section>
  );
}

function SecondaryViews({ workspace }: { workspace: IntelligenceWorkspace }) {
  const records = workspace.validation.forward_validation_records;
  const outcomes = records.outcomes;
  const tracking = workspace.validation.history_replay.outcome_tracking_summary;
  const count = (source: Record<string, unknown>, key: string) => typeof source[key] === "number" ? source[key] : "—";
  return (
    <section className="v41-secondary" aria-label="数据与系统 / 辅助详情">
      <details id="all-matches"><summary>全部比赛</summary><ol>{workspace.matches.map((match) => <li key={match.fixture_id}><span>{localDateTime(match.kickoff_utc)}</span><strong>{matchName(match)}</strong><b>{label(match.readiness.status)}</b></li>)}</ol></details>
      <details id="secondary-validation" open><summary>赛后验证</summary><p>统一前向验证账本 · 方向状态 {label(workspace.validation.directional.status)} · 市场方向基准 {label(workspace.validation.directional.market_direction_benchmark)}</p><ul className="v41-validation-counts"><li><span>验证总记录</span><strong>{records.validation_count}</strong></li><li><span>已结算</span><strong>{count(outcomes, "settled_sample_count")}</strong></li><li><span>纳入统计</span><strong>{records.eligible_count}</strong></li><li><span>待结算</span><strong>{records.pending_count}</strong></li><li><span>证据排除</span><strong>{records.excluded_count}</strong></li><li><span>赛果匹配 / 缺失</span><strong>{count(tracking, "matched_outcome_count")} / {count(tracking, "missing_outcome_count")}</strong></li></ul>{workspace.validation.history_replay.replay_gaps.length ? <p className="v41-validation-gaps">当前缺口：{workspace.validation.history_replay.replay_gaps.map((gap) => `${label(gap)} [${gap}]`).join("；")}</p> : null}<ul>{workspace.validation.league_performance.slice(0, 13).map((league) => <li key={`${league.competition_id}-${league.source_league}`}><strong>{translateCompetition(league.competition_name || league.league)}</strong><span>{league.only_record_reason === "PROBABILITY_QUALITY_NOT_READY" ? "概率质量待就绪" : league.only_record_reason === "AGGREGATION_CONFLICT" ? "聚合冲突" : league.only_record_reason === "SAMPLE_INSUFFICIENT" ? "样本不足" : "可用"}</span></li>)}</ul></details>
      <details data-contract="HISTORICAL_INCREMENTAL_EDGE=NOT_PROVEN" id="history"><summary>前向记录 / 回放</summary><p>{label(workspace.validation.history_replay.status)} · 卡片 {workspace.validation.history_replay.decision_summary.total_cards} · 缺口 {workspace.validation.history_replay.replay_gaps.length}</p></details>
      <details id="system-status"><summary>系统状态与读取合同</summary><p>13 联赛 · {workspace.runtime.free_bridge_mode} · Candidate/Formal/Lock/Production 全部关闭</p><p>公开系统状态：{PUBLIC_SYSTEM_LABELS[workspace.data_operations.public_system_health]} · 原始技术代码：{workspace.data_operations.system_health}</p><p>provider_calls={workspace.read_contract.provider_calls} · db_writes={workspace.read_contract.db_writes} · would_write_checkpoint={String(workspace.read_contract.would_write_checkpoint)} · no_call_on_read={String(workspace.read_contract.no_call_on_read)}</p></details>
    </section>
  );
}

export function IntelligenceConsole(props: Props) {
  const { workspace } = props;
  const [selectedId, setSelectedId] = useState<string | null>(workspace.default_focus_fixture_id);

  useEffect(() => {
    setSelectedId(workspace.default_focus_fixture_id);
  }, [workspace.default_focus_fixture_id, workspace.request_id]);

  const selected = useMemo(() => {
    if (workspace.default_focus_type !== "MATCH") return null;
    return workspace.matches.find((match) => match.fixture_id === selectedId) || null;
  }, [selectedId, workspace.default_focus_type, workspace.matches]);

  return (
    <main aria-label="W2 INTELLIGENCE" className="dashboard-v41" data-day-mode={workspace.day_mode} data-focus-type={workspace.default_focus_type} data-intelligence-vocabulary="MODEL_MARKET_DISAGREEMENT" data-schema-version={workspace.schema_version} id="top">
      <Header {...props} />
      <TodaySummary workspace={workspace} />
      <div className="v41-main">
        <PriorityShortlist workspace={workspace} onSelect={setSelectedId} selectedId={selectedId} />
        {selected ? <MatchFocus generatedAt={workspace.generated_at} match={selected} /> : <GlobalFocus date={props.date} onDateChange={props.onDateChange} workspace={workspace} />}
      </div>
      <QualityRail workspace={workspace} />
      <SecondaryViews workspace={workspace} />
    </main>
  );
}
