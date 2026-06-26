import type { SettlementStatus } from "../types/dashboard";

const LABELS: Record<SettlementStatus, string> = {
  PENDING: "待验证",
  HIT: "已验证 · 命中",
  MISS: "已验证 · 未中",
  PUSH: "走水",
  VOID: "无效",
  NO_BET: "无推荐",
  UNKNOWN: "待确认",
};

export function SettlementBadge({ status }: { status: SettlementStatus }) {
  return <span className={`settlement-badge is-${status.toLowerCase().replace("_", "-")}`}>{LABELS[status]}</span>;
}
