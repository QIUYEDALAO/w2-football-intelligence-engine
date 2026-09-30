import type { AhOuV3ValidationView, IntelligenceCalibratedValidationResponse, IntelligenceValidationResponse } from "../types/intelligenceWorkspace";

function kickoffLabel(value: string | null | undefined): string {
  if (!value || Number.isNaN(Date.parse(value))) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((item) => item.type === type)?.value || "";
  return `${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`;
}

function newestKickoffFirst<T extends { kickoff_utc: string | null }>(rows: T[]): T[] {
  const timestamp = (row: T) => row.kickoff_utc && !Number.isNaN(Date.parse(row.kickoff_utc))
    ? Date.parse(row.kickoff_utc) : -Infinity;
  return rows.slice().sort((left, right) => timestamp(right) - timestamp(left));
}

function Pagination({ page, rows, onPageChange }: { page?: { limit: number | null; offset: number; total: number }; rows: number; onPageChange?: (offset: number) => void }) {
  if (!page || !onPageChange) return null;
  const step = page.limit || 50;
  return <div className="w2-review-head"><span className="w2-counts">{page.total ? page.offset + 1 : 0}–{Math.min(page.offset + rows, page.total)} / {page.total}</span><button type="button" className="w2-link" disabled={page.offset <= 0} onClick={() => onPageChange(Math.max(0, page.offset - step))}>上一页</button><button type="button" className="w2-link" disabled={page.offset + rows >= page.total} onClick={() => onPageChange(page.offset + step)}>下一页</button></div>;
}

function Result({ result, profit }: { result: string | null | undefined; profit: number | null | undefined }) {
  const label = ({ WIN: "赢", HALF_WIN: "赢一半", PUSH: "走盘", HALF_LOSS: "输一半", LOSS: "输" } as Record<string, string>)[result || ""] || result || "—";
  const kind = result === "WIN" || result === "HALF_WIN" ? "win" : result === "PUSH" ? "push" : "lose";
  return <span className={`w2-result w2-result--${kind}`}><span className="w2-result__icon" aria-hidden="true">{kind === "win" ? "✓" : kind === "lose" ? "✗" : "–"}</span>{label}{profit == null ? null : <span className="num"> {profit >= 0 ? "+" : "−"}{Math.abs(profit).toFixed(2)}</span>}</span>;
}

function AhOuV3ValidationSection({ view }: { view?: AhOuV3ValidationView }) {
  if (!view) return <section data-ah-ou-v3 className="w2-validation-signals"><h3>AH/OU v3 赛后验证</h3><p>v3 验证数据不可用。</p></section>;
  const marketNames: Record<string, string> = { ASIAN_HANDICAP: "亚洲让球", TOTALS: "大小球" };
  const stateNames: Record<string, string> = { PENDING: "待赛果", BLOCKED: "来源阻断", VOID: "作废" };
  return <section data-ah-ou-v3 className="w2-validation-signals">
    <h3>AH/OU v3 赛后验证</h3>
    <p>按冻结盘口和入场赔率结算；与下方旧代际复盘分列。待赛果、作废及阻断均不计入命中率分母。</p>
    <div className="w2-counts"><span>注册 cohort <b>{view.registered_cohorts}</b></span><span>完成决策 <b>{view.completed_decisions}</b></span><span>选中 <b>{view.selected}</b></span></div>
    {Object.entries(view.by_market).map(([market, stats]) => <div className="w2-review-head" key={market} data-v3-market={market}>
      <strong>{marketNames[market] || market}</strong>
      <div className="w2-counts">
        <span>选中 <b>{stats.selected}</b></span>
        <span>待赛果 <b>{stats.pending}</b></span>
        <span>已结算 <b>{stats.settled}</b></span>
        <span>作废 <b>{stats.void}</b></span>
        <span>阻断 <b>{stats.blocked}</b></span>
        <span>命中率 <b>{stats.hit_rate == null ? "—" : `${(stats.hit_rate * 100).toFixed(1)}%`}</b>（分母 {stats.hit_rate_denominator}）</span>
        <span>净单位 <b className="num">{stats.net_units}</b></span>
      </div>
    </div>)}
    {view.rows.length ? <div className="w2-table-wrap w2-table-wrap--review"><table className="w2-table"><thead><tr><th>开球时间</th><th>市场</th><th>场次 / 决策</th><th>冻结选择</th><th className="col-right">入场赔率</th><th>状态</th><th>结算</th></tr></thead><tbody>{newestKickoffFirst(view.rows).map((row) => <tr key={row.decision_id} data-v3-decision-id={row.decision_id}><td className="num">{kickoffLabel(row.kickoff_utc)}</td><td>{marketNames[row.market]}</td><td><span className="num">{row.fixture_id}</span><br /><small title={row.decision_id}>{row.decision_id.slice(0, 12)}…</small></td><td>{row.selection || "—"} {row.exact_line || "—"}</td><td className="col-right num">{row.decimal_odds || "—"}</td><td>{row.state === "SETTLED" ? "已结算" : stateNames[row.state]}</td><td>{row.state === "SETTLED" ? <Result result={row.settlement} profit={row.net_units == null ? null : Number(row.net_units)} /> : "—"}</td></tr>)}</tbody></table></div> : <p>目前没有选中的 v3 决策。</p>}
  </section>;
}

export function DesignV1ValidationView({ response, onPageChange }: { response: IntelligenceValidationResponse; onPageChange?: (offset: number) => void }) {
  const rows = newestKickoffFirst(response.samples || []);
  return <div data-design-v1-review>
    <div className="w2-review-head"><span className="faint">AH/OU v3.1 冻结决策 · 全历史</span><div className="w2-counts"><span>累计净单位 <b className="num">{response.cumulative_profit_units >= 0 ? "+" : "−"}{Math.abs(response.cumulative_profit_units).toFixed(2)}</b></span><span>选中决策 <b>{response.ah_ou_v3?.selected ?? rows.length}</b></span></div></div>
    <div className="w2-table-wrap w2-table-wrap--review"><table className="w2-table"><thead><tr><th>开球时间</th><th>联赛</th><th>对阵</th><th>冻结选择</th><th>赔率</th><th>五态 / 结算</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={row.decision_id || `${row.fixture_id}-${row.market}`} data-v3-decision-id={row.decision_id}><td className="num">{kickoffLabel(row.kickoff_utc)}</td><td><span className="w2-league">{row.league || "—"}</span></td><td>{row.match || "—"}</td><td className="w2-pick">{row.recommendation || "—"}</td><td className="num">{row.decimal_odds ?? "—"}</td><td><Result result={row.result} profit={row.profit_units} /></td></tr>) : <tr><td colSpan={6}>目前没有选中的 v3.1 决策。</td></tr>}</tbody></table></div>
    <Pagination page={response.pagination} rows={rows.length} onPageChange={onPageChange} />
    <AhOuV3ValidationSection view={response.ah_ou_v3} />
  </div>;
}

export function DesignV1CalibratedValidationView({ response, onPageChange }: { response: IntelligenceCalibratedValidationResponse; onPageChange?: (offset: number) => void }) {
  const rows = newestKickoffFirst(response.samples);
  return <div data-design-v1-calibrated-review><div className="w2-review-head"><span className="faint">前向进度 {String(response.forward_progress.kept ?? 0)} / {String(response.forward_progress.target ?? 300)}</span><div className="w2-counts"><span>保留 <b>{response.counts.kept}</b></span><span>过滤 <b>{response.counts.filtered}</b></span><span>保留 <b className="num">{response.kept_profit_units >= 0 ? "+" : "−"}{Math.abs(response.kept_profit_units).toFixed(2)}</b>（含返水 <b className="num">{(response.kept_profit_units_with_rebate ?? response.kept_profit_units) >= 0 ? "+" : "−"}{Math.abs(response.kept_profit_units_with_rebate ?? response.kept_profit_units).toFixed(2)}</b>） · 过滤 <b className="num">{response.filtered_profit_units >= 0 ? "+" : "−"}{Math.abs(response.filtered_profit_units).toFixed(2)}</b>（含返水 <b className="num">{(response.filtered_profit_units_with_rebate ?? response.filtered_profit_units) >= 0 ? "+" : "−"}{Math.abs(response.filtered_profit_units_with_rebate ?? response.filtered_profit_units).toFixed(2)}</b>）</span></div></div><div className="w2-table-wrap w2-table-wrap--review"><table className="w2-table"><thead><tr><th>开球时间</th><th>联赛</th><th>对阵</th><th>展示</th><th>比分</th><th className="col-right">赔率</th><th>校准判定</th><th>校准后 EV</th><th>结果</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={`${row.fixture_id}-${row.market}`}><td className="num">{kickoffLabel(row.kickoff_utc)}</td><td><span className="w2-league">{row.league || row.competition_id || "—"}</span></td><td>{row.match || "—"}</td><td className="w2-pick">{row.recommendation || "—"}</td><td className="num">{row.score || "—"}</td><td className="col-right num">{row.decimal_odds}</td><td><span className={`w2-decision w2-decision--${row.warmup ? "warmup" : row.filter_decision === "KEPT" ? "kept" : "filtered"}`}>{row.warmup ? "热身放行" : row.forward ? row.filter_decision === "KEPT" ? "前向 · 保留" : "前向 · 过滤" : row.filter_decision === "KEPT" ? "回溯 · 保留" : "回溯 · 过滤"}</span></td><td className="num">{row.calibrated_ev == null ? "—" : `${(row.calibrated_ev * 100).toFixed(1)}%`}</td><td><Result result={row.result || row.settlement} profit={row.profit_units} /></td></tr>) : <tr><td colSpan={9}>当前分页没有校准样本。</td></tr>}</tbody></table></div><Pagination page={response.pagination} rows={rows.length} onPageChange={onPageChange} /></div>;
}

export default DesignV1ValidationView;
