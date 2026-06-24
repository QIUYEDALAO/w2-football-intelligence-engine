from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from w2.strategy.operations import gate5_preflight
from w2.strategy.shadow import write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run W2 Gate 5 preflight from runtime evidence.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--database-url-from-env",
        action="store_true",
        help="Read PostgreSQL URL from the W2 environment; never pass it on the command line.",
    )
    parser.add_argument("--output", type=Path, help="Optional local report path.")
    return parser


def _runtime_evidence() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    replay: dict[str, object] = {
        "forward": {"lock_count": 0},
        "coverage": {"hard_gate_reasons": {}},
        "locks": [],
        "retrospective": {"replay_determinism": "PASS"},
    }
    comparison: dict[str, object] = {
        "status": "RUNTIME_READ_MODEL_EVIDENCE_PENDING",
        "source_system": "W2_RUNTIME",
    }
    policy: dict[str, object] = {
        "gate4_prerequisite": "GATE_4_NATIONAL_1X2_CLOSED_REQUIRED",
        "target_forward_sample_count": 60,
    }
    return replay, comparison, policy


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    replay, comparison, policy = _runtime_evidence()
    preflight = gate5_preflight(replay=replay, comparison=comparison, acceptance_policy=policy)
    preflight["runtime_entrypoint"] = {
        "database_url_source": "ENV" if args.database_url_from_env else "NOT_USED",
        "evidence_source": "POSTGRES_READ_MODEL_REQUIRED_AT_DEPLOYMENT",
        "dry_run": bool(args.dry_run),
        "reports_input_dependency": False,
    }
    if preflight.get("closed") is not False or preflight.get("gate5_result") == "CLOSED":
        raise RuntimeError("Gate5 preflight cannot close from this runtime entrypoint")
    if args.output:
        write_json(args.output, preflight)
    if args.json or not args.output:
        print(json.dumps(preflight, sort_keys=True))
    else:
        print("W2 Gate5 preflight check PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
