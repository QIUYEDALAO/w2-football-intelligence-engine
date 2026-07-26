#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ingestion_models import ProviderRequestLogModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

DEFAULT_FIXTURES = ("1494212", "1494213", "1494214", "1494215", "1494216")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only ARCH-P1-03B identity evidence.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--fixtures", nargs="+", default=list(DEFAULT_FIXTURES))
    parser.add_argument("--m3-fixtures", nargs="*", default=[])
    args = parser.parse_args()
    as_of = _parse_time(args.as_of)
    repository = FutureRefreshDbRepository()
    write_statements: list[str] = []

    def detect_write(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        operation = statement.lstrip().split(None, 1)[0].upper()
        if operation in {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}:
            write_statements.append(operation)

    event.listen(repository.engine, "before_cursor_execute", detect_write)
    with Session(repository.engine) as session:
        provider_before = int(
            session.scalar(select(func.count()).select_from(ProviderRequestLogModel)) or 0
        )
    audit = repository.player_identity_candidate_audit(
        fixture_ids=list(args.fixtures),
        as_of=as_of,
    )
    matrix = repository.player_identity_fixture_matrix(
        fixture_ids=list(args.fixtures),
        as_of=as_of,
    )
    m3_runs: dict[str, list[dict[str, Any]]] = {
        fixture_id: [
            repository.player_identity_join_evidence(
                fixture_id=fixture_id,
                as_of=as_of,
            )
            for _ in range(3)
        ]
        for fixture_id in args.m3_fixtures
    }
    with Session(repository.engine) as session:
        provider_after = int(
            session.scalar(select(func.count()).select_from(ProviderRequestLogModel)) or 0
        )
    event.remove(repository.engine, "before_cursor_execute", detect_write)
    stability = {
        fixture_id: {
            "row_counts": [len(run["rows"]) for run in runs],
            "business_hashes": [run["business_hash"] for run in runs],
            "rows_identical": runs[0]["rows"] == runs[1]["rows"] == runs[2]["rows"],
            "status": [run["status"] for run in runs],
        }
        for fixture_id, runs in m3_runs.items()
    }
    print(
        json.dumps(
            {
                "schema_version": "w2.arch_p1_03b_identity_acceptance.v1",
                "as_of": as_of.isoformat(),
                "candidate_audit": audit,
                "candidate_audit_count": len(audit),
                "fixture_matrix": matrix,
                "m3_evidence": {
                    fixture_id: runs[0] for fixture_id, runs in m3_runs.items()
                },
                "three_run_stability": stability,
                "provider_call_delta": provider_after - provider_before,
                "db_write_delta": len(write_statements),
                "write_operations": write_statements,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
