import { confidenceDots } from "../lib/normalize";

export function ConfidenceDots({ value }: { value: unknown }) {
  const count = confidenceDots(value);
  return (
    <span className="confidence-dots" aria-label={`信心 ${count}/5`}>
      {[0, 1, 2, 3, 4].map((index) => (
        <span className={index < count ? "dot is-filled" : "dot"} key={index} />
      ))}
    </span>
  );
}
