import { useEffect, useMemo, useState } from "react";
import { fetchDashboardView, getCachedDashboardView } from "../lib/dashboardApi";
import { todayShanghai } from "../lib/formatters";
import { matchPhase, minutesToKickoff } from "../lib/matchPhase";
import { hasValidatedAhCalibration } from "../lib/pricingDisplay";
import type { DashboardMode, DashboardView, LoadState } from "../types/dashboard";
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
    return { title: "暂无完场复盘", detail: "比赛完场并同步结果后会显示验证状态。" };
  }
  return { title: "暂无可展示比赛", detail: "数据不足时保持空白，不强出推荐。" };
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

export function DashboardPage() {
  const [view, setView] = useState<DashboardView | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [mode, setMode] = useState<DashboardMode>("today");
  const [date, setDate] = useState(todayShanghai());
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
    if (mode === "next36") return sortByKickoffUrgency(view.upcoming);
    if (mode === "results") return view.finished;
    return sortByKickoffUrgency(view.all);
  }, [mode, view]);

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
            今日 <strong>{visibleMatches.length}</strong> 场
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

      {state === "empty" && view ? <DataDiagnosticsPanel debug={view.debug} release={view.release} /> : null}

      {state === "ok" && view ? (
        <>
          {visibleMatches.length ? (
            <section className="match-card-grid" aria-label="比赛卡片">
              {visibleMatches.map((match) => (
                <RecommendationCard key={match.fixture_id} match={match} />
              ))}
            </section>
          ) : (
            <EmptySection title={empty.title} detail={empty.detail} />
          )}
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
