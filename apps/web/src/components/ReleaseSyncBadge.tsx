import type { ReleaseSyncState } from "../types/dashboard";

function shortSha(value: string): string {
  return value && value !== "UNKNOWN" ? value.slice(0, 7) : "UNKNOWN";
}

export function ReleaseSyncBadge({ release }: { release: ReleaseSyncState }) {
  return (
    <section className={`release-sync ${release.mismatch ? "is-mismatch" : ""}`}>
      {release.mismatch ? <strong>部署版本不一致：Web 与 API 不是同一 commit。</strong> : null}
      {release.demo ? <strong className="mode-badge demo">DEMO DATA · 非真实云端数据</strong> : null}
      {release.data_profile === "staging-seed" ? <strong className="mode-badge seed">STAGING SEED · 显式种子数据</strong> : null}
      <span>Web SHA {shortSha(release.web_git_sha)}</span>
      <span>API SHA {shortSha(release.api_git_sha)}</span>
      <span>Data {release.data_profile} / {release.data_source}</span>
      <span>Updated {new Date(release.updated_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span>
    </section>
  );
}
