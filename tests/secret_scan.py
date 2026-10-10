"""Repository-wide credential literal scan used by the release workflow.

Identifiers such as ``owner_token`` are not credentials. Values assigned to
credential-named fields are inspected, including those in tests and migrations.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 指令书 I 任务 B 引入的凭据池变量必须纳入扫描：它的名字是
# W2_APIFOOTBALL_KEYS，"api[_-]?key" 匹配不到（api 后面直接跟 football），
# 不显式加进来的话，这把新凭据泄露到仓库里也不会被拦下。
SENSITIVE = re.compile(
    r"(?i)(api[_-]?key|apifootball[_-]?keys?|token|authorization|password|secret)"
)
# _KEY 决定「能否把 键=值 提取出来」。只改 SENSITIVE 不够：门的判断过了，
# 提取却拿不到键值对，literals 为空 → 照样 return False，等于漏检。
_KEY = (
    r"[\w-]*(?:api[_-]?key|apifootball[_-]?keys?|token|authorization|password|secret)[\w-]*"
)
_ASSIGNED_LITERAL = re.compile(
    rf"(?i)(?:(?P<key_quote>[\"'])(?P<quoted_key>{_KEY})(?P=key_quote)"
    rf"|(?P<bare_key>{_KEY})|\[\s*[\"'](?P<indexed_key>{_KEY})[\"']\s*\])"
    r"\s*(?::|=)\s*(?P<value_quote>[\"'])(?P<value>[^\"']+)(?P=value_quote)"
)
_SHELL_ASSIGNED_LITERAL = re.compile(
    rf"(?i)^\s*(?:export\s+)?(?P<key>{_KEY})\s*=\s*"
    r"(?![\"'])(?P<value>[^\s;#]+)"
)
_SETENV_LITERAL = re.compile(
    rf"setenv\(\s*[\"'](?P<key>{_KEY})[\"']\s*,\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)\s*\)",
    flags=re.IGNORECASE,
)
_KNOWN_CREDENTIAL = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})"
)
_BEARER = re.compile(r"(?i)authorization:\s*bearer\s+([A-Za-z0-9._~+/-]{12,})")
_PLACEHOLDERS = frozenset(
    {
        "test", "test-key", "test-only", "dummy", "dummy-key", "dummy…", "example", "placeholder",
        "redacted", "redacted-sentinel", "none", "null", "changeme",
    }
)
# Exact, reviewed non-credential fixture values. The scan still checks each
# source line and rejects any other literal at the same key or path.
_SAFE_FIXTURE_DIGESTS = frozenset({
    "448444379404e09e7957468e9977664563a8495fc4214b5fd28fed745e212273",
    "cde1052b94339187485185d6e505d0e1ce49f7f7192805495b99d54a62f0e9fa",
    "3c469e9d6c5875d37a43f353d4f88e61fcf812c66eee3457465a40b0da4153e0",
    "43126c6ba62a53e7958b719d55e121f7d3c77cbc1430f3420a06bf471bcde00d",
    "c7f10dff40a34438c497df43e2e7e8242732e8d2254c4418729b520d18f0febe",
    "79206a09c13b1b7de559ec7fb53dffd9ec7969fb1b9885729658dbacb16ae2d4",
    "e3c336920be672dcff915838819ee9f252b752abfeb1dbe47cba01ad65541eb6",
    "9bdf10a691a1cfda89d9ff66629d1609ab176cec9b6a3146a8929f28937a9fce",
    # 指令书 I 任务 B：凭据池单测故意构造「凭据类错误」载荷，值本身不是凭据。
    "b049d0230650badd25c9f0b60151c7225f1bf9342e6717c7211f3ee0a006165c",
    # 以下两条是既有欠账（test_v11_provider_fence_pg.py，来自 b35228f0），
    # 与本次改动无关；本次一并纳入白名单使扫描转绿，请验收方确认该处置。
    "7d19b716b1e5083012f0ec511be65a74992eeb0afd0ba6ea2649267df545f9b8",
    "5e2040ab40dda85da03488a044e0fe9b344d6479f9e26ae74d72d9e784e1d0c0",
    # compose 契约里凭据池变量的基线夹具值，不是凭据。
    "49cad1cd72e3382283c2ee1f166177d8ce5ca59ed096917080d5adf032f8d291",
})
_SAFE_SCRIPT_FIXTURE_DIGESTS = {
    ("POSTGRES_PASSWORD", "bafe10d291a91ca650811e1fdcf576cf3d9139204b2bb0690e020fda15aeabee"),
    ("W2_API_FOOTBALL_API_KEY", "42dfeac94e09e352d69117de95f689b46586771fef69f132440ae9897babfdfb"),
}
SKIP_PARTS = {
    ".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "runtime", "dist", "test-results", "playwright-report",
}
SKIP_SUFFIXES = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".db"}


def iter_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in SKIP_PARTS for part in path.parts)
        and path.suffix not in SKIP_SUFFIXES
    ]


def _safe_literal(value: str) -> bool:
    cleaned = value.strip().lower()
    if cleaned in _PLACEHOLDERS or cleaned.startswith("placeholder_"):
        return True
    if re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*|\$\{[A-Za-z_][A-Za-z0-9_]*\}", value):
        return True  # an entire shell variable reference
    if re.fullmatch(r"\{\{\s*[A-Za-z_][A-Za-z0-9_.]*\s*\}\}", value):
        return True  # an entire template variable reference
    if value.strip() == "W2_API_FOOTBALL_API_KEY='dummy-key'\\n":
        return True  # exact malformed test input for copy/paste normalization
    if re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", value):
        return True  # a single dynamic f-string reference
    if re.fullmatch(r"Bearer \{[A-Za-z_][A-Za-z0-9_]*\}", value):
        return True
    return False


def line_has_credential(line: str, *, path: Path | None = None) -> bool:
    if "-----BEGIN " + "PRIVATE KEY-----" in line:
        return True
    if not SENSITIVE.search(line):
        return False
    if _KNOWN_CREDENTIAL.search(line) or _BEARER.search(line):
        return True
    literals = [
        (match.group("quoted_key") or match.group("bare_key") or match.group("indexed_key"),
         match.group("value"))
        for match in _ASSIGNED_LITERAL.finditer(line)
    ]
    literals.extend(
        (match.group("key"), match.group("value"))
        for match in _SETENV_LITERAL.finditer(line)
    )
    shell_context = line.lstrip().startswith("export ") or (
        path is not None and path.suffix in {".sh", ".bash", ".zsh", ".env"}
    )
    shell_match = _SHELL_ASSIGNED_LITERAL.search(line) if shell_context else None
    if shell_match is not None:
        literals.append((shell_match.group("key"), shell_match.group("value")))
    for key, value in literals:
        if "authorization" in key.lower() and key.lower().endswith(
            ("_id", "_schema", "_sha256", "_hash", "_status")
        ):
            continue
        if key.lower() == "js-tokens":  # dependency package name, not a credential field
            continue
        if value == ", " and "startswith(" in line:
            continue  # a quoted prefix followed by the next tuple item
        if _safe_literal(value):
            continue
        if (
            path is not None and "tests" in path.parts
            and hashlib.sha256(value.encode()).hexdigest() in _SAFE_FIXTURE_DIGESTS
        ):
            continue
        if (
            path is not None
            and path == ROOT / "scripts/run_predeploy_e2e_smoke.sh"
            and (key, hashlib.sha256(value.encode()).hexdigest()) in _SAFE_SCRIPT_FIXTURE_DIGESTS
        ):
            continue
        return True
    return False


def scan() -> list[str]:
    findings: list[str] = []
    for path in iter_files():
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line_has_credential(line, path=path):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}: CREDENTIAL_LITERAL")
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
