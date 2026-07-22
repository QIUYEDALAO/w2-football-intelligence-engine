from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from w2.infrastructure.database import create_engine  # noqa: E402
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel  # noqa: E402
from w2.infrastructure.persistence.matchday_intake_models import (  # noqa: E402
    MatchdayEndpointCaptureModel,
)
from w2.ingestion.future_refresh import (  # noqa: E402
    fixture_id_from_payload,
    iso,
    kickoff_from_payload,
    sha256_payload,
)
from w2.matchday.intake_v2 import normalize_matchday_odds_payload  # noqa: E402
from w2.matchday.repository import MatchdayRuntimeRepository  # noqa: E402


def _iso(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.isoformat().replace("+00:00", "Z")


def _fixture_id(value: str) -> str:
    return value if value.startswith("api_football:") else f"api_football:{value}"


def _latest_capture(session: Session, fixture_id: str) -> MatchdayEndpointCaptureModel | None:
    return session.scalar(
        select(MatchdayEndpointCaptureModel)
        .where(
            MatchdayEndpointCaptureModel.endpoint == "odds",
            MatchdayEndpointCaptureModel.fixture_id == _fixture_id(fixture_id),
            MatchdayEndpointCaptureModel.capture_status == "CAPTURED",
        )
        .order_by(MatchdayEndpointCaptureModel.provider_captured_at.desc())
        .limit(1)
    )


def _fixture_identity_from_capture(
    session: Session,
    *,
    fixture_id: str,
    competition_id: str,
) -> dict[str, Any] | None:
    """Recover an identity from the captured fixtures payload before odds replay.

    The recovery path must never create odds-only fixtures.  Historic captures
    predate the identity write, so locate the matching fixture in the source
    endpoint capture and rebuild the same identity shape used by live refresh.
    """
    provider_fixture_id = _fixture_id(fixture_id).removeprefix("api_football:")
    captures = session.scalars(
        select(MatchdayEndpointCaptureModel)
        .where(
            MatchdayEndpointCaptureModel.endpoint == "fixtures",
            MatchdayEndpointCaptureModel.competition_id == competition_id,
            MatchdayEndpointCaptureModel.capture_status == "CAPTURED",
        )
        .order_by(MatchdayEndpointCaptureModel.provider_captured_at.desc())
    )
    for capture in captures:
        raw = session.get(RawPayloadModel, capture.raw_payload_sha256)
        if raw is None:
            continue
        response = raw.payload.get("response") if isinstance(raw.payload, dict) else None
        if not isinstance(response, list):
            continue
        item = next(
            (
                value
                for value in response
                if isinstance(value, dict) and fixture_id_from_payload(value) == provider_fixture_id
            ),
            None,
        )
        if item is None:
            continue
        kickoff = kickoff_from_payload(item)
        if kickoff is None:
            return None
        fixture = item.get("fixture") if isinstance(item.get("fixture"), dict) else {}
        league = item.get("league") if isinstance(item.get("league"), dict) else {}
        teams = item.get("teams") if isinstance(item.get("teams"), dict) else {}
        status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        identity_body = {
            "fixture_id": _fixture_id(fixture_id),
            "provider": "api_football",
            "provider_fixture_id": provider_fixture_id,
            "competition_id": competition_id,
            "provider_league_id": str(league.get("id") or ""),
            "season": str(league.get("season") or ""),
            "kickoff_utc": iso(kickoff),
            "fixture_status": str(status.get("short") or ""),
            "home_provider_team_id": str(home.get("id") or ""),
            "away_provider_team_id": str(away.get("id") or ""),
            "home_w2_team_id": None,
            "away_w2_team_id": None,
            "team_identity_status": "REVIEW_REQUIRED",
            "raw_payload_sha256": capture.raw_payload_sha256,
            "endpoint_capture_id": capture.capture_id,
            "captured_at": iso(capture.provider_captured_at),
            "payload": item,
            "schema_version": "MatchdayFixtureIdentityV1",
        }
        return {**identity_body, "identity_hash": sha256_payload(identity_body)}
    return None


def materialize(
    fixture_ids: list[str],
    *,
    competition_id: str,
    source_revision: str,
) -> dict[str, Any]:
    engine = create_engine()
    repository = MatchdayRuntimeRepository(engine=engine)
    now = datetime.now(UTC)
    results: list[dict[str, Any]] = []
    total_rows = 0
    total_rejections = 0
    with Session(engine) as session:
        for fixture_id in fixture_ids:
            identity = _fixture_identity_from_capture(
                session,
                fixture_id=fixture_id,
                competition_id=competition_id,
            )
            if identity is None:
                results.append(
                    {
                        "fixture_id": fixture_id,
                        "status": "FIXTURE_IDENTITY_CAPTURE_MISSING",
                        "inserted": 0,
                        "rejected": 0,
                    }
                )
                continue
            identity_inserted = repository.insert_fixture_identities([identity])
            capture = _latest_capture(session, fixture_id)
            if capture is None:
                results.append(
                    {
                        "fixture_id": fixture_id,
                        "status": "NO_CAPTURE",
                        "inserted": 0,
                        "rejected": 0,
                    }
                )
                continue
            raw = session.get(RawPayloadModel, capture.raw_payload_sha256)
            if raw is None:
                results.append(
                    {
                        "fixture_id": fixture_id,
                        "status": "RAW_PAYLOAD_MISSING",
                        "capture_id": capture.capture_id,
                        "inserted": 0,
                        "rejected": 0,
                    }
                )
                continue
            rows, rejected = normalize_matchday_odds_payload(
                raw.payload,
                captured_at=capture.provider_captured_at,
                ingested_at=now,
                raw_payload_sha256=capture.raw_payload_sha256,
                source_revision=source_revision,
                capture_id=capture.capture_id,
                competition_id=competition_id,
            )
            inserted = repository.insert_market_observations(rows)
            total_rows += inserted
            total_rejections += len(rejected)
            results.append(
                {
                    "fixture_id": fixture_id,
                    "status": "MATERIALIZED",
                    "fixture_identity_inserted": identity_inserted,
                    "capture_id": capture.capture_id,
                    "captured_at": _iso(capture.provider_captured_at),
                    "raw_payload_sha256": capture.raw_payload_sha256,
                    "normalized": len(rows),
                    "inserted": inserted,
                    "rejected": len(rejected),
                }
            )
    return {
        "generated_at_utc": _iso(now),
        "competition_id": competition_id,
        "source_revision": source_revision,
        "fixture_count": len(fixture_ids),
        "inserted": total_rows,
        "rejected": total_rejections,
        "provider_calls": 0,
        "candidate": False,
        "formal_recommendation": False,
        "fixtures": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize canonical odds observations from already captured "
            "matchday odds payloads."
        ),
    )
    parser.add_argument("--competition-id", required=True)
    parser.add_argument("--source-revision", default="LOCAL_UNDEPLOYED")
    parser.add_argument("fixture_ids", nargs="+")
    args = parser.parse_args()
    print(
        json.dumps(
            materialize(
                args.fixture_ids,
                competition_id=args.competition_id,
                source_revision=args.source_revision,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
