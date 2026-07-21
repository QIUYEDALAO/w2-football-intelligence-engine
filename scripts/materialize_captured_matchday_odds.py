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
