from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from w2.prematch.candidate_notifications import (
    enqueue_test_message,
    notification_health,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="w2-candidate-notifications")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="read channel and outbox health")
    test = subparsers.add_parser("test", help="enqueue one idempotent test message")
    test.add_argument("--request-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "health":
        payload = notification_health()
    else:
        event_id = enqueue_test_message(request_id=str(args.request_id))
        payload = {
            "status": "QUEUED",
            "notification_event_id": event_id,
            "delivery_note": "delivery waits for the Owner-selected channel adapter",
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
