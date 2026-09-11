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
sys.path.insert(0, str(ROOT))
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
from w2.prematch.repository import project_exact_eval_02b_pairs  # noqa: E402


def _diagnostic_fixture_aliases(fixture_id: object) -> frozenset[str]:
    """Every spelling of one fixture id, so the diagnostic can scope onto it.

    The evaluation rows carry the ``api_football:`` prefixed spelling while the
    lineup events and the reservation carry the bare provider id, so scoping on a
    single literal would silently match nothing.
    """
    text = str(fixture_id or "").strip()
    if not text:
        return frozenset()
    bare = text.removeprefix("api_football:")
    return frozenset({text, bare, f"api_football:{bare}"})


def _pair_evaluation_diagnostic(
    engine: object, *, fixture_aliases: frozenset[str]
) -> list[dict[str, object]]:
    """Pre/Post inputs as the pairing sees them, for this run's fixture only.

    This used to read every lineup event, fixture identity and evaluation in the
    database. Against a shared instance that put other runs' rows into this run's
    failure output, so an operator could not tell which rows belonged to the
    failure being diagnosed. With no fixture resolved it returns nothing rather
    than falling back to an unscoped dump.
    """
    if not fixture_aliases:
        return []

    from sqlalchemy import or_  # noqa: PLC0415
    from sqlalchemy.orm import Session  # noqa: PLC0415

    from w2.infrastructure.persistence.dynamic_prematch_models import (  # noqa: PLC0415
        DynamicPrematchEvaluationModel,
        LineupConfirmedEventModel,
    )
    from w2.infrastructure.persistence.matchday_intake_models import (  # noqa: PLC0415
        MatchdayFixtureIdentityModel,
    )
    from w2.prematch.repository import (  # noqa: PLC0415
        _eligible_pair_evaluation,
        _fixture_alias_index,
    )

    scope = sorted(fixture_aliases)
    rows: list[dict[str, object]] = []
    with Session(engine) as session:  # type: ignore[arg-type]
        for event in (
            session.query(LineupConfirmedEventModel)
            .filter(LineupConfirmedEventModel.fixture_id.in_(scope))
            .all()
        ):
            rows.append(
                {
                    "kind": "lineup_event",
                    "fixture_id": event.fixture_id,
                    "captured_at": str(event.captured_at),
                    "lineup_input_hash": event.lineup_input_hash,
                }
            )
        fixtures = (
            session.query(MatchdayFixtureIdentityModel)
            .filter(
                or_(
                    MatchdayFixtureIdentityModel.fixture_id.in_(scope),
                    MatchdayFixtureIdentityModel.provider_fixture_id.in_(scope),
                )
            )
            .all()
        )
        alias_index = _fixture_alias_index(fixtures)
        for row in (
            session.query(DynamicPrematchEvaluationModel)
            .filter(DynamicPrematchEvaluationModel.fixture_id.in_(scope))
            .all()
        ):
            eligible = None
            for fixture in fixtures:
                eligible = _eligible_pair_evaluation(row, fixture, alias_index)
                if eligible is not None:
                    break
            rows.append(
                {
                    "kind": "evaluation",
                    "fixture_id": row.fixture_id,
                    "market": row.market,
                    "original_state": row.original_state,
                    "evaluated_at": str(row.evaluated_at),
                    "lineup_input_hash": getattr(row, "lineup_input_hash", None),
                    "pair_eligible": eligible is not None,
                    "blockers": (row.payload or {}).get("blockers"),
                    "quote_scope": (list(eligible.quote_scope) if eligible is not None else None),
                    "capture_at": str(eligible.capture_at) if eligible is not None else None,
                }
            )
    return rows


from w2.providers.api_football import ApiFootballClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the isolated staged Gate-A canary.")
    parser.add_argument("--authorization-file", type=Path, required=True)
    parser.add_argument("--fixture-id")
    parser.add_argument("--competition-id", required=True)
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
        value = subprocess.check_output(["git", "rev-parse", revision], cwd=ROOT, text=True).strip()
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
    # Bound before the try so the failure diagnostic below can scope onto the
    # fixture this run actually selected even when the failure happened later.
    audit = None
    try:
        authorization = GateARuntimeAuthorization.load(args.authorization_file, **trust_kwargs)
        identity = _runtime_identity(authorization)
        policy = load_refresh_policy(competition_id=args.competition_id)
        authorization.validate_scope(
            competition_id=args.competition_id,
            season=args.season,
            policy_season=policy.season,
            policy_provider_league_id=policy.provider_league_id,
            policy_config_hash=policy.config_hash,
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
        # Evidence is only written after validation passes, so a rejected run
        # left nothing to inspect and the bare error code was all the operator
        # got. Emit why the exact Pre/Post projection produced what it did --
        # that is the one input to the counts that is derived rather than
        # persisted, so it cannot be recovered from the database afterwards.
        try:
            selected = args.fixture_id
            if not selected and audit is not None:
                chosen = (audit.result or {}).get("selected_market_fixture_ids") or []
                selected = chosen[0] if chosen else None
            aliases = _diagnostic_fixture_aliases(selected)
            projection = project_exact_eval_02b_pairs(create_engine())
            print(
                json.dumps(
                    {
                        "pair_projection_diagnostic": {
                            # Which run this describes. Without it a scoped
                            # diagnostic is indistinguishable from an empty one.
                            "task_key": key,
                            "fixture_scope": sorted(aliases),
                            "pairs": sum(
                                pair.identity.canonical_fixture_id in aliases
                                for pair in projection.pairs
                            ),
                            "evaluations": _pair_evaluation_diagnostic(
                                create_engine(), fixture_aliases=aliases
                            ),
                            "exclusions": [
                                {
                                    "fixture_id": exclusion.fixture_id,
                                    "market": exclusion.market,
                                    "reason": exclusion.reason,
                                }
                                for exclusion in projection.exclusions
                                if exclusion.fixture_id in aliases
                            ],
                        }
                    },
                    default=str,
                ),
                file=sys.stderr,
            )
        except Exception as diagnostic_error:  # noqa: BLE001
            # Diagnostics must never mask the real failure above.
            print(
                f"pair_projection_diagnostic_unavailable: {diagnostic_error}",
                file=sys.stderr,
            )
        return 1
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "task_key": key,
                "fixture_id": audit.result["selected_market_fixture_ids"][0],
                "request_count": audit.result["request_count"],
                "evidence": str(args.evidence_output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
