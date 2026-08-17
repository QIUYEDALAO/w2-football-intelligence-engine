import { useEffect, useMemo, useRef, useState } from "react";
import { footballDayShanghai, translateCompetition, translateReason } from "../lib/formatters";
import { PUBLIC_ENUM_LABELS, PUBLIC_REASON_LABELS } from "../lib/labels";
import { publicPresentation } from "../lib/publicPresentation";
import type {
  FixtureFactor,
  FixtureFactorChecklist,
  IntelligenceWorkspace,
  RiskAxisName,
  WorkspaceMarket,
  WorkspaceMatch,
  WorkspaceDateStripEntry,
  WorkspacePublicTeamLabel,
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

const SELECTION_LABELS: Record<string, string> = {
  HOME: "主队",
  AWAY: "客队",
  OVER: "大球",
  UNDER: "小球",
};

const RISK_LABELS: Record<RiskAxisName, string> = {
  EVENT_RISK: "事件风险",
  DATA_RISK: "数据风险",
  MODEL_RISK: "可比较模型校准",
  COLLECTION_RISK: "采集风险",
};

const REASON_LABELS = PUBLIC_REASON_LABELS;

const PRIORITY_ORDER: Record<string, number> = {
  MARKET_MOVEMENT: 0,
  MODEL_DIAGNOSTIC: 1,
};

const STATUS_LABELS = PUBLIC_ENUM_LABELS;

function label(value: string | null | undefined, fallback = "暂无"): string {
  if (!value) return fallback;
  return STATUS_LABELS[value] || REASON_LABELS[value] || translateReason(value);
}

function candidateAggregateLabel(value: WorkspaceMatch["readiness"]["market_aggregate_status"]): string {
  return value === "NOT_READY" ? "均未就绪" : label(value);
}

function selectedDaySemantics(workspace: IntelligenceWorkspace) {
  return workspace.date_strip.find((entry) => entry.football_day === workspace.date)?.public_semantics
    || { scope: "SELECTED_DAY" as const, cause: null };
}

function selectedDayPublicStatus(workspace: IntelligenceWorkspace) {
  const selectedDay = workspace.date_strip.find((entry) => entry.football_day === workspace.date);
  return publicPresentation(selectedDaySemantics(workspace), {
    dayNoun: selectedDayNoun(workspace),
    fixtureCount: workspace.today_summary.match_count,
    competitionCount: workspace.today_summary.competition_count,
    marketReadyCount: workspace.matches.filter((match) => match.readiness.market_evidence_status === "AVAILABLE").length,
    marketObservationCount: selectedDay?.market_evidence_fixture_count,
    priorityCount: workspace.today_summary.priority_match_count,
  });
}

function selectedDayNoun(workspace: IntelligenceWorkspace): "今日" | "所选比赛日" {
  return workspace.date === footballDayShanghai() ? "今日" : "所选比赛日";
}

function snapshotClock(value: string | null, kickoff: string | null): string {
  const captured = localDateTime(value);
  const fixture = localDateTime(kickoff);
  if (captured === "—") return captured;
  return captured.slice(0, 10) === fixture.slice(0, 10) ? captured.slice(11) : captured.slice(5);
}

function TeamLabel({ team }: { team: WorkspacePublicTeamLabel }) {
  const presentation = publicPresentation(team.public_semantics, { subject: team.display_name });
  return <span className="v41-team-label"><span>{team.display_name}</span>{team.public_semantics.cause ? <em className={`is-${presentation.tone}`}>{presentation.label}</em> : null}</span>;
}

function MatchName({ match }: { match: WorkspaceMatch }) {
  return <span className="v41-match-name"><TeamLabel team={match.home_team_label} /><span className="v41-versus"> vs </span><TeamLabel team={match.away_team_label} /></span>;
}

function localDateTime(value: string | null): string {
  if (!value) return "时间待确认";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

function clock(value: string | null): string {
  const formatted = localDateTime(value);
  return formatted === "时间待确认" ? formatted : formatted.slice(-5);
}

function kickoffLabel(value: string | null, selectedDate: string): string {
  const formatted = localDateTime(value);
  if (formatted === "时间待确认") return formatted;
  const kickoffDate = formatted.slice(0, 10);
  if (kickoffDate === selectedDate) return formatted.slice(-5);
  if (kickoffDate === dateShift(selectedDate, 1)) return `次日 ${formatted.slice(-5)}`;
  return formatted;
}

function byKickoff(matches: WorkspaceMatch[]): WorkspaceMatch[] {
  return matches.slice().sort((left, right) => String(left.kickoff_utc || "").localeCompare(String(right.kickoff_utc || "")) || left.fixture_id.localeCompare(right.fixture_id));
}

function historyRecordLabel(recordKind: IntelligenceWorkspace["validation"]["history_replay"]["record_kind"]): string {
  if (recordKind === "FORWARD_RECORD") return "前向记录";
  if (recordKind === "REPLAY") return "回放记录";
  if (recordKind === "MIXED_RECORD") return "前向 / 回放记录";
  return "比赛记录";
}

function ageLabel(generatedAt: string | null, sourceAt: string | null): string {
  if (!generatedAt || !sourceAt) return "时间证据不足";
  const age = Math.max(0, new Date(generatedAt).valueOf() - new Date(sourceAt).valueOf());
  if (!Number.isFinite(age)) return "时间证据不足";
  const minutes = Math.floor(age / 60_000);
  return minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function duration(seconds: number): string {
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  return minutes < 60 ? `${minutes} 分钟` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function nextEvaluation(next: string | null, generatedAt: string | null): string {
  if (!next) return "暂无未来评估时间";
  const nextAt = new Date(next).valueOf();
  const generated = generatedAt ? new Date(generatedAt).valueOf() : Number.NaN;
  if (!Number.isFinite(nextAt) || !Number.isFinite(generated) || nextAt <= generated) {
    return "评估时间已过期";
  }
  return localDateTime(next);
}

function scheduledEvaluation(next: string | null, generatedAt: string | null): string {
  if (!next) return "等待既有调度确认";
  const nextAt = new Date(next).valueOf();
  const generated = generatedAt ? new Date(generatedAt).valueOf() : Number.NaN;
  if (!Number.isFinite(nextAt) || !Number.isFinite(generated)) return localDateTime(next);
  if (nextAt <= generated) return `${localDateTime(next)}（该评估时间已过）`;
  const minutes = Math.ceil((nextAt - generated) / 60_000);
  const relative = minutes < 60 ? `约 ${minutes} 分钟后` : `约 ${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分后`;
  return `${localDateTime(next)}（${relative}）`;
}

function hasFutureEvaluation(next: string | null, generatedAt: string | null): boolean {
  if (!next || !generatedAt) return false;
  const nextAt = new Date(next).valueOf();
  const generated = new Date(generatedAt).valueOf();
  return Number.isFinite(nextAt) && Number.isFinite(generated) && nextAt > generated;
}

function dateShift(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  date.setUTCDate(date.getUTCDate() + days);
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(date);
}

function footballDayWindow(workspace: IntelligenceWorkspace): string {
  const start = localDateTime(workspace.football_day_start_utc);
  const end = localDateTime(workspace.football_day_end_utc);
  return `比赛日 ${start} → ${end}（不含）`;
}

function isIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00+08:00`);
  return !Number.isNaN(parsed.valueOf()) && dateShift(value, 0) === value;
}

function price(value: unknown): string {
  const raw = value && typeof value === "object" && "median" in value
    ? (value as { median?: unknown }).median
    : value;
  if (typeof raw === "number") return raw.toFixed(2);
  return raw === null || raw === undefined || raw === "" ? "—" : String(raw);
}

function comparisonSummary(market: WorkspaceMarket): string {
  if (market.cross_sectional_comparison_status === "AVAILABLE") return "同一时刻机构双边报价可比较";
  return "当前横截面对比证据不足";
}

function collectionLabel(match: WorkspaceMatch): string {
  const cause = match.market_collection.public_semantics.cause;
  const checkpoint = match.market_collection.target_checkpoint || "下一档";
  if (cause === "NOT_YET_DUE") return `未到 ${checkpoint} 采集时点`;
  if (cause === "AWAITING_COLLECTION") {
    return match.market_collection.overdue
      ? `${checkpoint} 采集已逾期`
      : `${checkpoint} 采集窗口进行中`;
  }
  if (cause === "UNASSESSED") return "采集计划未评估";
  return "当前档位已满足";
}

function Header({ date, loading, onDateChange, onRefresh, workspace }: Props) {
  const publicStatus = selectedDayPublicStatus(workspace);
  return (
    <header className="v41-header">
      <a className="v41-brand" href="#top"><strong>W2</strong><span>情报工作台</span></a>
      <span className="v41-separator" />
      <nav className="v41-date-nav" aria-label="比赛日导航">
        <button aria-label="前一天" onClick={() => onDateChange(dateShift(date, -1))} type="button">‹</button>
        <input aria-label="选择比赛日" defaultValue={date} inputMode="numeric" key={date} onChange={(event) => isIsoDate(event.target.value) && onDateChange(event.target.value)} pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" placeholder="YYYY-MM-DD" type="text" />
        <button aria-label="后一天" onClick={() => onDateChange(dateShift(date, 1))} type="button">›</button>
        <button className="is-text" onClick={() => onDateChange(footballDayShanghai())} type="button">今天</button>
        <button aria-label="刷新" disabled={loading} onClick={onRefresh} type="button">⟳</button>
      </nav>
      <span className="v41-separator" />
      <span className="v41-pill v41-pill--read">{workspace.runtime.candidate === "SHADOW_ONLY" ? "影子候选已启用" : "影子只读"}</span>
      <span className={`v41-pill v41-pill--${publicStatus.className}`} data-public-cause={selectedDaySemantics(workspace).cause || "NONE"}>
        {publicStatus.label}
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

function dateStripLabel(entry: WorkspaceDateStripEntry): string {
  return publicPresentation(entry.public_semantics, {
    fixtureCount: entry.fixture_count,
    competitionCount: entry.competition_count,
    marketObservationCount: entry.market_evidence_fixture_count,
    finishedCount: entry.finished_fixture_count,
  }).label;
}

function RecentDateNav({ date, onDateChange, workspace }: Pick<Props, "date" | "onDateChange" | "workspace">) {
  const [sliceStart, setSliceStart] = useState(4);
  const selectedDateRef = useRef<HTMLButtonElement>(null);
  useEffect(() => setSliceStart(4), [date]);
  useEffect(() => {
    selectedDateRef.current?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [date, sliceStart, workspace.date_strip]);
  const dates = workspace.date_strip.slice(sliceStart, sliceStart + 7);
  return (
    <nav className="v41-recent-days" aria-label="近七日比赛浏览">
      <span>已持久化赛程</span>
      <button aria-label="查看更早日期" className="v41-window-control" disabled={sliceStart === 0} onClick={() => setSliceStart(Math.max(0, sliceStart - 4))} type="button">‹</button>
      {dates.map((item) => (
        <button aria-current={item.football_day === date ? "date" : undefined} key={item.football_day} onClick={() => onDateChange(item.football_day)} ref={item.football_day === date ? selectedDateRef : undefined} type="button">
          <small>{item.football_day}</small>
          <b>{item.fixture_count} 场{item.football_day === footballDayShanghai() ? " · 今天" : item.football_day === date ? " · 当前" : ""}</b>
          <em>{dateStripLabel(item)}{item.competition_count ? ` · ${item.competition_count}/13 联赛` : ""}</em>
        </button>
      ))}
      <button aria-label="查看更晚日期" className="v41-window-control" disabled={sliceStart + 7 >= workspace.date_strip.length} onClick={() => setSliceStart(Math.min(workspace.date_strip.length - 7, sliceStart + 4))} type="button">›</button>
      <span className="v41-recent-days-note">每次只读取所选日期，不额外查询 Provider</span>
    </nav>
  );
}

function TodaySummary({ workspace }: { workspace: IntelligenceWorkspace }) {
  const dayNoun = selectedDayNoun(workspace);
  const selectedCause = selectedDaySemantics(workspace).cause;
  const presentation = selectedDayPublicStatus(workspace);
  const counts = workspace.today_summary.primary_reason_counts;
  const readyCount = workspace.matches.filter((match) => match.readiness.market_aggregate_status === "READY").length;
  const partialCount = workspace.matches.filter((match) => match.readiness.market_aggregate_status === "PARTIAL").length;
  const candidateBlockedCount = workspace.matches.filter((match) => match.readiness.market_aggregate_status === "NOT_READY").length;
  const marketBlockedCount = workspace.matches.filter((match) => match.readiness.market_evidence_status === "NOT_READY").length;
  const limitedCount = selectedCause && marketBlockedCount === workspace.today_summary.match_count
    ? marketBlockedCount
    : 0;
  const calmCount = !selectedCause && !workspace.selected_fixture_id ? workspace.today_summary.match_count : 0;
  const candidateCount = workspace.matches.filter((match) => match.shadow_candidate.status === "ACTIVE").length;
  return (
    <section className="v41-today" aria-label={`${dayNoun}比赛摘要`}>
      <div className="v41-today-primary">
        <div><strong>{workspace.today_summary.match_count}</strong><span>场{dayNoun}比赛</span></div>
        <p>
      {limitedCount ? <><span className="is-accent"><b>{workspace.today_summary.match_count}</b> 场可查看赛程</span><span className={presentation.tone === "neutral" ? "is-accent" : "is-warning"}><b>0</b> 场可进行市场分析</span></> : <><span className={readyCount ? "is-accent" : "is-warning"}><b>{readyCount}</b> 场候选输入全部就绪</span>{partialCount ? <span className="is-warning"><b>{partialCount}</b> 场候选输入部分就绪</span> : null}{candidateBlockedCount ? <span className="is-critical"><b>{candidateBlockedCount}</b> 场候选输入均未就绪</span> : null}{marketBlockedCount ? <span className="is-critical"><b>{marketBlockedCount}</b> 场尚无市场证据</span> : null}</>}
        </p>
      </div>
      {limitedCount ? <div className="v41-today-other"><span>当前口径</span><p><b>{limitedCount} 场可查看赛程；{presentation.label}</b></p></div> : calmCount ? <div className="v41-today-other"><span>当前口径</span><p><b>{calmCount} 场均未触发优先复核</b></p></div> : Object.keys(counts).length ? <div className="v41-today-other"><span>优先复核</span><p>{Object.entries(counts).slice(0, 3).map(([reason, count]) => <b key={reason}>{count} 场{REASON_LABELS[reason] || label(reason)}</b>)}</p></div> : null}
      <div className="v41-today-day"><strong>共 {workspace.today_summary.match_count} 场 · {candidateCount} 场影子候选 · {workspace.today_summary.competition_count || workspace.runtime.active_whitelist_count} 联赛{workspace.today_summary.pending_owner_review_team_count ? ` · ${workspace.today_summary.pending_owner_review_team_count} 支候选译名待审` : ""}</strong><small>{footballDayWindow(workspace)}</small></div>
    </section>
  );
}

function PriorityShortlist({ workspace, selectedId, onSelect }: { workspace: IntelligenceWorkspace; selectedId: string | null; onSelect: (id: string) => void }) {
  const [competitionFilter, setCompetitionFilter] = useState("ALL");
  const dayNoun = selectedDayNoun(workspace);
  const selectedSemantics = selectedDaySemantics(workspace);
  const selectedCause = selectedSemantics.cause;
  const presentation = publicPresentation(selectedSemantics, {
    dayNoun,
    fixtureCount: workspace.today_summary.match_count,
    competitionCount: workspace.today_summary.competition_count,
    priorityCount: workspace.today_summary.priority_match_count,
  });
  const matches = workspace.matches.slice().sort((left, right) => {
    const priority = (PRIORITY_ORDER[left.priority_reason_primary || ""] ?? 99) - (PRIORITY_ORDER[right.priority_reason_primary || ""] ?? 99);
    return priority || String(left.kickoff_utc || "").localeCompare(String(right.kickoff_utc || "")) || left.fixture_id.localeCompare(right.fixture_id);
  });
  const competitions = Array.from(matches.reduce((items, match) => {
    const key = match.competition_id || match.competition_name || "UNKNOWN";
    if (!items.has(key)) items.set(key, { key, label: translateCompetition(match.competition_name || match.competition_id || "赛事待确认", match.competition_id), count: 0 });
    items.get(key)!.count += 1;
    return items;
  }, new Map<string, { key: string; label: string; count: number }>()).values());
  const activeCompetition = competitionFilter === "ALL" || competitions.some((item) => item.key === competitionFilter) ? competitionFilter : "ALL";
  const filteredMatches = activeCompetition === "ALL" ? matches : matches.filter((match) => (match.competition_id || match.competition_name || "UNKNOWN") === activeCompetition);
  const marketBlockedCount = matches.filter((match) => match.readiness.market_evidence_status === "NOT_READY").length;
  const limited = selectedCause !== null && marketBlockedCount === matches.length
    ? workspace.global_focus
    : null;
  const allPrioritized = matches.filter((match) => match.priority_reason_primary);
  const prioritized = limited ? [] : filteredMatches.filter((match) => match.priority_reason_primary);
  const otherAttention = limited ? [] : filteredMatches.filter((match) => !match.priority_reason_primary && match.priority_reason_secondary.length);
  const remaining = limited ? filteredMatches : filteredMatches.filter((match) => !match.priority_reason_primary && !match.priority_reason_secondary.length);
  const empty = workspace.today_summary.match_count === 0 && workspace.global_focus;
  const calm = selectedCause === null && workspace.today_summary.match_count > 0 && !workspace.selected_fixture_id ? workspace.global_focus : null;
  const aggregate = limited || calm;
  const selectCompetition = (key: string) => {
    setCompetitionFilter(key);
    if (key !== "ALL") {
      const first = matches.find((match) => (match.competition_id || match.competition_name || "UNKNOWN") === key);
      if (first) onSelect(first.fixture_id);
    }
  };
  const row = (match: WorkspaceMatch, kind: "priority" | "attention" | "remaining") => {
    const priorityPosition = kind === "priority" ? allPrioritized.findIndex((item) => item.fixture_id === match.fixture_id) + 1 : 0;
    const stripe = kind === "priority" ? match.priority_reason_primary?.toLowerCase() : kind === "attention" ? "data_incomplete" : limited ? presentation.tone : "fresh_market_evidence";
    return (
      <button aria-pressed={selectedId === match.fixture_id} className={`${limited ? "v41-limited-match " : ""}${selectedId === match.fixture_id ? "is-selected" : ""}`.trim() || undefined} data-fixture-id={match.fixture_id} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} type="button">
        <span className={`v41-stripe v41-stripe--${stripe}`} />
        <span className="v41-shortlist-copy">
          <small>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认", match.competition_id)}</small>
          <strong><MatchName match={match} /></strong>
          {kind === "priority" ? <span className="v41-reason-line"><b>优先 {priorityPosition} · 主因：{REASON_LABELS[match.priority_reason_primary || ""] || label(match.priority_reason_primary)}</b>{match.priority_reason_secondary.length ? <small>次因：{match.priority_reason_secondary.map((reason) => REASON_LABELS[reason] || label(reason)).join("、")}</small> : null}</span> : kind === "attention" ? <span className="v41-reason-line"><small>关注：{match.priority_reason_secondary.map((reason) => REASON_LABELS[reason] || label(reason)).join("、")}</small></span> : limited ? <span><b>{presentation.label}</b> · W2 盘口证据尚未落盘</span> : <span><b>{match.shadow_candidate.status === "ACTIVE" ? "影子候选" : "普通查看"}</b> · 未触发优先复核</span>}
        </span>
        <time>{kickoffLabel(match.kickoff_utc, workspace.date)}</time>
      </button>
    );
  };
  return (
    <aside className="v41-shortlist" aria-label={`关注情报 / ${dayNoun}优先查看`} data-ui="attention-feed">
      <header><span>{dayNoun}优先查看 · 按信息价值排序 · <span className="v41-no-break">优先阈值：</span>盘口移动或任一侧赔率相对变化 ≥ {(workspace.runtime.market_price_attention_threshold_ratio * 100).toFixed(0)}%</span><b>{prioritized.length} 场优先 · {filteredMatches.length} 场可滚动查看</b></header>
      {competitions.length > 1 ? <div aria-label="按联赛筛选比赛" className="v41-shortlist-filters" role="toolbar"><button aria-pressed={activeCompetition === "ALL"} onClick={() => selectCompetition("ALL")} type="button">全部 <b>{matches.length}</b></button>{competitions.map((competition) => <button aria-pressed={activeCompetition === competition.key} key={competition.key} onClick={() => selectCompetition(competition.key)} type="button">{competition.label} <b>{competition.count}</b></button>)}</div> : null}
      <div aria-label={`${activeCompetition === "ALL" ? "全部联赛" : competitions.find((item) => item.key === activeCompetition)?.label || "已选联赛"}比赛列表`} className="v41-shortlist-list" tabIndex={0}>
        {empty ? <div className="v41-shortlist-empty">本比赛日观察池内没有比赛</div> : null}
        {aggregate ? <div className="v41-shortlist-empty">{limited ? presentation.summary : `${dayNoun}无需优先排查；这是有效观测结果。`}</div> : null}
        {limited && !matches.length ? (
          <div className="v41-shortlist-incident">
            <span className={`v41-stripe v41-stripe--${presentation.tone}`} />
            <span className="v41-shortlist-copy">
              <small>{limited.affected_competition_count} 个联赛受影响</small>
              <strong>盘口证据待采集 · {limited.affected_fixture_count} 场</strong>
              <span><b>{presentation.label}</b> · 暂不生成市场分析</span>
            </span>
          </div>
        ) : null}
        {prioritized.length ? <><div className="v41-shortlist-group">优先查看 · {prioritized.length} 场</div>{prioritized.map((match) => row(match, "priority"))}</> : null}
        {otherAttention.length ? <><div className="v41-shortlist-group">其他关注 · {otherAttention.length} 场（不计入优先）</div>{otherAttention.map((match) => row(match, "attention"))}</> : null}
        {remaining.length ? <><div className="v41-shortlist-group">{limited ? "盘口证据待采集" : "其他比赛"} · {remaining.length} 场</div>{remaining.map((match) => row(match, "remaining"))}</> : null}
        {!empty && !filteredMatches.length ? <div className="v41-shortlist-empty">所选联赛暂无比赛</div> : null}
      </div>
    </aside>
  );
}

function Timeline({ kickoff, market }: { kickoff: string | null; market: WorkspaceMarket }) {
  if (!market.timeline_points.length) return <div className="v41-no-evidence">暂无已落盘时间线证据，不推断走势。</div>;
  return (
    <ol className="v41-snapshots" data-point-count={market.timeline_points.length}>
      {market.timeline_points.map((point, index) => (
        <li className={index === market.timeline_points.length - 1 ? "is-latest" : undefined} key={point.capture_id || `${point.captured_at}-${index}`}>
          <time>{snapshotClock(point.captured_at, kickoff)}</time>
          <strong>{point.canonical_line || "—"}</strong>
          <span>{point.bookmaker_count} 家 {price(point.prices.HOME ?? point.prices.OVER)}/{price(point.prices.AWAY ?? point.prices.UNDER)}</span>
        </li>
      ))}
    </ol>
  );
}

function MarketEvidence({ market, generatedAt, kickoff, latestSnapshotAt, latestSnapshotCheckpoint }: { market: WorkspaceMarket; generatedAt: string | null; kickoff: string | null; latestSnapshotAt: string | null; latestSnapshotCheckpoint: string | null }) {
  const timelineCheckpoint = market.timeline_points[market.timeline_points.length - 1]?.checkpoint;
  const collectionCheckpoint = latestSnapshotCheckpoint && market.latest_snapshot_at && latestSnapshotAt
    && Date.parse(market.latest_snapshot_at) === Date.parse(latestSnapshotAt) ? latestSnapshotCheckpoint : null;
  return (
    <section className="v41-market" data-market={market.market} data-status={market.status}>
      <header><span>市场雷达 · {MARKET_LABELS[market.market]} · 仅绘制已落盘快照</span></header>
      <div className="v41-market-line"><strong>{market.main_line || "—"}</strong><span className={`v41-status v41-status--${market.status.toLowerCase()}`}>{market.status === "READY" ? `当前可得最新 · ${market.bookmaker_count} 家机构双边报价` : "证据不足"}</span></div>
      <Timeline kickoff={kickoff} market={market} />
      <p className="v41-market-foot">
        <span>{market.snapshot_count} 个真实快照 · 点间不插值、不推断缺失路径</span>
        <span>最新 {localDateTime(market.latest_snapshot_at)}</span>
      </p>
      <div className="v41-market-freshness"><span>市场证据</span><strong>{label(market.eligibility.observation_status)}</strong><span>捕获档位</span><strong>{timelineCheckpoint || collectionCheckpoint || "档位待确认"}</strong><span>距最新快照</span><strong>{ageLabel(generatedAt, market.latest_snapshot_at)}</strong></div>
      <div className="v41-market-semantics"><b>走势证据：{label(market.trend_evidence_status)}</b><span>{comparisonSummary(market)}</span></div>
      <div className="v41-market-semantics"><b>候选输入</b><span>候选报价可锁定：{label(market.eligibility.candidate_quote_lock_status)} · 候选可用模型：{label(market.eligibility.candidate_model_status)}</span></div>
    </section>
  );
}

function RiskSummary({ generatedAt, match }: { generatedAt: string | null; match: WorkspaceMatch }) {
  const lineupWaiting = match.readiness.missing_fields.includes("lineups")
    && match.lineup_collection.public_semantics.cause === "NOT_YET_DUE";
  return (
    <div className="v41-risk-list" aria-label="四轴风险">
      {(Object.keys(RISK_LABELS) as RiskAxisName[]).map((axis) => {
        const risk = match.risks[axis];
        const unassessed = risk.assessment_status === "UNASSESSED";
        const status = axis === "MODEL_RISK" && unassessed ? "尚无已验证校准" : unassessed ? "未评估" : label(risk.status);
        return <div className={`is-${risk.status.toLowerCase()}`} data-risk-axis={axis} key={axis}><span>{RISK_LABELS[axis]}</span><strong>{status}</strong><small>{risk.explanation || "没有可陈述的源证据"}</small>{axis === "DATA_RISK" && match.factor_checklist.enhancement_quality.state === "DEGRADED" ? <small>解释质量降级：{match.factor_checklist.enhancement_quality.missing_factor_ids.join("、")}；不作为模型预测硬门。</small> : null}{axis === "DATA_RISK" && lineupWaiting ? <small>等待中：首发（{match.lineup_collection.target_checkpoint} 窗口）· 计划 {scheduledEvaluation(match.lineup_collection.scheduled_at, generatedAt)}</small> : null}{risk.reason_codes.length ? <details className="v41-risk-codes"><summary>技术原因 {risk.reason_codes.length} 项</summary>{risk.reason_codes.map((reason) => <code key={`${axis}-${reason}`}>{reason}</code>)}</details> : null}</div>;
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

const FACTOR_CAUSE_LABELS: Record<Exclude<FixtureFactor["cause"], null>, string> = {
  NOT_YET_DUE: "未到采集窗口",
  AWAITING_COLLECTION: "窗口内等待采集",
  COLLECTION_WINDOW_MISSED: "采集窗口已错过",
  UNDER_SAMPLED: "样本不足",
  PROVIDER_NOT_AVAILABLE: "Provider 不提供",
  POLICY_DISABLED: "政策关闭，非缺失",
  NOT_MATERIALIZED: "尚未物化",
  SOURCE_NOT_CONFIGURED: "来源未配置",
  IDENTITY_UNRESOLVED: "身份未解析",
  NO_MATERIALIZED_HISTORY: "尚无已物化历史",
};

const FACTOR_PERMANENCE_LABELS: Record<FixtureFactor["permanence"], string> = {
  TRANSIENT: "临时状态",
  SELF_RESOLVING: "满足所示条件后可自愈",
  STRUCTURAL_PERMANENT: "结构性永久",
  UNKNOWN: "持久性尚未确认",
  NOT_APPLICABLE: "不适用",
};

function evidenceNumber(factor: FixtureFactor, key: string): number | null {
  const value = factor.evidence[key];
  return typeof value === "number" ? value : null;
}

function factorEvidence(factor: FixtureFactor): string {
  if (factor.factor_id === "MK_QUOTE_AGE") {
    const age = evidenceNumber(factor, "quote_age_seconds");
    return age === null ? "暂无快照" : `快照年龄 ${duration(age)}`;
  }
  if (factor.factor_id === "MK_BOOKMAKER_DEPTH") {
    return `${evidenceNumber(factor, "bookmaker_count") || 0} 家 / 至少 ${evidenceNumber(factor, "minimum_required") || 3} 家`;
  }
  if (factor.factor_id === "F9_TRUE_XG") {
    const home = evidenceNumber(factor, "home_sample_count") || 0;
    const away = evidenceNumber(factor, "away_sample_count") || 0;
    const shortfall = evidenceNumber(factor, "shortfall") || 0;
    if (factor.cause === "PROVIDER_NOT_AVAILABLE") return "Free 模式下永久不可得";
    if (factor.cause === "NO_MATERIALIZED_HISTORY") return `主队 0 场（差 ${evidenceNumber(factor, "home_shortfall") || 0}）· 客队 0 场（差 ${evidenceNumber(factor, "away_shortfall") || 0}）`;
    return `主队 ${home} 场 · 客队 ${away} 场${shortfall ? ` · 至少一队还差 ${shortfall} 场` : ""}`;
  }
  const count = evidenceNumber(factor, "sample_count");
  return count === null ? "查看技术证据" : `已物化 ${count} 条`;
}

function FactorRows({ factors }: { factors: FixtureFactor[] }) {
  return <div className="v41-factor-rows">{factors.map((factor) => <div className={`v41-factor-row is-${factor.state.toLowerCase()}`} key={`${factor.factor_id}-${factor.market || "fixture"}`}>
    <div><strong>{factor.display_name_zh}</strong>{factor.market ? <small>{MARKET_LABELS[factor.market]}</small> : null}{factor.factor_lifecycle === "EXPLANATION_ONLY" && !factor.numeric_effect_enabled ? <small>仅解释 · 不参与评分</small> : null}</div>
    <b>{factor.state === "READY" ? "已就绪" : factor.state === "PARTIAL" ? "部分就绪" : factor.state === "WAITING" ? "等待窗口" : factor.state === "DISABLED" ? "已关闭" : "缺失"}</b>
    <span>{factor.cause ? FACTOR_CAUSE_LABELS[factor.cause] : "证据已就绪"}</span>
    <span>{factorEvidence(factor)}</span>
    <small>{factor.next_window_at ? `下次窗口 ${localDateTime(factor.next_window_at)} · ${FACTOR_PERMANENCE_LABELS[factor.permanence]}` : FACTOR_PERMANENCE_LABELS[factor.permanence]}</small>
    <details><summary>技术证据</summary><code>{String(factor.evidence.source || "NO_SOURCE")}</code><code>{factor.factor_id}</code></details>
  </div>)}</div>;
}

function LedgerFact({ checklist }: { checklist: FixtureFactorChecklist }) {
  const ledger = checklist.ledger_fact;
  if (ledger.state === "NOT_CAPTURED") return <div className="v41-factor-ledger"><b>模型预测账本事实</b><strong>尚未冻结</strong><span>本场没有已持久化 ModelForecastCapture。</span></div>;
  const captureLeadSeconds = checklist.kickoff_utc && ledger.captured_at
    ? Math.floor((Date.parse(checklist.kickoff_utc) - Date.parse(ledger.captured_at)) / 1000)
    : null;
  const captureLead = captureLeadSeconds !== null && Number.isFinite(captureLeadSeconds)
    ? `${captureLeadSeconds >= 0 ? "开球前" : "开球后"} ${duration(Math.abs(captureLeadSeconds))}`
    : "距开球时长待确认";
  const captureHash = ledger.capture_identity_hash?.slice(0, 8) || "hash 待确认";
  const calibration = [ledger.calibration_version, ledger.calibration_status].filter(Boolean).join(" · ") || "校准信息待确认";
  const settlement = ledger.state === "SETTLED" ? `已结算 · ${localDateTime(ledger.settled_at || null)}` : "等待真实完场";
  return <div className="v41-factor-ledger"><b>模型预测账本事实</b><strong>{ledger.state === "SETTLED" ? "已结算" : "已冻结"}</strong><span>{localDateTime(ledger.captured_at || null)} · {captureLead} · capture {captureHash}<br />{ledger.model_version || "模型版本待确认"} · {calibration}<br />结算状态：{settlement}{ledger.state === "SETTLED" ? <><br />Brier {ledger.brier?.toFixed(4)} · LogLoss {ledger.log_loss?.toFixed(4)} · RPS {ledger.rps?.toFixed(4)}</> : null}</span></div>;
}

function FactorChecklist({ match }: { match: WorkspaceMatch }) {
  const checklist = match.factor_checklist;
  const modelGates = checklist.factors.filter((factor) => factor.role_model_forecast === "HARD_GATE");
  const candidateGates = checklist.factors.filter((factor) => factor.role_shadow_candidate === "HARD_GATE" && factor.role_model_forecast !== "HARD_GATE");
  const enhancements = checklist.factors
    .filter((factor) => !modelGates.includes(factor) && !candidateGates.includes(factor))
    .sort((left, right) => Number(left.cause === "POLICY_DISABLED") - Number(right.cause === "POLICY_DISABLED"));
  return <section className="v41-factor-checklist" aria-labelledby="factor-checklist-title">
    <header><div><span className="v41-eyebrow">本场因子体检</span><h2 id="factor-checklist-title">{checklist.conclusion_zh}</h2></div><div className="v41-factor-tracks"><b className={checklist.track_model_forecast.state === "READY" ? "is-ready" : "is-blocked"}>模型账本 {checklist.track_model_forecast.state}</b><b className={checklist.track_shadow_candidate.state === "READY" ? "is-ready" : "is-blocked"}>影子候选 {checklist.track_shadow_candidate.state}</b></div></header>
    <p>{checklist.market_identity_note_zh}</p>
    <LedgerFact checklist={checklist} />
    <div className="v41-factor-group"><h3>模型预测硬门 <small>决定能否进入验证账本</small></h3><FactorRows factors={modelGates} /></div>
    <div className="v41-factor-group"><h3>候选市场硬门 <small>让球 / 大小球独立显示</small></h3><FactorRows factors={candidateGates} /></div>
    <div className="v41-factor-group"><h3>增强与解释因子 <small>不影响能否推荐，只影响解释质量</small></h3><FactorRows factors={enhancements} /></div>
  </section>;
}

function MatchFocus({ generatedAt, match }: { generatedAt: string | null; match: WorkspaceMatch }) {
  const markets = [match.market_radar.markets.ASIAN_HANDICAP, match.market_radar.markets.TOTALS];
  const primary = markets.find((market) => market.main_line) || markets[0];
  const model = match.w2_analysis.model_view;
  const marketRelations = markets.map((market) => match.w2_analysis.model_market_relation[market.market]);
  const collectionWarning = match.market_collection.public_semantics.cause === "AWAITING_COLLECTION";
  const candidate = match.shadow_candidate;
  return (
    <article className="v41-focus" data-focus-type="MATCH" data-fixture-id={match.fixture_id}>
      <header className="v41-focus-header">
        <div><h1><MatchName match={match} /></h1><p>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认", match.competition_id)} · {localDateTime(match.kickoff_utc)} · 比赛 {match.fixture_id}</p></div>
        <div><span>开球时间</span><strong>{clock(match.kickoff_utc)}</strong></div>
      </header>
      <div className={`v41-focus-summary ${collectionWarning ? "is-warning" : ""}`}><b>{collectionWarning ? "采集状态" : "本场摘要"}</b><span>{match.factual_summary}</span></div>
      <div className="v41-focus-body">
        <div className="v41-focus-markets">{markets.map((market) => <MarketEvidence generatedAt={generatedAt} key={market.market} kickoff={match.kickoff_utc} latestSnapshotAt={match.market_collection.latest_snapshot_at} latestSnapshotCheckpoint={match.market_collection.latest_snapshot_checkpoint} market={market} />)}</div>
        <div className="v41-focus-meaning">
          <span className="v41-eyebrow">{candidate.status === "ACTIVE" ? "四层" : "三层"}语义 · 互不等同</span>
          <div className={`v41-three-layer ${candidate.status === "ACTIVE" ? "v41-three-layer--candidate" : ""}`}>
            <div><span>市场主事实</span><strong>{MARKET_LABELS[primary.market]}</strong><b>{primary.main_line || "—"}</b></div>
            <div><span>W2 诊断</span><strong>模型—市场比较</strong><b>逐市场 · {candidateAggregateLabel(match.readiness.market_aggregate_status)}</b></div>
            {candidate.status === "ACTIVE" ? <div><span>影子候选</span><strong>已形成</strong><b>进入赛后验证</b></div> : null}
            <div><span>正式推荐</span><strong>产品权限</strong><b>未启用</b></div>
          </div>
          {candidate.status === "ACTIVE" ? <section className="v41-candidate" data-candidate-status={candidate.status}>
            <header><span>影子候选 · 非正式推荐</span><b>验证中</b></header>
            <div><strong>{candidate.market ? MARKET_LABELS[candidate.market] : "市场待确认"} · {SELECTION_LABELS[candidate.selection || ""] || candidate.selection}</strong><span>盘口 {candidate.exact_line} · 赔率 {price(candidate.decimal_odds)}</span><small>已按 V4 身份进入统一前向账本；赛后自动结算并累计验证。</small></div>
            <footer>Formal、Lock、Production 与实盘保持关闭；达到既有证据门槛后另行提交 Owner 审批。</footer>
          </section> : null}
          <div className="v41-diagnostic" data-evaluation-status={match.evaluation_execution.status}><span /><p><b>评估执行结果：{match.evaluation_execution.status === "UNASSESSED" ? "尚未评估" : match.evaluation_execution.status}</b>{match.evaluation_execution.summary_zh}</p></div>
          <div className="v41-diagnostic"><span /><p><b>可比较模型（需已验证校准）：{label(model.status)}</b>{`让球：${label(marketRelations[0]?.status)}；大小球：${label(marketRelations[1]?.status)}。该状态只决定能否绘制模型—市场对比图；${marketRelations.some((relation) => ["COMPARABLE_WITHIN_MARKET_RANGE", "MODEL_OUTSIDE_MARKET_RANGE"].includes(relation?.status || "")) ? "已就绪市场可绘制诊断图。" : "当前暂不绘制。"}优先检查模型校准、特征时效、盘口身份和数据质量。`}</p></div>
          <RiskSummary generatedAt={generatedAt} match={match} />
          <Scoreline match={match} />
          <div className="v41-next"><span>市场 / 候选就绪</span><strong>{candidateAggregateLabel(match.readiness.market_aggregate_status)}</strong><span>采集状态</span><strong>{collectionLabel(match)}</strong><span>计划时刻</span><strong>{match.market_collection.scheduled_at ? scheduledEvaluation(match.market_collection.scheduled_at, generatedAt) : "暂无后续计划"}</strong><span>宽限结束</span><strong>{match.market_collection.window_end_at ? localDateTime(match.market_collection.window_end_at) : "不适用"}</strong><span>下次评估</span><strong>{nextEvaluation(match.readiness.next_eval_at, generatedAt)}</strong></div>
          <details className="v41-details"><summary>技术详情</summary><code>{match.intelligence_state}</code><code>{match.readiness.reason_code || "NO_REASON_CODE"}</code><code>market_aggregate={match.readiness.market_aggregate_status}</code><code>model_source={model.source_status}</code>{markets.map((market) => <span key={market.market}><code>{market.market}:{market.eligibility.model_diagnostic_status}</code>{market.reason_codes.map((reason) => <code key={`${market.market}-${reason}`}>{market.market}:{reason}</code>)}{market.eligibility.blockers.map((blocker) => <code key={`${market.market}-${blocker}`}>{market.market}:{blocker}</code>)}</span>)}</details>
        </div>
      </div>
      <FactorChecklist match={match} />
    </article>
  );
}

function GlobalFocus({ date, onDateChange, workspace }: Pick<Props, "date" | "onDateChange" | "workspace">) {
  const focus = workspace.global_focus;
  if (!focus) return <article className="v41-focus v41-global"><div className="v41-global-copy"><span className="v41-eyebrow">当前焦点</span><h1>尚未选择比赛</h1><p>请选择具有已持久化证据的比赛；页面不会自动填充其他焦点。</p></div></article>;
  const dayNoun = selectedDayNoun(workspace);
  const limited = focus.public_semantics.cause !== null;
  const empty = workspace.today_summary.match_count === 0;
  const calm = !limited && !empty;
  const presentation = publicPresentation(focus.public_semantics, {
    dayNoun,
    fixtureCount: workspace.today_summary.match_count,
    competitionCount: workspace.today_summary.competition_count,
    marketReadyCount: workspace.matches.filter((match) => match.readiness.market_evidence_status === "AVAILABLE").length,
    priorityCount: workspace.today_summary.priority_match_count,
  });
  const detail = limited ? `影响 ${focus.affected_fixture_count} 场比赛 · ${focus.affected_competition_count} 个联赛 —— 本足球日全部比赛` : calm ? `${workspace.today_summary.match_count} 场比赛未触发优先复核 —— 这是有效观测结果，不是系统未完成。` : `${workspace.runtime.active_whitelist_count} 个白名单联赛在本足球日均无赛程`;
  return (
    <article className={`v41-focus v41-global is-${presentation.tone}`} data-public-cause={focus.public_semantics.cause || "NONE"}>
      <div className="v41-global-copy"><span className="v41-eyebrow">{dayNoun}摘要</span><h1>{presentation.headline}</h1><p>{detail}</p></div>
      <section className="v41-global-explanation"><span>{limited ? "当前可用内容" : `${dayNoun}判定`}</span><strong>{limited ? presentation.summary : focus.factual_summary}</strong><p>{presentation.detail}</p><small>证据截至 {localDateTime(focus.source_as_of)}</small></section>
      <div className="v41-global-stats">
        <div><span>{limited ? "可查看赛程" : calm ? "优先复核" : "白名单联赛"}</span><strong>{limited ? `${workspace.today_summary.match_count} 场` : calm ? "0 场" : workspace.runtime.active_whitelist_count}</strong></div>
        <div><span>{limited ? "市场分析" : calm ? "覆盖比赛" : "本日赛程"}</span><strong>{limited ? "0 场" : calm ? `${workspace.today_summary.match_count} / ${workspace.today_summary.match_count}` : 0}</strong></div>
        <div><span>{empty ? "下一有赛日" : hasFutureEvaluation(focus.next_eval_at, workspace.generated_at) ? "下一次适用调度评估" : "适用调度记录"}</span><strong>{empty ? typeof workspace.navigation.next_available_date === "string" ? workspace.navigation.next_available_date : "尚未确认" : limited && !focus.next_eval_at ? "暂无适用于所选比赛日的调度记录" : scheduledEvaluation(focus.next_eval_at, workspace.generated_at)}</strong></div>
      </div>
      {limited ? <div className="v41-global-note"><span>说明</span><strong>{presentation.detail}</strong><small>本页面不发起任何 Provider 请求，也不会用缺失数据补算。</small></div> : calm ? <div className="v41-global-note"><span>说明</span><strong>页面内容少不会改变既有关注阈值。</strong><small>继续等待既有调度形成下一次持久化评估。</small></div> : null}
      {limited ? <details className="v41-details v41-global-technical"><summary>技术详情与读取保护</summary><code>{focus.reason_code}</code><code>provider_calls={workspace.read_contract.provider_calls}</code><code>db_writes={workspace.read_contract.db_writes}</code><code>no_call_on_read={String(workspace.read_contract.no_call_on_read)}</code></details> : null}
      {empty ? <nav className="v41-adjacent-days"><button onClick={() => onDateChange(typeof workspace.navigation.previous_date === "string" ? workspace.navigation.previous_date : dateShift(date, -1))} type="button">‹ 前一天</button><button onClick={() => onDateChange(typeof workspace.navigation.next_date === "string" ? workspace.navigation.next_date : dateShift(date, 1))} type="button">后一天 ›</button></nav> : null}
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
        ? `历史指标不完整（截至 ${localDateTime(quality.checkpoint_generated_at)}）`
        : "尚无可用模型质量证据";
  if (!available) return (
    <section className="v41-quality v41-quality--compact" id="validation">
      <header><span>全局模型质量</span><p><b>{qualityCopy}</b></p><a href="#secondary-validation">进入赛后验证</a></header>
    </section>
  );
  return (
    <section className="v41-quality" id="validation">
      <header><span>全局模型质量 · 已持久化验证证据</span><p>整体表现：<b>{qualityCopy}</b></p></header>
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

function ValidationCenter({ workspace }: { workspace: IntelligenceWorkspace }) {
  const modelForecast = workspace.validation.model_forecast;
  const evaluationFunnel = modelForecast.market_evaluation_funnel;
  const records = workspace.validation.forward_validation_records;
  const outcomes = records.outcomes;
  const settledCandidateCount = typeof outcomes.settled_sample_count === "number" ? outcomes.settled_sample_count : 0;
  const legacyAnalysisPickCount = Math.max(0, settledCandidateCount - modelForecast.current_flow_settled_count);
  const modelVerdict = modelForecast.settled_count < modelForecast.sample_target
    ? `模型验证：已结算 ${modelForecast.settled_count} 场，样本量远不足以判断模型好坏（需 ${modelForecast.sample_target} 场）。`
    : `模型验证：已结算 ${modelForecast.settled_count} 场，已达到 ${modelForecast.sample_target} 场目标。`;
  const candidateVerdict = modelForecast.current_flow_candidate_count === 0
    ? "候选：当前 T-30 四门流程尚未冻结任何候选。"
    : `候选：当前 T-30 四门流程已冻结 ${modelForecast.current_flow_candidate_count} 条候选。`;
  const replay = workspace.validation.history_replay;
  const finishedCount = workspace.matches.filter((match) => match.outcome.is_finished).length;
  const replayPresentation = publicPresentation(replay.public_semantics, { subject: "赛果", fixtureCount: workspace.matches.length, finishedCount, outcomeRecorded: workspace.matches.length > 0 && workspace.matches.every((match) => match.outcome.is_recorded) });
  const selectedRecordsLabel = historyRecordLabel(replay.record_kind);
  const outcomePresentation = (match: WorkspaceMatch) => publicPresentation(match.outcome.public_semantics, { subject: "赛果", fixtureCount: 1, finishedCount: match.outcome.is_finished ? 1 : 0, outcomeRecorded: match.outcome.is_recorded });
  return (
    <section className="v41-validation-center" id="secondary-validation" aria-labelledby="validation-title">
      <header>
        <div><span className="v41-eyebrow">跨比赛日累计证据</span><h2 id="validation-title">赛后验证</h2><p>先看系统是否可用；审计口径与历史记账默认折叠。</p></div>
      </header>
      <p className="v41-validation-verdict"><strong>{modelVerdict}</strong><span>{candidateVerdict}</span></p>
      <div className="v41-validation-layout">
        <section>
          <h3>模型预测验证账本</h3>
          <ul className="v41-validation-counts"><li><span>Capture</span><strong>{modelForecast.capture_count}</strong></li><li><span>Settled</span><strong>{modelForecast.settled_count}</strong></li><li><span>Pending</span><strong>{modelForecast.pending_count}</strong></li></ul>
          <p className="v41-validation-context">作用域：不依赖报价的模型预测账本。</p>
          <details className="v41-validation-audit"><summary>展开模型账本审计细节</summary>
            <ul className="v41-validation-counts"><li><span>已有 ≥{modelForecast.min_xg_matches} 场历史的球队</span><strong>{modelForecast.xg_ready_team_count}</strong></li><li><span>未来 7 天双方均就绪</span><strong>{modelForecast.next_7d_xg_ready_fixture_count}</strong></li></ul>
            <ul className="v41-validation-counts v41-model-forecast-buckets">{([['LT_6H', '<6h'], ['H6_TO_LT_24H', '6–24h'], ['D1_TO_D3', '1–3d'], ['GT_3D', '>3d']] as const).map(([bucket, bucketLabel]) => <li key={bucket}><span>{bucketLabel}</span><strong>{modelForecast.lead_time_buckets[bucket].settled_count}/{modelForecast.lead_time_buckets[bucket].capture_count}</strong></li>)}</ul>
            <ul className="v41-validation-counts">{Object.entries(modelForecast.data_versions).map(([version, rows]) => <li key={version}><span>{rows.team_xg_match_count === null ? version : `xG 数据版本 ${rows.team_xg_match_count.toLocaleString()} 行`}</span><strong>{rows.settled_count}/{rows.capture_count}</strong></li>)}</ul>
            <p className="v41-validation-context">lead-time 与数据版本数字均为 Settled / Capture；可复现性标记属于同级审计证据，不参与顶部可用性结论。</p>
          </details>
        </section>
        <section>
          <h3>候选流程</h3>
          <ul className="v41-validation-counts"><li><span>当前 T-30 流程已冻结候选</span><strong>{modelForecast.current_flow_candidate_count}</strong></li><li><span>历史已结算 ANALYSIS_PICK</span><strong>{legacyAnalysisPickCount}</strong></li></ul>
          <p className="v41-validation-warning"><strong>历史遗留，非当前流程产出。</strong>不显示命中率：n={legacyAnalysisPickCount}、选择过程尚未审计，且与 Phase 0.5 全量回测的 NO_EDGE 结论相反。</p>
          <details className="v41-validation-audit"><summary>展开当前流程逐门覆盖（固定分母 {evaluationFunnel.market_unit_count}）</summary>
            <ul className="v41-validation-counts">{([
              ['model_ready', '模型就绪'],
              ['mainline_parsed', '主盘解析'],
              ['bookmaker_depth', '深度通过'],
              ['quote_fresh', '时效通过'],
              ['evaluated', '实际评估'],
              ['no_edge', 'NO_EDGE'],
              ['candidate', '动态评估候选判定'],
            ] as const).map(([gate, gateLabel]) => <li key={gate}><span>{gateLabel}</span><strong>{evaluationFunnel.gate_counts[gate] ?? 0}/{evaluationFunnel.market_unit_count}</strong></li>)}</ul>
            <p className="v41-validation-context">分母为所有已冻结模型预测的 fixture × AH/TOTALS；已持久化 {evaluationFunnel.persisted_market_unit_count}/{evaluationFunnel.market_unit_count}，带真实写入时刻 {evaluationFunnel.recorded_at_count}。动态评估候选判定不等于已在 T-30 锁定为候选。</p>
          </details>
          <details className="v41-validation-audit"><summary>展开历史账本记账明细</summary>
            <ul className="v41-validation-counts"><li><span>赛果基表记录</span><strong>{records.validation_count}</strong></li><li><span>旧账本纳入统计</span><strong>{records.eligible_count}</strong></li><li><span>候选待结算</span><strong>{records.pending_count}</strong></li><li><span>无 Pick / 入场报价</span><strong>{records.excluded_count}</strong></li></ul>
            <p className="v41-validation-context">作用域：跨比赛日历史记账；不混入所选比赛日的前向记录与赛果缺口。</p>
          </details>
        </section>
        <section>
          <h3>{workspace.date} {selectedRecordsLabel}</h3>
          <p className="v41-validation-context">所选比赛日 {workspace.today_summary.match_count} 场 · 已形成 {replay.decision_summary.total_cards} 张{selectedRecordsLabel}</p>
          {workspace.matches.length ? <ol className="v41-validation-matches">{byKickoff(workspace.matches).map((match) => <li key={match.fixture_id}><time>{localDateTime(match.kickoff_utc)}</time><strong><MatchName match={match} /></strong><span>{outcomePresentation(match).label}</span></li>)}</ol> : <p className="v41-validation-empty">所选比赛日没有比赛记录；可使用上方日期浏览历史。</p>}
          {workspace.matches.length ? <p className={replayPresentation.tone === "warning" ? "v41-validation-gaps" : "v41-validation-ok"}>{replayPresentation.summary}</p> : null}
        </section>
      </div>
      {workspace.validation.league_performance.length ? <details className="v41-validation-leagues"><summary>按联赛查看验证状态（{workspace.validation.league_performance.length}）</summary><ul>{workspace.validation.league_performance.slice(0, 13).map((league) => <li key={`${league.competition_id}-${league.source_league}`}><strong>{translateCompetition(league.competition_name || league.league, league.canonical_competition_id || league.competition_id)}</strong><span>{league.only_record_reason === "PROBABILITY_QUALITY_NOT_READY" ? "概率质量待就绪" : league.only_record_reason === "AGGREGATION_CONFLICT" ? "聚合冲突" : league.only_record_reason === "SAMPLE_INSUFFICIENT" ? "样本不足" : "可用"}</span></li>)}</ul></details> : null}
      <details className="v41-validation-technical"><summary>技术证据详情</summary><p>回放状态：<code>{replay.status}</code></p><p>原始缺口：{replay.replay_gaps.map((gap) => <code key={gap}>{gap}</code>)}</p><p>读取合同：<code>provider_calls={workspace.read_contract.provider_calls}</code> <code>db_writes={workspace.read_contract.db_writes}</code> <code>no_call_on_read={String(workspace.read_contract.no_call_on_read)}</code></p></details>
    </section>
  );
}

function SecondaryViews({ workspace }: { workspace: IntelligenceWorkspace }) {
  const replay = workspace.validation.history_replay;
  const recordLabel = historyRecordLabel(replay.record_kind);
  const finishedCount = workspace.matches.filter((match) => match.outcome.is_finished).length;
  const replayPresentation = publicPresentation(replay.public_semantics, { subject: "赛果", fixtureCount: workspace.matches.length, finishedCount, outcomeRecorded: workspace.matches.length > 0 && workspace.matches.every((match) => match.outcome.is_recorded) });
  const publicStatus = selectedDayPublicStatus(workspace);
  return (
    <section className="v41-secondary" aria-label="数据与系统 / 辅助详情">
      <details id="all-matches"><summary>全部比赛</summary><ol>{byKickoff(workspace.matches).map((match) => <li key={match.fixture_id}><span>{localDateTime(match.kickoff_utc)}</span><strong><MatchName match={match} /></strong><b>{label(match.readiness.market_aggregate_status)}</b></li>)}</ol></details>
      <details data-contract="HISTORICAL_INCREMENTAL_EDGE=NOT_PROVEN" id="history"><summary>证据审计台 / {recordLabel}</summary><p>{recordLabel} {replay.decision_summary.total_cards} · {replayPresentation.summary}</p><details><summary>技术合同</summary><p>原始状态：<code>{replay.status}</code></p><p>原始缺口：{replay.replay_gaps.map((gap) => <code key={gap}>{gap}</code>)}</p><code>HISTORICAL_INCREMENTAL_EDGE=NOT_PROVEN</code></details></details>
      <details id="system-status"><summary>系统状态与读取合同</summary><p>13 联赛 · 影子候选 {workspace.runtime.candidate === "SHADOW_ONLY" ? "已启用" : "未启用"} · 正式、锁定、生产与实盘均关闭</p><p>所选比赛日公开状态：{publicStatus.label}</p><details><summary>技术字段</summary><p><code>{workspace.data_operations.system_health}</code></p><p><code>provider_calls={workspace.read_contract.provider_calls}</code> · <code>db_writes={workspace.read_contract.db_writes}</code> · <code>would_write_checkpoint={String(workspace.read_contract.would_write_checkpoint)}</code> · <code>no_call_on_read={String(workspace.read_contract.no_call_on_read)}</code></p></details></details>
    </section>
  );
}

export function IntelligenceConsole(props: Props) {
  const { workspace } = props;
  const [selectedId, setSelectedId] = useState<string | null>(workspace.selected_fixture_id);

  useEffect(() => {
    setSelectedId(workspace.selected_fixture_id);
  }, [workspace.selected_fixture_id, workspace.request_id]);

  const selected = useMemo(() => {
    return workspace.matches.find((match) => match.fixture_id === selectedId) || null;
  }, [selectedId, workspace.matches]);

  return (
    <main aria-label="W2 INTELLIGENCE" className="dashboard-v41" data-public-cause={selectedDaySemantics(workspace).cause || "NONE"} data-intelligence-vocabulary="MODEL_MARKET_DISAGREEMENT" data-schema-version={workspace.schema_version} id="top">
      <Header {...props} />
      <RecentDateNav date={props.date} onDateChange={props.onDateChange} workspace={workspace} />
      <TodaySummary workspace={workspace} />
      <div className="v41-main">
        <PriorityShortlist key={workspace.request_id} workspace={workspace} onSelect={setSelectedId} selectedId={selectedId} />
        {selected ? <MatchFocus generatedAt={workspace.generated_at} match={selected} /> : <GlobalFocus date={props.date} onDateChange={props.onDateChange} workspace={workspace} />}
      </div>
      <ValidationCenter workspace={workspace} />
      <QualityRail workspace={workspace} />
      <SecondaryViews workspace={workspace} />
    </main>
  );
}
