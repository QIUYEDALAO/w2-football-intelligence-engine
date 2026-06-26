export type MatchPhase = "FINISHED" | "LIVE" | "T_MINUS_30" | "T_MINUS_60" | "T_MINUS_180" | "TODAY" | "FUTURE" | "UNKNOWN";

const LIVE_STATUSES = new Set(["LIVE", "1H", "HT", "2H", "ET", "P", "SUSP", "INT"]);
const FINISHED_STATUSES = new Set(["FINISHED", "FT", "AET", "PEN"]);

export function minutesToKickoff(kickoffUtc: string): number | null {
  if (!kickoffUtc) return null;
  const kickoffMs = Date.parse(kickoffUtc);
  if (!Number.isFinite(kickoffMs)) return null;
  return Math.round((kickoffMs - Date.now()) / 60000);
}

export function matchPhase(kickoffUtc: string, status?: string): MatchPhase {
  const normalizedStatus = (status ?? "").toUpperCase();
  if (FINISHED_STATUSES.has(normalizedStatus)) return "FINISHED";
  if (LIVE_STATUSES.has(normalizedStatus)) return "LIVE";
  const minutes = minutesToKickoff(kickoffUtc);
  if (minutes === null) return "UNKNOWN";
  if (minutes <= -1) return "LIVE";
  if (minutes <= 30) return "T_MINUS_30";
  if (minutes <= 60) return "T_MINUS_60";
  if (minutes <= 180) return "T_MINUS_180";
  if (minutes <= 24 * 60) return "TODAY";
  return "FUTURE";
}

export function phaseLabel(phase: MatchPhase, minutes?: number | null): string {
  if (phase === "FINISHED") return "已完场";
  if (phase === "LIVE") return "比赛进行中";
  if (phase === "T_MINUS_30") return minutes !== null && minutes !== undefined ? `${Math.max(minutes, 0)} 分钟后开赛` : "临近开赛";
  if (phase === "T_MINUS_60") return minutes !== null && minutes !== undefined ? `${minutes} 分钟后开赛` : "60 分钟内开赛";
  if (phase === "T_MINUS_180") return "3 小时内开赛";
  if (phase === "TODAY") return "今日比赛";
  if (phase === "FUTURE") return "未来赛程";
  return "时间待确认";
}

export function requiresPrematchReview(phase: MatchPhase): boolean {
  return phase === "T_MINUS_30" || phase === "T_MINUS_60";
}
