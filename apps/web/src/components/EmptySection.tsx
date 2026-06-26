export function EmptySection({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-section">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}
