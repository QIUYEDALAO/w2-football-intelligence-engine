import type { IntelligenceCalibratedValidationResponse, IntelligenceValidationResponse } from "../types/intelligenceWorkspace";

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

export function DesignV1ValidationView({ response, onPageChange }: { response: IntelligenceValidationResponse; onPageChange?: (offset: number) => void }) {
  const rows = response.samples || [];
  return <div data-design-v1-review><div className="w2-review-head"><span className="faint">近 {response.pagination?.days ?? 7} 天</span><div className="w2-counts"><span>累计盈亏 <b className="num">{response.cumulative_profit_units >= 0 ? "+" : "−"}{Math.abs(response.cumulative_profit_units).toFixed(2)}</b></span><span>场次 <b>{response.pagination?.total ?? rows.length}</b></span></div></div><div className="w2-table-wrap w2-table-wrap--review"><table className="w2-table"><thead><tr><th>日期</th><th>联赛</th><th>对阵</th><th>推荐</th><th className="col-right">赔率</th><th>结果</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={`${row.fixture_id}-${row.recommendation}`}><td className="num">{row.date || "—"}</td><td><span className="w2-league">{row.league || "—"}</span></td><td>{row.match || "—"}</td><td className="w2-pick">{row.recommendation || "—"}</td><td className="col-right num">{row.decimal_odds ?? "—"}</td><td><Result result={row.result} profit={row.profit_units} /></td></tr>) : <tr><td colSpan={6}>当前分页没有可展示的复盘样本。</td></tr>}</tbody></table></div><Pagination page={response.pagination} rows={rows.length} onPageChange={onPageChange} /></div>;
}

export function DesignV1CalibratedValidationView({ response, onPageChange }: { response: IntelligenceCalibratedValidationResponse; onPageChange?: (offset: number) => void }) {
  const rows = response.samples;
  return <div data-design-v1-calibrated-review><div className="w2-review-head"><span className="faint">前向进度 {String(response.forward_progress.kept ?? 0)} / {String(response.forward_progress.target ?? 300)}</span><div className="w2-counts"><span>保留 <b>{response.counts.kept}</b></span><span>过滤 <b>{response.counts.filtered}</b></span><span>保留盈亏 <b className="num">{response.kept_profit_units >= 0 ? "+" : "−"}{Math.abs(response.kept_profit_units).toFixed(2)}</b> · 过滤盈亏 <b className="num">{response.filtered_profit_units >= 0 ? "+" : "−"}{Math.abs(response.filtered_profit_units).toFixed(2)}</b></span></div></div><div className="w2-table-wrap w2-table-wrap--review"><table className="w2-table"><thead><tr><th>日期</th><th>联赛</th><th>对阵</th><th>推荐</th><th className="col-right">赔率</th><th>校准判定</th><th>校准后 EV</th><th>结果</th></tr></thead><tbody>{rows.length ? rows.map((row) => <tr key={`${row.fixture_id}-${row.market}`}><td className="num">{row.date || "—"}</td><td><span className="w2-league">{row.league || row.competition_id || "—"}</span></td><td>{row.match || "—"}</td><td className="w2-pick">{row.recommendation || `${row.market} ${row.selection} ${row.exact_line}`}</td><td className="col-right num">{row.decimal_odds}</td><td><span className={`w2-decision w2-decision--${row.warmup ? "warmup" : row.filter_decision === "KEPT" ? "kept" : "filtered"}`}>{row.warmup ? "热身放行" : row.forward ? row.filter_decision === "KEPT" ? "前向 · 保留" : "前向 · 过滤" : row.filter_decision === "KEPT" ? "回溯 · 保留" : "回溯 · 过滤"}</span></td><td className="num">{row.calibrated_ev == null ? "—" : `${(row.calibrated_ev * 100).toFixed(1)}%`}</td><td><Result result={row.result || row.settlement} profit={row.profit_units} /></td></tr>) : <tr><td colSpan={8}>当前分页没有校准样本。</td></tr>}</tbody></table></div><Pagination page={response.pagination} rows={rows.length} onPageChange={onPageChange} /></div>;
}

export default DesignV1ValidationView;
