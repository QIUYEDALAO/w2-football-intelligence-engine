import { API_BASE } from "./labels";
import type {
  PerformancePayload,
  PerformanceTier,
  PerformanceWindow,
} from "../types/performance";

export async function fetchPerformance(
  window: PerformanceWindow,
  tier: PerformanceTier,
): Promise<PerformancePayload> {
  const query = new URLSearchParams({ window, tier });
  const response = await fetch(`${API_BASE}/performance?${query}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`performance -> HTTP ${response.status}`);
  }
  return response.json() as Promise<PerformancePayload>;
}
