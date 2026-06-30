import { COMPETITION_TRANSLATIONS, REASON_TRANSLATIONS, TEAM_TRANSLATIONS } from "./labels";

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function trimTrailingZeros(value: string): string {
  return value.replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
}

export function formatOdds(value: unknown): string {
  const numeric = numericValue(value);
  if (numeric == null) {
    return typeof value === "string" && value.trim() ? value.trim() : "-";
  }
  return numeric.toFixed(2);
}

export function formatLine(value: unknown): string {
  const numeric = numericValue(value);
  if (numeric == null) {
    return typeof value === "string" && value.trim() ? value.trim() : "-";
  }
  if (Math.abs(numeric) < 0.005) {
    return "0";
  }
  return trimTrailingZeros(numeric.toFixed(2));
}

export function todayShanghai(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function footballDayShanghai(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  }).formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  const localDate = `${value("year")}-${value("month")}-${value("day")}`;
  const rawHour = Number(value("hour"));
  const hour = rawHour === 24 ? 0 : rawHour;
  if (Number.isFinite(hour) && hour < 12) {
    const utcNoon = new Date(`${localDate}T12:00:00+08:00`);
    utcNoon.setUTCDate(utcNoon.getUTCDate() - 1);
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(utcNoon);
  }
  return localDate;
}

export function fmtTime(iso?: unknown): string {
  const raw = typeof iso === "string" && iso ? iso : "";
  if (!raw) {
    return "--:--";
  }
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(raw));
  } catch {
    return "--:--";
  }
}

export function teamCode(name: string): string {
  const cleaned = name.replace(/[^A-Za-z]/g, "").toUpperCase();
  if (cleaned.length >= 3) {
    return cleaned.slice(0, 3);
  }
  return name.slice(0, 2).toUpperCase();
}

export function translateTeam(value: unknown): string {
  const raw = typeof value === "string" && value ? value : "球队";
  return TEAM_TRANSLATIONS[raw] ?? raw;
}

export function confidenceLabel(value: unknown): string {
  const numeric = typeof value === "number" && Number.isFinite(value) ? value : 0;
  const percent = numeric > 1 ? Math.round(numeric) : Math.round(numeric * 100);
  if (percent <= 0) {
    return "未成形";
  }
  return `${Math.min(percent, 100)}%`;
}

function translateReasonSegment(segment: string): string {
  const s = segment.trim();
  if (!s) {
    return "";
  }
  for (const [pattern, translated] of REASON_TRANSLATIONS) {
    if (pattern.test(s)) {
      return translated;
    }
  }
  return s.replace(/_/g, " ").replace(/:/g, "：");
}

export function translateReason(reason: unknown): string {
  const raw = typeof reason === "string" && reason ? reason : "数据不足时保持 SKIP";
  const segments = raw
    .split(/\s*\+\s*/)
    .map(translateReasonSegment)
    .filter(Boolean);
  const unique = Array.from(new Set(segments));
  return unique.length ? unique.join(" · ") : raw.replace(/_/g, " ").replace(/:/g, "：");
}

export function translateCompetition(value: unknown): string {
  let text = typeof value === "string" && value ? value : "世界杯";
  for (const [pattern, translated] of COMPETITION_TRANSLATIONS) {
    text = text.replace(pattern, translated);
  }
  return text;
}
