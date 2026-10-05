import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchIntelligenceMatch, fetchSystemHealth } from "../lib/intelligenceWorkspaceApi";
import { footballDayShanghai, translateCompetition } from "../lib/formatters";
import { publicPresentation } from "../lib/publicPresentation";
import { formatAhMarketHandicap } from "../lib/pricingDisplay";
import type { IntelligenceWorkspaceList, PerformanceSummary, SystemHealth, TodayRecommendation, WorkspaceMatch, WorkspaceMatchItem, WorkspaceMatchProjectionError } from "../types/intelligenceWorkspace";

type Tab = "matches" | "validation" | "validation-calibrated" | "replay";
type Props = {
  workspace: IntelligenceWorkspaceList;
  date: string;
  initialFixtureId?: string | null;
  onDateChange: (date: string) => void;
  onRefresh: () => void;
  loading: boolean;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  tabContent?: ReactNode;
  renderInputDiagnostics?: (match: WorkspaceMatch) => ReactNode;
  historicalQuality?: ReactNode;
  capabilityStatus?: ReactNode;
  dayContext?: ReactNode;
};

const EMPTY_PERFORMANCE: PerformanceSummary = {
  calibration_identity: null,
  status: "UNAVAILABLE",
  total_profit_units: 0,
  total_profit_units_with_rebate: 0,
  last_7_days: { match_count: 0, hit_rate: null, profit_units: 0 },
  last_30_days: { match_count: 0, hit_rate: null, profit_units: 0 },
  daily_series: [],
};

function signed(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(digits)}`;
}
function percent(value: number | null | undefined): string {
  return value === null || value === undefined || !Number.isFinite(value) ? "—" : `${(value * 100).toFixed(1)}%`;
}
function isoDateShift(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}
function localDate(value: string | null | undefined, options: Intl.DateTimeFormatOptions = {}): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", ...options }).format(date);
}
function localTime(value: string | null | undefined): string {
  return localDate(value, { hour: "2-digit", minute: "2-digit", hour12: false });
}
function fixtureTime(value: string | null | undefined, footballDay: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "—";
  const calendarDay = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  return `${calendarDay > footballDay ? "次日 " : ""}${localTime(value)}`;
}
function dayLabel(value: string): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", weekday: "short" }).format(date);
}
function upcomingDayLabel(value: string, isToday: boolean): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  const label = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric" }).format(date);
  return isToday ? `${label}·今天` : label;
}
function statusLabel(value: string): string {
  return ({ settled: "已结算", pending: "待赛果", blocked: "结算阻断", void: "无效", confirmed: "已确认", candidate: "候选", withdrawn: "已撤回" } as Record<string, string>)[value] || value || "—";
}
function marketLabel(value: string | null): string {
  return ({ ASIAN_HANDICAP: "让球", TOTALS: "大小球" } as Record<string, string>)[value || ""] || value || "—";
}
function sideLabel(value: string | null): string {
  return ({ HOME: "主", AWAY: "客", OVER: "大", UNDER: "小" } as Record<string, string>)[value || ""] || value || "—";
}
function finalStatusLabel(value: string): string {
  return ({
    UNASSESSED: "未评估",
    GATE_BLOCKED: "门禁阻断",
    CANDIDATE_ACTIVE: "候选活跃",
    CHECKPOINT_MISSED: "检查点错过",
    PROVIDER_EMPTY: "数据缺失",
    EVALUATION_ERROR: "评估错误",
    NO_EDGE: "无优势",
  } as Record<string, string>)[value] || value;
}
function settlementKind(value: string | null | undefined): "win" | "lose" | "push" {
  if (value === "WIN" || value === "HALF_WIN") return "win";
  if (value === "LOSS" || value === "HALF_LOSS") return "lose";
  return "push";
}
function resultLabel(value: string | null | undefined): string {
  return ({ WIN: "赢", HALF_WIN: "赢一半", PUSH: "走盘", HALF_LOSS: "输一半", LOSS: "输", VOID: "无效" } as Record<string, string>)[value || ""] || value || "—";
}
function teamName(value: unknown): string {
  if (value && typeof value === "object" && "display_name" in value && typeof value.display_name === "string") return value.display_name;
  return typeof value === "string" && value ? value : "球队待确认";
}
function matchTeams(match: WorkspaceMatchItem): [string, string] {
  const item = match as unknown as Record<string, unknown>;
  return [teamName(item.home_team_label || item.home_team_name), teamName(item.away_team_label || item.away_team_name)];
}
const LIVE_STATUSES = new Set(["1H", "2H", "HT", "ET", "BT", "P", "LIVE", "IN_PLAY"]);
const FINISHED_STATUSES = new Set(["FT", "AET", "PEN", "FINISHED"]);
// 列表是赛前视角：标签按开球状态区分，未开赛/进行中不再落到赛果语义。
function fixtureStatusTag(match: WorkspaceMatchItem, v3Count: number): string {
  if ("projection_error" in match) return "投影异常";
  if (v3Count) return `${v3Count} 条 v3 推荐`;
  const raw = (match.status || "").toUpperCase();
  if (match.outcome.is_finished || FINISHED_STATUSES.has(raw)) {
    return publicPresentation(match.outcome.public_semantics, {
      subject: "赛果",
      fixtureCount: 1,
      finishedCount: match.outcome.is_finished ? 1 : 0,
      outcomeRecorded: match.outcome.is_recorded,
    }).label;
  }
  if (LIVE_STATUSES.has(raw)) return "进行中";
  return "未开赛";
}
function performance(workspace: IntelligenceWorkspaceList): PerformanceSummary {
  return workspace.performance_summary || EMPTY_PERFORMANCE;
}
function recommendations(workspace: IntelligenceWorkspaceList): TodayRecommendation[] {
  return workspace.today_recommendations || [];
}

function SystemHealthPanel() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  useEffect(() => {
    const controller = new AbortController();
    fetchSystemHealth(controller.signal)
      .then((payload) => {
        setHealth(payload);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
      });
    return () => controller.abort();
  }, []);
  if (state === "loading") {
    return <details className="w2-system-health"><summary>系统健康 <span>只读 · 不调用 Provider</span></summary><p className="w2-system-health__empty">正在读取系统健康状态…</p></details>;
  }
  if (state === "error" || !health) {
    return <details className="w2-system-health"><summary>系统健康 <span>只读 · 不调用 Provider</span></summary><p className="w2-system-health__empty">系统健康状态暂不可用。</p></details>;
  }
  const items = [
    { label: "数据新鲜度", ok: health.data_freshness.ok, detail: health.data_freshness.f9_snapshot_lag_hours === null ? "F9 快照断供（无快照）" : `F9 快照滞后 ${health.data_freshness.f9_snapshot_lag_hours.toFixed(1)}h · 阈值 ${health.data_freshness.threshold_hours}h` },
    { label: "推荐链路", ok: health.recommendation_chain.ok, detail: `今日 ${health.recommendation_chain.match_count} 场 · 到决策点 ${health.recommendation_chain.decision_due_count} 场 · 推荐 ${health.recommendation_chain.selected_count} 场 · SKIP ${health.recommendation_chain.skip_count} 场` },
    { label: "采集额度", ok: health.collection_quota.ok, detail: health.collection_quota.remaining_quota === null ? "额度未知" : `Provider 剩余 ${health.collection_quota.remaining_quota} · 保留桶 ${health.collection_quota.reserve_bucket}` },
    { label: "结算", ok: health.settlement.ok, detail: `已结算 ${health.settlement.settled_count} 场 · 异常 ${health.settlement.anomaly_count} 场` },
    { label: "告警", ok: health.alerts.length === 0, detail: health.alerts.length ? `${health.alerts.length} 条活跃告警` : "无活跃告警" },
  ];
  return (
    <details className="w2-system-health">
      <summary>系统健康 <span>只读 · 不调用 Provider</span></summary>
      <div className="w2-system-health__grid">
        {items.map((item) => (
          <div className={`w2-system-health__item${item.ok ? " is-ok" : " is-warn"}`} key={item.label}>
            <strong>{item.ok ? "✓" : "!"} {item.label}</strong>
            <span>{item.detail}</span>
          </div>
        ))}
        {health.alerts.length ? <p className="w2-system-health__alert">{health.alerts.map((alert) => `${alert.type}：${alert.detail}`).join("；")}</p> : null}
      </div>
    </details>
  );
}

function Result({ value, profit }: { value?: string | null; profit?: number | null }) {
  const kind = settlementKind(value);
  return <span className={`w2-result w2-result--${kind}`}><span className="w2-result__icon" aria-hidden="true">{kind === "win" ? "✓" : kind === "lose" ? "✗" : "–"}</span>{resultLabel(value)} {profit === null || profit === undefined ? null : <span className="num">{signed(profit)}</span>}</span>;
}

function PnlChart({ points }: { points: PerformanceSummary["daily_series"] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  if (!points.length) return <div className="w2-chart__empty muted">暂无近 30 天累计盈亏数据</div>;
  const width = 600;
  const height = 170;
  const pad = { left: 30, right: 44, top: 12, bottom: 22 };
  const values = points.map((point) => point.cumulative_profit_units);
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const margin = Math.max(1, (max - min) * 0.15);
  const yMin = Math.floor(min - margin);
  const yMax = Math.ceil(max + margin);
  const span = yMax - yMin || 1;
  const x = (index: number) => pad.left + (index / Math.max(1, points.length - 1)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + ((yMax - value) / span) * (height - pad.top - pad.bottom);
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(point.cumulative_profit_units).toFixed(1)}`).join(" ");
  const area = `${path} L${x(points.length - 1)} ${y(0)} L${x(0)} ${y(0)} Z`;
  const ticks = Array.from({ length: 5 }, (_, index) => yMin + (span * index) / 4);
  const dateLabel = (value: string) => value.slice(5).replace("-", "–");
  const last = points[points.length - 1];
  return <>
    <svg id="pnlSvg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="近 30 天累计盈亏折线图">
      {ticks.map((tick) => <g key={tick}><line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} stroke={Math.abs(tick) < 1e-8 ? "var(--v41-ink-3)" : "var(--v41-line-faint)"} strokeDasharray={Math.abs(tick) < 1e-8 ? "3 3" : undefined} /><text x={pad.left - 6} y={y(tick) + 4} textAnchor="end" fontSize="10.5" fill="var(--v41-ink-3)" className="num">{Number(tick.toFixed(1))}</text></g>)}
      <path d={area} fill="var(--v41-accent-soft)" opacity="0.55" />
      <path d={path} fill="none" stroke="var(--v41-accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(points.length - 1)} cy={y(last.cumulative_profit_units)} r="4.5" fill="var(--v41-accent)" stroke="var(--v41-panel)" strokeWidth="2" />
      <text x={Math.min(width - 50, x(points.length - 1) + 8)} y={y(last.cumulative_profit_units) + 4} fill="var(--v41-ink)" fontSize="11" className="num">{signed(last.cumulative_profit_units)}</text>
      {[0, Math.floor((points.length - 1) / 2), points.length - 1].map((index) => <text key={index} x={x(index)} y={height - 6} textAnchor={index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"} fontSize="10.5" fill="var(--v41-ink-3)" className="num">{dateLabel(points[index].date)}</text>)}
      {hovered !== null ? <><line x1={x(hovered)} x2={x(hovered)} y1={pad.top} y2={height - pad.bottom} stroke="var(--v41-ink-3)" /><circle cx={x(hovered)} cy={y(points[hovered].cumulative_profit_units)} r="4.5" fill="var(--v41-accent)" stroke="var(--v41-panel)" strokeWidth="2" /></> : null}
      <rect x={pad.left} y={pad.top} width={width - pad.left - pad.right} height={height - pad.top - pad.bottom} fill="transparent" onPointerMove={(event) => { const box = event.currentTarget.ownerSVGElement?.getBoundingClientRect(); if (!box) return; const px = ((event.clientX - box.left) / box.width) * width; setHovered(Math.max(0, Math.min(points.length - 1, Math.round(((px - pad.left) / (width - pad.left - pad.right)) * (points.length - 1))))); }} onPointerLeave={() => setHovered(null)} />
    </svg>
    {hovered !== null ? <div className="w2-chart__tip" style={{ left: `${(x(hovered) / width) * 100}%`, top: `${(y(points[hovered].cumulative_profit_units) / height) * 170 + 35}px` }}><strong>{points[hovered].date}</strong>当日 <span className="num">{signed(points[hovered].daily_profit_units)}</span> · 累计 <span className="num">{signed(points[hovered].cumulative_profit_units)}</span></div> : <div className="w2-chart__tip" hidden />}
  </>;
}

function FixtureList({ workspace, picks, onSelect }: { workspace: IntelligenceWorkspaceList; picks: TodayRecommendation[]; onSelect: (fixtureId: string) => void }) {
  const [league, setLeague] = useState("全部");
  const allMatches = workspace.matches.slice().sort((left, right) => {
    const rank = (match: WorkspaceMatchItem) => {
      if (!("priority_reason_primary" in match) || !match.priority_reason_primary) return 2;
      return "readiness" in match && match.readiness.status === "READY" ? 0 : 1;
    };
    return rank(left) - rank(right)
      || String(left.kickoff_utc || "").localeCompare(String(right.kickoff_utc || ""))
      || left.fixture_id.localeCompare(right.fixture_id);
  });
  const competitionKey = (match: WorkspaceMatchItem) => match.competition_name || match.competition_id || "赛事待确认";
  const leagueLabels = new Map<string, string>();
  for (const match of allMatches) {
    const key = competitionKey(match);
    if (!leagueLabels.has(key)) leagueLabels.set(key, translateCompetition(key, match.competition_id));
  }
  const leagues = Array.from(leagueLabels.keys());
  const matches = league === "全部" ? allMatches : allMatches.filter((match) => competitionKey(match) === league);
  return <div className="w2-match-browser">{leagues.length > 1 ? <div className="w2-match-filters" role="toolbar" aria-label="按联赛筛选比赛"><button type="button" aria-pressed={league === "全部"} onClick={() => setLeague("全部")}>全部 {allMatches.length}</button>{leagues.map((name) => <button type="button" aria-pressed={league === name} key={name} onClick={() => setLeague(name)}>{leagueLabels.get(name)} {allMatches.filter((match) => competitionKey(match) === name).length}</button>)}</div> : null}<ul className="w2-fixtures">{matches.length ? matches.map((match) => {
    const [home, away] = matchTeams(match);
    const radar = "market_radar" in match ? match.market_radar : null;
    const ah = radar?.markets?.ASIAN_HANDICAP;
    const totals = radar?.markets?.TOTALS;
    const v3Count = picks.filter((pick) => pick.fixture_id === match.fixture_id).length;
    return <li className="w2-fixture" data-fixture-id={match.fixture_id} data-v3-count={v3Count} data-priority={"priority_reason_primary" in match ? match.priority_reason_primary || "NONE" : "UNKNOWN"} title={`${home} vs ${away}`} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} onKeyDown={(event) => { if (event.key === "Enter") onSelect(match.fixture_id); }} role="button" tabIndex={0}>
      <span className="num">{fixtureTime(match.kickoff_utc, workspace.date)}</span>
      <span className="w2-fixture__league"><span className="w2-league">{translateCompetition(match.competition_name || match.competition_id || "赛事待确认", match.competition_id)}</span></span>
      <div className="w2-fixture__teams" aria-label={`${home} vs ${away}`}><span>{home}</span>{" "}<span className="faint">vs</span>{" "}<span>{away}</span></div>
      <div className="w2-market"><span>让球 <span className="num">{formatAhMarketHandicap(ah?.main_line) ?? "—"}</span></span><span className="num">{ah?.status === "READY" ? "市场已就绪" : "数据待补"}</span></div>
      <div className="w2-market"><span>大小 <span className="num">{totals?.main_line ?? "—"}</span></span><span className="num">{totals?.status === "READY" ? "市场已就绪" : "数据待补"}</span></div>
      <span className={`w2-tag${v3Count ? " w2-tag--pick" : ""}`}>{fixtureStatusTag(match, v3Count)}</span>
    </li>;
  }) : <li className="w2-empty-row">当前足球日没有持久化比赛。</li>}</ul></div>;
}

export function DesignV1Overview({ workspace, date, initialFixtureId, onDateChange, onRefresh, loading, activeTab, onTabChange, tabContent, renderInputDiagnostics, historicalQuality, capabilityStatus, dayContext }: Props) {
  const summary = performance(workspace);
  const publicAvailable = summary.schema_version === "w2.ah_ou_v3_public_performance.v1" && Array.isArray(workspace.today_recommendations);
  const picks = publicAvailable ? recommendations(workspace) : [];
  const [activeLeague, setActiveLeague] = useState("全部");
  const [webVersion, setWebVersion] = useState<string | null>(null);
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(initialFixtureId || null);
  const [selectedDetail, setSelectedDetail] = useState<WorkspaceMatch | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "error">("idle");
  const selectedFailure = workspace.matches.find((match) => match.fixture_id === selectedFixtureId && "projection_error" in match) as WorkspaceMatchProjectionError | undefined;
  useEffect(() => {
    if (!selectedFixtureId) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setSelectedFixtureId(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedFixtureId]);
  useEffect(() => {
    if (!selectedFixtureId) return;
    if (workspace.matches.some((match) => match.fixture_id === selectedFixtureId && "projection_error" in match)) {
      setDetailState("idle");
      setSelectedDetail(null);
      return;
    }
    const controller = new AbortController();
    setDetailState("loading");
    setSelectedDetail(null);
    fetchIntelligenceMatch(selectedFixtureId, controller.signal).then((detail) => { setSelectedDetail(detail); setDetailState("idle"); }).catch((error: unknown) => { if (error instanceof DOMException && error.name === "AbortError") return; setDetailState("error"); });
    return () => controller.abort();
  }, [selectedFixtureId, workspace.matches]);
  const [theme, setTheme] = useState<"light" | "dark">(() => document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");
  const [mobileView, setMobileView] = useState<"picks" | "matches" | "review" | "more">("picks");
  useEffect(() => {
    const saved = localStorage.getItem("w2-theme");
    if (saved === "light" || saved === "dark") setTheme(saved);
  }, []);
  const filteredPicks = useMemo(() => activeLeague === "全部" ? picks : picks.filter((pick) => pick.competition_name_zh === activeLeague), [activeLeague, picks]);
  const leagues = ["全部", ...Array.from(new Set(picks.map((pick) => pick.competition_name_zh).filter((value): value is string => Boolean(value))))];
  const nextPick = picks.filter((pick) => pick.status === "pending" && pick.kickoff_utc && new Date(pick.kickoff_utc).valueOf() > Date.now()).sort((left, right) => String(left.kickoff_utc).localeCompare(String(right.kickoff_utc)))[0];
  const upcoming = workspace.matches.filter((match) => match.kickoff_utc && new Date(match.kickoff_utc).valueOf() > Date.now()).sort((left, right) => String(left.kickoff_utc).localeCompare(String(right.kickoff_utc))).slice(0, 5);
  const selectedDay = workspace.date_strip?.find((item) => item.football_day === date);
  const dayStatus = publicPresentation(selectedDay?.public_semantics || { scope: "SELECTED_DAY", cause: null }, {
    dayNoun: date === footballDayShanghai() ? "今日" : "所选比赛日",
    fixtureCount: selectedDay?.fixture_count ?? workspace.matches.length,
    competitionCount: selectedDay?.competition_count ?? 0,
    marketReadyCount: selectedDay?.market_collection_window_status === "MARKET_EVIDENCE_AVAILABLE" ? selectedDay.market_evidence_fixture_count : 0,
    priorityCount: workspace.today_summary?.priority_match_count,
    finishedCount: selectedDay?.finished_fixture_count,
  });
  const settled = picks.filter((pick) => pick.status === "settled");
  const todayProfit = summary.daily_series.find((point) => point.date === date)?.daily_profit_units;
  const loadWebVersion = (open: boolean) => {
    if (!open || webVersion !== null) return;
    fetch("/meta.json", { headers: { Accept: "application/json" } }).then((response) => response.ok ? response.json() : null).then((meta: unknown) => {
      if (meta && typeof meta === "object" && "release_id" in meta && typeof meta.release_id === "string") setWebVersion(meta.release_id);
    }).catch(() => { /* Version is optional display metadata. */ });
  };
  const setThemeMode = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("w2-theme", next);
  };
  const selectMobile = (view: "picks" | "matches" | "review" | "more") => {
    setMobileView(view);
    if (view === "review") onTabChange("validation");
    if (view === "matches" || view === "picks") onTabChange("matches");
    if (view === "more") onTabChange("replay");
  };
  return <div className="w2-app" data-mview={mobileView}>
    <header className="w2-statusbar">
      <div className="w2-statusbar__inner">
        <div className="w2-brand"><span className="w2-brand__mark">W2</span><span className="w2-brand__name">足球情报</span></div>
        <div className="w2-day" role="group" aria-label="足球日切换">
          <button type="button" aria-label="前一个足球日" onClick={() => onDateChange(isoDateShift(date, -1))}>‹</button>
          <div className="w2-day__label"><strong>{dayLabel(date)}</strong><span>足球日 12:00 至次日 12:00</span></div>
          <button type="button" aria-label="后一个足球日" onClick={() => onDateChange(isoDateShift(date, 1))}>›</button>
          <input type="date" aria-label="选择比赛日" value={date} onChange={(event) => { if (event.target.value) onDateChange(event.target.value); }} />
          <button type="button" onClick={() => onDateChange(footballDayShanghai())}>今天</button>
          <button type="button" disabled={loading} onClick={onRefresh}>刷新</button>
        </div>
        <div className="w2-statusbar__upcoming" aria-label="未来赛程">
          {(workspace.upcoming_football_days || []).map((day, index) => {
            const pending = Math.max(0, day.match_count - day.evaluated_count);
            return (
              <div className="w2-statusbar__upcoming-item" key={day.date}>
                <span className="w2-statusbar__upcoming-date">{upcomingDayLabel(day.date, index === 0)}</span>
                <span className="w2-statusbar__upcoming-count num">{day.match_count}<small>场</small></span>
                <span className="w2-statusbar__upcoming-foot">已评估 <b className="num">{day.evaluated_count}</b> · 待 <b className="num">{pending}</b></span>
              </div>
            );
          })}
        </div>
        <div className="w2-badges" data-component="StatusBadge">
          <span className="w2-badge" title={workspace.generated_at ? `更新于 ${localDate(workspace.generated_at, { hour: "2-digit", minute: "2-digit", hour12: false })}` : undefined}><span className="w2-badge__dot" aria-hidden="true" />{workspace.system_status?.data || "数据未就绪"}</span>
          <span className="w2-badge"><span aria-hidden="true">✓</span>{workspace.system_status?.recommendations || "推荐未开启"}</span>
        </div>
        <div className="w2-statusbar__meta"><span><span className="w2-updated-label">更新于 </span><span className="num">{localDate(workspace.generated_at, { hour: "2-digit", minute: "2-digit", hour12: false })}</span></span><button type="button" className="w2-theme" aria-label="切换深浅色" onClick={setThemeMode}><span aria-hidden="true">◐</span><span>{theme === "light" ? "浅色" : "深色"}</span></button></div>
      </div>
    </header>
    <main className="w2-main">
      <section className={`w2-day-status w2-day-status--${dayStatus.className}`} data-public-cause={selectedDay?.public_semantics?.cause || "NONE"} aria-label="所选比赛日状态">
        <strong>{dayStatus.headline}</strong><span>{dayStatus.label} · {dayStatus.summary}{workspace.today_summary?.priority_match_count === 0 && workspace.matches.length > 0 && !selectedDay?.public_semantics?.cause ? ` ${workspace.matches.length} 场比赛未触发优先复核。` : ""}</span>
      </section>
      {dayContext ? <details className="w2-day-diagnostics"><summary>比赛日采集与调度详情</summary>{dayContext}</details> : null}
      <section data-mviews="picks" aria-label="核心指标">
        <div className="w2-kpis-wrap"><div className="w2-kpis">
          <article className="w2-kpi"><span className="w2-kpi__label">今日推荐</span><span className="w2-kpi__value num">{publicAvailable ? picks.length : "—"}<small>条</small></span><span className="w2-kpi__foot">已结算 <b className="num">{settled.length}</b> · 待赛果 <b className="num">{picks.filter((pick) => pick.status === "pending").length}</b> · 阻断 <b className="num">{picks.filter((pick) => pick.status === "blocked").length}</b></span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">今日结算</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(todayProfit) : "—"}<small>单位</small></span><span className="w2-kpi__foot">{settled.filter((pick) => pick.result === "WIN" || pick.result === "HALF_WIN").length} 赢 · {settled.filter((pick) => pick.result === "LOSS" || pick.result === "HALF_LOSS").length} 输</span></article>
          <article className="w2-kpi w2-kpi--next"><span className="w2-kpi__label">下一场推荐</span><span className="w2-kpi__value num">{nextPick ? localTime(nextPick.kickoff_utc) : "—"}<small>{nextPick ? "开赛" : "暂无"}</small></span><span className="w2-kpi__foot">{nextPick ? `${nextPick.competition_name_zh || "赛事待确认"} · ${nextPick.home || "主队待确认"} vs ${nextPick.away || "客队待确认"}` : "暂无待开赛推荐"}</span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">总盈亏</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.total_profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot">含返水 <b className="num">{summary.status === "AVAILABLE" ? signed(summary.total_profit_units_with_rebate) : "—"}</b> · 当前模型版本 · 全历史</span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">近 7 天</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.last_7_days.profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot"><b className="num">{summary.status === "AVAILABLE" ? summary.last_7_days.match_count : "—"}</b> 条 · 命中 <b className="num">{percent(summary.last_7_days.hit_rate)}</b></span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">近 30 天</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.last_30_days.profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot"><b className="num">{summary.status === "AVAILABLE" ? summary.last_30_days.match_count : "—"}</b> 条 · 命中 <b className="num">{percent(summary.last_30_days.hit_rate)}</b></span></article>
        </div></div>
        <p className="w2-kpis-note">战绩统计口径：AH/OU v3.1 冻结决策 · 每条 decision_id 单独计数 · 待赛果和无效盘不进命中率分母</p>
        {summary.by_market ? <p className="w2-kpis-note">让球 {summary.by_market.ASIAN_HANDICAP?.match_count ?? 0} 条已结算 · 命中 {percent(summary.by_market.ASIAN_HANDICAP?.hit_rate)} · 净 {signed(summary.by_market.ASIAN_HANDICAP?.profit_units)}；大小球 {summary.by_market.TOTALS?.match_count ?? 0} 条已结算 · 命中 {percent(summary.by_market.TOTALS?.hit_rate)} · 净 {signed(summary.by_market.TOTALS?.profit_units)}</p> : null}
      </section>
      <div className="w2-grid">
        <section className="w2-panel" data-mviews="picks" aria-labelledby="picksTitle">
          <div className="w2-panel__head"><h2 className="section-title" id="picksTitle">今日推荐</h2><div className="w2-chips" role="group" aria-label="按联赛筛选">{leagues.map((league) => <button type="button" className="w2-chip" aria-pressed={league === activeLeague} key={league} onClick={() => setActiveLeague(league)}>{league}</button>)}</div></div>
          {!publicAvailable ? <p className="w2-pending" role="alert">v3 推荐读模型不可用</p> : null}
          <div className="w2-table-wrap"><table className="w2-table"><thead><tr><th>开球</th><th>联赛</th><th>对阵</th><th>冻结推荐</th><th className="col-right">入场赔率</th><th className="col-right">模型分数</th><th>决策身份</th><th>状态</th><th>结果 / 净单位</th></tr></thead><tbody>
            {filteredPicks.length ? filteredPicks.map((pick) => <tr key={pick.decision_id || `${pick.fixture_id}-${pick.market}`} data-decision-id={pick.decision_id} data-market={pick.market || undefined} onClick={() => setSelectedFixtureId(pick.fixture_id)} onKeyDown={(event) => { if (event.key === "Enter") setSelectedFixtureId(pick.fixture_id); }} tabIndex={0}>
              <td className="num">{localTime(pick.kickoff_utc)}</td><td><span className="w2-league">{pick.competition_name_zh || "赛事待确认"}</span></td><td><div className="w2-match"><strong>{pick.home || "主队待确认"} vs {pick.away || "客队待确认"}</strong></div></td>
              <td className="w2-pick">{marketLabel(pick.market)} {sideLabel(pick.selection)} <span className="num">{pick.line ?? "—"}</span></td><td className="col-right num">{pick.odds ?? "—"}</td><td className="col-right num">{pick.score ?? "—"}</td>
              <td className="num" title={pick.decision_id || undefined}>{pick.decision_id ? pick.decision_id.slice(0, 12) : "—"}</td><td><span className={`w2-status w2-status--${pick.status}`}>{statusLabel(pick.status)}</span></td><td>{pick.result ? resultLabel(pick.result) : statusLabel(pick.status)}{pick.net_units !== null && pick.net_units !== undefined ? ` · ${signed(Number(pick.net_units))} 单位` : ""}</td>
            </tr>) : <tr><td colSpan={9} className="w2-pending">{publicAvailable ? "今日没有 AH/OU v3 推荐。" : "v3 推荐数据不可用。"}</td></tr>}
          </tbody></table></div>
          <div className="w2-cards">{filteredPicks.map((pick) => <button type="button" className="w2-card" key={`${pick.decision_id || `${pick.fixture_id}-${pick.market}`}-card`} data-decision-id={pick.decision_id} data-market={pick.market || undefined} onClick={() => setSelectedFixtureId(pick.fixture_id)}><div className="w2-card__top"><span className="num">{localTime(pick.kickoff_utc)}</span><span className="w2-league">{pick.competition_name_zh || "赛事待确认"}</span><span className={`w2-status w2-status--${pick.status}`}>{statusLabel(pick.status)}</span></div><div className="w2-card__teams">{pick.home || "主队待确认"} vs {pick.away || "客队待确认"}</div><div className="w2-card__pick"><span className="w2-pick">{marketLabel(pick.market)} {sideLabel(pick.selection)} {pick.line}</span><span className="w2-card__odds num">@{pick.odds ?? "—"}</span><span className="w2-card__ev">分数 {pick.score ?? "—"}</span></div><div className="w2-card__foot"><span className="w2-pending">{pick.result ? `${resultLabel(pick.result)} · ${signed(Number(pick.net_units))} 单位` : statusLabel(pick.status)}</span><span className="num">{pick.decision_id?.slice(0, 12) || "—"}</span></div></button>)}</div>
        </section>
        <aside className="w2-side">
          <section className="w2-panel" data-mviews="review" aria-labelledby="pnlTitle"><div className="w2-panel__head"><h2 className="section-title" id="pnlTitle">近 30 天累计盈亏</h2></div><div className="w2-chart"><div className="w2-chart__hero"><span className="num">{summary.status === "AVAILABLE" ? signed(summary.last_30_days.profit_units) : "—"}</span><span className="muted">单位 · 截至 {localDate(summary.daily_series[summary.daily_series.length - 1]?.date ? `${summary.daily_series[summary.daily_series.length - 1].date}T12:00:00+08:00` : null, { month: "numeric", day: "numeric" })}</span></div><PnlChart points={summary.daily_series} /></div><details className="w2-chart__table"><summary>查看每日数据</summary><div className="w2-chart__scroll"><table><thead><tr><th>日期</th><th>当日</th><th>累计</th></tr></thead><tbody>{summary.daily_series.slice().reverse().map((point) => <tr key={point.date}><td>{point.date}</td><td className="num">{signed(point.daily_profit_units)}</td><td className="num">{signed(point.cumulative_profit_units)}</td></tr>)}</tbody></table></div></details></section>
          <section className="w2-panel" data-mviews="picks" aria-labelledby="upTitle"><div className="w2-panel__head"><h2 className="section-title" id="upTitle">即将开赛</h2></div><ul className="w2-upcoming">{upcoming.map((match) => { const [home, away] = matchTeams(match); const pick = picks.find((row) => row.fixture_id === match.fixture_id && row.status === "pending"); return <li key={match.fixture_id}><time className="num">{localTime(match.kickoff_utc)}</time><div className="w2-match"><strong>{home} vs {away}</strong><span>{translateCompetition(match.competition_name || match.competition_id || "赛事待确认", match.competition_id)} · {pick ? statusLabel(pick.status) : "无推荐"}</span></div><span className="w2-countdown num">{pick ? statusLabel(pick.status) : "—"}</span></li>; })}{!upcoming.length ? <li><span className="w2-pending">暂无即将开赛比赛</span></li> : null}</ul></section>
        </aside>
      </div>
      <section className="w2-panel" data-mviews="matches review more" aria-label="比赛与战绩">
        <div className="w2-tabs w2-tabs-desktop" role="tablist" aria-label="视图"><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "matches"} onClick={() => onTabChange("matches")}>比赛列表</button><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "validation" || activeTab === "validation-calibrated"} onClick={() => onTabChange("validation")}>战绩复盘</button><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "replay"} onClick={() => onTabChange("replay")}>回放记录</button></div>
        {activeTab === "matches" ? <div className="w2-tabpanel"><FixtureList workspace={workspace} picks={picks} onSelect={setSelectedFixtureId} /></div> : <div className="w2-tabpanel">{activeTab === "validation" || activeTab === "validation-calibrated" ? <div className="w2-review-head"><div className="w2-seg" role="group" aria-label="复盘口径"><button type="button" aria-pressed={activeTab === "validation"} onClick={() => onTabChange("validation")}>原始</button><button type="button" aria-pressed={activeTab === "validation-calibrated"} onClick={() => onTabChange("validation-calibrated")}>校准</button></div></div> : null}{tabContent}</div>}
      </section>
      <details className="w2-system" data-mviews="more" onToggle={(event) => loadWebVersion(event.currentTarget.open)}><summary>系统详情 <span>运行状态、版本、采集与规则</span></summary><div className="w2-system__grid"><div className="w2-system__block"><h3>运行状态</h3><dl className="w2-kv"><dt>数据</dt><dd>{workspace.system_status?.data || "—"}</dd><dt>推荐</dt><dd>{workspace.system_status?.recommendations || "—"}</dd><dt>正式推荐</dt><dd>{workspace.runtime.formal === "OFF" ? "关闭" : workspace.runtime.formal}</dd><dt>联赛白名单</dt><dd className="num">{workspace.runtime.active_whitelist_count}</dd></dl></div><div className="w2-system__block"><h3>版本与采集</h3><dl className="w2-kv"><dt>版本</dt><dd className="num">{webVersion ? webVersion.slice(0, 8) : "—"}</dd><dt>数据库</dt><dd className="num">—</dd><dt>今日采集</dt><dd>—</dd><dt>读取</dt><dd>只读 · 不调用 Provider</dd></dl></div><div className="w2-system__block"><h3>推荐规则</h3><dl className="w2-kv"><dt>推荐权威</dt><dd>AH/OU v3.1 冻结决策账本</dd><dt>模型分数</dt><dd>赛前冻结，不是 EV 档位</dd><dt>结算</dt><dd>按冻结盘口与入场赔率</dd><dt>数据读取</dt><dd>只读所选足球日</dd></dl></div></div>{capabilityStatus}<div className="w2-historical-quality"><p>旧代际模型质量历史证据；不参与当前 AH/OU v3 战绩。</p>{historicalQuality}</div><SystemHealthPanel /></details>
    </main>
    {selectedFixtureId ? <><div className="w2-scrim" onClick={() => setSelectedFixtureId(null)} /><aside className="w2-drawer" role="dialog" aria-modal="true" aria-labelledby="drawerTitle"><div className="w2-drawer__head"><span className="w2-league">{translateCompetition(selectedDetail?.competition_name || workspace.matches.find((match) => match.fixture_id === selectedFixtureId)?.competition_name || selectedDetail?.competition_id || "赛事待确认", selectedDetail?.competition_id || workspace.matches.find((match) => match.fixture_id === selectedFixtureId)?.competition_id)}</span><span className="faint num">{localTime(selectedDetail?.kickoff_utc)}</span><button type="button" className="w2-link" onClick={() => setSelectedFixtureId(null)}>关闭</button></div><div className="w2-drawer__body">{selectedFailure ? <section className="w2-projection-error" role="alert"><h3>单场投影已隔离</h3><p>{selectedFailure.projection_error.message}</p><small>{selectedFailure.projection_error.code}</small></section> : detailState === "loading" ? <p>正在读取比赛详情…</p> : detailState === "error" ? <p>比赛详情暂不可用，请稍后重试。</p> : selectedDetail ? <><div className="w2-drawer__intro"><div><div className="w2-drawer__teams" id="drawerTitle">{teamName(selectedDetail.home_team_label)} vs {teamName(selectedDetail.away_team_label)}</div><span className="faint">{localDate(selectedDetail.kickoff_utc, { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span></div></div><div className="w2-drawer__pick"><div className="w2-stat"><span>让球</span><strong>{formatAhMarketHandicap(selectedDetail.market_radar.markets.ASIAN_HANDICAP.main_line) || "—"}</strong></div><div className="w2-stat"><span>大小</span><strong>{selectedDetail.market_radar.markets.TOTALS.main_line || "—"}</strong></div><div className="w2-stat"><span>最终状态</span><strong>{finalStatusLabel(selectedDetail.evaluation_execution.status)}</strong></div></div><section><h3 className="section-title">本场 AH/OU v3 冻结推荐</h3>{selectedDetail.ah_ou_v3_recommendations ? selectedDetail.ah_ou_v3_recommendations.length ? <ul className="w2-v3-detail-recommendations">{selectedDetail.ah_ou_v3_recommendations.map((pick) => <li key={pick.decision_id} data-decision-id={pick.decision_id} data-market={pick.market || undefined}><strong>{marketLabel(pick.market)} {sideLabel(pick.selection)} {pick.line} @{pick.odds}</strong><span>模型分数 {pick.score} · {statusLabel(pick.status)}{pick.result ? ` · ${resultLabel(pick.result)} ${signed(Number(pick.net_units))} 单位` : ""}</span><code>{pick.decision_id}</code></li>)}</ul> : <p>本场没有 AH/OU v3 选中决策。</p> : <p role="alert">本场 v3 推荐读模型不可用。</p>}</section><section><h3 className="section-title">分析摘要</h3><p>{selectedDetail.factual_summary || "暂无摘要"}</p></section>{renderInputDiagnostics ? <details className="w2-input-diagnostics"><summary>赛前输入与风险诊断（不构成当前推荐）</summary>{renderInputDiagnostics(selectedDetail)}</details> : null}</> : null}</div></aside></> : null}
    <nav className="w2-bottomnav" aria-label="主导航"><div className="w2-bottomnav__inner"><button type="button" aria-current={mobileView === "picks" ? "page" : undefined} onClick={() => selectMobile("picks")}>☰<span>推荐</span></button><button type="button" aria-current={mobileView === "matches" ? "page" : undefined} onClick={() => selectMobile("matches")}>◉<span>比赛</span></button><button type="button" aria-current={mobileView === "review" ? "page" : undefined} onClick={() => selectMobile("review")}>↗<span>复盘</span></button><button type="button" aria-current={mobileView === "more" ? "page" : undefined} onClick={() => selectMobile("more")}>•••<span>更多</span></button></div></nav>
  </div>;
}

export default DesignV1Overview;
