import { useEffect, useMemo, useState } from "react";
import { fetchDashboardView, getCachedDashboardView } from "../lib/dashboardApi";
import { todayShanghai } from "../lib/formatters";
import type { DashboardMode, DashboardView, LoadState } from "../types/dashboard";
import { BossDecisionView } from "./BossDecisionView";
import { DataDiagnosticsPanel } from "./DataDiagnosticsPanel";
import { EmptySection } from "./EmptySection";
import { ReleaseSyncBadge } from "./ReleaseSyncBadge";
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
  if (mode === "future") {
    return { title: "未来 14 天暂无可展示比赛", detail: "白名单联赛未进入赛程窗口、未启用或数据未齐时，这里会保持空态并在诊断里说明原因。" };
  }
  if (mode === "results") {
    return { title: "本足球日暂无完场比赛", detail: "北京时间中午 12:00 到次日 11:59 的比赛完场并同步赛果后，会显示复盘。" };
  }
  if (mode === "today") return { title: "本足球日暂无可展示比赛", detail: "数据不足时保持空白，不强出推荐。" };
  if (mode === "all") return { title: "本足球日暂无比赛", detail: "当前足球日没有可展示比赛；未来赛程进入窗口后会自动出现。" };
  return { title: "暂无可展示比赛", detail: "数据不足时保持空白，不强出推荐。" };
}

function shouldShowDiagnostics(): boolean {
  const params = new URLSearchParams(window.location.search);
  return params.get("debug") === "1" || params.get("diagnostics") === "1";
}

export function DashboardPage() {
  const [view, setView] = useState<DashboardView | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const mode: DashboardMode = "future";
  const [date, setDate] = useState(todayShanghai());
  const [updatedAt, setUpdatedAt] = useState("--");
  const [refreshKey, setRefreshKey] = useState(0);

  function refreshDashboard(): void {
    // Keep the current snapshot visible while a fresh one is loaded in the background.
    if (!view) setState("loading");
    setRefreshKey((value) => value + 1);
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const cached = getCachedDashboardView(date, mode);
      if (cached) {
        setView(cached);
        setUpdatedAt(updatedAtShanghai());
        setState((cached.day_view?.cards.length ?? cached.all.length) ? "ok" : "empty");
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
        setState((nextView.day_view?.cards.length ?? nextView.all.length) ? "ok" : "empty");
      } catch {
        if (!cancelled && !cached) setState("error");
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [date, mode, refreshKey]);

  const legacyMatches = useMemo(() => view?.all ?? [], [view]);

  const empty = emptyCopy(mode);
  const showDiagnostics = shouldShowDiagnostics();

  return (
    <main className="app-shell dashboard-v2">
      {view?.cache_status === "STALE_CACHE" ? (
        <aside className="soft-errors">
          <strong>缓存快照 · STALE_CACHE</strong>
          <p>网络读取失败前先保留最近一次 DayView；不会冒充当前 release。</p>
        </aside>
      ) : null}
      {view?.day_view ? null : view ? <ReleaseSyncBadge release={view.release} /> : null}
      {view?.day_view ? null : (
        <div className="dashboard-controls">
          <div className="date-refresh">
            <label>
              日期
              <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
            </label>
            <button className="toolbar-button refresh-button" onClick={refreshDashboard} type="button">
              刷新
            </button>
          </div>
        </div>
      )}

      {state === "loading" ? (
        <section className="match-card-grid" aria-label="比赛加载中">
          <SkeletonCard />
          <SkeletonCard />
        </section>
      ) : null}

      {state === "error" ? <EmptySection title="加载失败" detail="请确认公网 /v1 API 可访问；不会用假数据顶替真实数据。" /> : null}

      {state === "empty" && view ? (
        view.day_view ? (
          <BossDecisionView dayView={view.day_view} legacyMatches={legacyMatches} performance={view.performance} release={view.release} />
        ) : showDiagnostics ? (
          <DataDiagnosticsPanel debug={view.debug} release={view.release} />
        ) : (
          <EmptySection title={empty.title} detail={empty.detail} />
        )
      ) : null}

      {state === "ok" && view ? (
        <>
          {view.day_view ? (
            <BossDecisionView dayView={view.day_view} legacyMatches={legacyMatches} performance={view.performance} release={view.release} />
          ) : (
            <EmptySection title={empty.title} detail={empty.detail} />
          )}
          <details className="global-diagnostics-drawer" open={showDiagnostics}>
            <summary>全局技术诊断</summary>
            <DataDiagnosticsPanel debug={view.debug} release={view.release} />
          </details>
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
