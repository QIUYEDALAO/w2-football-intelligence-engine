import { useEffect, useMemo, useState } from "react";
import { fetchDashboardView, getCachedDashboardView } from "../lib/dashboardApi";
import { todayShanghai } from "../lib/formatters";
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
    if (mode === "next36") return view.upcoming;
    if (mode === "results") return view.finished;
    return view.all;
  }, [mode, view]);

  const empty = emptyCopy(mode);

  return (
    <main className="app-shell dashboard-v2">
      {view ? <ReleaseSyncBadge release={view.release} /> : null}
      {view ? <PerformanceHeader performance={view.performance} updatedAt={updatedAt} /> : null}
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

      <footer className="dashboard-disclaimer">本页为分析参考，非投注建议，不承诺盈利；数据不足时不强出方向。</footer>
    </main>
  );
}
