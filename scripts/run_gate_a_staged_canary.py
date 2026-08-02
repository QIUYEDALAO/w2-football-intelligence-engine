#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from scripts.run_prematch_refresh import (  # noqa: E402
    ExactCodeIdentity,
    exact_code_identity,
    parse_utc,
    planned_task_key,
)
from scripts.validate_gate_a_offline_evidence import _write_atomic  # noqa: E402

from w2.config import get_settings  # noqa: E402
from w2.infrastructure.database import create_engine  # noqa: E402
from w2.ingestion.future_refresh import (  # noqa: E402
    load_refresh_policy,
    run_staged_gate_a_canary_task,
)
from w2.monitoring.readiness import schema_check  # noqa: E402
from w2.operations.gate_a import (  # noqa: E402
    GateAError,
    GateARuntimeAuthorization,
    reserve_gate_a_run,
)
from w2.operations.gate_a_evidence import (  # noqa: E402
    GateAEvidenceError,
    validate_gate_a_evidence,
)
from w2.operations.gate_a_evidence_producer import produce_gate_a_evidence  # noqa: E402
from w2.providers.api_football import ApiFootballClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the isolated staged Gate-A canary.")
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--competition-id", default="world_cup_2026")
    parser.add_argument("--season", required=True)
    parser.add_argument("--interval-seconds", type=int, default=900)
    parser.add_argument("--now-utc")
    parser.add_argument("--persistence", choices=("db",), required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--offline-fake-provider-base-url")
    parser.add_argument("--offline-trust-store", type=Path)
    return parser


def _runtime_identity(authorization: GateARuntimeAuthorization) -> ExactCodeIdentity:
    if authorization.execution_mode != "IMMUTABLE_IMAGE":
        return exact_code_identity()
    digest = os.environ.get("W2_RUNTIME_ARTIFACT_DIGEST", "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise GateAError("GATE_A_RUNTIME_ARTIFACT_IDENTITY_INVALID")
    return ExactCodeIdentity(
        head=_git_value("HEAD"),
        tree=_git_value("HEAD^{tree}"),
        execution_mode="IMMUTABLE_IMAGE",
        runtime_artifact_digest=digest,
    )


def _git_value(revision: str) -> str:
    import subprocess

    try:
        value = subprocess.check_output(
            ["git", "rev-parse", revision], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GateAError("GATE_A_EXACT_CODE_IDENTITY_UNAVAILABLE") from exc
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise GateAError("GATE_A_EXACT_CODE_IDENTITY_UNAVAILABLE")
    return value


def _offline_fake_client(
    base_url: str | None,
    trust_store: Path | None,
) -> ApiFootballClient | None:
    if base_url is None and trust_store is None:
        return None
    if base_url is None or trust_store is None:
        raise GateAError("GATE_A_OFFLINE_FAKE_MODE_INCOMPLETE")
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise GateAError("GATE_A_OFFLINE_FAKE_PROVIDER_NOT_LOOPBACK")
    return ApiFootballClient(
        allow_live=True,
        allowed_live_endpoints=frozenset({"status", "fixtures", "odds", "lineups"}),
        base_url=base_url.rstrip("/"),
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    now = parse_utc(args.now_utc)
    key = planned_task_key(
        competition_id=args.competition_id,
        season=args.season,
        now=now,
        interval_seconds=args.interval_seconds,
    )
    trust_kwargs = (
        {"trust_store_path": args.offline_trust_store}
        if args.offline_trust_store is not None
        else {}
    )
    try:
        authorization = GateARuntimeAuthorization.load(args.authorization_file, **trust_kwargs)
        identity = _runtime_identity(authorization)
        policy = load_refresh_policy(competition_id=args.competition_id)
        authorization.validate_scope(
            competition_id=args.competition_id,
            season=args.season,
            policy_season=policy.season,
            persistence=args.persistence,
            task_key=key,
            fixture_id=args.fixture_id,
            exact_head=identity.head,
            exact_tree=identity.tree,
            execution_mode=identity.execution_mode,
            runtime_artifact_digest=identity.runtime_artifact_digest,
            complete_checkout_manifest_sha256=identity.complete_checkout_manifest_sha256,
            now=datetime.now(UTC),
        )
        client = _offline_fake_client(
            args.offline_fake_provider_base_url,
            args.offline_trust_store,
        )
        ready, detail = schema_check(get_settings())
        if not ready:
            raise GateAError(f"GATE_A_MIGRATION_HEAD_MISMATCH:{detail}")
        owner = f"staged:{hashlib.sha256(key.encode()).hexdigest()[:16]}"
        reservation = reserve_gate_a_run(authorization, owner=owner, now=datetime.now(UTC))
        audit = run_staged_gate_a_canary_task(
            task_id=f"{key}:staged-canary",
            key=key,
            queued_at=now,
            competition_id=args.competition_id,
            season=args.season,
            fixture_id=args.fixture_id,
            runtime_authorization=authorization,
            provider_call_reservation=reservation,
            now=now,
            client=client,
        )
        if audit.status != "COMPLETED":
            print(json.dumps(audit.__dict__, default=str), file=sys.stderr)
            return 1
        evidence = produce_gate_a_evidence(
            engine=create_engine(),
            authorization_source=args.authorization_file,
            **trust_kwargs,
        )
        validate_gate_a_evidence(
            evidence,
            authorization=authorization,
            authorization_source_sha256=hashlib.sha256(
                args.authorization_file.read_bytes()
            ).hexdigest(),
        )
        _write_atomic(args.evidence_output, evidence)
    except (GateAError, GateAEvidenceError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "task_key": key,
                "fixture_id": args.fixture_id,
                "request_count": audit.result["request_count"],
                "evidence": str(args.evidence_output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
