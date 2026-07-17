import type { DashboardCard, DashboardStats, FilterMode, LoadState } from "../types/dashboard";
import { DashboardToolbar } from "./DashboardToolbar";
import { EmptyState } from "./EmptyState";
import { MatchCard } from "./MatchCard";
import { SkeletonCard } from "./SkeletonCard";
import { SummaryMetric } from "./SummaryMetric";

export function DashboardShell({
  cards,
  date,
  filter,
  state,
  stats,
  updatedAt,
  onDateChange,
  onFilterChange,
  onRefresh,
}: {
  cards: DashboardCard[];
  date: string;
  filter: FilterMode;
  state: LoadState;
  stats: DashboardStats;
  updatedAt: string;
  onDateChange: (value: string) => void;
  onFilterChange: (value: FilterMode) => void;
  onRefresh: () => void;
}) {
  return (
    <main className="app-shell">
      <header className="dashboard-header">
        <div>
          <p>W2 Football Intelligence</p>
          <h1>Compact match dashboard</h1>
          <span>W2 足球分析 · 今日比赛 · 分析参考 · 非稳赢</span>
        </div>
        <strong>candidate=false · formal=false</strong>
      </header>

      <section className="summary-grid" aria-label="Summary metrics">
        <SummaryMetric label="比赛数" value={stats.total} sub={date} />
        <SummaryMetric label="有分析" value={stats.picks} sub="主市场可读" />
        <SummaryMetric label="数据较完整" value={stats.ready} sub={`更新 ${updatedAt}`} />
        <SummaryMetric label="高关注" value={stats.highWatch} sub="关注度 ≥ 3" />
      </section>

      <DashboardToolbar
        date={date}
        filter={filter}
        onDateChange={onDateChange}
        onFilterChange={onFilterChange}
        onRefresh={onRefresh}
      />

      {state === "loading" ? (
        <section className="cards-grid">
          <SkeletonCard />
          <SkeletonCard />
        </section>
      ) : null}
      {state === "error" ? <EmptyState message="加载失败。请确认 /v1 API 反代正常后刷新页面。" /> : null}
      {state === "empty" ? <EmptyState message="当前日期没有白名单比赛或数据还未进入 read-model。" /> : null}
      {state === "ok" ? (
        <section className="cards-grid">
          {cards.length ? cards.map((card) => <MatchCard card={card} key={String(card.fixture_id ?? JSON.stringify(card))} />) : <EmptyState message="当前筛选下没有比赛。" />}
        </section>
      ) : null}

      <footer className="dashboard-disclaimer">赛前输出由真实数据和策略规则生成；数据不足时保持观察，赛后统计仅在完场后展示。</footer>
    </main>
  );
}
