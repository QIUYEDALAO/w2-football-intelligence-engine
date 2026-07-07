import { fmtTime, formatLine, formatOdds, translateCompetition } from "../lib/formatters";
import { asRecord, textValue } from "../lib/normalize";
import type { DashboardDayView, DashboardDayViewCard, DashboardMatchCard } from "../types/dashboard";
import { RecommendationCard } from "./RecommendationCard";

const TIER_LABELS: Record<string, string> = {
  RECOMMEND: "正式可锁",
  ANALYSIS_PICK: "分析推荐",
  WATCH: "观察",
  NOT_READY: "未就绪",
  SKIP: "跳过",
};

const DATA_STATUS_LABELS: Record<string, string> = {
  READY: "数据齐",
  PARTIAL: "部分就绪",
  STALE: "数据陈旧",
  BLOCKED: "数据阻塞",
};

const REASON_LABELS: Record<string, string> = {
  LINEUPS_PENDING: "首发未出",
  MARKET_UNAVAILABLE: "盘口未齐",
  ODDS_UNAVAILABLE: "赔率未返回",
  DATA_STALE_ODDS: "赔率过期",
  PROVIDER_BUDGET_EXHAUSTED: "provider 预算耗尽",
  MARKET_INCOMPLETE: "盘口不完整",
  XG_PENDING: "xG 待刷新",
  CONTRACT_BLOCKED_BY_DATA_STATUS: "数据状态阻塞",
  NO_SUPPORTED_MARKET: "无可支持市场",
  FIXTURE_NOT_UPCOMING: "非赛前窗口",
};

const ACTION_LABELS: Record<string, string> = {
  WAIT_LINEUPS: "等首发",
  WAIT_MARKET: "等盘口",
  WAIT_ODDS: "等赔率",
  WAIT_NEXT_REFRESH: "等下一次刷新",
  REVIEW_DATA_PIPELINE: "检查数据链路",
  KEEP_WATCHING: "继续观察",
};

function tierLabel(value: string): string {
  return TIER_LABELS[value] ?? "未判定";
}

function dataStatusLabel(value: string): string {
  return DATA_STATUS_LABELS[value] ?? "数据待确认";
}

function reasonLabel(value?: string | null): string {
  if (!value) return "暂无阻塞原因";
  return REASON_LABELS[value] ?? "未就绪原因";
}

function actionLabel(value?: string | null): string {
  if (!value) return "等待下一次刷新";
  return ACTION_LABELS[value] ?? "继续观察";
}

function isWorldCup(dayView: DashboardDayView): boolean {
  return dayView.cards.some((card) => card.competition_id === "world_cup_2026" || (card.competition_name ?? "").toLowerCase().includes("world cup"));
}

function l1OneLiner(card: DashboardDayViewCard): string {
  const oneLiner = (card.one_liner ?? "").trim();
  if (oneLiner && !oneLiner.includes("缺少人话解释") && !/[A-Z0-9_]{6,}/.test(oneLiner)) {
    return oneLiner;
  }
  if (card.decision_tier === "ANALYSIS_PICK" && card.pick) {
    return `${tierLabel(card.decision_tier)}：${marketPickLabel(card)}；分析参考·非稳赢。`;
  }
  return `${reasonLabel(card.reason_code)}，${actionLabel(card.action)}。`;
}

function oddsSummary(card: DashboardDayViewCard): string | null {
  const odds = asRecord(card.current_odds);
  const ah = asRecord(odds.ah);
  const ou = asRecord(odds.ou);
  const rows: string[] = [];
  if (Object.keys(ah).length) {
    const homeLine = textValue(ah.home_display_line_cn) || signedLine("主", ah.home_line);
    const awayLine = textValue(ah.away_display_line_cn) || signedLine("客", ah.away_line);
    const homePrice = formatOdds(ah.home_price);
    const awayPrice = formatOdds(ah.away_price);
    rows.push(`让球 ${homeLine} @${homePrice} / ${awayLine} @${awayPrice}`);
  }
  if (Object.keys(ou).length) {
    const line = textValue(ou.line) || textValue(ou.over_line) || textValue(ou.under_line);
    const overPrice = formatOdds(ou.over_price);
    const underPrice = formatOdds(ou.under_price);
    rows.push(`大小 ${formatLine(line)} 大@${overPrice} / 小@${underPrice}`);
  }
  return rows.length ? rows.join(" · ") : null;
}

function trustSignalSummary(card: DashboardDayViewCard): string {
  const refresh = card.data_refresh ?? {};
  const odds = textValue(refresh.odds_status, Object.keys(asRecord(card.current_odds)).length ? "READY" : "WAITING");
  const lineups = textValue(refresh.lineups_status, textValue(asRecord(card.data_readiness).lineups_status, "UNKNOWN"));
  const xg = textValue(refresh.xg_status, textValue(asRecord(card.data_readiness).xg_status, "UNKNOWN"));
  return `盘口 ${statusCn(odds)} · 首发 ${statusCn(lineups)} · xG ${statusCn(xg)}`;
}

function signedLine(prefix: string, value: unknown): string {
  const line = formatLine(value);
  return line === "-" ? `${prefix} --` : `${prefix} ${line}`;
}

function statusCn(value: string): string {
  const status = value.toUpperCase();
  if (status === "READY") return "已就绪";
  if (status === "WAITING") return "等待";
  if (status === "PROVIDER_EMPTY") return "provider 空返";
  if (status === "INSUFFICIENT_HISTORY") return "样本不足";
  if (status === "NOT_REQUESTED") return "未请求";
  if (status === "UNKNOWN") return "未知";
  return value;
}

function marketPickLabel(card: DashboardDayViewCard): string {
  if (!card.pick) return "等待盘口";
  const market = card.pick.market ? marketLabel(card.pick.market) : "市场";
  const selection = card.pick.selection ? selectionLabel(card.pick.selection) : "方向待确认";
  const line = displayableLine(card.pick.line) ? ` ${formatLine(card.pick.line)}` : "";
  const odds = card.pick.odds != null ? ` @ ${formatOdds(card.pick.odds)}` : "";
  return `${market} ${selection}${line}${odds}`.trim();
}

function displayableLine(value: string | number | null | undefined): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value !== "string") return false;
  return /^[-+]?\d+(?:\.\d+)?$/.test(value.trim());
}

function marketLabel(value: string): string {
  if (value === "ASIAN_HANDICAP") return "让球";
  if (value === "TOTALS") return "大小球";
  if (value === "ONE_X_TWO") return "胜平负";
  return "市场";
}

function selectionLabel(value: string): string {
  if (value === "HOME") return "主队";
  if (value === "AWAY") return "客队";
  if (value === "OVER") return "大";
  if (value === "UNDER") return "小";
  if (value === "DRAW") return "平";
  return "方向";
}

function teamLabel(card: DashboardDayViewCard): string {
  const home = card.home_team_name || "主队";
  const away = card.away_team_name || "客队";
  return `${home} vs ${away}`;
}

function competitionLabel(card: DashboardDayViewCard): string {
  return translateCompetition(card.competition_name || card.competition_id || "比赛");
}

function byFixtureId(matches: DashboardMatchCard[]): Map<string, DashboardMatchCard> {
  return new Map(matches.map((match) => [String(match.fixture_id), match]));
}

function orderedCards(cards: DashboardDayViewCard[]): DashboardDayViewCard[] {
  const tierRank: Record<string, number> = {
    RECOMMEND: 0,
    ANALYSIS_PICK: 1,
    WATCH: 2,
    NOT_READY: 3,
    SKIP: 4,
  };
  return [...cards].sort((left, right) => {
    const leftLock = left.lock_eligible ? 0 : 1;
    const rightLock = right.lock_eligible ? 0 : 1;
    if (leftLock !== rightLock) return leftLock - rightLock;
    const leftTier = tierRank[left.decision_tier] ?? 99;
    const rightTier = tierRank[right.decision_tier] ?? 99;
    if (leftTier !== rightTier) return leftTier - rightTier;
    return (left.kickoff_utc ?? "").localeCompare(right.kickoff_utc ?? "");
  });
}

function reasonSummary(cards: DashboardDayViewCard[]): Array<{ label: string; count: number }> {
  const counter = new Map<string, number>();
  for (const card of cards) {
    const label = reasonLabel(card.reason_code);
    if (label === "暂无阻塞原因") continue;
    counter.set(label, (counter.get(label) ?? 0) + 1);
  }
  return [...counter.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label));
}

function diagnosticRows(card: DashboardDayViewCard): Array<[string, string]> {
  const diagnostics = asRecord(card.diagnostics);
  const readiness = asRecord(diagnostics.data_readiness_summary);
  const missingFields = card.missing_fields ?? [];
  const staleFields = card.stale_fields ?? [];
  return [
    ["decision", tierLabel(card.decision_tier)],
    ["data", dataStatusLabel(card.data_status)],
    ["reason", reasonLabel(card.reason_code)],
    ["action", actionLabel(card.action)],
    ["next_eval_at", textValue(card.next_eval_at, "-")],
    ["card_hash", textValue(card.card_hash, "-").slice(0, 16)],
    ["missing", missingFields.join(", ") || "-"],
    ["stale", staleFields.join(", ") || "-"],
    ["readiness", textValue(readiness.data_status, "-")],
  ];
}

export function MatchdayHeader({ dayView, updatedAt }: { dayView: DashboardDayView; updatedAt: string }) {
  const worldCup = isWorldCup(dayView);
  return (
    <header className="boss-header">
      <div>
        <p className="boss-eyebrow">W2 Matchday · {dayView.environment}</p>
        <h1>{dayView.football_day} 老板视角</h1>
        <span>
          上次刷新 {dayView.freshness.last_refresh ? fmtTime(dayView.freshness.last_refresh) : "--:--"} · 下次刷新{" "}
          {dayView.freshness.next_refresh_tick ? fmtTime(dayView.freshness.next_refresh_tick) : "待定"} · 页面更新 {updatedAt}
        </span>
      </div>
      <strong>{worldCup ? "世界杯 live 证据" : "DecisionCard 首屏"}</strong>
    </header>
  );
}

export function DecisionCounts({ dayView }: { dayView: DashboardDayView }) {
  const lockLabel = dayView.environment === "production" ? "正式可锁" : "可锁审批";
  const metrics = [
    [lockLabel, dayView.counts.lock_eligible, "审批候选由 DecisionCard 给出"],
    ["分析推荐", dayView.counts.analysis_pick + dayView.counts.recommend, "分析参考·非稳赢"],
    ["观察", dayView.counts.watch, "数据够看但不出方向"],
    ["未就绪·不判", dayView.counts.not_ready + dayView.counts.skip, "给原因，不硬推"],
  ] as const;
  return (
    <section className="decision-counts" aria-label="今日决策计数">
      {metrics.map(([label, value, hint]) => (
        <div className="decision-count" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{hint}</small>
        </div>
      ))}
    </section>
  );
}

export function ReasonCodePanel({ cards }: { cards: DashboardDayViewCard[] }) {
  const reasons = reasonSummary(cards);
  if (!reasons.length) {
    const partialCount = cards.filter((card) => card.data_status === "PARTIAL").length;
    if (partialCount) {
      return (
        <section className="reason-panel">
          <span>主要原因</span>
          <strong>部分数据仍在刷新 × {partialCount}</strong>
        </section>
      );
    }
    return (
      <section className="reason-panel">
        <span>主要原因</span>
        <strong>暂无阻塞原因</strong>
      </section>
    );
  }
  return (
    <section className="reason-panel" aria-label="未出原因统计">
      <span>主要原因</span>
      <div>
        {reasons.slice(0, 6).map((reason) => (
          <strong key={reason.label}>{reason.label} × {reason.count}</strong>
        ))}
      </div>
    </section>
  );
}

export function DecisionRow({
  card,
  legacyMatch,
}: {
  card: DashboardDayViewCard;
  legacyMatch?: DashboardMatchCard;
}) {
  const tierClass = `tier-${card.decision_tier.toLowerCase().replace("_", "-")}`;
  return (
    <article className={`decision-row ${tierClass}`}>
      <div className="decision-row-main">
        <div className="decision-fixture">
          <span>{fmtTime(card.kickoff_utc)} · {competitionLabel(card)}</span>
          <strong>{teamLabel(card)}</strong>
        </div>
        <div className="decision-copy">
          <p>{l1OneLiner(card)}</p>
          {oddsSummary(card) ? <span>{oddsSummary(card)}</span> : null}
        </div>
      </div>
      <div className="decision-row-side">
        <span className={`tier-badge ${tierClass}`}>{tierLabel(card.decision_tier)}</span>
        <small>{dataStatusLabel(card.data_status)}</small>
        <small>{trustSignalSummary(card)}</small>
        {card.lock_eligible ? <em>{card.decision_tier === "RECOMMEND" ? "正式可锁" : "staging-only · 需要审批"}</em> : null}
      </div>
      <details className="l2-diagnostics-drawer">
        <summary>L2 技术诊断</summary>
        <div className="l2-diagnostics-body">
          {legacyMatch ? <RecommendationCard match={legacyMatch} /> : null}
          <dl className="l2-diagnostics-grid">
            {diagnosticRows(card).map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </details>
    </article>
  );
}

export function BossDecisionView({
  dayView,
  legacyMatches,
  updatedAt,
}: {
  dayView: DashboardDayView;
  legacyMatches: DashboardMatchCard[];
  updatedAt: string;
}) {
  const legacyById = byFixtureId(legacyMatches);
  const cards = orderedCards(dayView.cards);
  return (
    <section className="boss-dashboard" aria-label="老板视角决策页">
      <MatchdayHeader dayView={dayView} updatedAt={updatedAt} />
      {isWorldCup(dayView) ? (
        <aside className="model-caveat">
          世界杯输出按 staging 保守展示：当前拟合模型在五大俱乐部离线验证，尚未对国际赛完成独立验证。
        </aside>
      ) : null}
      <DecisionCounts dayView={dayView} />
      <ReasonCodePanel cards={cards} />
      <section className="decision-list" aria-label="今日比赛判断">
        {cards.length ? (
          cards.map((card) => (
            <DecisionRow key={card.fixture_id} card={card} legacyMatch={legacyById.get(card.fixture_id)} />
          ))
        ) : (
          <div className="decision-empty">今日暂无比赛；数据不足时保持空白，不强出推荐。</div>
        )}
      </section>
      <footer className="boss-disclaimer">分析参考·非稳赢·不构成投注建议</footer>
    </section>
  );
}
