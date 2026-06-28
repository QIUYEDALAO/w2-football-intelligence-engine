import { formatLine } from "./formatters";
import type { PricingShadow } from "../types/dashboard";

export type ScoreLeader = "HOME" | "AWAY" | "NEUTRAL" | "UNKNOWN";

function numericValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function formatSignedLine(value: unknown): string {
  const numeric = numericValue(value);
  if (numeric == null) return typeof value === "string" && value.trim() ? value.trim() : "-";
  if (Math.abs(numeric) < 0.005) return "0";
  return `${numeric > 0 ? "+" : ""}${formatLine(numeric)}`;
}

export function formatAhMainLine(value: unknown): string | null {
  const numeric = numericValue(value);
  if (numeric == null) return null;
  if (Math.abs(numeric) < 0.005) return "平手";
  const abs = formatLine(Math.abs(numeric));
  return numeric < 0 ? `主 -${abs}` : `客 -${abs}`;
}

export function formatAhSideLines(homeLine: unknown): { home: string; away: string } | null {
  const numeric = numericValue(homeLine);
  if (numeric == null) return null;
  return {
    home: `主 ${formatSignedLine(numeric)}`,
    away: `客 ${formatSignedLine(-numeric)}`,
  };
}

export function formatAhDelta(value: unknown): string | null {
  const numeric = numericValue(value);
  if (numeric == null) return null;
  return formatLine(Math.abs(numeric));
}

export function hasValidatedAhCalibration(shadow: PricingShadow | null | undefined): boolean {
  if (!shadow) return false;
  if (shadow.simulation_status === "READY") return true;
  const version = String(shadow.calibration_version ?? "").trim().toUpperCase();
  if (!version) return false;
  return !["UNVALIDATED", "UNCALIBRATED", "RULE_BASED_UNCALIBRATED", "SHADOW", "SHADOW_ONLY"].includes(version);
}

export function teamScoreLeader(shadow: PricingShadow | null | undefined): ScoreLeader {
  const home = numericValue(shadow?.team_score?.home);
  const away = numericValue(shadow?.team_score?.away);
  if (home == null || away == null) return "UNKNOWN";
  const diff = home - away;
  if (Math.abs(diff) < 0.05) return "NEUTRAL";
  return diff > 0 ? "HOME" : "AWAY";
}

export function unvalidatedAhLean(shadow: PricingShadow | null | undefined): ScoreLeader {
  const fair = numericValue(shadow?.fair_ah);
  const market = numericValue(shadow?.market_ah);
  if (fair == null || market == null) return "UNKNOWN";
  const diff = market - fair;
  if (Math.abs(diff) < 0.25) return "NEUTRAL";
  return diff > 0 ? "HOME" : "AWAY";
}

export function hasFactorLeanConflict(shadow: PricingShadow | null | undefined): boolean {
  const leader = teamScoreLeader(shadow);
  const lean = unvalidatedAhLean(shadow);
  return (leader === "HOME" || leader === "AWAY") && (lean === "HOME" || lean === "AWAY") && leader !== lean;
}
