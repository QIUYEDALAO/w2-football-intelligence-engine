#!/usr/bin/env python3
from __future__ import annotations

from apps.api.main import health
from apps.scheduler.main import heartbeat
from apps.worker.celery_app import ping


def main() -> int:
    payload = health()
    if payload.service != "w2-football-intelligence-engine":
        raise SystemExit("unexpected service name")
    if ping.run() != "pong":
        raise SystemExit("celery ping failed")
    if "heartbeat" not in heartbeat():
        raise SystemExit("scheduler heartbeat failed")
    print("W2 smoke PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

