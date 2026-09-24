import type {
  IntelligenceReplayResponse,
  IntelligenceValidationResponse,
  IntelligenceCalibratedValidationResponse,
  IntelligenceWorkspaceList,
  WorkspaceMatch,
} from "../types/intelligenceWorkspace";
import { API_BASE } from "./labels";

export async function fetchIntelligenceWorkspace(
  date: string,
  signal?: AbortSignal,
): Promise<IntelligenceWorkspaceList> {
  const query = new URLSearchParams({
    date,
    window: "today",
    timezone: "Asia/Shanghai",
  });
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace/list?${query.toString()}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw new Error(`intelligence-workspace -> HTTP ${response.status}`);
  }
  return response.json() as Promise<IntelligenceWorkspaceList>;
}

export async function fetchIntelligenceValidation(
  date: string,
  signal?: AbortSignal,
  options: { days?: number; limit?: number; offset?: number } = {},
): Promise<IntelligenceValidationResponse> {
  const query = new URLSearchParams({ window: "today", timezone: "Asia/Shanghai" });
  if (options.days !== undefined) {
    query.set("date", date);
    query.set("days", String(options.days));
  }
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset !== undefined) query.set("offset", String(options.offset));
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace/validation?${query.toString()}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) throw new Error(`intelligence-workspace validation -> HTTP ${response.status}`);
  return response.json() as Promise<IntelligenceValidationResponse>;
}

export async function fetchIntelligenceCalibratedValidation(
  date: string,
  signal?: AbortSignal,
  options: { days?: number; limit?: number; offset?: number } = {},
): Promise<IntelligenceCalibratedValidationResponse> {
  const query = new URLSearchParams({ window: "today", timezone: "Asia/Shanghai" });
  if (options.days !== undefined) {
    query.set("date", date);
    query.set("days", String(options.days));
  }
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset !== undefined) query.set("offset", String(options.offset));
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace/validation-calibrated?${query.toString()}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) throw new Error(`intelligence-workspace calibrated validation -> HTTP ${response.status}`);
  return response.json() as Promise<IntelligenceCalibratedValidationResponse>;
}

export async function fetchIntelligenceReplay(
  date: string,
  signal?: AbortSignal,
): Promise<IntelligenceReplayResponse> {
  const query = new URLSearchParams({ date, window: "today", timezone: "Asia/Shanghai" });
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace/replay?${query.toString()}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) throw new Error(`intelligence-workspace replay -> HTTP ${response.status}`);
  return response.json() as Promise<IntelligenceReplayResponse>;
}

export async function fetchIntelligenceMatch(
  fixtureId: string,
  signal?: AbortSignal,
): Promise<WorkspaceMatch> {
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace/matches/${encodeURIComponent(fixtureId)}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw new Error(`intelligence-workspace match -> HTTP ${response.status}`);
  }
  return response.json() as Promise<WorkspaceMatch>;
}
