import type { IntelligenceWorkspace, WorkspaceMatch } from "../types/intelligenceWorkspace";
import { API_BASE } from "./labels";

export async function fetchIntelligenceWorkspace(
  date: string,
  signal?: AbortSignal,
): Promise<IntelligenceWorkspace> {
  const query = new URLSearchParams({
    date,
    window: "today",
    timezone: "Asia/Shanghai",
    projection: "full",
  });
  const response = await fetch(
    `${API_BASE}/dashboard/intelligence-workspace?${query.toString()}`,
    { headers: { Accept: "application/json" }, signal },
  );
  if (!response.ok) {
    throw new Error(`intelligence-workspace -> HTTP ${response.status}`);
  }
  return response.json() as Promise<IntelligenceWorkspace>;
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
