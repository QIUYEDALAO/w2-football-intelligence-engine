import { useEffect, useState } from "react";
import { footballDayShanghai } from "../lib/formatters";
import { fetchIntelligenceWorkspace } from "../lib/intelligenceWorkspaceApi";
import type { IntelligenceWorkspace } from "../types/intelligenceWorkspace";
import { IntelligenceConsole } from "./IntelligenceConsole";

type LoadState = "loading" | "ready" | "error";

function initialQuery() {
  const query = new URLSearchParams(window.location.search);
  const date = query.get("date");
  return {
    date: date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : footballDayShanghai(),
    fixtureId: query.get("fixture_id"),
  };
}

export function DashboardPage() {
  const [query] = useState(initialQuery);
  const [date, setDate] = useState(query.date);
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
    return <main className="workspace-load-state"><strong>正在读取统一情报工作台…</strong><span>本次读取不会调用 Provider。</span></main>;
  }
  if (state === "error" || !workspace) {
    return <main className="workspace-load-state workspace-load-state--error"><strong>统一情报工作台暂不可用</strong><span>系统已安全关闭：不会回退旧 Dashboard，也不会填充合成数据。</span><button type="button" onClick={() => setRefreshKey((value) => value + 1)}>重新读取</button></main>;
  }
  return (
    <IntelligenceConsole
      date={date}
      loading={state === "loading"}
      onDateChange={setDate}
      onRefresh={() => setRefreshKey((value) => value + 1)}
      initialFixtureId={query.fixtureId}
      workspace={workspace}
    />
  );
}
