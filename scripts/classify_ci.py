#!/usr/bin/env python3
"""Fail-safe path classifier for W2 pull-request CI."""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

DOC_STATUS_FILES = {
    "NEXT_ACTION.md",
    "PROJECT_STATE.yaml",
    "PROJECT_LEDGER.md",
    "tests/contract/test_delivery_status_documentation.py",
    "tests/unit/test_architecture_governance.py",
}
PYTHON_ROOTS = ("src/", "apps/api/", "apps/scheduler/", "apps/worker/", "tests/")
WEB_ROOTS = ("apps/web/",)
MIGRATION_ROOTS = ("migrations/",)
INFRA_ROOTS = ("infra/",)
INFRA_FILES = {
    "docker-compose.yml",
    "Dockerfile.api",
    "Dockerfile.migrations",
    "Dockerfile.scheduler",
    "Dockerfile.web",
    "Dockerfile.worker",
}
FULL_CI_FILES = {
    ".github/workflows/ci.yml",
    "scripts/check_architecture_governance.py",
    "scripts/classify_ci.py",
    "scripts/check_w2_all.py",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
}
CI_JOB_NAMES = (
    "governance",
    "python_focused",
    "web",
    "migration",
    "compose",
    "staging_parity",
    "predeploy_e2e",
    "verify",
)


@dataclass(frozen=True)
class CiPlan:
    governance: bool = True
    python_focused: bool = False
    web: bool = False
    migration: bool = False
    compose: bool = False
    staging_parity: bool = False
    predeploy_e2e: bool = False
    verify: bool = False
    full: bool = False

    def outputs(self) -> dict[str, str]:
        return {
            key: str(value).lower()
            for key, value in vars(self).items()
        }


def _domains(path: str) -> set[str]:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or path in {"", "."}:
        return {"unknown"}
    if path in FULL_CI_FILES or path.startswith(".github/"):
        return {"unknown"}
    if path.startswith(MIGRATION_ROOTS):
        return {"migration"}
    if path.startswith(WEB_ROOTS):
        return {"web"}
    if path.startswith(INFRA_ROOTS) or path in INFRA_FILES:
        return {"infra"}
    if path.startswith("scripts/"):
        if pure.suffix == ".py":
            return {"python", "infra"} if "deploy" in pure.name else {"python"}
        return {"infra"} if pure.suffix == ".sh" else {"unknown"}
    if path in DOC_STATUS_FILES or path.startswith("docs/"):
        return {"docs"}
    if path.startswith(PYTHON_ROOTS) or path.startswith(("config/", "contracts/")):
        return {"python"}
    if pure.suffix.lower() in {".md", ".markdown"}:
        return {"docs"}
    return {"unknown"}


def classify(paths: list[str], *, force_full: bool = False) -> CiPlan:
    domains = set().union(*(_domains(path) for path in paths)) if paths else set()
    heavy_domains = domains - {"docs"}
    full = (
        force_full
        or not paths
        or "unknown" in domains
        or "migration" in domains
        or len(heavy_domains) > 1
    )
    if full:
        return CiPlan(
            web=True,
            migration=True,
            compose=True,
            staging_parity=True,
            predeploy_e2e=True,
            verify=True,
            full=True,
        )
    if heavy_domains == {"python"}:
        return CiPlan(python_focused=True)
    if heavy_domains == {"web"}:
        return CiPlan(web=True)
    if heavy_domains == {"infra"}:
        return CiPlan(compose=True, staging_parity=True, predeploy_e2e=True)
    return CiPlan()


def required_ci_plan(paths: list[str], pr_kind: str) -> CiPlan:
    plan = classify(paths)
    if pr_kind == "IMPLEMENTATION" and plan.python_focused:
        return classify(paths, force_full=True)
    return plan


def ci_required_passes(expected: dict[str, bool], results: dict[str, str]) -> bool:
    return results.get("classify") == "success" and all(
        results.get(job) == ("success" if expected.get(job) else "skipped")
        for job in CI_JOB_NAMES
    )


def _key_values(values: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key or not item:
            raise ValueError(f"invalid KEY=VALUE pair: {value}")
        pairs[key] = item
    return pairs


def changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def resolve_plan(base: str, head: str, *, force_full: bool = False) -> CiPlan:
    if force_full:
        return classify([], force_full=True)
    try:
        return classify(changed_paths(base, head))
    except subprocess.CalledProcessError:
        return classify([], force_full=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--expected-job", action="append", default=[])
    parser.add_argument("--result", action="append", default=[])
    args = parser.parse_args()
    if args.result:
        expected = {
            key: value == "true"
            for key, value in _key_values(args.expected_job).items()
        }
        return 0 if ci_required_passes(expected, _key_values(args.result)) else 1
    if args.path:
        plan = classify(args.path, force_full=args.force_full)
    else:
        if args.base is None or args.head is None:
            parser.error("--base and --head are required when --path is omitted")
        plan = resolve_plan(args.base, args.head, force_full=args.force_full)
    lines = [f"{key}={value}" for key, value in plan.outputs().items()]
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
