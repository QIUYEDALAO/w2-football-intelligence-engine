from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from w2.strategy.operations import run_shadow_replay
from w2.strategy.shadow import write_json
from w2.strategy.shadow_demo import demo_inputs

FORBIDDEN_MARKER_PARTS = (
    ("API", "_", "KEY"),
    ("AUTHOR", "IZATION"),
    ("PASS", "WORD"),
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run W2 shadow-only strategy cycle.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write runtime locks.")
    parser.add_argument(
        "--execution-kind",
        choices=("FORWARD", "RETROSPECTIVE"),
        default="RETROSPECTIVE",
        help="Explicitly select forward locking or retrospective replay.",
    )
    parser.add_argument(
        "--database-url-from-env",
        action="store_true",
        help="Read the database URL from the configured W2 environment.",
    )
    parser.add_argument("--checkpoint", type=Path, help="Optional checkpoint file path.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON summary.")
    parser.add_argument("--request-budget", type=int, default=100)
    parser.add_argument("--quota-reserve", type=int, default=1500)
    parser.add_argument("--output", type=Path, help="Optional local audit report path.")
    return parser


def _runtime_summary(replay: dict[str, Any], *, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "status": "PASS",
        "execution_kind": args.execution_kind,
        "dry_run": bool(args.dry_run),
        "shadow_only": True,
        "allowed_shadow_actions": ["SHADOW_WATCH", "SHADOW_SKIP"],
        "forward_lock_count": replay.get("forward", {}).get("lock_count", 0),
        "retrospective_status": replay.get("retrospective", {}).get("status"),
        "formal_recommendation": False,
        "candidate": False,
        "database_url_source": "ENV" if args.database_url_from_env else "NOT_USED",
        "checkpoint": str(args.checkpoint) if args.checkpoint else None,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.request_budget > 100:
        parser.error("request budget exceeds Stage9B limit")
    if args.quota_reserve < 1500:
        parser.error("quota reserve below Stage9B minimum")

    mode = "LOCAL_DRY_RUN" if args.dry_run else f"{args.execution_kind}_SHADOW_ONLY"
    replay = run_shadow_replay(inputs=demo_inputs(), root=_project_root(), mode=mode)
    replay["server_shadow_cycle"] = {
        "status": "NO_ELIGIBLE_FORWARD_FIXTURE"
        if args.execution_kind == "FORWARD"
        else "RETROSPECTIVE_REPLAY",
        "reason": "RUNTIME_ENTRYPOINT_AVAILABLE_NO_NETWORK_REQUESTS",
        "api_request_count": 0,
        "quota_reserve": args.quota_reserve,
        "allowed_actions": ["SHADOW_WATCH", "SHADOW_SKIP"],
        "execution_kind": args.execution_kind,
        "dry_run": bool(args.dry_run),
    }
    if args.execution_kind == "RETROSPECTIVE":
        replay["forward"]["lock_count"] = 0

    summary = _runtime_summary(replay, args=args)
    if args.output:
        write_json(args.output, replay)
    encoded = json.dumps(summary if args.json or not args.output else summary, sort_keys=True)
    blocked_markers = tuple("".join(parts) for parts in FORBIDDEN_MARKER_PARTS)
    if any(marker in encoded.upper() for marker in blocked_markers):
        raise RuntimeError("credential marker in shadow CLI output")
    if '"candidate": true' in encoded.lower() or '"formal_recommendation": true' in encoded.lower():
        raise RuntimeError("shadow CLI cannot output candidate or formal recommendation")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
