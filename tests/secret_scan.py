from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|token|authorization:\s*bearer|password|secret)"
)
ALLOWLIST = (
    "api keys must come from environment",
    "api[_-]?key",
    "placeholder_password",
    "placeholder_secret_key",
    "placeholder_access_key",
    "SecretStr",
    "get_secret_value()",
    "secret manager",
    "secret runbooks",
    "secret_scan.py",
    "secret scan",
    "secrets guard",
    "without_secrets",
    "Secret pattern scan",
    "pattern scan",
    "database passwords",
    "authorization headers",
    "API keys",
    "POSTGRES_PASSWORD",
    "MINIO_ROOT_PASSWORD",
    "W2_MINIO_SECRET_KEY",
    "password@",
    'password" not',
    "passwords or",
    "no secrets",
    "no_secret_logged",
    "tests.secret_scan",
    "test_secret_patterns",
    "for token",
    "if token",
    "token =",
    "{token}",
    "real_world_tokens",
    "adapter token",
    "js-tokens",
    "W2_API_FOOTBALL_API_KEY",
    "BASELIGHT_API_KEY",
    "x-api-key",
    "x-apisports-key",
    "x-rapidapi-key",
    "api_key",
    "API_KEY_NOT_PRESENT",
    "secrets and environments",
    "Secrets and Environments",
    "secrets via environment",
    "never log or store",
    "Secret scan",
    "secret scan",
    "password auto-generated",
    "32-byte hex",
    "printing secrets",
    "SECRETS_AND_ENVIRONMENTS",
    "Secrets and Environments",
    "本文件不得保存 `.env` 内容、密钥、token、密码或私密 payload",
    "权限、密钥、凭据、secret 或 `.env` 变更",
    "需要权限、凭据、密钥、secret、`.env` 或公网端口变更",
)
SKIP_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "runtime",
    "dist",
}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".db"}


def iter_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in SKIP_PARTS for part in path.parts)
        and path.suffix not in SKIP_SUFFIXES
    ]


def scan() -> list[str]:
    findings: list[str] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not SENSITIVE.search(line):
                continue
            if any(allowed in line for allowed in ALLOWLIST):
                continue
            findings.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("\n".join(findings), file=sys.stderr)
        return 1
    print("secret scan PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
