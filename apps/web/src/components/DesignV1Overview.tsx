import { useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchIntelligenceMatch } from "../lib/intelligenceWorkspaceApi";
import type { IntelligenceWorkspaceList, PerformanceSummary, TodayRecommendation, WorkspaceMatch, WorkspaceMatchItem } from "../types/intelligenceWorkspace";

type Tab = "matches" | "validation" | "validation-calibrated" | "replay";
type Props = {
  workspace: IntelligenceWorkspaceList;
  date: string;
  onDateChange: (date: string) => void;
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  tabContent?: ReactNode;
};

const EMPTY_PERFORMANCE: PerformanceSummary = {
  calibration_identity: null,
  status: "UNAVAILABLE",
  total_profit_units: 0,
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
function dayLabel(value: string): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", weekday: "short" }).format(date);
}
function upcomingDayLabel(value: string, isToday: boolean): string {
  const date = new Date(`${value}T12:00:00+08:00`);
  const label = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric" }).format(date);
  return isToday ? `${label}·今天` : label;
}
function tierFor(ev: number | null | undefined): "重点" | "一般" | "观察" | "不推" | "待融合" {
  if (ev === null || ev === undefined || !Number.isFinite(ev)) return "待融合";
  if (ev >= 0.05) return "重点";
  if (ev >= 0.02) return "一般";
  if (ev >= 0) return "观察";
  return "不推";
}
function statusLabel(value: string): string {
  return ({ settled: "已结算", confirmed: "已确认", candidate: "候选", withdrawn: "已撤回" } as Record<string, string>)[value] || value || "—";
}
function settlementKind(value: string | null | undefined): "win" | "lose" | "push" {
  if (value === "WIN" || value === "HALF_WIN") return "win";
  if (value === "LOSS" || value === "HALF_LOSS") return "lose";
  return "push";
}
function resultLabel(value: string | null | undefined): string {
  return ({ WIN: "赢", HALF_WIN: "赢一半", PUSH: "走盘", HALF_LOSS: "输一半", LOSS: "输" } as Record<string, string>)[value || ""] || value || "—";
}
function teamName(value: unknown): string {
  if (value && typeof value === "object" && "display_name" in value && typeof value.display_name === "string") return value.display_name;
  return typeof value === "string" && value ? value : "球队待确认";
}
function matchTeams(match: WorkspaceMatchItem): [string, string] {
  const item = match as unknown as Record<string, unknown>;
  return [teamName(item.home_team_label || item.home_team_name), teamName(item.away_team_label || item.away_team_name)];
}
function performance(workspace: IntelligenceWorkspaceList): PerformanceSummary {
  return workspace.performance_summary || EMPTY_PERFORMANCE;
}
function recommendations(workspace: IntelligenceWorkspaceList): TodayRecommendation[] {
  return workspace.today_recommendations || [];
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

function FixtureList({ workspace, onSelect }: { workspace: IntelligenceWorkspaceList; onSelect: (fixtureId: string) => void }) {
  const matches = workspace.matches.slice().sort((left, right) => String(left.kickoff_utc || "").localeCompare(String(right.kickoff_utc || "")));
  return <ul className="w2-fixtures">{matches.length ? matches.map((match) => {
    const [home, away] = matchTeams(match);
    const item = match as unknown as Record<string, unknown>;
    const markets = item.market_radar && typeof item.market_radar === "object" && "markets" in item.market_radar ? item.market_radar.markets as Record<string, Record<string, unknown>> : {};
    const ah = markets.ASIAN_HANDICAP || {};
    const totals = markets.TOTALS || {};
    const pick = item.pick && typeof item.pick === "object" ? item.pick as Record<string, unknown> : null;
    const hasPick = Boolean(pick?.market);
    return <li className="w2-fixture" data-fixture-id={match.fixture_id} key={match.fixture_id} onClick={() => onSelect(match.fixture_id)} onKeyDown={(event) => { if (event.key === "Enter") onSelect(match.fixture_id); }} role="button" tabIndex={0}>
      <span className="num">{localTime(match.kickoff_utc)}</span>
      <span className="w2-fixture__league"><span className="w2-league">{String(match.competition_name || match.competition_id || "赛事待确认")}</span></span>
      <div className="w2-fixture__teams"><span>{home}</span><span className="faint">vs</span><span>{away}</span></div>
      <div className="w2-market"><span>让球 <span className="num">{String(ah.main_line || "—")}</span></span><span className="num">{ah.status === "READY" ? "市场已就绪" : "数据待补"}</span></div>
      <div className="w2-market"><span>大小 <span className="num">{String(totals.main_line || "—")}</span></span><span className="num">{totals.status === "READY" ? "市场已就绪" : "数据待补"}</span></div>
      <span className={`w2-tag${hasPick ? " w2-tag--pick" : ""}`}>{hasPick ? "有推荐" : "—"}</span>
    </li>;
  }) : <li className="w2-empty-row">当前足球日没有持久化比赛。</li>}</ul>;
}

export function DesignV1Overview({ workspace, date, onDateChange, activeTab, onTabChange, tabContent }: Props) {
  const summary = performance(workspace);
  const picks = recommendations(workspace);
  const [activeLeague, setActiveLeague] = useState("全部");
  const [webVersion, setWebVersion] = useState<string | null>(null);
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<WorkspaceMatch | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "error">("idle");
  useEffect(() => {
    if (!selectedFixtureId) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setSelectedFixtureId(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedFixtureId]);
  useEffect(() => {
    if (!selectedFixtureId) return;
    const controller = new AbortController();
    setDetailState("loading");
    setSelectedDetail(null);
    fetchIntelligenceMatch(selectedFixtureId, controller.signal).then((detail) => { setSelectedDetail(detail); setDetailState("idle"); }).catch((error: unknown) => { if (error instanceof DOMException && error.name === "AbortError") return; setDetailState("error"); });
    return () => controller.abort();
  }, [selectedFixtureId]);
  const [theme, setTheme] = useState<"light" | "dark">(() => document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");
  const [mobileView, setMobileView] = useState<"picks" | "matches" | "review" | "more">("picks");
  useEffect(() => {
    const saved = localStorage.getItem("w2-theme");
    if (saved === "light" || saved === "dark") setTheme(saved);
  }, []);
  const filteredPicks = useMemo(() => activeLeague === "全部" ? picks : picks.filter((pick) => pick.competition_name_zh === activeLeague), [activeLeague, picks]);
  const leagues = ["全部", ...Array.from(new Set(picks.map((pick) => pick.competition_name_zh).filter((value): value is string => Boolean(value))))];
  const nextPick = picks.filter((pick) => (pick.status === "confirmed" || pick.status === "candidate") && pick.kickoff_utc && new Date(pick.kickoff_utc).valueOf() > Date.now()).sort((left, right) => String(left.kickoff_utc).localeCompare(String(right.kickoff_utc)))[0];
  const upcoming = workspace.matches.filter((match) => match.kickoff_utc && new Date(match.kickoff_utc).valueOf() > Date.now()).sort((left, right) => String(left.kickoff_utc).localeCompare(String(right.kickoff_utc))).slice(0, 5);
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
      <section data-mviews="picks" aria-label="核心指标">
        <div className="w2-kpis-wrap"><div className="w2-kpis">
          <article className="w2-kpi"><span className="w2-kpi__label">今日推荐</span><span className="w2-kpi__value num">{picks.length}<small>条</small></span><span className="w2-kpi__foot">已结算 <b className="num">{settled.length}</b> · 待开赛 <b className="num">{picks.filter((pick) => pick.status === "confirmed" || pick.status === "candidate").length}</b> · 撤回 <b className="num">{picks.filter((pick) => pick.status === "withdrawn").length}</b></span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">今日结算</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(todayProfit) : "—"}<small>单位</small></span><span className="w2-kpi__foot">{settled.filter((pick) => pick.result === "WIN" || pick.result === "HALF_WIN").length} 赢 · {settled.filter((pick) => pick.result === "LOSS" || pick.result === "HALF_LOSS").length} 输</span></article>
          <article className="w2-kpi w2-kpi--next"><span className="w2-kpi__label">下一场推荐</span><span className="w2-kpi__value num">{nextPick ? localTime(nextPick.kickoff_utc) : "—"}<small>{nextPick ? "开赛" : "暂无"}</small></span><span className="w2-kpi__foot">{nextPick ? `${nextPick.competition_name_zh || "赛事待确认"} · ${nextPick.home || "主队待确认"} vs ${nextPick.away || "客队待确认"}` : "暂无待开赛推荐"}</span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">总盈亏</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.total_profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot">当前模型版本 · 全历史</span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">近 7 天</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.last_7_days.profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot"><b className="num">{summary.status === "AVAILABLE" ? summary.last_7_days.match_count : "—"}</b> 场 · 命中 <b className="num">{percent(summary.last_7_days.hit_rate)}</b></span></article>
          <article className="w2-kpi"><span className="w2-kpi__label">近 30 天</span><span className="w2-kpi__value num">{summary.status === "AVAILABLE" ? signed(summary.last_30_days.profit_units) : "—"}<small>单位</small></span><span className="w2-kpi__foot"><b className="num">{summary.status === "AVAILABLE" ? summary.last_30_days.match_count : "—"}</b> 场 · 命中 <b className="num">{percent(summary.last_30_days.hit_rate)}</b></span></article>
        </div></div>
        <p className="w2-kpis-note">战绩统计口径：当前模型版本{summary.calibration_identity ? ` · ${summary.calibration_identity}` : ""}</p>
      </section>
      <div className="w2-grid">
        <section className="w2-panel" data-mviews="picks" aria-labelledby="picksTitle">
          <div className="w2-panel__head"><h2 className="section-title" id="picksTitle">今日推荐</h2><div className="w2-chips" role="group" aria-label="按联赛筛选">{leagues.map((league) => <button type="button" className="w2-chip" aria-pressed={league === activeLeague} key={league} onClick={() => setActiveLeague(league)}>{league}</button>)}</div></div>
          <div className="w2-table-wrap"><table className="w2-table"><thead><tr><th>开球</th><th>联赛</th><th>对阵</th><th>推荐</th><th className="col-right">赔率</th><th className="col-right col-ev">EV</th><th>档位</th><th>公平线 / 价差</th><th>状态</th><th>结果</th></tr></thead><tbody>{filteredPicks.length ? filteredPicks.map((pick) => { const ev = pick.fusion_ev ?? pick.ev; const tier = pick.tier || tierFor(pick.fusion_ev); return <tr key={`${pick.fixture_id}-${pick.market}`} className={pick.status === "withdrawn" ? "is-withdrawn" : ""} onClick={() => setSelectedFixtureId(pick.fixture_id)} onKeyDown={(event) => { if (event.key === "Enter") setSelectedFixtureId(pick.fixture_id); }} tabIndex={0}><td className="num">{localTime(pick.kickoff_utc)}</td><td><span className="w2-league">{pick.competition_name_zh || "赛事待确认"}</span></td><td><div className="w2-match"><strong>{pick.home || "主队待确认"} vs {pick.away || "客队待确认"}</strong></div></td><td className="w2-pick">{pick.market || "—"} <span className="num">{pick.line ?? "—"}</span> · {pick.selection || "—"}</td><td className="col-right num">{pick.odds === null || pick.odds === undefined ? "—" : Number(pick.odds).toFixed(2)}</td><td className="col-right col-ev num">{ev === null || ev === undefined ? "—" : `${(ev * 100).toFixed(1)}%`}</td><td><span className={`w2-tier w2-tier--${tier}`}>{tier}</span></td><td className="num">{pick.pinnacle_fair_line ?? "—"} / {pick.channel_price_gap === null || pick.channel_price_gap === undefined ? "—" : `${(pick.channel_price_gap * 100).toFixed(1)}%`}</td><td><span className={`w2-status w2-status--${pick.status}`}>{statusLabel(pick.status)}</span>{pick.withdraw_reason ? <span className="w2-pending">{pick.withdraw_reason}</span> : null}</td><td>{pick.result ? <Result value={pick.result} /> : pick.status === "withdrawn" ? <span className="w2-pending">{pick.withdraw_reason || "已撤回"}</span> : <span className="w2-pending">待结算</span>}</td></tr>; }) : <tr><td colSpan={10} className="w2-pending">今日没有当前模型版本推荐。</td></tr>}</tbody></table></div>
          <div className="w2-cards">{filteredPicks.map((pick) => <button type="button" className="w2-card" key={`${pick.fixture_id}-${pick.market}-card`} onClick={() => setSelectedFixtureId(pick.fixture_id)}><div className="w2-card__top"><span className="num">{localTime(pick.kickoff_utc)}</span><span className="w2-league">{pick.competition_name_zh || "赛事待确认"}</span><span className={`w2-status w2-status--${pick.status}`}>{statusLabel(pick.status)}</span></div><div className="w2-card__teams">{pick.home || "主队待确认"} vs {pick.away || "客队待确认"}</div><div className="w2-card__pick"><span className="w2-pick">{pick.market} {pick.line} · {pick.selection}</span><span className="w2-card__odds num">@{pick.odds == null ? "—" : Number(pick.odds).toFixed(2)}</span><span className="w2-card__ev">EV <span className="num">{pick.ev == null ? "—" : percent(pick.ev)}</span></span></div><div className="w2-card__foot"><span className="w2-pending">{pick.result ? resultLabel(pick.result) : pick.withdraw_reason || "待结算"}</span></div></button>)}</div>
        </section>
        <aside className="w2-side">
          <section className="w2-panel" data-mviews="review" aria-labelledby="pnlTitle"><div className="w2-panel__head"><h2 className="section-title" id="pnlTitle">近 30 天累计盈亏</h2></div><div className="w2-chart"><div className="w2-chart__hero"><span className="num">{summary.status === "AVAILABLE" ? signed(summary.last_30_days.profit_units) : "—"}</span><span className="muted">单位 · 截至 {localDate(summary.daily_series[summary.daily_series.length - 1]?.date ? `${summary.daily_series[summary.daily_series.length - 1].date}T12:00:00+08:00` : null, { month: "numeric", day: "numeric" })}</span></div><PnlChart points={summary.daily_series} /></div><details className="w2-chart__table"><summary>查看每日数据</summary><div className="w2-chart__scroll"><table><thead><tr><th>日期</th><th>当日</th><th>累计</th></tr></thead><tbody>{summary.daily_series.slice().reverse().map((point) => <tr key={point.date}><td>{point.date}</td><td className="num">{signed(point.daily_profit_units)}</td><td className="num">{signed(point.cumulative_profit_units)}</td></tr>)}</tbody></table></div></details></section>
          <section className="w2-panel" data-mviews="picks" aria-labelledby="upTitle"><div className="w2-panel__head"><h2 className="section-title" id="upTitle">即将开赛</h2></div><ul className="w2-upcoming">{upcoming.map((match) => { const [home, away] = matchTeams(match); const pick = picks.find((row) => row.fixture_id === match.fixture_id && (row.status === "confirmed" || row.status === "candidate")); return <li key={match.fixture_id}><time className="num">{localTime(match.kickoff_utc)}</time><div className="w2-match"><strong>{home} vs {away}</strong><span>{match.competition_name || "赛事待确认"} · {pick ? statusLabel(pick.status) : "无推荐"}</span></div><span className="w2-countdown num">{pick ? statusLabel(pick.status) : "—"}</span></li>; })}{!upcoming.length ? <li><span className="w2-pending">暂无即将开赛比赛</span></li> : null}</ul></section>
        </aside>
      </div>
      <section className="w2-panel" data-mviews="matches review more" aria-label="比赛与战绩">
        <div className="w2-tabs w2-tabs-desktop" role="tablist" aria-label="视图"><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "matches"} onClick={() => onTabChange("matches")}>比赛列表</button><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "validation" || activeTab === "validation-calibrated"} onClick={() => onTabChange("validation")}>战绩复盘</button><button type="button" className="w2-tab" role="tab" aria-selected={activeTab === "replay"} onClick={() => onTabChange("replay")}>回放记录</button></div>
        {activeTab === "matches" ? <div className="w2-tabpanel"><FixtureList workspace={workspace} onSelect={setSelectedFixtureId} /></div> : <div className="w2-tabpanel">{activeTab === "validation" || activeTab === "validation-calibrated" ? <div className="w2-review-head"><div className="w2-seg" role="group" aria-label="复盘口径"><button type="button" aria-pressed={activeTab === "validation"} onClick={() => onTabChange("validation")}>原始</button><button type="button" aria-pressed={activeTab === "validation-calibrated"} onClick={() => onTabChange("validation-calibrated")}>校准</button></div></div> : null}{tabContent}</div>}
      </section>
      <details className="w2-system" data-mviews="more" onToggle={(event) => loadWebVersion(event.currentTarget.open)}><summary>系统详情 <span>运行状态、版本、采集与规则</span></summary><div className="w2-system__grid"><div className="w2-system__block"><h3>运行状态</h3><dl className="w2-kv"><dt>数据</dt><dd>{workspace.system_status?.data || "—"}</dd><dt>推荐</dt><dd>{workspace.system_status?.recommendations || "—"}</dd><dt>正式推荐</dt><dd>{workspace.runtime.formal === "OFF" ? "关闭" : workspace.runtime.formal}</dd><dt>联赛白名单</dt><dd className="num">{workspace.runtime.active_whitelist_count}</dd></dl></div><div className="w2-system__block"><h3>版本与采集</h3><dl className="w2-kv"><dt>版本</dt><dd className="num">{webVersion ? webVersion.slice(0, 8) : "—"}</dd><dt>数据库</dt><dd className="num">—</dd><dt>今日采集</dt><dd>—</dd><dt>读取</dt><dd>只读 · 不调用 Provider</dd></dl></div><div className="w2-system__block"><h3>推荐规则</h3><dl className="w2-kv"><dt>期望值</dt><dd>由服务端投影</dd><dt>价格边际</dt><dd>按当前模型版本</dd><dt>因子准入</dt><dd>服务端状态为准</dd><dt>数据读取</dt><dd>只读所选足球日</dd></dl></div></div></details>
    </main>
    {selectedFixtureId ? <><div className="w2-scrim" onClick={() => setSelectedFixtureId(null)} /><aside className="w2-drawer" role="dialog" aria-modal="true" aria-labelledby="drawerTitle"><div className="w2-drawer__head"><span className="w2-league">{selectedDetail?.competition_name || workspace.matches.find((match) => match.fixture_id === selectedFixtureId)?.competition_name || "赛事待确认"}</span><span className="faint num">{localTime(selectedDetail?.kickoff_utc)}</span><button type="button" className="w2-link" onClick={() => setSelectedFixtureId(null)}>关闭</button></div><div className="w2-drawer__body">{detailState === "loading" ? <p>正在读取比赛详情…</p> : detailState === "error" ? <p>比赛详情暂不可用，请稍后重试。</p> : selectedDetail ? <><div className="w2-drawer__intro"><div><div className="w2-drawer__teams" id="drawerTitle">{teamName(selectedDetail.home_team_label)} vs {teamName(selectedDetail.away_team_label)}</div><span className="faint">{localDate(selectedDetail.kickoff_utc, { year: "numeric", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span></div></div><div className="w2-drawer__pick"><div className="w2-stat"><span>让球</span><strong>{selectedDetail.market_radar.markets.ASIAN_HANDICAP.main_line || "—"}</strong></div><div className="w2-stat"><span>大小</span><strong>{selectedDetail.market_radar.markets.TOTALS.main_line || "—"}</strong></div><div className="w2-stat"><span>最终状态</span><strong>{selectedDetail.evaluation_execution.status}</strong></div></div><section><h3 className="section-title">分析摘要</h3><p>{selectedDetail.factual_summary || "暂无摘要"}</p></section></> : null}</div></aside></> : null}
    <nav className="w2-bottomnav" aria-label="主导航"><div className="w2-bottomnav__inner"><button type="button" aria-current={mobileView === "picks" ? "page" : undefined} onClick={() => selectMobile("picks")}>☰<span>推荐</span></button><button type="button" aria-current={mobileView === "matches" ? "page" : undefined} onClick={() => selectMobile("matches")}>◉<span>比赛</span></button><button type="button" aria-current={mobileView === "review" ? "page" : undefined} onClick={() => selectMobile("review")}>↗<span>复盘</span></button><button type="button" aria-current={mobileView === "more" ? "page" : undefined} onClick={() => selectMobile("more")}>•••<span>更多</span></button></div></nav>
  </div>;
}

export default DesignV1Overview;
