export function SkeletonCard() {
  return (
    <article className="match-card skeleton-card">
      <div className="skeleton-line w30" />
      <div className="skeleton-line w55" />
      <div className="skeleton-panel" />
      <div className="skeleton-line w85" />
    </article>
  );
}
