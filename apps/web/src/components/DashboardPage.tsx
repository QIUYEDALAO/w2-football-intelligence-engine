import { useEffect, useState } from "react";
import { footballDayShanghai } from "../lib/formatters";
import { fetchIntelligenceWorkspace } from "../lib/intelligenceWorkspaceApi";
import type { IntelligenceWorkspaceList } from "../types/intelligenceWorkspace";
import { IntelligenceConsole } from "./IntelligenceConsole";

type LoadState = "loading" | "ready" | "error";

function initialQuery() {
  const query = new URLSearchParams(window.location.search);
  // 默认日期永远解析为「今天（足球日）」。URL 里可能残留用户上次
  // 手动切换后浏览器缓存的 `date` 参数，但它不得覆盖默认行为——只有
  // 用户在页面里手动切换日期时才改变当前日期（经 onDateChange 更新 state）。
  return {
    date: footballDayShanghai(),
    fixtureId: query.get("fixture_id"),
  };
}

export function DashboardPage() {
  const [query] = useState(initialQuery);
  const [date, setDate] = useState(query.date);
  const [workspace, setWorkspace] = useState<IntelligenceWorkspaceList | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      fetchIntelligenceWorkspace(date, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setWorkspace(payload);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (controller.signal.aborted) return;
        setState("error");
      });
    });
    return () => controller.abort();
  }, [date, refreshKey]);

  if (state === "loading" && !workspace) {
    return <main className="workspace-load-state" aria-busy="true"><strong>正在读取统一情报工作台…</strong><span>本次读取不会调用 Provider。</span><div className="design-v1-loading-grid" aria-hidden="true">{Array.from({ length: 5 }, (_, index) => <i key={index} />)}</div><div className="design-v1-loading-panel" aria-hidden="true" /></main>;
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
