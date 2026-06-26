import type { DashboardDebug, ReleaseSyncState } from "../types/dashboard";

function valueText(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "--";
  return String(value);
}

export function DataDiagnosticsPanel({ debug, release }: { debug: DashboardDebug; release: ReleaseSyncState }) {
  const rows = [
    ["empty_reason", debug.empty_reason],
    ["read_model_fixture_count", debug.read_model_fixture_count],
    ["matchday_card_count", debug.matchday_card_count],
    ["future_fixture_count", debug.future_fixture_count],
    ["future_fixture_in_window_count", debug.future_fixture_in_window_count],
    ["future_fixture_parse_error_count", debug.future_fixture_parse_error_count],
    ["result_event_count", debug.result_event_count],
    ["selected_date", debug.selected_date],
    ["next_available_date", debug.next_available_date],
    ["future_fixture_min_kickoff_utc", debug.future_fixture_min_kickoff_utc],
    ["future_fixture_max_kickoff_utc", debug.future_fixture_max_kickoff_utc],
    ["api_sha", release.api_git_sha],
    ["web_sha", release.web_git_sha],
    ["data_source", release.data_source],
  ] as const;
  return (
    <section className="diagnostics-panel">
      <div>
        <p className="eyebrow">DATA DIAGNOSTICS</p>
        <h2>云端 read-model 当前没有可展示比赛</h2>
        <p>页面已连通 API，但当前窗口没有聚合数据。下面是后端返回的诊断，不再用空白页面掩盖问题。</p>
        {debug.empty_detail ? <p className="diagnostics-detail">{debug.empty_detail}</p> : null}
      </div>
      <dl className="diagnostics-grid">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{valueText(value)}</dd>
          </div>
        ))}
      </dl>
      <div className="diagnostics-actions">
        <strong>建议动作</strong>
        <ul>
          {(debug.suggested_actions?.length ? debug.suggested_actions : ["run staging seed", "check ingestion", "check read-model checkpoints"]).map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
      </div>
      {debug.future_fixture_status_distribution ? (
        <div className="diagnostics-actions">
          <strong>future fixture 状态分布</strong>
          <p>{JSON.stringify(debug.future_fixture_status_distribution)}</p>
        </div>
      ) : null}
      {debug.future_fixture_date_distribution ? (
        <div className="diagnostics-actions">
          <strong>future fixture 日期分布</strong>
          <p>{JSON.stringify(debug.future_fixture_date_distribution)}</p>
        </div>
      ) : null}
    </section>
  );
}
