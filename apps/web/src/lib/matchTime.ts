import { fmtTime } from "./formatters";

export interface MatchTimeInput {
  kickoff_utc?: string | null;
  status?: string | null;
}

const SHANGHAI_DATE = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const SHANGHAI_WEEKDAY = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  weekday: "short",
});
const SHANGHAI_MONTH_DAY = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
});

export function shanghaiDateKey(value?: string | Date | null): string | null {
  if (!value) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : SHANGHAI_DATE.format(parsed);
}

export function dateGroupLabel(value?: string | null): string {
  if (!value) return "日期待定";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "日期待定";
  return `${SHANGHAI_MONTH_DAY.format(parsed).replace("/", "-")} ${SHANGHAI_WEEKDAY.format(parsed)}`;
}

export function isSameShanghaiDate(
  left?: string | null,
  right?: string | null,
): boolean {
  const leftKey = shanghaiDateKey(left);
  const rightKey = shanghaiDateKey(right);
  return leftKey !== null && leftKey === rightKey;
}

export function minutesUntil(card: MatchTimeInput, now: Date): number | null {
  if (!card.kickoff_utc) return null;
  const kickoff = new Date(card.kickoff_utc);
  if (Number.isNaN(kickoff.getTime())) return null;
  return Math.round((kickoff.getTime() - now.getTime()) / 60000);
}

function countdownLabel(card: MatchTimeInput, now: Date): string {
  const minutes = minutesUntil(card, now);
  if (minutes == null) return "时间待定";
  if (minutes < 0) return `已开赛 ${Math.abs(minutes)} 分钟`;
  if (minutes < 60) return `还有 ${minutes} 分钟`;
  if (minutes < 1440) {
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    return `还有 ${hours} 小时${remainder ? `${remainder} 分` : ""}`;
  }
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return `还有 ${days} 天${hours ? ` ${hours} 小时` : ""}`;
}

export function kickoffPresentation(
  card: MatchTimeInput,
  now: Date,
): { primary: string; secondary: string; relative?: string } {
  const raw = card.kickoff_utc;
  const kickoff = raw ? new Date(raw) : null;
  if (!kickoff || Number.isNaN(kickoff.getTime())) {
    return { primary: "时间待定", secondary: "无有效时间" };
  }
  const status = (card.status ?? "").toUpperCase();
  const absolute = `${SHANGHAI_MONTH_DAY.format(kickoff).replace("/", "-")} ${fmtTime(raw)}`;
  if (["FT", "AET", "PEN", "FINISHED"].includes(status)) {
    return { primary: "完场", secondary: absolute };
  }
  if (["LIVE", "1H", "2H", "HT", "ET", "BT", "P"].includes(status)) {
    const elapsed = Math.max(0, Math.abs(minutesUntil(card, now) ?? 0));
    return { primary: `进行中 ${elapsed}′`, secondary: absolute };
  }
  const minutes = minutesUntil(card, now);
  if (minutes == null) return { primary: "时间待定", secondary: "无有效时间" };
  const today = shanghaiDateKey(now);
  const tomorrow = shanghaiDateKey(new Date(now.getTime() + 86_400_000));
  const kickoffDay = shanghaiDateKey(kickoff);
  if (kickoffDay === today) {
    return {
      primary: `今天 ${fmtTime(raw)}`,
      secondary: minutes < 60 ? `还有 ${Math.max(minutes, 0)} 分钟` : countdownLabel(card, now),
    };
  }
  if (kickoffDay === tomorrow) {
    return { primary: `明天 ${fmtTime(raw)}`, secondary: dateGroupLabel(raw) };
  }
  return {
    primary: dateGroupLabel(raw),
    secondary: fmtTime(raw),
    relative: minutes > 0 ? `${Math.max(1, Math.floor(minutes / 1440))}天后` : undefined,
  };
}
