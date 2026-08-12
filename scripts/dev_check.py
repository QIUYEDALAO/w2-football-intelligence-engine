#!/usr/bin/env python3
"""Run fast, change-aware local checks; never substitutes for Release Candidate CI."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

import yaml
from classify_ci import changed_paths, classify

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_TESTS = (
    "tests/unit/test_ci_classifier.py",
    "tests/unit/test_ci_shards.py",
    "tests/unit/test_release_manifest.py",
    "tests/contract/test_delivery_pipeline.py",
)


def run(command: list[str], *, cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True, env=os.environ | {
        "W2_ENVIRONMENT": "test",
        "W2_PROVIDER_CALLS_DISABLED": "true",
        "W2_PROVIDER_SCHEDULER_ENABLED": "false",
        "W2_XG_BACKFILL_ENABLED": "false",
    })


def existing(paths: tuple[str, ...] | list[str]) -> list[str]:
    return [path for path in paths if (ROOT / path).is_file()]


def python_tests(paths: list[str]) -> list[str]:
    direct = [path for path in paths if path.startswith("tests/") and path.endswith(".py")]
    stems = {Path(path).stem.removeprefix("test_") for path in paths if path.endswith(".py")}
    mapped = [
        str(path.relative_to(ROOT))
        for root in (ROOT / "tests/unit", ROOT / "tests/contract")
        for path in root.glob("test_*.py")
        if path.stem.removeprefix("test_") in stems
    ]
    pipeline_roots = (".github/", "scripts/ci_", "scripts/dev_check", "scripts/release_")
    if any(path.startswith(pipeline_roots) for path in paths):
        mapped.extend(existing(list(PIPELINE_TESTS)))
    if any("future_refresh" in path or "staging" in path for path in paths):
        mapped.extend(
            existing(
                [
                    "tests/integration/test_future_refresh_staging_parity.py",
                    "tests/integration/test_future_refresh_e2e_smoke.py",
                ]
            )
        )
    return sorted(set(direct + mapped))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--print-class", action="store_true")
    args = parser.parse_args()
    paths = changed_paths(args.base, args.head)
    plan = classify(paths)
    if args.print_class:
        print(plan.change_class)
        return 0

    run(["git", "diff", "--check", f"{args.base}...{args.head}"])
    run(["uv", "run", "python", "scripts/check_dashboard_single_public_authority.py"])
    for path in paths:
        if path.endswith((".yaml", ".yml")) and (ROOT / path).is_file():
            yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    if plan.change_class == "docs":
        tests = existing(
            [
                "tests/contract/test_delivery_status_documentation.py",
                "tests/contract/test_delivery_pipeline.py",
            ]
        )
        run(["uv", "run", "python", "scripts/check_tracked_outputs.py"])
        if tests:
            run(["uv", "run", "pytest", "-q", *tests])
    elif plan.change_class == "web":
        run(["npm", "--prefix", "apps/web", "run", "typecheck"])
        run(["npm", "--prefix", "apps/web", "run", "build"])
        specs = [
            str(Path(path).relative_to("apps/web"))
            for path in paths
            if path.startswith("apps/web/e2e/") and path.endswith(".spec.ts")
        ]
        run(
            ["npx", "playwright", "test", *(specs or ["e2e/decision-contract.spec.ts"])],
            cwd=ROOT / "apps/web",
        )
    elif plan.change_class == "python":
        changed_python = [path for path in paths if path.endswith(".py")]
        run(["uv", "run", "ruff", "check", *(changed_python or ["scripts/classify_ci.py"])])
        run(["uv", "run", "mypy", "src", "apps"])
        tests = python_tests(paths)
        run(["uv", "run", "pytest", "-q", *(tests or ["tests/unit", "tests/contract"])])
    else:
        run(["uv", "run", "ruff", "check", "scripts", "tests"])
        run(["uv", "run", "alembic", "heads"])
        if shutil.which("docker"):
            run(["docker", "compose", "config"])
        run(["uv", "run", "pytest", "-q", *existing(list(PIPELINE_TESTS))])
    run(["uv", "run", "python", "tests/secret_scan.py"])
    print(
        f"LOCAL_FEEDBACK=PASS change_class={plan.change_class}; "
        "Release Candidate Full CI still required"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
