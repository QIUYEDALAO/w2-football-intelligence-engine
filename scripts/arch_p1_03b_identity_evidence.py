#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.ingestion_models import ProviderRequestLogModel
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    approved_player_identity_manifest_rows,
)

DEFAULT_FIXTURES = ("1494212", "1494213", "1494214", "1494215", "1494216")
GENERATOR_PATH = "scripts/arch_p1_03b_identity_evidence.py"
SCHEMA_PATH = "contracts/governance/architecture_acceptance_lifecycle.v1.schema.json"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone")
    return parsed.astimezone(UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only ARCH-P1-03B identity evidence.")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--fixtures", nargs="+", default=list(DEFAULT_FIXTURES))
    parser.add_argument("--m3-fixtures", nargs="*", default=[])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-package-sha256", required=True)
    parser.add_argument("--approval-artifact-sha256", required=True)
    parser.add_argument("--reviewed-by", required=True)
    parser.add_argument("--output", type=Path)
    return parser


def _replay_argv(args: argparse.Namespace) -> list[str]:
    argv = [
        "python3",
        GENERATOR_PATH,
        "--as-of",
        args.as_of,
        "--fixtures",
        *args.fixtures,
    ]
    if args.m3_fixtures:
        argv.extend(("--m3-fixtures", *args.m3_fixtures))
    argv.extend(
        (
            "--manifest",
            args.manifest.as_posix(),
            "--review-package-sha256",
            args.review_package_sha256,
            "--approval-artifact-sha256",
            args.approval_artifact_sha256,
            "--reviewed-by",
            args.reviewed_by,
        )
    )
    return argv


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    as_of = _parse_time(args.as_of)
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

    def force_read_only(connection: Any) -> None:
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")

    event.listen(repository.engine, "before_cursor_execute", detect_write)
    event.listen(repository.engine, "begin", force_read_only)
    try:
        with Session(repository.engine) as session:
            provider_before = int(
                session.scalar(select(func.count()).select_from(ProviderRequestLogModel)) or 0
            )
            migration_head = str(
                session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
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
                    approved_rows=approved_rows,
                    review_package_sha256=args.review_package_sha256,
                    approval_artifact_sha256=args.approval_artifact_sha256,
                    reviewed_by=args.reviewed_by,
                )
                for _ in range(3)
            ]
            for fixture_id in args.m3_fixtures
        }
        with Session(repository.engine) as session:
            provider_after = int(
                session.scalar(select(func.count()).select_from(ProviderRequestLogModel)) or 0
            )
    finally:
        event.remove(repository.engine, "begin", force_read_only)
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
    report = {
        "schema_version": "w2.arch_p1_03b_identity_acceptance.v1",
        "as_of": as_of.isoformat(),
        "candidate_audit": audit,
        "candidate_audit_count": len(audit),
        "fixture_matrix": matrix,
        "m3_evidence": {fixture_id: runs[0] for fixture_id, runs in m3_runs.items()},
        "three_run_stability": stability,
        "provider_call_delta": provider_after - provider_before,
        "db_write_delta": len(write_statements),
        "write_operations": write_statements,
    }
    if report["provider_call_delta"] != 0 or report["db_write_delta"] != 0:
        raise RuntimeError("IDENTITY_EVIDENCE_READ_ONLY_INVARIANT_VIOLATED")
    if args.output is None:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    replay_argv = _replay_argv(args)
    generator_file = Path(__file__).resolve()
    artifact = {
        "schema_version": "w2.architecture_acceptance_lifecycle.v1",
        "schema_path": SCHEMA_PATH,
        "artifact_kind": "REAL_PRODUCER_OUTPUT_EVIDENCE",
        "task_id": "ARCH-P1-03B-R1",
        "generator": {
            "path": GENERATOR_PATH,
            "symbol": "main",
            "file_sha256": hashlib.sha256(generator_file.read_bytes()).hexdigest(),
        },
        "replay": {
            "argv": replay_argv,
            "output_flag": "--output",
            "command_sha256": _canonical_sha256(replay_argv),
        },
        "migration_head": migration_head,
        "captured_at": as_of.isoformat(),
        "source_identity": {
            "database_engine": repository.engine.dialect.name,
            "database_host": repository.engine.url.host or "local",
            "database_name": repository.engine.url.database or "unknown",
            "manifest_sha256": manifest_sha256,
        },
        "row_count": len(audit)
        + len(matrix)
        + sum(len(run[0]["rows"]) for run in m3_runs.values()),
        "result_fingerprint": _canonical_sha256(report),
        "provider_call_delta": 0,
        "db_write_delta": 0,
        "subject_head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "artifact_sha256": "",
    }
    artifact["artifact_sha256"] = _canonical_sha256(
        {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    )
    args.output.write_bytes(_canonical_bytes(artifact) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
