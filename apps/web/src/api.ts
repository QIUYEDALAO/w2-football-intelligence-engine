import type { Fixture, LoadStatus, Matchday, Resource } from "./types";

const staleMs = 15 * 60 * 1000;

export function emptyResource<T>(endpoint: string): Resource<T> {
  return {
    status: "LOADING",
    endpoint,
    data: null,
    requestId: null,
    errorCode: null,
    message: null,
  };
}

function isEmptyPayload(payload: unknown): boolean {
  if (payload === null || payload === undefined) {
    return true;
  }
  if (Array.isArray(payload)) {
    return payload.length === 0;
  }
  if (typeof payload === "object") {
    const maybeItems = (payload as { items?: unknown }).items;
    return Array.isArray(maybeItems) && maybeItems.length === 0;
  }
  return false;
}

function isStale(payload: unknown): boolean {
  const typed = payload as { generated_at?: string; as_of_time?: string; updated_at?: string };
  const maybeTime = typed?.generated_at ?? typed?.as_of_time ?? typed?.updated_at;
  if (!maybeTime) {
    return false;
  }
  const timestamp = Date.parse(maybeTime);
  return Number.isFinite(timestamp) && Date.now() - timestamp > staleMs;
}

export async function loadJson<T>(endpoint: string): Promise<Resource<T>> {
  const requestId = crypto.randomUUID();
  try {
    const response = await fetch(endpoint, {
      headers: { Accept: "application/json", "X-Request-ID": requestId },
    });
    const text = await response.text();
    const payload = text
      ? (JSON.parse(text) as T & { request_id?: string; code?: string; message?: string })
      : null;
    if (!response.ok) {
      return {
        status: "ERROR",
        endpoint,
        data: null,
        requestId: payload?.request_id ?? requestId,
        errorCode: payload?.code ?? String(response.status),
        message: payload?.message ?? response.statusText,
      };
    }
    return {
      status: isEmptyPayload(payload) ? "EMPTY" : isStale(payload) ? "STALE" : "SUCCESS",
      endpoint,
      data: payload as T,
      requestId: payload?.request_id ?? requestId,
      errorCode: null,
      message: null,
    };
  } catch (error) {
    return {
      status: "ERROR",
      endpoint,
      data: null,
      requestId,
      errorCode: error instanceof SyntaxError ? "JSON_PARSE_ERROR" : "FETCH_FAILED",
      message: error instanceof Error ? error.message : "Request failed",
    };
  }
}

export function beijingToday(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function matchdayFixture(item: Record<string, unknown>): Fixture {
  return {
    fixture_id: String(item.fixture_id),
    competition_id: String(item.competition_id),
    competition_name: String(item.competition_name),
    kickoff_utc: String(item.kickoff_utc),
    kickoff_beijing: item.kickoff_beijing ? String(item.kickoff_beijing) : null,
    operational_date_beijing: item.operational_date_beijing
      ? String(item.operational_date_beijing)
      : null,
    kickoff_display: String(item.kickoff_beijing ?? item.kickoff_utc),
    status: String(item.status),
    home_team_id: String(item.home_team_id),
    home_team_name: item.home_team_name ? String(item.home_team_name) : null,
    away_team_id: String(item.away_team_id),
    away_team_name: item.away_team_name ? String(item.away_team_name) : null,
    lifecycle_state: String(item.action ?? item.lifecycle_state ?? "SKIP"),
    data_state: String(item.data_health ?? item.data_state ?? "CAPTURED_AT"),
    published_grade: item.published_grade ? String(item.published_grade) : null,
    primary_market: item.primary_market ? String(item.primary_market) : null,
    primary_line: item.primary_line ? String(item.primary_line) : null,
    primary_odds: item.primary_odds ? String(item.primary_odds) : null,
    last_captured: item.last_captured ? String(item.last_captured) : null,
  };
}

export function resourceTone(status: LoadStatus): string {
  return status.toLowerCase();
}

export function fixtureListFromMatchday(payload: Resource<Matchday>): Resource<{ items: Fixture[] }> {
  return {
    ...payload,
    data: payload.data ? { items: payload.data.items.map(matchdayFixture) } : null,
  };
}
