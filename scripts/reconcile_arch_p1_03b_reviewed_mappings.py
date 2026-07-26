#!/usr/bin/env python3
"""Read-only idempotent reconciliation for the fixed ARCH-P1-03B review package."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ingestion_models import ProviderRequestLogModel
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    approved_player_identity_manifest_rows,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-package-sha256", required=True)
    parser.add_argument("--approval-artifact-sha256", required=True)
    parser.add_argument("--reviewed-by", required=True)
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != args.review_package_sha256:
        raise ValueError("PLAYER_IDENTITY_REVIEW_MANIFEST_HASH_MISMATCH")
    approved_rows = approved_player_identity_manifest_rows(json.loads(manifest_bytes))
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
    runs: list[dict[str, Any]] = [
        repository.player_identity_review_reconciliation(
            approved_rows=approved_rows,
            review_package_sha256=args.review_package_sha256,
            approval_artifact_sha256=args.approval_artifact_sha256,
            reviewed_by=args.reviewed_by,
        )
        for _ in range(2)
    ]
    with Session(repository.engine) as session:
        provider_after = int(
            session.scalar(select(func.count()).select_from(ProviderRequestLogModel)) or 0
        )
    event.remove(repository.engine, "before_cursor_execute", detect_write)
    result = {
        **runs[0],
        "manifest_sha256": manifest_sha256,
        "runs_identical": runs[0] == runs[1],
        "provider_call_delta": provider_after - provider_before,
        "db_write_delta": len(write_statements),
        "write_operations": write_statements,
    }
    if (
        result["status"] != "PASS"
        or not result["runs_identical"]
        or result["provider_call_delta"] != 0
        or result["db_write_delta"] != 0
    ):
        result["status"] = "FAIL"
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
