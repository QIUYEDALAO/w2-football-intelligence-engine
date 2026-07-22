import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type {
  BossConsoleModel,
  BossDecisionItem,
} from "./boss-console-model";

type FilterId = "priority" | "all" | "risk";

export interface BossDecisionConsoleReferenceProps {
  model: BossConsoleModel;
  fixedNow?: Date;
  prototypeCopy?: boolean;
}

const SHANGHAI_PARTS = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  hourCycle: "h23",
});

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"] as const;
const FINISHED_STATUSES = new Set(["FT", "AET", "PEN", "FINISHED"]);
const LIVE_STATUSES = new Set(["LIVE", "1H", "HT", "2H", "ET", "BT", "P", "INT"]);

interface ShanghaiParts {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

export interface KickoffDisplay {
  primary: string;
  secondary: string | null;
  tertiary: string | null;
}

function useMinuteClock(fixedNow?: Date): Date {
  const [now, setNow] = useState(() => fixedNow ?? new Date());
  useEffect(() => {
    if (fixedNow) {
      setNow(fixedNow);
      return undefined;
    }
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, [fixedNow]);
  return now;
}

function safeDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function shanghaiParts(date: Date): ShanghaiParts {
  const parts = Object.fromEntries(
    SHANGHAI_PARTS.formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, Number(part.value)]),
  );
  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    hour: parts.hour,
    minute: parts.minute,
  };
}

function localDayNumber(parts: ShanghaiParts): number {
  return Date.UTC(parts.year, parts.month - 1, parts.day) / 86_400_000;
}

function twoDigits(value: number): string {
  return String(value).padStart(2, "0");
}

function dateLabel(parts: ShanghaiParts): string {
  const weekday = WEEKDAYS[new Date(Date.UTC(parts.year, parts.month - 1, parts.day)).getUTCDay()];
  return `${twoDigits(parts.month)}-${twoDigits(parts.day)} ${weekday}`;
}

function dateTimeLabel(value?: string | null): string {
  const date = safeDate(value);
  if (!date) return "—";
  const parts = shanghaiParts(date);
  return `${twoDigits(parts.month)}-${twoDigits(parts.day)} ${twoDigits(parts.hour)}:${twoDigits(parts.minute)}`;
}

function liveMinute(status: string): number | null {
  const match = status.match(/^(?:LIVE[_\s-])?(\d{1,3})(?:['′])?$/i);
  if (!match) return null;
  const value = Number(match[1]);
  return value > 0 && value <= 130 ? value : null;
}

export function kickoffDisplay(value: string, status: string, now: Date): KickoffDisplay {
  const date = safeDate(value);
  if (!date) return { primary: "时间待定", secondary: null, tertiary: null };
  const parts = shanghaiParts(date);
  const nowParts = shanghaiParts(now);
  const normalizedStatus = status.toUpperCase();
  const absolute = `${twoDigits(parts.month)}-${twoDigits(parts.day)} ${twoDigits(parts.hour)}:${twoDigits(parts.minute)}`;
  if (FINISHED_STATUSES.has(normalizedStatus)) {
    return { primary: "完场", secondary: absolute, tertiary: null };
  }
  const minute = liveMinute(normalizedStatus);
  if (LIVE_STATUSES.has(normalizedStatus) || minute != null) {
    return {
      primary: `进行中${minute == null ? "" : ` ${minute}′`}`,
      secondary: absolute,
      tertiary: null,
    };
  }

  const minutes = Math.max(0, Math.floor((date.getTime() - now.getTime()) / 60_000));
  const dayDifference = localDayNumber(parts) - localDayNumber(nowParts);
  const time = `${twoDigits(parts.hour)}:${twoDigits(parts.minute)}`;
  if (dayDifference > 1) {
    return { primary: dateLabel(parts), secondary: time, tertiary: `${dayDifference}天后` };
  }
  if (dayDifference === 1) {
    return { primary: "明天", secondary: time, tertiary: dateLabel(parts) };
  }
  if (minutes <= 60) {
    return { primary: "今天", secondary: time, tertiary: `还有 ${minutes}分钟` };
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return {
    primary: "今天",
    secondary: time,
    tertiary: `还有 ${hours}小时${remainingMinutes ? `${remainingMinutes}分` : ""}`,
  };
}

function ageLabel(value: string | null, now: Date): string {
  const date = safeDate(value);
  if (!date) return "待定";
  const minutes = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 60_000));
  if (minutes < 60) return `${minutes}分钟`;
  return `${Math.floor(minutes / 60)}小时${minutes % 60 ? `${minutes % 60}分` : ""}`;
}

function hasTimeSequenceAnomaly(model: BossConsoleModel): boolean {
  const odds = safeDate(model.release.oddsConfirmedAt);
  const page = safeDate(model.release.pageUpdatedAt);
  return Boolean(odds && page && odds.getTime() > page.getTime());
}

function formatPercent(value: number | null): string {
  return value == null ? "--" : `${(value * 100).toFixed(1)}%`;
}

function formatDelta(value: number | null): string {
  return value == null ? "--" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}pp`;
}

function formatEv(value: number | null): string {
  return value == null ? "--" : `${value >= 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;
}

function shortHash(value: string): string {
  return value === "—" ? value : value.slice(0, 7);
}

function DecisionRow({
  item,
  selected,
  now,
  onSelect,
}: {
  item: BossDecisionItem;
  selected: boolean;
  now: Date;
  onSelect: (id: string) => void;
}) {
  const kickoff = kickoffDisplay(item.kickoffUtc, item.fixtureStatus, now);
  const scoreline = item.status === "pick" && item.scorelineProjection?.status === "READY"
    ? item.scorelineProjection.top3.map((row) => row.scoreline).join(" · ")
    : null;
  return (
    <button
      className={`decision-row status-${item.status}${selected ? " is-selected" : ""}`}
      data-fixture-id={item.id}
      onClick={() => onSelect(item.id)}
      aria-pressed={selected}
    >
      <div><span className="priority">{item.priority}</span></div>
      <div className="kickoff"><strong>{kickoff.primary}</strong>{kickoff.secondary ? <b>{kickoff.secondary}</b> : null}{kickoff.tertiary ? <span>{kickoff.tertiary}</span> : null}</div>
      <div className="matchup"><strong>{item.match}</strong><span>{item.league}</span></div>
      <div className="decision-main">
        <strong>{item.recommendation}</strong>
        {item.marketMainlineLabel ? <div className="market-layer"><b>{item.marketMainlineLabel}</b><span>{item.executionQuoteLabel}</span></div> : null}
        <div className="metric-line">
          {item.modelProbability == null ? (
            <span><b>状态</b> {item.recommendation}</span>
          ) : (
            <>
              <span><b>模型</b> {formatPercent(item.modelProbability)}</span>
              <span><b>市场</b> {formatPercent(item.marketProbability)}</span>
              <span><b>差值</b> {formatDelta(item.probabilityDelta)}</span>
              <span><b>EV</b> {formatEv(item.expectedValue)}</span>
            </>
          )}
        </div>
        {scoreline ? <div className="scoreline-inline"><b>模型比分</b> {scoreline}</div> : null}
      </div>
      <div className={`risk-level ${item.riskLevel}`}><span>{item.risk}风险</span><small>{item.riskNote}</small></div>
      <div className="next-action"><strong>{item.nextAction}</strong><span>{item.nextDetail}</span></div>
    </button>
  );
}

function ScorelineProjection({ item }: { item: BossDecisionItem }) {
  if (item.status !== "pick") return null;
  const projection = item.scorelineProjection;
  if (!projection || projection.status !== "READY") {
    return (
      <section className="scoreline-panel not-ready" data-ui="scoreline-projection">
        <div><h3>模型比分 Top 3</h3><span>NOT_READY</span></div>
        <p>{projection?.blocker || "SCORELINE_PROJECTION_MISSING"}</p>
      </section>
    );
  }
  return (
    <section className="scoreline-panel" data-ui="scoreline-projection">
      <div className="scoreline-head"><h3>模型比分 Top 3</h3><span>{projection.simulationsCompleted.toLocaleString("en-US")} 次模拟</span></div>
      <div className="scoreline-list">
        {projection.top3.map((row) => (
          <div className="scoreline-row" key={`${row.scoreline}-${row.sampleCount}`}>
            <strong>{row.scoreline}</strong>
            <span>{formatPercent(row.unconditionalProbability)}</span>
            <small>{row.sampleCount.toLocaleString("en-US")}次</small>
          </div>
        ))}
      </div>
      <div className="scoreline-foot">
        <strong>一致样本 {projection.consistentSampleCount.toLocaleString("en-US")} / {projection.simulationsCompleted.toLocaleString("en-US")}</strong>
        <span>{projection.consistencyLabel}</span>
        <code>decision {shortHash(projection.decisionHash)} · evidence {shortHash(projection.evidenceHash)}</code>
      </div>
    </section>
  );
}

function MarketLadder({ item }: { item: BossDecisionItem }) {
  if (!item.marketLadder.length) return null;
  return (
    <details className="market-ladder" data-ui="market-ladder">
      <summary><span>盘口阶梯</span><small>{item.marketLadder.length} 条完整 line · 点击展开</small></summary>
      <div className="market-ladder-table">
        <div className="market-ladder-row head"><span>Line</span><span>双边中位价</span><span>完整/票</span><span>模型/市场</span><span>EV/SE</span><span>裁决</span></div>
        {item.marketLadder.map((row) => (
          <div className="market-ladder-row" key={row.line}>
            <strong>{row.line}</strong>
            <span>{row.leftPrice?.toFixed(2) ?? "--"} / {row.rightPrice?.toFixed(2) ?? "--"}</span>
            <span>{row.completePairBookmakerCount}家 / {row.bookmakerVoteCount}票</span>
            <span>{formatPercent(row.modelProbability)} / {formatPercent(row.marketProbability)}</span>
            <span>{formatEv(row.expectedValue)} / ±{formatPercent(row.uncertainty)}</span>
            <span className={row.status === "SELECTED_MARKET_MAINLINE" ? "selected" : "rejected"}>{row.status === "SELECTED_MARKET_MAINLINE" ? "市场主线" : row.reason ?? "拒绝"}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

function DetailPanel({ item, now }: { item: BossDecisionItem; now: Date }) {
  const badgeClass = item.status === "watch" ? " watch" : item.status === "not-ready" ? " not-ready" : "";
  const kickoff = kickoffDisplay(item.kickoffUtc, item.fixtureStatus, now);
  return (
    <aside className="panel detail-panel" aria-label="选中决策详情" data-ui="selected-match-panel">
      <div className="detail-top">
        <div className="detail-eyebrow">
          <div className={`decision-badge${badgeClass}`}>{item.decision}</div>
          <div className="snapshot-age">{item.snapshotAt ? `本场决策快照 · ${dateTimeLabel(item.snapshotAt)}` : "尚无本场决策快照"}</div>
        </div>
        <h1 className="detail-match">{item.match}</h1>
        <div className="detail-meta"><span>{item.league}</span><strong>{kickoff.primary === "今天" || kickoff.primary === "明天" ? `${kickoff.primary} · ${kickoff.secondary}` : `${kickoff.primary} ${kickoff.secondary ?? ""}`.trim()}</strong>{kickoff.tertiary ? <small>{kickoff.tertiary}</small> : null}</div>
        <div className="market-contract">
          <strong>当前状态：{item.lifecycleState ?? "等待不可变评估版本"}</strong>
          <span>报价年龄：{item.quoteAgeSeconds == null ? "待确认" : `${Math.floor(item.quoteAgeSeconds / 60)} 分钟`} · 最近 checkpoint：{item.latestCheckpoint ?? "待确认"}</span>
          <code>下一 checkpoint：{item.nextCheckpoint ?? "无"} · {item.automaticRefreshStatus}</code>
        </div>
        <div className="hero-recommendation">
          <span>{item.status === "pick" ? "分析盘口" : item.status === "watch" ? "当前结论" : "数据状态"}</span>
          <strong>{item.recommendation}</strong>
          <small>{item.status === "pick" ? "分析参考 · 非正式推荐 · 不执行自动锁单" : item.status === "watch" ? "NO_EDGE · 不强行产生推荐" : "数据不完整 · 暂不输出模型结论"}</small>
        </div>
        {item.marketMainlineLabel ? <div className="market-contract"><strong>{item.marketMainlineLabel}</strong><span>{item.executionQuoteLabel}</span><code>{item.marketPolicyLabel}</code></div> : null}
      </div>

      <div className="metric-grid">
        <div className="metric-card"><span>模型概率</span><strong>{formatPercent(item.modelProbability)}</strong></div>
        <div className="metric-card"><span>市场概率</span><strong>{formatPercent(item.marketProbability)}</strong></div>
        <div className="metric-card delta"><span>模型－市场</span><strong>{formatDelta(item.probabilityDelta)}</strong></div>
        <div className="metric-card ev"><span>模型 EV</span><strong>{formatEv(item.expectedValue)}</strong></div>
        <div className="metric-standard-error">EV 标准误 <strong>±{formatPercent(item.uncertainty)}</strong></div>
      </div>

      <ScorelineProjection item={item} />
      <MarketLadder item={item} />
      <div className="detail-sections">
        <section className="detail-section"><h3>首发变化证据</h3><ul>{item.lineupFacts.map((fact) => <li key={fact}>{fact}</li>)}</ul></section>
        <section className="detail-section"><h3>核心依据</h3><ul>{item.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></section>
        <section className="detail-section risks"><h3>风险与失效条件</h3>{item.marketPolicyLabel ? <div className="risk-breakdown"><span>数据风险 <b>{item.dataRisk}</b></span><span>盘口身份 <b>{item.marketIdentityRisk}</b></span><span>首发风险 <b>{item.lineupRisk}</b></span><span>EV 标准误 <b>±{formatPercent(item.uncertainty)}</b></span></div> : null}<ul>{item.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul></section>
        <section className="detail-section">
          <h3>下一动作</h3>
          <div className="next-action-box"><strong>{item.marketPolicyLabel ? item.nextAction : item.status === "pick" ? `${item.nextAction}重新评估` : item.nextAction}</strong><span>{item.marketPolicyLabel ? item.nextDetail : `触发条件：${item.nextDetail}。`}</span></div>
          <div className="ledger-card"><div><strong>{item.ledgerStatus}</strong><span>{item.ledgerDetail}</span></div><code>{shortHash(item.ledgerCode)}</code></div>
        </section>
      </div>
    </aside>
  );
}

function SystemDrawer({ model, open, onClose }: { model: BossConsoleModel; open: boolean; onClose: () => void }) {
  const timeSequenceAnomaly = hasTimeSequenceAnomaly(model);
  return (
    <div className={`drawer-backdrop${open ? " is-open" : ""}`} aria-hidden={!open} onClick={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <aside className="system-drawer" role="dialog" aria-modal="true" aria-label="系统状态">
        <div className="drawer-head"><div><div className="drawer-kicker">System Status</div><h2>运行与安全边界</h2></div><button className="drawer-close" onClick={onClose} aria-label="关闭系统状态">×</button></div>
        <div className="system-list">
          <div className="system-item"><span>API 版本</span><strong>{model.release.apiSha.slice(0, 7)}</strong></div>
          <div className="system-item"><span>Web 版本</span><strong>{model.release.webSha.slice(0, 7)}</strong></div>
          <div className="system-item"><span>Schema</span><strong className="pass">{model.runtime.schemaStatus}</strong></div>
          <div className="system-item"><span>API / Worker / Web</span><strong className="pass">{model.runtime.serviceStatus}</strong></div>
          <div className="system-item"><span>Provider Calls</span><strong className="off">{model.runtime.providerStatus}</strong></div>
          <div className="system-item"><span>Scheduler</span><strong className="off">{model.runtime.schedulerStatus}</strong></div>
          <div className="system-item"><span>Formal Recommendation</span><strong className="off">{model.runtime.formalStatus}</strong></div>
          <div className="system-item"><span>Lock / Production</span><strong className="off">{model.runtime.lockProductionStatus}</strong></div>
          {timeSequenceAnomaly ? <div className="system-item anomaly"><span>时间状态异常</span><code>odds={model.release.oddsConfirmedAt ?? "null"}<br />page={model.release.pageUpdatedAt}</code></div> : null}
        </div>
        <div className="drawer-warning">这是老板层的系统摘要，不展示密钥、原始 payload、内部主机信息或完整 SHA。技术审计应进入独立 L2 页面。</div>
      </aside>
    </div>
  );
}

export function BossDecisionConsoleReference({ model, fixedNow, prototypeCopy = false }: BossDecisionConsoleReferenceProps) {
  const now = useMinuteClock(fixedNow);
  const [filter, setFilter] = useState<FilterId>("priority");
  const [selectedId, setSelectedId] = useState(model.selectedDecisionId ?? model.decisions[0]?.id ?? "");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const filtered = useMemo(() => {
    if (filter === "priority") return model.decisions.filter((item) => item.status === "pick");
    if (filter === "risk") return model.decisions.filter((item) => item.riskLevel === "high" || item.status === "not-ready");
    return model.decisions;
  }, [filter, model.decisions]);
  const selected = model.decisions.find((item) => item.id === selectedId) ?? filtered[0] ?? model.decisions[0];
  const pickCount = model.decisions.filter((item) => item.status === "pick").length;
  const watchCount = model.decisions.filter((item) => item.status === "watch").length;
  const timeSequenceAnomaly = hasTimeSequenceAnomaly(model);

  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawerOpen(false); };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, []);

  function selectFilter(nextFilter: FilterId) {
    setFilter(nextFilter);
    const candidates = nextFilter === "priority"
      ? model.decisions.filter((item) => item.status === "pick")
      : nextFilter === "risk"
        ? model.decisions.filter((item) => item.riskLevel === "high" || item.status === "not-ready")
        : model.decisions;
    if (!candidates.some((item) => item.id === selectedId)) setSelectedId(candidates[0]?.id ?? model.decisions[0]?.id ?? "");
  }

  if (!selected) return null;

  return (
    <div className="app" data-ui="boss-decision-console">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">W2</div><div className="brand-copy"><strong>足球智能决策台</strong><span>老板视角 · 先看结论，再看证据</span></div><div className="mode-pill">{model.release.environment.toUpperCase()} · 只读</div></div>
        <div className="headline-kpis" aria-label="今日关键决策指标">
          <div className="headline-kpi pick"><span>分析建议</span><strong>{pickCount}</strong></div>
          <div className="headline-kpi watch"><span>继续观察</span><strong>{watchCount}</strong></div>
          <div className="headline-kpi formal"><span>正式建议</span><strong>0</strong></div>
          <div className="headline-kpi pending"><span>待结算</span><strong>{model.ledger.pendingCount}</strong></div>
          <div className="headline-kpi alert"><span>高风险赛事</span><strong>{model.riskExceptionCount}</strong></div>
        </div>
        <div className="snapshot-block"><div className="snapshot-times"><div className="snapshot-time"><span>全局最近赔率</span><strong>{dateTimeLabel(model.release.oddsConfirmedAt)}</strong></div><div className="snapshot-time"><span>页面刷新</span><strong>{dateTimeLabel(model.release.pageUpdatedAt)}</strong></div><div className="snapshot-time"><span>快照年龄</span><strong className={timeSequenceAnomaly ? "is-anomaly" : undefined}>{timeSequenceAnomaly ? "时间状态异常" : ageLabel(model.release.oddsConfirmedAt, now)}</strong></div><div className="snapshot-time"><span>自动采集</span><strong className={model.automaticCollectionPaused ? "is-paused" : "is-running"}>{model.automaticCollectionPaused ? "已暂停" : "运行中"}</strong></div></div><button className="status-button" onClick={() => setDrawerOpen(true)} aria-label="打开系统状态">⚙</button></div>
      </header>

      <section className="risk-strip" aria-label="风险与例外"><strong>风险与例外</strong><p>自动采集当前{model.automaticCollectionPaused ? "暂停" : "运行"}；高风险赛事 {model.riskExceptionCount}；首发待确认 {model.lineupPendingCount}；验证证据待补 {model.ledger.evidenceRepairPendingCount}。</p><div className="risk-meta">最后检查 {dateTimeLabel(model.lastCheckedAt)}</div></section>

      <main className="workspace">
        <section className="panel decision-panel" data-ui="decision-panel">
          <div className="panel-header"><div className="panel-title"><span>Executive Queue</span><h2>今日重点决策</h2><p>分析建议置顶；其余严格按开球时间。{prototypeCopy ? "固定数据用于视觉验收。" : "所有数值均来自当前冻结证据。"}</p></div><div className="filter-tabs" role="tablist" aria-label="决策筛选"><button className={`filter-tab${filter === "priority" ? " is-active" : ""}`} onClick={() => selectFilter("priority")}>决策优先</button><button className={`filter-tab${filter === "all" ? " is-active" : ""}`} onClick={() => selectFilter("all")}>全部赛程 {model.decisions.length}/{model.decisions.length} 场</button><button className={`filter-tab${filter === "risk" ? " is-active" : ""}`} onClick={() => selectFilter("risk")}>仅看异常</button></div></div>
          <div className="decision-table-head" aria-hidden="true"><span>序号</span><span>开球</span><span>比赛</span><span>结论与核心差异</span><span>风险状态</span><span>下一动作</span></div>
          <div className="decision-list" data-ui="schedule-scroller">{filtered.length ? filtered.map((item) => <DecisionRow key={item.id} item={item} selected={item.id === selected.id} now={now} onSelect={setSelectedId} />) : <div className="empty-list">当前筛选条件下没有比赛</div>}</div>
        </section>
        <DetailPanel item={selected} now={now} />
      </main>

      <section className="lower-grid">
        <article className="panel" data-ui="forward-validation-panel"><div className="panel-header"><div className="panel-title"><span>Forward Validation</span><h2>前向验证统一账本</h2><p>全部记录使用同一连续账目；来源信息仅保留在技术层。</p></div><div className="decision-badge watch">{model.ledger.pendingCount} 场待结算</div></div><div className="validation-body"><div className="validation-flow"><div className="flow-card"><span>验证总记录</span><strong>{model.ledger.validationCount}</strong><small>统一前向验证账本</small></div><div className="flow-card"><span>已完成结算</span><strong>{model.ledger.settledCount}</strong><small>已有真实赛果</small></div><div className="flow-card included"><span>纳入统计</span><strong>{model.ledger.eligibleCount}</strong><small>证据链完整</small></div><div className="flow-card excluded"><span>证据待补</span><strong>{model.ledger.evidenceRepairPendingCount}</strong><small>不进入命中率分母</small></div><div className="flow-card pending"><span>待结算</span><strong>{model.ledger.pendingCount}</strong><small>同一账本中的待处理状态</small></div></div><div className="ledger-summary"><div className="ledger-result"><header><strong>有效样本</strong><span>统一口径</span></header><div className="cohort-score">{model.ledger.hitCount} - {model.ledger.missCount} - {model.ledger.pushCount}<small>命中 · 未中 · 走水</small></div><div className="progress" style={{ "--value": `${(model.ledger.hitRate ?? 0) * 100}%` } as CSSProperties}><span /></div><div className="cohort-caption">有效输赢命中率 {formatPercent(model.ledger.hitRate)}（{model.ledger.hitCount}/{model.ledger.decisiveCount}）</div></div><div className="ledger-reconciliation"><strong>账目核对</strong><span>{model.ledger.validationCount} = {model.ledger.settledCount} 已结算 + {model.ledger.pendingCount} 待结算</span><span>{model.ledger.settledCount} = {model.ledger.eligibleCount} 纳入统计 + {model.ledger.evidenceRepairPendingCount} 证据待补</span><span>{model.ledger.eligibleCount} = {model.ledger.hitCount} 命中 + {model.ledger.missCount} 未中 + {model.ledger.pushCount} 走水</span></div></div></div></article>
        <article className="panel" data-ui="league-performance-panel"><div className="panel-header"><div className="panel-title"><span>League Performance</span><h2>联赛表现</h2><p>命中率、CLV 与样本量必须同时展示。</p></div></div><div className="league-table"><div className="league-row head"><span>联赛</span><span>样本</span><span>结果</span><span>临场 CLV</span><span>状态</span></div>{model.leaguePerformance.map((row) => <div className="league-row" key={row.league}><strong>{row.league}</strong><span>{row.eligibleCount}</span><span>{row.hitCount}-{row.missCount}-{row.pushCount}</span><span className={row.clvMedian == null ? undefined : row.clvMedian >= 0 ? "clv-positive" : "clv-negative"}>{row.clvMedian == null ? "暂无" : `${row.clvMedian > 0 ? "+" : ""}${row.clvMedian.toFixed(3)}`}（n={row.clvSampleCount}）</span><span className="sample-state">{row.statusLabel}</span></div>)}</div><p className="league-note">临场 CLV = 推荐赔率 − 开赛前 30 分钟内的同盘口赔率。n &lt; 5 时只作观察，不做绩效结论。</p></article>
      </section>

      <footer className="footer-note"><span><strong>产品边界：</strong>分析建议 ≠ 正式推荐；正式建议、锁单与生产发布仍保持关闭。</span><span>W2 Boss Decision Console v2.1</span></footer>
      <SystemDrawer model={model} open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
