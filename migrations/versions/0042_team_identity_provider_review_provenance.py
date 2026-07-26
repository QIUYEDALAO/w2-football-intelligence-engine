"""ARCH-P1-03 M2A: add review provenance to the team identity authority and
migrate the legacy team crosswalks into transfermarkt provider rows.

No new identity table. Adds review_status / reviewed_by / reviewed_at /
source_hashes / payload to ``provider_team_identity_crosswalks`` and, for every
APPROVED ``team_identity_crosswalks`` row, (a) backfills the matching
api_football authority row's review provenance and (b) inserts a transfermarkt
provider row pointing at the same canonical ``w2_team_id``. Fail-closed on any
missing or ambiguous canonical mapping (no guessing).

Revision ID: 0042_team_identity_provider_review_provenance
Revises: 0041_converge_odds_history_and_projection
Create Date: 2026-07-26 00:00:00.000000
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

from w2.matchday.intake_v2 import stable_hash


def _coerce_dt(value: Any) -> Any:
    """Datetime columns need real datetimes; postgres returns them, sqlite text."""
    if value is None or isinstance(value, (datetime, date)):
        return value
    return datetime.fromisoformat(str(value))


def _coerce_json(value: Any) -> Any:
    """JSON columns need dict/list; postgres json returns objects, sqlite text."""
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(str(value))

revision: str = "0042_team_identity_provider_review_provenance"
down_revision: str | None = "0041_converge_odds_history_and_projection"
branch_labels: str | None = None
depends_on: str | None = None

_TABLE = "provider_team_identity_crosswalks"
_NEW_COLUMNS = (
    ("review_status", sa.String(length=64)),
    ("reviewed_by", sa.String(length=128)),
    ("reviewed_at", sa.DateTime(timezone=True)),
    ("source_hashes", sa.JSON()),
    ("payload", sa.JSON()),
)
_PROVIDER_PRIMARY_READY = "PROVIDER_PRIMARY_READY"

# Lightweight table handle so SQLAlchemy serializes JSON portably (postgres/sqlite).
_ptic = sa.table(
    _TABLE,
    sa.column("id", sa.String),
    sa.column("provider", sa.String),
    sa.column("provider_team_id", sa.String),
    sa.column("w2_team_id", sa.String),
    sa.column("competition_id", sa.String),
    sa.column("season", sa.String),
    sa.column("valid_from", sa.DateTime(timezone=True)),
    sa.column("valid_to", sa.DateTime(timezone=True)),
    sa.column("identity_status", sa.String),
    sa.column("evidence_hashes", sa.JSON),
    sa.column("identity_hash", sa.String),
    sa.column("review_status", sa.String),
    sa.column("reviewed_by", sa.String),
    sa.column("reviewed_at", sa.DateTime(timezone=True)),
    sa.column("source_hashes", sa.JSON),
    sa.column("payload", sa.JSON),
)


def _transfermarkt_identity_hash(
    *, provider_team_id: str, w2_team_id: str, competition_id: str, season: str
) -> str:
    payload = {
        "schema_version": "ProviderTeamIdentityCrosswalkV1",
        "provider": "transfermarkt",
        "provider_team_id": provider_team_id,
        "w2_team_id": w2_team_id,
        "competition_id": competition_id,
        "season": season,
        "identity_status": _PROVIDER_PRIMARY_READY,
        "scope_note": "Transfermarkt provider identity migrated from team_identity_crosswalks.",
    }
    return stable_hash(payload)


def upgrade() -> None:
    for name, col_type in _NEW_COLUMNS:
        op.add_column(_TABLE, sa.Column(name, col_type, nullable=True))

    bind = op.get_bind()
    legacy = bind.execute(
        sa.text(
            "select id, api_football_team_id, transfermarkt_club_id, competition_id, "
            "review_status, reviewed_by, reviewed_at, source_sha256, payload, "
            "valid_from, valid_to from team_identity_crosswalks"
        )
    ).mappings().all()

    blockers: list[str] = []
    for row in legacy:
        if str(row["review_status"] or "").upper() != "APPROVED":
            continue
        api_id = str(row["api_football_team_id"] or "")
        tm_id = str(row["transfermarkt_club_id"] or "")
        comp = str(row["competition_id"] or "")
        if not api_id or not tm_id:
            blockers.append(f"{row['id']}:MISSING_API_OR_TM_ID")
            continue

        # Resolve canonical w2_team_id via the existing api_football authority row
        # (never by parsing the id). Require exactly one.
        authority = bind.execute(
            sa.text(
                "select w2_team_id, season from provider_team_identity_crosswalks "
                "where provider='api_football' and provider_team_id=:pid "
                "and competition_id=:comp"
            ),
            {"pid": api_id, "comp": comp},
        ).mappings().all()
        if len(authority) != 1:
            blockers.append(f"{row['id']}:AUTHORITY_MAPPINGS={len(authority)}")
            continue
        w2 = str(authority[0]["w2_team_id"])
        season = str(authority[0]["season"])

        source_hashes = [row["source_sha256"]] if row["source_sha256"] else []

        # (a) Backfill the api_football authority row's review provenance.
        bind.execute(
            sa.update(_ptic)
            .where(
                _ptic.c.provider == "api_football",
                _ptic.c.provider_team_id == api_id,
                _ptic.c.competition_id == comp,
            )
            .values(
                review_status=row["review_status"],
                reviewed_by=row["reviewed_by"],
                reviewed_at=_coerce_dt(row["reviewed_at"]),
                source_hashes=source_hashes,
                payload=_coerce_json(row["payload"]),
            )
        )

        # (b) Insert the transfermarkt provider row, same w2_team_id. If a target
        # row already exists it must reconcile exactly against what this migration
        # would write; a divergent existing row is a blocker, never skipped.
        row_id = f"transfermarkt:{tm_id}:{comp}:{season}"
        expected_identity_hash = _transfermarkt_identity_hash(
            provider_team_id=tm_id, w2_team_id=w2, competition_id=comp, season=season
        )
        existing = bind.execute(
            sa.text(
                "select id, w2_team_id, identity_status, identity_hash, review_status, "
                "reviewed_by from provider_team_identity_crosswalks "
                "where provider='transfermarkt' and provider_team_id=:pid "
                "and competition_id=:comp and season=:season"
            ),
            {"pid": tm_id, "comp": comp, "season": season},
        ).mappings().all()
        if existing:
            if len(existing) != 1:
                blockers.append(f"{row['id']}:TRANSFERMARKT_TARGET_ROWS={len(existing)}")
                continue
            target = existing[0]
            divergences = [
                field
                for field, expected in (
                    ("id", row_id),
                    ("w2_team_id", w2),
                    ("identity_status", _PROVIDER_PRIMARY_READY),
                    ("identity_hash", expected_identity_hash),
                    ("review_status", row["review_status"]),
                    ("reviewed_by", row["reviewed_by"]),
                )
                if target[field] != expected
            ]
            if divergences:
                blockers.append(
                    f"{row['id']}:TRANSFERMARKT_TARGET_DIVERGENT:{','.join(divergences)}"
                )
            continue
        bind.execute(
            sa.insert(_ptic).values(
                id=row_id,
                provider="transfermarkt",
                provider_team_id=tm_id,
                w2_team_id=w2,
                competition_id=comp,
                season=season,
                valid_from=_coerce_dt(row["valid_from"]),
                valid_to=_coerce_dt(row["valid_to"]),
                identity_status=_PROVIDER_PRIMARY_READY,
                evidence_hashes=source_hashes,
                identity_hash=expected_identity_hash,
                review_status=row["review_status"],
                reviewed_by=row["reviewed_by"],
                reviewed_at=_coerce_dt(row["reviewed_at"]),
                source_hashes=source_hashes,
                payload=_coerce_json(row["payload"]),
            )
        )

    if blockers:
        raise RuntimeError(
            "ARCH-P1-03 M2A team identity migration blocked (no guessing): "
            + "; ".join(sorted(blockers))
        )


def downgrade() -> None:
    """Remove only the transfermarkt rows this migration owns.

    Ownership is proven per row, never by ``provider='transfermarkt'`` alone:
    the row id must match this migration's id format *and* its identity_hash
    must equal the hash recomputed from this migration's own payload shape.
    Transfermarkt rows written by anything else are left untouched.
    """
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "select id, provider_team_id, w2_team_id, competition_id, season, identity_hash "
            "from provider_team_identity_crosswalks where provider='transfermarkt'"
        )
    ).mappings().all()
    for row in rows:
        owned_id = (
            f"transfermarkt:{row['provider_team_id']}:{row['competition_id']}:{row['season']}"
        )
        owned_hash = _transfermarkt_identity_hash(
            provider_team_id=str(row["provider_team_id"]),
            w2_team_id=str(row["w2_team_id"]),
            competition_id=str(row["competition_id"]),
            season=str(row["season"]),
        )
        if row["id"] != owned_id or row["identity_hash"] != owned_hash:
            continue
        bind.execute(
            sa.text("delete from provider_team_identity_crosswalks where id=:id"),
            {"id": row["id"]},
        )
    for name, _ in _NEW_COLUMNS:
        op.drop_column(_TABLE, name)
