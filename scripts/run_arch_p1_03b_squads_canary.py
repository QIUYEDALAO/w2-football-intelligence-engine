#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ingestion_models import ProviderRequestLogModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.providers.api_football import ApiFootballClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual bounded ARCH-P1-03B squads canary.")
    parser.add_argument("--team", action="append", required=True)
    parser.add_argument("--max-calls", required=True, type=int)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    teams = list(dict.fromkeys(str(team).strip() for team in args.team if str(team).strip()))
    if not args.live:
        raise SystemExit("--live is required for the explicitly authorized one-shot")
    if not teams or len(teams) > 10 or len(teams) > args.max_calls:
        raise SystemExit("team count must be between 1 and min(10, --max-calls)")

    repository = FutureRefreshDbRepository()
    client = ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"squads"}),
    )
    started_at = datetime.now(UTC)
    actual_calls = 0
    raw_payloads = 0
    failures: list[dict[str, str]] = []
    for team_id in teams:
        actual_calls += 1
        try:
            response = client.request_live("squads", {"team": team_id})
        except Exception as exc:  # ledger records the bounded transport failure first
            failures.append({"team_id": team_id, "error_type": type(exc).__name__})
            continue
        stored_payload = {
            **response.payload,
            "endpoint": "squads",
            "parameters": {"team": team_id},
        }
        source_sha256 = hashlib.sha256(
            json.dumps(
                stored_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        repository.save_raw_payload(
            sha256=source_sha256,
            endpoint="squads",
            captured_at=response.captured_at,
            payload=stored_payload,
        )
        raw_payloads += 1

    with Session(repository.engine) as session:
        ledger_rows = list(
            session.scalars(
                select(ProviderRequestLogModel).where(
                    ProviderRequestLogModel.provider == "api_football",
                    ProviderRequestLogModel.endpoint == "squads",
                    ProviderRequestLogModel.requested_at >= started_at,
                )
            )
        )
    success_rows = sum(
        row.error is None and row.status_code is not None and row.status_code < 400
        for row in ledger_rows
    )
    failure_rows = len(ledger_rows) - success_rows
    equation_passed = actual_calls == success_rows + failure_rows
    print(
        json.dumps(
            {
                "schema_version": "w2.arch_p1_03b_squads_canary.v1",
                "team_ids": teams,
                "actual_calls": actual_calls,
                "success_ledger_rows": success_rows,
                "failure_ledger_rows": failure_rows,
                "ledger_equation_passed": equation_passed,
                "raw_payloads_written": raw_payloads,
                "failures": failures,
                "scheduler_used": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if equation_passed and not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
