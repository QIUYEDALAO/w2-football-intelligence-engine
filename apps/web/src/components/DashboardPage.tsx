import { useEffect, useMemo, useState } from "react";
import { fetchDashboardView, getCachedDashboardView } from "../lib/dashboardApi";
import { footballDayShanghai } from "../lib/formatters";
import { matchPhase, minutesToKickoff } from "../lib/matchPhase";
import { hasValidatedAhCalibration } from "../lib/pricingDisplay";
import type { DashboardMatchCard, DashboardMode, DashboardView, LoadState } from "../types/dashboard";
import { DataDiagnosticsPanel } from "./DataDiagnosticsPanel";
import { EmptySection } from "./EmptySection";
import { PerformanceHeader } from "./PerformanceHeader";
import { RecommendationCard } from "./RecommendationCard";
import { ReleaseSyncBadge } from "./ReleaseSyncBadge";
import { SegmentTabs } from "./SegmentTabs";
import { SkeletonCard } from "./SkeletonCard";

function updatedAtShanghai(): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
}

function emptyCopy(mode: DashboardMode): { title: string; detail: string } {
  if (mode === "next36") {
    return { title: "未来 36 小时暂无比赛", detail: "白名单赛程进入 read-model 后会自动显示。" };
  }
  if (mode === "results") {
    return { title: "本足球日暂无完场比赛", detail: "北京时间中午 12:00 到次日 11:59 的比赛完场并同步赛果后，会显示复盘。" };
  }
  if (mode === "today") return { title: "本足球日暂无可展示比赛", detail: "数据不足时保持空白，不强出推荐。" };
  if (mode === "all") return { title: "本足球日暂无比赛", detail: "当前足球日没有可展示比赛；未来赛程进入窗口后会自动出现。" };
  return { title: "暂无可展示比赛", detail: "数据不足时保持空白，不强出推荐。" };
}

function shouldShowDiagnostics(): boolean {
  if (import.meta.env.DEV) return true;
  const params = new URLSearchParams(window.location.search);
  return params.get("debug") === "1" || params.get("diagnostics") === "1";
}

function sortByKickoffUrgency<T extends { kickoff_utc: string }>(matches: T[]): T[] {
  return [...matches].sort((left, right) => {
    const leftMinutes = minutesToKickoff(left.kickoff_utc);
    const rightMinutes = minutesToKickoff(right.kickoff_utc);
    const leftScore = leftMinutes === null ? Number.POSITIVE_INFINITY : Math.max(leftMinutes, -1);
    const rightScore = rightMinutes === null ? Number.POSITIVE_INFINITY : Math.max(rightMinutes, -1);
    return leftScore - rightScore;
  });
}

function isFormalMatch(match: DashboardMatchCard): boolean {
  return match.formal_recommendation === true && match.recommendation?.tier === "FORMAL";
}

function sortFormalFirst(matches: DashboardMatchCard[]): DashboardMatchCard[] {
  return sortByKickoffUrgency(matches).sort((left, right) => Number(isFormalMatch(right)) - Number(isFormalMatch(left)));
}

export function DashboardPage() {
  const [view, setView] = useState<DashboardView | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [mode, setMode] = useState<DashboardMode>("next36");
  const [date, setDate] = useState(footballDayShanghai());
  const [updatedAt, setUpdatedAt] = useState("--");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const cached = getCachedDashboardView(date, mode);
      if (cached) {
        setView(cached);
        setUpdatedAt(updatedAtShanghai());
        setState(cached.all.length ? "ok" : "empty");
      } else {
        setState("loading");
      }
      try {
        const nextView = await fetchDashboardView({ date, mode });
        if (cancelled) return;
        const fallbackDate = nextView.next_available_date ?? nextView.debug.next_available_date;
        if (nextView.selected_date_has_data === false && fallbackDate && fallbackDate !== date) {
          setView(nextView);
          setDate(fallbackDate);
          setUpdatedAt(updatedAtShanghai());
          setState("loading");
          return;
        }
        if (nextView.selected_football_day && nextView.selected_football_day !== date) {
          setDate(nextView.selected_football_day);
        }
        setView(nextView);
        setUpdatedAt(updatedAtShanghai());
        setState(nextView.all.length ? "ok" : "empty");
      } catch {
        if (!cancelled && !cached) setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [date, mode, refreshKey]);

  const visibleMatches = useMemo(() => {
    if (!view) return [];
    if (mode === "next36") return sortFormalFirst(view.upcoming);
    if (mode === "results") return view.finished;
    return sortFormalFirst(view.all);
  }, [mode, view]);

  const primaryMatches = useMemo(() => {
    const formal = visibleMatches.filter(isFormalMatch);
    if (!formal.length) return visibleMatches;
    return formal;
  }, [visibleMatches]);

  const referenceMatches = useMemo(() => {
    if (!primaryMatches.length || primaryMatches.length === visibleMatches.length) return [];
    return visibleMatches.filter((match) => !isFormalMatch(match));
  }, [primaryMatches.length, visibleMatches]);

  const summary = useMemo(() => {
    const counts = { pick: 0, low: 0, live: 0, formal: 0 };
    for (const match of visibleMatches) {
      const phase = matchPhase(match.kickoff_utc ?? "", (match as { status?: string }).status);
      if (phase === "LIVE" || phase === "FINISHED") {
        counts.live += 1;
        continue;
      }
      if (match.formal_recommendation === true && match.recommendation?.tier === "FORMAL") {
        counts.formal += 1;
      }
      const tier = match.recommendation?.tier;
      if (tier === "FORMAL" || tier === "CANDIDATE" || (tier === "ANALYSIS_PICK" && hasValidatedAhCalibration(match.pricing_shadow))) {
        counts.pick += 1;
      } else {
        counts.low += 1;
      }
    }
    return counts;
  }, [visibleMatches]);

  const empty = emptyCopy(mode);
  const showDiagnostics = shouldShowDiagnostics();

  return (
    <main className="app-shell dashboard-v2">
      {view ? <ReleaseSyncBadge release={view.release} /> : null}
      {view ? <PerformanceHeader performance={view.performance} formalTracking={view.formal_tracking} updatedAt={updatedAt} /> : null}
      <div className="dashboard-controls">
        <SegmentTabs mode={mode} onModeChange={setMode} />
        <div className="date-refresh">
          <label>
            日期
            <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
          <button className="toolbar-button refresh-button" onClick={() => setRefreshKey((value) => value + 1)} type="button">
            刷新
          </button>
        </div>
      </div>

      {state === "ok" && view ? (
        <div
          className="dashboard-summary"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            flexWrap: "wrap",
            background: "#f6f5f0",
            borderRadius: 12,
            padding: "10px 16px",
            margin: "0 0 14px",
            fontSize: 13,
          }}
        >
          <span>
            当前 <strong>{visibleMatches.length}</strong> 场
          </span>
          {summary.formal > 0 ? (
            <span style={{ color: "#0F6E56" }}>● 正式推荐 {summary.formal}</span>
          ) : (
            <span style={{ color: "#9B6B16" }}>○ 当前暂无正式推荐</span>
          )}
          <span style={{ color: "#0F6E56" }}>● 可参考 {summary.pick}</span>
          <span style={{ color: "#9a978d" }}>○ 数据不足 {summary.low}</span>
          <span style={{ color: "#9a978d" }}>· 已开赛 {summary.live}</span>
        </div>
      ) : null}

      {state === "loading" ? (
        <section className="match-card-grid" aria-label="比赛加载中">
          <SkeletonCard />
          <SkeletonCard />
        </section>
      ) : null}

      {state === "error" ? <EmptySection title="加载失败" detail="请确认公网 /v1 API 可访问；不会用假数据顶替真实数据。" /> : null}

      {state === "empty" && view ? (
        showDiagnostics ? (
          <DataDiagnosticsPanel debug={view.debug} release={view.release} />
        ) : (
          <EmptySection title={empty.title} detail={empty.detail} />
        )
      ) : null}

      {state === "ok" && view ? (
        <>
          {primaryMatches.length ? (
            <section className="match-card-grid" aria-label="比赛卡片">
              {primaryMatches.map((match) => (
                <RecommendationCard key={match.fixture_id} match={match} />
              ))}
            </section>
          ) : (
            <EmptySection title={empty.title} detail={empty.detail} />
          )}
          {referenceMatches.length ? (
            <details className="reference-match-details">
              <summary>其他比赛分析参考（{referenceMatches.length}）</summary>
              <section className="match-card-grid" aria-label="其他比赛分析参考">
                {referenceMatches.map((match) => (
                  <RecommendationCard key={match.fixture_id} match={match} />
                ))}
              </section>
            </details>
          ) : null}
          {view.errors.length ? (
            <aside className="soft-errors">
              <strong>部分数据源暂不可用</strong>
              <p>{view.errors.slice(0, 3).join("；")}</p>
            </aside>
          ) : null}
        </>
      ) : null}

      <footer className="dashboard-disclaimer">赛前推荐仅由真实输入和策略规则生成；数据不足时保持观察，赛后统计仅在完场后展示。</footer>
    </main>
  );
}
