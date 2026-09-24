import type { IntelligenceCalibratedValidationResponse, IntelligenceValidationResponse } from "../types/intelligenceWorkspace";

export function DesignV1ValidationView({ response, onPageChange }: { response: IntelligenceValidationResponse; onPageChange?: (offset: number) => void }) {
  const rows = response.samples || [];
  const page = response.pagination;
  return <section className="design-v1-review" aria-label="战绩复盘" data-design-v1-review>
    <header><div><span className="design-v1-eyebrow">REVIEW</span><h2>战绩复盘</h2></div><span>近 {response.pagination?.days ?? 7} 天 · {response.pagination?.total ?? rows.length} 条</span></header>
    {rows.length ? <div className="design-v1-table-wrap"><table className="design-v1-table"><thead><tr><th>日期</th><th>联赛</th><th>对阵</th><th>推荐</th><th>赔率</th><th>结果</th></tr></thead><tbody>{rows.map((row) => <tr key={`${row.fixture_id}-${row.recommendation}`}><td>{row.date || "—"}</td><td>{row.league || "—"}</td><td>{row.match || "—"}</td><td>{row.recommendation || "—"}</td><td>{row.odds ?? "—"}</td><td>{row.result || "—"}</td></tr>)}</tbody></table></div> : <p className="design-v1-empty">当前分页没有可展示的复盘样本。</p>}
    {page && onPageChange ? <footer className="design-v1-pagination"><span>{page.offset + 1}–{Math.min(page.offset + (page.limit || rows.length), page.total)} / {page.total}</span><button type="button" disabled={page.offset <= 0} onClick={() => onPageChange(Math.max(0, page.offset - (page.limit || 50)))}>上一页</button><button type="button" disabled={page.offset + (page.limit || rows.length) >= page.total} onClick={() => onPageChange(page.offset + (page.limit || 50))}>下一页</button></footer> : null}
  </section>;
}

export function DesignV1CalibratedValidationView({ response, onPageChange }: { response: IntelligenceCalibratedValidationResponse; onPageChange?: (offset: number) => void }) {
  const page = response.pagination;
  return <section className="design-v1-review" aria-label="战绩复盘校准版" data-design-v1-calibrated-review>
    <header><div><span className="design-v1-eyebrow">EV-ONLINE-02</span><h2>战绩复盘 · 校准版</h2></div><span>前向进度 {String(response.forward_progress.kept ?? 0)} / {String(response.forward_progress.target ?? 300)}</span></header>
    {response.samples.length ? <div className="design-v1-table-wrap"><table className="design-v1-table"><thead><tr><th>日期</th><th>联赛</th><th>对阵</th><th>推荐</th><th>赔率</th><th>校准判定</th><th>校准后 EV</th><th>结果</th></tr></thead><tbody>{response.samples.map((row) => <tr key={`${row.fixture_id}-${row.market}`}><td>{row.date || "—"}</td><td>{row.league || row.competition_id || "—"}</td><td>{row.match || "—"}</td><td>{row.recommendation || `${row.market} ${row.selection} ${row.exact_line}`}</td><td>{row.decimal_odds}</td><td>{row.calibration_decision || row.filter_decision}</td><td>{row.calibrated_ev === null || row.calibrated_ev === undefined ? "—" : `${(row.calibrated_ev * 100).toFixed(1)}%`}</td><td>{row.result || row.settlement}</td></tr>)}</tbody></table></div> : <p className="design-v1-empty">当前分页没有校准样本。</p>}
    {page && onPageChange ? <footer className="design-v1-pagination"><span>{page.offset + 1}–{Math.min(page.offset + (page.limit || response.samples.length), page.total)} / {page.total}</span><button type="button" disabled={page.offset <= 0} onClick={() => onPageChange(Math.max(0, page.offset - (page.limit || 50)))}>上一页</button><button type="button" disabled={page.offset + (page.limit || response.samples.length) >= page.total} onClick={() => onPageChange(page.offset + (page.limit || 50))}>下一页</button></footer> : null}
  </section>;
}

export default DesignV1ValidationView;
