import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function gitSha() {
  if (process.env.VITE_GIT_SHA) return process.env.VITE_GIT_SHA;
  if (process.env.W2_GIT_SHA) return process.env.W2_GIT_SHA;
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { cwd: join(root, "..", ".."), encoding: "utf8" }).trim();
  } catch {
    return "UNKNOWN";
  }
}

const sha = gitSha();
const buildTime = process.env.VITE_BUILD_TIME || process.env.W2_BUILD_TIME || new Date().toISOString();
const payload = {
  web_git_sha: sha,
  web_build_time: buildTime,
  release_id: process.env.W2_RELEASE_ID || sha,
  data_mode: process.env.VITE_DASHBOARD_DATA_MODE || "api",
};
const output = join(root, "public", "meta.json");
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
