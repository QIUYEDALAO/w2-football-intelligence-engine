import { Fragment, useEffect, useMemo, useState } from "react";
import type {
  DashboardV2FixtureModel,
  DashboardV2LeaguePerformanceRow,
  DashboardV2ViewModel,
} from "./dashboard-v2-model";
import "./dashboard-v2-reference.css";

const SHANGHAI_DATE = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const SHANGHAI_MONTH_DAY = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
});
const SHANGHAI_WEEKDAY = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  weekday: "short",
});
const SHANGHAI_TIME = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const TIER_LABEL: Record<string, string> = {
  ANALYSIS_PICK: "分析参考",
  NO_EDGE: "无优势",
  WATCH: "观察",
  NOT_READY: "未就绪",
  SKIP: "跳过",
};
const DATA_LABEL: Record<string, string> = {
  READY: "分析级就绪",
  PARTIAL: "部分就绪",
  STALE: "赔率待更新",
  BLOCKED: "数据阻塞",
};

type FilterId = "all" | "analysis" | "hide-not-ready";

export interface DashboardV2ReferenceProps {
  model: DashboardV2ViewModel;
  fixedNow?: Date;
}

function shortHash(value?: string | null): string {
  return value ? value.slice(0, 7) : "--";
}

function formatPercent(value: number | null, digits = 1): string {
  return value == null || !Number.isFinite(value) ? "--" : `${(value * 100).toFixed(digits)}%`;
}

function formatSigned(value: number | null, digits = 3): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function dateKey(value: string): string {
  return SHANGHAI_DATE.format(new Date(value));
}

function dateLabel(value: string): string {
  const date = new Date(value);
  return `${SHANGHAI_MONTH_DAY.format(date).replace("/", "-")} ${SHANGHAI_WEEKDAY.format(date)}`;
}

function timeLabel(value: string): string {
  return SHANGHAI_TIME.format(new Date(value));
}

function minuteDistance(kickoffUtc: string, now: Date): number {
  return Math.round((new Date(kickoffUtc).getTime() - now.getTime()) / 60_000);
}

function kickoffCopy(fixture: DashboardV2FixtureModel, now: Date): {
  date: string;
  time: string;
  relative: string;
} {
  const minutes = minuteDistance(fixture.kickoffUtc, now);
  const status = fixture.status.toUpperCase();
  if (["FT", "AET", "PEN", "FINISHED"].includes(status)) {
    return { date: "完场", time: `${dateLabel(fixture.kickoffUtc)} ${timeLabel(fixture.kickoffUtc)}`, relative: "已结算" };
  }
  if (["LIVE", "1H", "2H", "HT", "ET", "P"].includes(status)) {
    return {
      date: `进行中 ${Math.max(0, Math.abs(minutes))}′`,
      time: `${dateLabel(fixture.kickoffUtc)} ${timeLabel(fixture.kickoffUtc)}`,
      relative: "实时状态",
    };
  }
  const today = dateKey(now.toISOString());
  const tomorrow = dateKey(new Date(now.getTime() + 86_400_000).toISOString());
  const kickoffDay = dateKey(fixture.kickoffUtc);
  if (kickoffDay === today) {
    return {
      date: "今天",
      time: timeLabel(fixture.kickoffUtc),
      relative: minutes < 60 ? `还有 ${Math.max(0, minutes)} 分钟` : `还有 ${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`,
    };
  }
  if (kickoffDay === tomorrow) {
    return { date: "明天", time: timeLabel(fixture.kickoffUtc), relative: dateLabel(fixture.kickoffUtc) };
  }
  return {
    date: dateLabel(fixture.kickoffUtc),
    time: timeLabel(fixture.kickoffUtc),
    relative: `${Math.max(1, Math.floor(minutes / 1440))}天后`,
  };
}

function useMinuteClock(fixedNow?: Date): Date {
  const [now, setNow] = useState(() => fixedNow ?? new Date());
  useEffect(() => {
    if (fixedNow) {
      setNow(fixedNow);
      return undefined;
    }
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, [fixedNow]);
  return now;
}

function fixtureMatchesFilter(fixture: DashboardV2FixtureModel, filter: FilterId): boolean {
  if (filter === "analysis") return fixture.decisionTier === "ANALYSIS_PICK";
  if (filter === "hide-not-ready") return !["NOT_READY", "SKIP"].includes(fixture.decisionTier);
  return true;
}

function groupByDate(fixtures: DashboardV2FixtureModel[]): Array<{
  key: string;
  label: string;
  fixtures: DashboardV2FixtureModel[];
}> {
  const groups = new Map<string, DashboardV2FixtureModel[]>();
  for (const fixture of fixtures) {
    const key = dateKey(fixture.kickoffUtc);
    groups.set(key, [...(groups.get(key) ?? []), fixture]);
  }
  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, rows]) => ({ key, label: dateLabel(rows[0].kickoffUtc), fixtures: rows }));
}

function LedgerStrip({ model }: { model: DashboardV2ViewModel }) {
  const { ledger } = model;
  return (
    <section className="d2-ledger-strip" data-ui="forward-ledger-strip">
      <strong>前向验证账本 {ledger.rangeLabel}</strong>
      <span>记录 <b>{ledger.validationCount}</b></span>
      <span>已结算 <b>{ledger.settledCount}</b></span>
      <span>纳入 <b>{ledger.eligibleCount}</b></span>
      <span>证据待补 <b>{ledger.evidenceRepairPendingCount}</b></span>
      <span>待结算 <b>{ledger.pendingCount}</b></span>
      <span>命中率 <b>{formatPercent(ledger.hitRate)}</b>（{ledger.hitCount}/{ledger.decisiveCount}）</span>
      <span>CLV <b>{formatSigned(ledger.clvMedian)}</b>（n={ledger.clvSampleCount}）</span>
    </section>
  );
}

function HealthStrip({ model }: { model: DashboardV2ViewModel }) {
  return (
    <section className="d2-health-strip" data-ui="collection-health-strip">
      <strong>{model.health.automaticCollectionPaused ? "自动采集已暂停" : "赛前数据持续更新"}</strong>
      <span>{model.health.competitionCount} 个联赛 · 待赛 {model.health.upcomingCount} 场</span>
      <small>{model.health.description}</small>
    </section>
  );
}

function FilterBar({
  filter,
  onChange,
  visible,
  total,
}: {
  filter: FilterId;
  onChange: (value: FilterId) => void;
  visible: number;
  total: number;
}) {
  const options: Array<[FilterId, string]> = [
    ["all", "全部赛程"],
    ["analysis", "只看分析建议"],
    ["hide-not-ready", "隐藏未就绪"],
  ];
  return (
    <div className="d2-filter-bar" data-ui="schedule-filter-bar">
      <div className="d2-filter-actions">
        {options.map(([id, label]) => (
          <button
            className={filter === id ? "is-active" : ""}
            key={id}
            onClick={() => onChange(id)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      <span>分析建议置顶 · 其余严格按开球时间</span>
      <b>{visible} / {total} 场</b>
    </div>
  );
}

function DecisionRow({
  fixture,
  selected,
  now,
  onSelect,
}: {
  fixture: DashboardV2FixtureModel;
  selected: boolean;
  now: Date;
  onSelect: () => void;
}) {
  const kickoff = kickoffCopy(fixture, now);
  const muted = ["NOT_READY", "SKIP"].includes(fixture.decisionTier) || fixture.dataStatus === "BLOCKED";
  return (
    <article
      className={`d2-fixture-row tier-${fixture.decisionTier.toLowerCase().replaceAll("_", "-")}${selected ? " is-selected" : ""}${muted ? " is-muted" : ""}`}
      data-fixture-id={fixture.fixtureId}
    >
      <button onClick={onSelect} type="button" aria-pressed={selected}>
        <div className="d2-time-cell">
          <strong>{kickoff.date}</strong>
          <span>{kickoff.time}</span>
          <small>{kickoff.relative}</small>
        </div>
        <div className="d2-league-cell"><span>{fixture.competition}</span></div>
        <div className="d2-match-cell">
          <strong>{fixture.homeTeam} <i>vs</i> {fixture.awayTeam}</strong>
          <span>{fixture.scorelineSummary ? `模型比分：${fixture.scorelineSummary}` : fixture.reasonLabel ?? "等待评估"}</span>
        </div>
        <div className="d2-market-cell">
          <strong>{fixture.primaryMarketLabel}</strong>
          <span>{fixture.secondaryMarketLabel ?? fixture.reasonLabel ?? "已审计市场"}</span>
        </div>
        <div className="d2-data-cell">
          <span>{DATA_LABEL[fixture.dataStatus] ?? fixture.dataStatus}</span><i aria-hidden="true" />
        </div>
        <div className="d2-tier-cell"><span>{TIER_LABEL[fixture.decisionTier] ?? fixture.decisionTier}</span></div>
        <div className="d2-next-cell"><span>{fixture.nextEvaluationAt ? timeLabel(fixture.nextEvaluationAt) : "待定"}</span></div>
      </button>
    </article>
  );
}

function ScheduleSection({
  title,
  subtitle,
  fixtures,
  selectedFixtureId,
  now,
  onSelect,
}: {
  title: string;
  subtitle: string;
  fixtures: DashboardV2FixtureModel[];
  selectedFixtureId: string | null;
  now: Date;
  onSelect: (fixtureId: string) => void;
}) {
  const groups = groupByDate(fixtures);
  return (
    <section className={`d2-schedule-section${fixtures.length ? "" : " is-empty"}`}>
      <header><div><strong>{title}</strong><span>{subtitle}</span></div><b>{fixtures.length}</b></header>
      {fixtures.length ? (
        <div className="d2-table">
          <div className="d2-table-head">
            <span>日期 / 时间</span><span>联赛</span><span>对阵 / 模型比分</span><span>分析盘口 / 市场</span><span>数据</span><span>决策</span><span>下次评估</span>
          </div>
          {groups.map((group) => (
            <Fragment key={group.key}>
              <div className="d2-date-header">{group.label} · {group.fixtures.length}场</div>
              {group.fixtures.map((fixture) => (
                <DecisionRow
                  key={fixture.fixtureId}
                  fixture={fixture}
                  selected={fixture.fixtureId === selectedFixtureId}
                  now={now}
                  onSelect={() => onSelect(fixture.fixtureId)}
                />
              ))}
            </Fragment>
          ))}
        </div>
      ) : <div className="d2-empty-row">当前没有符合本区条件的比赛</div>}
    </section>
  );
}

function ScorelinePanel({ fixture }: { fixture: DashboardV2FixtureModel }) {
  const projection = fixture.scorelineProjection;
  if (!projection || projection.status !== "READY") {
    return (
      <section className="d2-card d2-scoreline-card is-blocked" data-ui="scoreline-top3-panel">
        <header><span>模型比分 Top 3</span><b>不可用</b></header>
        <p>{projection?.blocker ?? "本场没有分析建议，不展示推荐比分。"}</p>
      </section>
    );
  }
  return (
    <section className="d2-card d2-scoreline-card" data-ui="scoreline-top3-panel">
      <header><span>模型比分 Top 3</span><b>10,000 次模拟</b></header>
      <div className="d2-scoreline-list">
        {projection.top3.map((row, index) => (
          <div key={row.scoreline}>
            <span>{index + 1}</span>
            <strong>{row.scoreline}</strong>
            <b>{formatPercent(row.unconditionalProbability)}</b>
            <small>{row.sampleCount.toLocaleString()} 次</small>
          </div>
        ))}
      </div>
      <div className="d2-scoreline-consistency">
        <strong>{projection.consistencyLabel}</strong>
        <span>一致样本 {projection.consistentSampleCount.toLocaleString()} / {projection.simulationsCompleted.toLocaleString()}</span>
        <small>decision {shortHash(projection.decisionHash)} · evidence {shortHash(projection.evidenceHash)}</small>
      </div>
    </section>
  );
}

function SelectedMatchPanel({ fixture }: { fixture: DashboardV2FixtureModel }) {
  const quote = fixture.quote;
  return (
    <section className="d2-card d2-selected-card" data-ui="selected-match-panel">
      <header><span>选中比赛证据</span><b>{TIER_LABEL[fixture.decisionTier]}</b></header>
      <h2>{fixture.homeTeam} <i>vs</i> {fixture.awayTeam}</h2>
      <p className="d2-kickoff-copy">{dateLabel(fixture.kickoffUtc)} · {timeLabel(fixture.kickoffUtc)} · {fixture.competition}</p>
      <div className="d2-primary-pick">
        <span>分析盘口</span>
        <strong>{fixture.primaryMarketLabel}</strong>
        {fixture.secondaryMarketLabel ? <small>次推：{fixture.secondaryMarketLabel}</small> : null}
      </div>
      {quote ? (
        <div className="d2-quote-grid">
          <div><span>主线策略</span><b>{quote.marketPolicyLabel}</b></div>
          <div><span>执行报价</span><b>{quote.bookmaker}</b></div>
          <div><span>决策快照</span><b>{dateLabel(quote.capturedAt)} {timeLabel(quote.capturedAt)}</b></div>
          <div><span>赔率</span><b>@{quote.odds.toFixed(2)}</b></div>
        </div>
      ) : null}
      {quote ? (
        <div className="d2-probability-grid">
          <div><span>模型概率</span><b>{formatPercent(quote.modelProbability)}</b></div>
          <div><span>市场概率</span><b>{formatPercent(quote.marketProbability)}</b></div>
          <div><span>概率差</span><b>{formatSigned(quote.probabilityDelta)}</b></div>
          <div><span>EV</span><b>{formatSigned(quote.expectedValue)}</b></div>
          <div><span>不确定性</span><b>{quote.uncertainty?.toFixed(3) ?? "--"}</b></div>
        </div>
      ) : null}
      <div className="d2-fact-list">
        {fixture.dataFacts.map((fact) => <span key={fact}>{fact}</span>)}
      </div>
      <div className="d2-tracking-note">
        <span>赛后追踪</span>
        <strong>{fixture.tracking.label}</strong>
        <small>{fixture.tracking.detail}{fixture.tracking.captureHash ? ` · capture ${shortHash(fixture.tracking.captureHash)}` : ""}</small>
      </div>
    </section>
  );
}

function ForwardValidationCard({ model }: { model: DashboardV2ViewModel }) {
  const { ledger } = model;
  return (
    <section className="d2-card d2-validation-card" data-ui="forward-validation-panel">
      <header><span>赛后验证</span><b>纳入统计 {ledger.eligibleCount} 场</b></header>
      <div className="d2-outcome-line">
        <strong>命中 {ledger.hitCount} · 未中 {ledger.missCount} · 走水 {ledger.pushCount}{ledger.voidCount ? ` · 作废 ${ledger.voidCount}` : ""}</strong>
        <span>有效输赢 {ledger.decisiveCount} 场 · 命中率 {formatPercent(ledger.hitRate)} · 待结算 {ledger.pendingCount} 场</span>
      </div>
      <div className="d2-ledger-reconcile">
        <span>{ledger.validationCount} = {ledger.settledCount} 已结算 + {ledger.pendingCount} 待结算</span>
        <span>{ledger.settledCount} = {ledger.eligibleCount} 纳入 + {ledger.evidenceRepairPendingCount} 证据待补</span>
      </div>
    </section>
  );
}

function LeaguePerformance({ rows }: { rows: DashboardV2LeaguePerformanceRow[] }) {
  return (
    <section className="d2-card d2-league-card" data-ui="league-performance-panel">
      <header><span>联赛表现</span><b>统一账本</b></header>
      <div className="d2-league-table">
        <div><b>联赛</b><b>纳入</b><b>结果</b><b>临场 CLV</b></div>
        {rows.map((row) => (
          <div key={row.league}>
            <span>{row.league}</span>
            <span>{row.eligibleCount} 场</span>
            <span>{row.hitCount}-{row.missCount}-{row.pushCount}</span>
            <span>{formatSigned(row.clvMedian)}（n={row.clvSampleCount}）</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function DashboardV2Reference({ model, fixedNow }: DashboardV2ReferenceProps) {
  const now = useMinuteClock(fixedNow);
  const [filter, setFilter] = useState<FilterId>("all");
  const [selectedFixtureId, setSelectedFixtureId] = useState<string | null>(model.selectedFixtureId);
  const sorted = useMemo(
    () => [...model.fixtures].sort((left, right) => left.kickoffUtc.localeCompare(right.kickoffUtc)),
    [model.fixtures],
  );
  const visible = useMemo(() => sorted.filter((fixture) => fixtureMatchesFilter(fixture, filter)), [filter, sorted]);
  const analysis = visible.filter((fixture) => fixture.decisionTier === "ANALYSIS_PICK");
  const other = visible.filter((fixture) => fixture.decisionTier !== "ANALYSIS_PICK");
  const selected = model.fixtures.find((fixture) => fixture.fixtureId === selectedFixtureId) ?? visible[0] ?? model.fixtures[0];

  return (
    <main className="dashboard-v2-reference" data-ui="dashboard-v2">
      <header className="d2-commandbar" data-ui="command-header">
        <div className="d2-brand"><strong>FOOTBALL</strong><span>INTELLIGENCE</span></div>
        <span className="d2-console-badge">只读决策台</span>
        <div className="d2-command-metrics">
          <span>观察日 <b>{model.observedFootballDay}</b></span>
          <span>环境 <b>{model.release.environment}</b></span>
          <span className="d2-time-pair"><small>页面更新 <b>{timeLabel(model.release.pageUpdatedAt)}</b></small><small>全局最近赔率 <b>{model.release.oddsConfirmedAt ? timeLabel(model.release.oddsConfirmedAt) : "暂无"}</b></small></span>
          <span>下次采集 <b>{model.release.nextRefreshAt ? timeLabel(model.release.nextRefreshAt) : "待定"}</b></span>
          <span>未来待赛 <b className="is-accent">{model.health.upcomingCount}</b></span>
          <span>分析建议 <b className="is-accent">{model.fixtures.filter((fixture) => fixture.decisionTier === "ANALYSIS_PICK").length}</b></span>
        </div>
        <div className="d2-release">Web {shortHash(model.release.webSha)} · API {shortHash(model.release.apiSha)}</div>
      </header>

      <LedgerStrip model={model} />
      <HealthStrip model={model} />

      <section className="d2-workspace" data-ui="dashboard-workspace">
        <section className="d2-schedule-board" data-ui="schedule-scroller">
          <FilterBar filter={filter} onChange={setFilter} visible={visible.length} total={model.fixtures.length} />
          <ScheduleSection title="已形成分析判断" subtitle="所有符合完整数据与决策条件的比赛均展示" fixtures={analysis} selectedFixtureId={selected?.fixtureId ?? null} now={now} onSelect={setSelectedFixtureId} />
          <ScheduleSection title="其余赛程" subtitle="按上海日期分组；无优势与未就绪比赛保留真实状态" fixtures={other} selectedFixtureId={selected?.fixtureId ?? null} now={now} onSelect={setSelectedFixtureId} />
        </section>

        <aside className="d2-side-rail" data-ui="evidence-rail">
          {selected ? <SelectedMatchPanel fixture={selected} /> : null}
          {selected ? <ScorelinePanel fixture={selected} /> : null}
          <ForwardValidationCard model={model} />
          <LeaguePerformance rows={model.leaguePerformance} />
        </aside>
      </section>

      <footer className="d2-disclaimer">分析参考 · 非稳赢 · 不构成投注建议</footer>
    </main>
  );
}
