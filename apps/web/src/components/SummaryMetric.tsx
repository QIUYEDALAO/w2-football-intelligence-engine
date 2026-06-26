export function SummaryMetric({ label, value, sub }: { label: string; value: string | number; sub: string }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{sub}</small>
    </div>
  );
}
