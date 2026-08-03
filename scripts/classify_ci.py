#!/usr/bin/env python3
"""Fail-safe path classifier for W2 delivery validation."""

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
}
DELIVERY_FILES = {
    ".gitignore",
    "ci/pytest_durations.v1.json",
    "scripts/ci_shards.py",
    "scripts/classify_ci.py",
    "scripts/dev_check.py",
    "scripts/deploy_stage7h_staging.sh",
    "scripts/release_manifest.py",
    "tests/contract/test_delivery_pipeline.py",
    "tests/contract/test_staging_runtime_hardening.py",
    "tests/contract/test_arch_p2_05_final_acceptance.py",
    "tests/unit/test_ci_classifier.py",
    "tests/unit/test_ci_shards.py",
    "tests/unit/test_release_manifest.py",
    "tests/unit/test_release_evidence.py",
    "docs/operations/W2_DELIVERY_PIPELINE_LEAD_TIME_RECOVERY.md",
}
PYTHON_ROOTS = ("src/", "apps/api/", "apps/scheduler/", "apps/worker/", "tests/")
WEB_ROOTS = ("apps/web/",)
RUNTIME_ROOTS = ("migrations/", "infra/", "config/", "contracts/")
RUNTIME_FILES = {
    "docker-compose.yml",
    "Dockerfile.python",
    "Dockerfile.web",
    "alembic.ini",
    "pyproject.toml",
    "uv.lock",
}


@dataclass(frozen=True)
class CiPlan:
    change_class: str
    quality_required: str
    images_required: bool
    deployable: bool

    def outputs(self) -> dict[str, str]:
        return {
            "change_class": self.change_class,
            "quality_required": self.quality_required,
            "images_required": str(self.images_required).lower(),
            "deployable": str(self.deployable).lower(),
        }


def _domain(path: str) -> str:
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or path in {"", "."}:
        return "unknown"
    if path.startswith((".github/workflows/", "scripts/release/")) or path in DELIVERY_FILES:
        return "delivery"
    if path in DOC_STATUS_FILES or path.startswith("docs/"):
        return "docs"
    if path.startswith(WEB_ROOTS):
        return "web"
    if path.startswith(RUNTIME_ROOTS) or path in RUNTIME_FILES:
        return "runtime"
    if path.startswith("scripts/"):
        return "runtime"
    if path.startswith(PYTHON_ROOTS):
        return "python"
    if pure.suffix.lower() in {".md", ".markdown"}:
        return "docs"
    return "unknown"


def classify(paths: list[str], *, force_full: bool = False) -> CiPlan:
    domains = {_domain(path) for path in paths}
    if domains and domains <= {"docs"}:
        return CiPlan("docs", "FULL" if force_full else "DOCS", False, False)
    if domains and domains <= {"docs", "delivery"}:
        return CiPlan("delivery", "FULL", False, False)
    if not domains or "unknown" in domains or len(domains - {"docs"}) > 1:
        return CiPlan("unknown", "FULL", True, True)
    change_class = next(iter(domains - {"docs"}), "unknown")
    if change_class == "delivery":
        return CiPlan("delivery", "FULL", False, False)
    return CiPlan(change_class, "FULL", True, True)


def changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--no-renames", "--name-only", f"{base}...{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def resolve_plan(base: str, head: str, *, force_full: bool = False) -> CiPlan:
    try:
        return classify(changed_paths(base, head), force_full=force_full)
    except subprocess.CalledProcessError:
        return classify([], force_full=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
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
