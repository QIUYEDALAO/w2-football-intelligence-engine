import {
  CANONICAL_COMPETITION_LABELS,
  COMPETITION_NAME_LABELS,
  COMPETITION_STAGE_TRANSLATIONS,
  REASON_TRANSLATIONS,
} from "./labels";

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

export function translateCompetition(value: unknown, competitionId?: unknown): string {
  let text = typeof value === "string" && value ? value : "世界杯";
  const canonical = typeof competitionId === "string"
    ? CANONICAL_COMPETITION_LABELS[competitionId]
    : undefined;
  const separator = text.indexOf(" · ");
  const name = separator >= 0 ? text.slice(0, separator) : text;
  const translated = canonical ?? COMPETITION_NAME_LABELS[name];
  if (translated) {
    text = `${translated}${separator >= 0 ? text.slice(separator) : ""}`;
  }
  for (const [pattern, stage] of COMPETITION_STAGE_TRANSLATIONS) {
    text = text.replace(pattern, stage);
  }
  return text;
}
