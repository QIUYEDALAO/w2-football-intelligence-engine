import { COMPETITION_TRANSLATIONS, REASON_TRANSLATIONS, TEAM_TRANSLATIONS } from "./labels";

export function todayShanghai(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
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

export function translateReason(reason: unknown): string {
  const raw = typeof reason === "string" && reason ? reason : "数据不足时保持 SKIP";
  for (const [pattern, translated] of REASON_TRANSLATIONS) {
    if (pattern.test(raw)) {
      return translated;
    }
  }
  return raw.replace(/_/g, " ").replace(/:/g, "：");
}

export function translateCompetition(value: unknown): string {
  let text = typeof value === "string" && value ? value : "世界杯";
  for (const [pattern, translated] of COMPETITION_TRANSLATIONS) {
    text = text.replace(pattern, translated);
  }
  return text;
}
