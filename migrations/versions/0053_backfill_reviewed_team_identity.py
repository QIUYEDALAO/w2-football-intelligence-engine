"""backfill reviewed team identity for three persisted dashboard fixtures

Revision ID: 0053_backfill_reviewed_team_identity
Revises: 0052_drop_retired_future_refresh_checkpoint_plan
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

from w2.factor_model.remediation import canonical_team_payload, provider_crosswalk_payload
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.matchday.repository import _fixture_identity_semantic_hash_from_payload

revision: str = "0053_backfill_reviewed_team_identity"
down_revision: str | None = "0052_drop_retired_future_refresh_checkpoint_plan"
branch_labels: str | None = None
depends_on: str | None = None

_READY = "PROVIDER_PRIMARY_READY"
_REVIEWED_AT = datetime(2026, 8, 12, tzinfo=UTC)
_TEAMS = {
    "225": ("Nacional", "国民队", "Portugal", "primeira_liga", "365scores"),
    "227": ("Santa Clara", "圣克拉拉", "Portugal", "primeira_liga", "365scores"),
    "440": (
        "Belgrano Cordoba",
        "贝尔格拉诺",
        "Argentina",
        "argentina_primera",
        "wikipedia",
    ),
    "441": (
        "Union Santa Fe",
        "圣菲联合",
        "Argentina",
        "argentina_primera",
        "sina_argentina",
    ),
    "449": (
        "Banfield",
        "班菲尔德",
        "Argentina",
        "argentina_primera",
        "sina_banfield",
    ),
    "1065": (
        "Central Cordoba de Santiago",
        "科尔多瓦中央",
        "Argentina",
        "argentina_primera",
        "sina_argentina",
    ),
}
_FIXTURES = {
    "1493049": ("argentina_primera", "128", "449", "440"),
    "1493061": ("argentina_primera", "128", "441", "1065"),
    "1575453": ("primeira_liga", "94", "227", "225"),
}
_SOURCES = {
    "365scores": (
        "https://www.365scores.com/zh/football/match/liga-portugal-73/"
        "nacional-madeira-santa-clara-894-935-73"
    ),
    "sina_argentina": "https://match.sports.sina.com.cn/football/team_vs.php?id=1853620",
    "sina_banfield": "https://match.sports.sina.com.cn/football/team_vs.php?id=1915188",
    "wikipedia": (
        "https://zh.wikipedia.org/wiki/"
        "%E8%B4%9D%E5%B0%94%E6%8B%89%E8%AF%BA%E7%AB%9E%E6%8A%80%E4%BF%B1%E4%B9%90%E9%83%A8"
    ),
}

_fixture = sa.table(
    "matchday_fixture_identities",
    sa.column("fixture_id", sa.String),
    sa.column("home_w2_team_id", sa.String),
    sa.column("away_w2_team_id", sa.String),
    sa.column("team_identity_status", sa.String),
    sa.column("identity_hash", sa.String),
)


def _json(value: Any) -> dict[str, Any]:
    decoded = json.loads(value) if isinstance(value, str) else value
    return decoded if isinstance(decoded, dict) else {}


def _utc(value: Any) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return parsed.replace(tzinfo=parsed.tzinfo or UTC).astimezone(UTC)


def _fixture_rows(bind: sa.Connection) -> dict[str, sa.RowMapping]:
    rows = bind.execute(
        sa.text(
            "select * from matchday_fixture_identities "
            "where provider='api_football' and provider_fixture_id in "
            "('1493049','1493061','1575453')"
        )
    ).mappings().all()
    if not rows:
        return {}
    if len(rows) != 3:
        raise RuntimeError(f"TEAM_IDENTITY_FIXTURE_SCOPE_PARTIAL:{len(rows)}")
    return {str(row["provider_fixture_id"]): row for row in rows}


def _validate(rows: dict[str, sa.RowMapping]) -> None:
    for fixture_id, (competition, league, home, away) in _FIXTURES.items():
        row = rows[fixture_id]
        teams = _json(row["payload"]).get("teams") or {}
        actual = (
            str(row["competition_id"]),
            str(row["provider_league_id"]),
            str(row["home_provider_team_id"]),
            str(row["away_provider_team_id"]),
            str((teams.get("home") or {}).get("name") or ""),
            str((teams.get("away") or {}).get("name") or ""),
            row["home_w2_team_id"],
            row["away_w2_team_id"],
            str(row["team_identity_status"]),
        )
        expected = (
            competition,
            league,
            home,
            away,
            _TEAMS[home][0],
            _TEAMS[away][0],
            None,
            None,
            "REVIEW_REQUIRED",
        )
        if actual != expected:
            raise RuntimeError(f"TEAM_IDENTITY_FIXTURE_CONFLICT:{fixture_id}")


def _insert_teams(bind: sa.Connection, rows: dict[str, sa.RowMapping]) -> None:
    evidence = {
        str(row[side]): (str(row["identity_hash"]), _utc(row["captured_at"]))
        for row in rows.values()
        for side in ("home_provider_team_id", "away_provider_team_id")
    }
    for team_id, (raw_name, public_name, country, competition, source_key) in _TEAMS.items():
        w2_team_id = f"w2:team:api_football:{team_id}"
        if bind.execute(
            sa.text("select count(*) from canonical_teams where w2_team_id=:id"),
            {"id": w2_team_id},
        ).scalar_one():
            raise RuntimeError(f"TEAM_IDENTITY_CANONICAL_PREEXISTS:{w2_team_id}")
        evidence_hash, valid_from = evidence[team_id]
        canonical = canonical_team_payload(
            provider_team_id=team_id,
            display_name=raw_name,
            country=country,
            created_at=valid_from,
        )
        bind.execute(sa.insert(CanonicalTeamModel.__table__).values(**canonical))
        crosswalk = provider_crosswalk_payload(
            provider_team_id=team_id,
            w2_team_id=w2_team_id,
            competition_id=competition,
            season="2026",
            evidence_hashes=[evidence_hash],
            valid_from=valid_from,
        )
        source = _SOURCES[source_key]
        crosswalk.update(
            review_status="APPROVED",
            reviewed_by="owner-authorized-public-source-review",
            reviewed_at=_REVIEWED_AT,
            source_hashes=[hashlib.sha256(source.encode()).hexdigest()],
            payload={"public_name": public_name, "source_ref": source},
        )
        bind.execute(
            sa.insert(ProviderTeamIdentityCrosswalkModel.__table__).values(**crosswalk)
        )


def _update_fixtures(bind: sa.Connection, rows: dict[str, sa.RowMapping]) -> None:
    for fixture_id, (_, _, home, away) in _FIXTURES.items():
        row = rows[fixture_id]
        home_w2 = f"w2:team:api_football:{home}"
        away_w2 = f"w2:team:api_football:{away}"
        values = {
            "home_w2_team_id": home_w2,
            "away_w2_team_id": away_w2,
            "team_identity_status": _READY,
        }
        values["identity_hash"] = _fixture_identity_semantic_hash_from_payload(
            {**row, **values}
        )
        bind.execute(
            sa.update(_fixture)
            .where(_fixture.c.fixture_id == row["fixture_id"])
            .values(**values)
        )


def upgrade() -> None:
    bind = op.get_bind()
    rows = _fixture_rows(bind)
    if not rows:
        return
    _validate(rows)
    _insert_teams(bind, rows)
    _update_fixtures(bind, rows)


def downgrade() -> None:
    # Identity may be referenced by post-match evidence after deployment.
    pass
