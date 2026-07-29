from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from w2.tracking.finished_match_scoring_projection import (
    run_finished_match_scoring_projection,
)
from w2.tracking.outcome_ledger_repository import OutcomeLedgerRepository

REFRESH_SCHEMA_VERSION = "w2.result_materialize.v1"


def run_outcome_result_refresh(
    *,
    repository: OutcomeLedgerRepository | None = None,
    fixture_ids: Sequence[str] | None = None,
    dry_run: bool = True,
    write_db: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    resolved_repository = repository or OutcomeLedgerRepository()
    result = resolved_repository.materialize_results(
        fixture_ids=fixture_ids,
        dry_run=dry_run,
        write_db=write_db,
        now=now,
    )
    scoring = (
        run_finished_match_scoring_projection(
            engine=resolved_repository.engine,
            fixture_ids=result["confirmed_fixture_ids"],
            dry_run=False,
            write_db=True,
            now=now,
        )
        if write_db and result["confirmed_fixture_ids"]
        else {
            "status": "NO_DUE_WORK",
            "db_writes": 0,
            "provider_calls": 0,
            "fixture_checkpoint_count": 0,
        }
    )
    return {
        "schema_version": REFRESH_SCHEMA_VERSION,
        **result,
        "status": (
            "BLOCKED"
            if result["status"] == "BLOCKED" or scoring["status"] == "BLOCKED"
            else result["status"]
        ),
        "result_db_writes": result["db_writes"],
        "scoring_projection": scoring,
        "scoring_projection_status": scoring["status"],
        "scoring_projection_db_writes": scoring["db_writes"],
        "db_writes": result["db_writes"] + scoring["db_writes"],
        "provider_calls": 0,
    }
