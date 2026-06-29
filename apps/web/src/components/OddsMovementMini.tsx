import type { DashboardMatchCard } from "../types/dashboard";
import { formatAhDelta, formatSignedLine } from "../lib/pricingDisplay";

const PATTERN_LABELS: Record<string, string> = {
  STABLE: "稳定",
  ONE_WAY: "单边",
  EARLY_DROP_LATE_REBOUND: "早动后回补",
  JUMP_LINE: "跳线",
  INSUFFICIENT: "轨迹不足",
};

const DIRECTION_LABELS: Record<string, string> = {
  HOME_DEEPENED: "主队侧加深",
  AWAY_DEEPENED: "客队侧加深",
  TOWARD_HOME: "向主队侧",
  TOWARD_AWAY: "向客队侧",
  STABLE: "稳定",
  UNKNOWN: "方向未知",
};

const CHECKPOINT_LABELS: Record<string, string> = {
  opening: "初盘",
  open: "初盘",
  "T-24h": "赛前24小时",
  "T-12h": "赛前12小时",
  "T-6h": "赛前6小时",
  "T-3h": "赛前3小时",
  "T-1h": "赛前1小时",
  lock: "锁盘",
};

function checkpointLabel(value: string): string {
  return CHECKPOINT_LABELS[value] ?? value;
}

function readableHypothesis(value: string): string {
  return value
    .replace(/value\s*gap/gi, "盘口差")
    .replace(/\bvalue\b/gi, "盘口价值")
    .replace(/\bedge\b/gi, "盘口差")
    .replace(/\bdevig\b/gi, "去水")
    .replace(/\bmarket\b/gi, "市场")
    .replace(/\bopening\b/gi, "初盘")
    .replace(/\bopen\b/gi, "初盘")
    .replace(/\block\b/gi, "锁盘");
}

function movementLine(match: DashboardMatchCard): string {
  const movement = match.market_movement;
  if (!movement || movement.status === "INSUFFICIENT") return "盘口走势：轨迹不足 / 观察中";
  const pattern = PATTERN_LABELS[String(movement.pattern ?? "")] ?? "观察中";
  const direction = DIRECTION_LABELS[String(movement.line_move_direction ?? "UNKNOWN")] ?? "方向未知";
  const magnitude = formatAhDelta(movement.line_move_magnitude);
  const checkpoints = movement.checkpoints_seen?.length
    ? ` · ${movement.checkpoints_seen.map(checkpointLabel).join("/")}`
    : "";
  return `盘口走势：${pattern} · ${direction}${magnitude ? ` ${magnitude}` : ""}${checkpoints}`;
}

function divergenceLine(match: DashboardMatchCard): string {
  const divergence = match.market_divergence;
  if (!divergence || divergence.status === "INSUFFICIENT") return "背离：样本不足，未校准，仅作观察";
  const open = divergence.open_divergence == null ? null : formatSignedLine(divergence.open_divergence);
  const lock = divergence.lock_divergence == null ? null : formatSignedLine(divergence.lock_divergence);
  const pieces = [open ? `初盘 ${open}` : null, lock ? `锁盘 ${lock}` : null].filter(Boolean);
  return `背离：${pieces.length ? pieces.join(" / ") : "未形成差值"} · 未校准，仅作观察`;
}

export function OddsMovementMini({ match }: { match: DashboardMatchCard }) {
  const hypothesis = match.bookmaker_hypothesis;
  const label = hypothesis?.label ?? "盘口假设 · 未验证";
  const text = readableHypothesis(hypothesis?.hypothesis ?? "盘口轨迹不足，暂不形成假设；仅作观察，不给方向。");
  const alternatives = hypothesis?.alternative_explanations?.length
    ? `替代解释：${hypothesis.alternative_explanations.join("、")}`
    : "替代解释：伤停或阵容信息、公众热度、盘口保护、我们的规则盘未校准";
  return (
    <div className="odds-movement">
      <span aria-hidden="true">↗</span>
      <strong>{label}</strong>
      <span>{movementLine(match)}</span>
      <span>{divergenceLine(match)}</span>
      <span>{text}</span>
      <span>{alternatives}</span>
      <span>样本状态：{hypothesis?.sample_status ?? "观察中"}；赛后样本不足时不展示统计。</span>
    </div>
  );
}
