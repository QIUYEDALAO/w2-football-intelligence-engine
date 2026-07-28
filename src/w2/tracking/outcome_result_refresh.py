from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

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
    result = (repository or OutcomeLedgerRepository()).materialize_results(
        fixture_ids=fixture_ids,
        dry_run=dry_run,
        write_db=write_db,
        now=now,
    )
    return {
        "schema_version": REFRESH_SCHEMA_VERSION,
        **result,
        "provider_calls": 0,
    }
