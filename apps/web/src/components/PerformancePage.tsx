import { useEffect, useState } from "react";
import { fetchPerformance } from "../lib/performanceApi";
import type {
  PerformancePayload,
  PerformanceTier,
  PerformanceWindow,
  ReliabilityBin,
} from "../types/performance";

const WINDOWS: PerformanceWindow[] = ["7d", "30d", "90d"];
const TIERS: PerformanceTier[] = ["ALL", "STRICT", "ADVISORY"];

function percent(value: number | null): string {
  return value === null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function decimal(value: number | null): string {
  return value === null ? "—" : value.toFixed(3);
}

function ReliabilityRows({
  label,
  bins,
}: {
  label: string;
  bins: ReliabilityBin[];
}) {
  return (
    <div className="reliability-series">
      <strong>{label}</strong>
      {bins.filter((bin) => bin.count > 0).map((bin) => (
        <div className="reliability-row" key={`${label}-${bin.lower}`}>
          <span>{percent(bin.mean_confidence)}</span>
          <div>
            <i style={{ width: bin.accuracy === null ? "0%" : percent(bin.accuracy) }} />
          </div>
          <b>{percent(bin.accuracy)}</b>
        </div>
      ))}
    </div>
  );
}

export function PerformancePage() {
  const [window, setWindow] = useState<PerformanceWindow>("30d");
  const [tier, setTier] = useState<PerformanceTier>("ALL");
  const [payload, setPayload] = useState<PerformancePayload | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    fetchPerformance(window, tier)
      .then((next) => {
        if (!cancelled) setPayload(next);
      })
      .catch(() => {
        if (!cancelled) {
          setPayload(null);
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [window, tier]);

  if (failed) {
    return (
      <main className="performance-shell">
        <section className="performance-error">
          <p>表现投影暂不可用</p>
          <strong>SYSTEM_DEGRADED</strong>
          <span>不会用旧 Dashboard、runtime JSON 或演示数据替代。</span>
        </section>
      </main>
    );
  }
  if (!payload) {
    return <main className="performance-shell performance-loading">读取表现投影…</main>;
  }

  const strict = payload.tier_comparison.STRICT;
  const advisory = payload.tier_comparison.ADVISORY;
  const remaining = Math.max(
    payload.sample_progress.target - payload.sample_progress.current,
    0,
  );

  return (
    <main className="performance-shell">
      <header className="performance-header">
        <div>
          <p>CANONICAL PERFORMANCE</p>
          <h1>表现复盘</h1>
          <span>只读 performance checkpoint · {payload.selected_window}</span>
        </div>
        <div className="performance-filters">
          <label>
            窗口
            <select value={window} onChange={(event) => setWindow(event.target.value as PerformanceWindow)}>
              {WINDOWS.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
          <label>
            分层
            <select value={tier} onChange={(event) => setTier(event.target.value as PerformanceTier)}>
              {TIERS.map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </header>

      <section className="performance-section clv-section" aria-labelledby="clv-title">
        <div className="section-heading">
          <div>
            <p>01 · 第一 KPI</p>
            <h2 id="clv-title">Canonical CLV</h2>
          </div>
          <span>{payload.clv.sample_count} 个样本</span>
        </div>
        <p
          className="performance-population"
          data-population={payload.clv.clv_population}
        >
          总体：已完成全量评分且具有 canonical CLV 的比赛
        </p>
        {payload.clv.sample_count === 0 ? (
          <div className="performance-empty">暂无 canonical CLV 样本</div>
        ) : (
          <>
            <div className="performance-kpis">
              <article><span>CLV 均值</span><strong>{decimal(payload.clv.mean)}</strong></article>
              <article><span>95% CI</span><strong>{payload.clv.ci95 ? `${decimal(payload.clv.ci95[0])} — ${decimal(payload.clv.ci95[1])}` : "样本不足"}</strong></article>
              <article><span>正 CLV 占比</span><strong>{percent(payload.clv.positive_share)}</strong></article>
              <article><span>样本数</span><strong>{payload.clv.sample_count}</strong></article>
            </div>
            <ol className="clv-points" aria-label="CLV 点分布">
              {payload.clv.points.map((point) => (
                <li key={point.fixture_id}>
                  <span>{point.fixture_id}</span>
                  <strong>{decimal(point.clv_decimal)}</strong>
                  <small>{point.league} · {point.evaluation_tier}</small>
                </li>
              ))}
            </ol>
          </>
        )}
      </section>

      <section className="performance-section" aria-labelledby="calibration-title">
        <div className="section-heading">
          <div><p>02 · 校准</p><h2 id="calibration-title">模型 vs 市场</h2></div>
          <span>{payload.calibration.scored_count} 场可评分</span>
        </div>
        {payload.calibration.scored_count === 0 ? (
          <div className="performance-empty">暂无可评分样本</div>
        ) : (
          <>
            <div className="performance-kpis calibration-kpis">
              <article><span>模型 Log loss</span><strong>{decimal(payload.calibration.model_log_loss)}</strong></article>
              <article><span>市场 Log loss</span><strong>{decimal(payload.calibration.market_log_loss)}</strong></article>
              <article><span>Model − Market</span><strong>{decimal(payload.calibration.model_minus_market_log_loss)}</strong></article>
              <article><span>模型 ECE</span><strong>{decimal(payload.calibration.model_ece)}</strong></article>
              <article><span>市场 ECE</span><strong>{decimal(payload.calibration.market_ece)}</strong></article>
              <article><span>Bootstrap</span><strong>{payload.calibration.paired_log_loss_bootstrap.status}</strong></article>
            </div>
            <div className="reliability-grid">
              <ReliabilityRows label="模型可靠性" bins={payload.calibration.model_reliability_bins} />
              <ReliabilityRows label="市场可靠性" bins={payload.calibration.market_reliability_bins} />
            </div>
          </>
        )}
      </section>

      <section className="performance-section" aria-labelledby="tier-title">
        <div className="section-heading">
          <div><p>03 · 分层</p><h2 id="tier-title">STRICT vs ADVISORY</h2></div>
        </div>
        <div className="tier-table-wrap">
          <table className="tier-table">
            <thead><tr><th>Tier</th><th>已完结</th><th>可评分</th><th>Canonical settled</th><th>命中率</th><th>CLV</th><th>正 CLV</th><th>样本状态</th></tr></thead>
            <tbody>
              {[strict, advisory].map((row) => (
                <tr key={row.tier}>
                  <th>{row.tier}</th>
                  <td>{row.finished_result_count}</td>
                  <td>{row.scored_count}</td>
                  <td>{row.canonical_settled_count}</td>
                  <td>{row.canonical_hit_rate === null ? "样本不足" : percent(row.canonical_hit_rate)}</td>
                  <td>{decimal(row.clv_mean)}</td>
                  <td>{percent(row.clv_positive_share)}</td>
                  <td>{row.canonical_hit_rate_status === "AVAILABLE" ? "可用" : "样本不足"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="performance-section progress-section" aria-labelledby="progress-title">
        <div className="section-heading">
          <div><p>04 · 样本底线</p><h2 id="progress-title">积累进度</h2></div>
          <strong>{payload.sample_progress.current} / {payload.sample_progress.target}</strong>
        </div>
        <div className="sample-progress" aria-label="样本进度">
          <i style={{ width: `${payload.sample_progress.ratio * 100}%` }} />
        </div>
        <p>距离目标剩余 {remaining} 个 canonical settled 样本</p>
        <div className="coverage-line">
          覆盖：{payload.coverage.fixture_checkpoint_count} 场已投影，
          {payload.coverage.not_scorable_count} 场不可评分，
          {payload.coverage.blocked_count} 场阻断
        </div>
      </section>
    </main>
  );
}
