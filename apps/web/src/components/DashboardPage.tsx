import { useEffect, useState } from "react";
import { footballDayShanghai } from "../lib/formatters";
import { fetchIntelligenceWorkspace } from "../lib/intelligenceWorkspaceApi";
import type { IntelligenceWorkspace } from "../types/intelligenceWorkspace";
import { IntelligenceConsole } from "./IntelligenceConsole";

type LoadState = "loading" | "ready" | "error";

export function DashboardPage() {
  const [date, setDate] = useState(footballDayShanghai());
  const [workspace, setWorkspace] = useState<IntelligenceWorkspace | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    fetchIntelligenceWorkspace(date, controller.signal)
      .then((payload) => {
        setWorkspace(payload);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setState("error");
      });
    return () => controller.abort();
  }, [date, refreshKey]);

  if (state === "loading" && !workspace) {
    return <main className="workspace-load-state"><strong>Loading unified intelligence workspace…</strong><span>No provider calls are made by this read.</span></main>;
  }
  if (state === "error" || !workspace) {
    return <main className="workspace-load-state workspace-load-state--error"><strong>Unified workspace unavailable</strong><span>Fail-closed: no legacy dashboard or synthetic data will be substituted.</span><button type="button" onClick={() => setRefreshKey((value) => value + 1)}>Retry read</button></main>;
  }
  return (
    <IntelligenceConsole
      date={date}
      loading={state === "loading"}
      onDateChange={setDate}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      workspace={workspace}
    />
  );
}
