import { useEffect, useMemo, useState } from "react";
import { fetchDashboardView } from "../lib/dashboardApi";
import { todayShanghai } from "../lib/formatters";
import type { DashboardMode, DashboardView, LoadState } from "../types/dashboard";
import { DataDiagnosticsPanel } from "./DataDiagnosticsPanel";
import { EmptySection } from "./EmptySection";
import { PerformanceHeader } from "./PerformanceHeader";
import { RecommendationBoard } from "./RecommendationBoard";
import { ReleaseSyncBadge } from "./ReleaseSyncBadge";
import { ResultsValidationPanel } from "./ResultsValidationPanel";
import { SegmentTabs } from "./SegmentTabs";
import { SkeletonCard } from "./SkeletonCard";
import { UpcomingFixturesPanel } from "./UpcomingFixturesPanel";

function updatedAtShanghai(): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
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
      try {
        setState("loading");
        const nextView = await fetchDashboardView({ date, mode });
        if (cancelled) return;
        setView(nextView);
        setUpdatedAt(updatedAtShanghai());
        setState(nextView.all.length ? "ok" : "empty");
      } catch {
        if (!cancelled) setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [date, mode, refreshKey]);

  const visibleAll = useMemo(() => {
    if (!view) return [];
    if (mode === "today") return view.all;
    if (mode === "next36") return view.upcoming;
    if (mode === "results") return view.finished;
    return view.all;
  }, [mode, view]);

  return (
    <main className="app-shell dashboard-v2">
      {view ? <ReleaseSyncBadge release={view.release} /> : null}
      {view ? <PerformanceHeader performance={view.performance} /> : null}
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
      <p className="update-line">最后更新 {updatedAt} · candidate/formal 只用于 +EV 证明；本页默认展示候选参考与观察。</p>

      {state === "loading" ? (
        <section className="cards-grid">
          <SkeletonCard />
          <SkeletonCard />
        </section>
      ) : null}

      {state === "error" ? <EmptySection title="加载失败" detail="请确认 /v1 API 反代正常；单个 fixture 失败不会阻塞整页。" /> : null}

      {state === "empty" && view ? <DataDiagnosticsPanel debug={view.debug} release={view.release} /> : null}

      {state === "ok" && view ? (
        <>
          {(mode === "today" || mode === "all") && <RecommendationBoard matches={view.recommendations} />}
          {(mode === "today" || mode === "next36" || mode === "all") && <UpcomingFixturesPanel matches={mode === "all" ? visibleAll.filter((match) => match.status !== "FINISHED") : view.upcoming} />}
          {(mode === "today" || mode === "results" || mode === "all") && <ResultsValidationPanel matches={view.finished} />}
          {view.errors.length ? (
            <aside className="soft-errors">
              <strong>部分数据源暂不可用</strong>
              <p>{view.errors.slice(0, 3).join("；")}</p>
            </aside>
          ) : null}
        </>
      ) : null}

      <footer className="dashboard-disclaimer">本页为分析参考·非稳赢，非投注建议，不承诺盈利 · 数据不足时一律 SKIP，不强出推荐</footer>
    </main>
  );
}
