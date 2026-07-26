from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine as sa_create_engine

from w2.identity import CanonicalIdentityRepository
from w2.infrastructure.persistence.factor_model_models import (
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.models import Base

AS_OF = datetime(2026, 7, 26, tzinfo=UTC)


def _engine():
    engine = sa_create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _provider_row(**over):
    base = dict(
        id="api_football:100:allsvenskan:2026",
        provider="api_football",
        provider_team_id="100",
        w2_team_id="w2:team:api_football:100",
        competition_id="allsvenskan",
        season="2026",
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_to=None,
        identity_status="PROVIDER_PRIMARY_READY",
        evidence_hashes=[],
        identity_hash="ih100",
    )
    base.update(over)
    return ProviderTeamIdentityCrosswalkModel(**base)


def _seed(engine, *rows):
    from sqlalchemy.orm import Session

    # canonical_teams FK target must exist
    with engine.begin() as conn:
        from sqlalchemy import text

        for index, w2 in enumerate(sorted({r.w2_team_id for r in rows})):
            conn.execute(
                text(
                    "insert into canonical_teams (w2_team_id, display_name, country, "
                    "active_status, created_at, identity_hash, payload) values "
                    "(:w2,'T','SE','ACTIVE','2026-01-01T00:00:00+00:00',:h,'{}')"
                ),
                {"w2": w2, "h": f"h{index}"},
            )
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


def test_resolve_team_returns_canonical_w2_id() -> None:
    engine = _engine()
    _seed(engine, _provider_row())
    repo = CanonicalIdentityRepository(engine=engine)
    assert (
        repo.resolve_team("api_football", "100", "allsvenskan", "2026", AS_OF)
        == "w2:team:api_football:100"
    )


def test_provider_identity_for_team_reverse_lookup() -> None:
    engine = _engine()
    _seed(
        engine,
        _provider_row(),
        _provider_row(
            id="transfermarkt:999:allsvenskan:2026",
            provider="transfermarkt",
            provider_team_id="999",
            identity_hash="ih999",
        ),
    )
    repo = CanonicalIdentityRepository(engine=engine)
    assert (
        repo.provider_identity_for_team(
            "w2:team:api_football:100", "transfermarkt", "allsvenskan", "2026", AS_OF
        )
        == "999"
    )


def test_resolve_team_unknown_provider_returns_none_not_constructed() -> None:
    engine = _engine()
    _seed(engine, _provider_row())
    repo = CanonicalIdentityRepository(engine=engine)
    # Unknown provider team id must not be auto-constructed into an identity.
    assert repo.resolve_team("api_football", "does-not-exist", "allsvenskan", "2026", AS_OF) is None


def test_resolve_team_respects_validity_window() -> None:
    engine = _engine()
    _seed(
        engine,
        _provider_row(valid_to=datetime(2026, 6, 1, tzinfo=UTC)),  # expired before AS_OF
    )
    repo = CanonicalIdentityRepository(engine=engine)
    assert repo.resolve_team("api_football", "100", "allsvenskan", "2026", AS_OF) is None


def test_player_methods_empty_and_never_fabricate() -> None:
    engine = _engine()
    repo = CanonicalIdentityRepository(engine=engine)
    w2 = "w2:team:api_football:100"
    assert repo.resolve_player("p1", w2, "allsvenskan", "2026", AS_OF) is None
    assert repo.approved_players_for_team(w2, "allsvenskan", "2026", AS_OF) == []


def test_mapping_in_session_excludes_rows_outside_validity_window() -> None:
    from sqlalchemy.orm import Session

    engine = _engine()
    _seed(
        engine,
        _provider_row(),  # valid
        _provider_row(
            id="api_football:200:allsvenskan:2026",
            provider_team_id="200",
            w2_team_id="w2:team:api_football:200",
            identity_hash="ih200",
            valid_to=datetime(2026, 6, 1, tzinfo=UTC),  # expired before AS_OF
        ),
    )
    with Session(engine) as session:
        mapping = CanonicalIdentityRepository.provider_team_mapping_in_session(
            session,
            provider="api_football",
            competition="allsvenskan",
            season="2026",
            as_of=AS_OF,
        )
    assert mapping == {"100": "w2:team:api_football:100"}


def test_mapping_in_session_drops_ambiguous_provider_id() -> None:
    from sqlalchemy.orm import Session

    engine = _engine()
    _seed(
        engine,
        _provider_row(),
        # same provider team id resolving to a second canonical team
        _provider_row(
            id="api_football:100:allsvenskan:2026:dup",
            w2_team_id="w2:team:api_football:999",
            identity_hash="ihdup",
            valid_from=datetime(2026, 2, 1, tzinfo=UTC),
        ),
    )
    with Session(engine) as session:
        mapping = CanonicalIdentityRepository.provider_team_mapping_in_session(
            session,
            provider="api_football",
            competition="allsvenskan",
            season="2026",
            as_of=AS_OF,
        )
    # Fail closed: ambiguous provider id yields no identity at all.
    assert mapping == {}


def test_reverse_mapping_drops_ambiguous_canonical_team() -> None:
    """One canonical team resolving to two provider source ids must fail closed."""
    from sqlalchemy.orm import Session

    engine = _engine()
    _seed(
        engine,
        _provider_row(),
        # a second provider team id pointing at the SAME canonical team
        _provider_row(
            id="api_football:101:allsvenskan:2026",
            provider_team_id="101",
            identity_hash="ih101",
        ),
    )
    with Session(engine) as session:
        reverse = CanonicalIdentityRepository.canonical_team_source_mapping_in_session(
            session,
            provider="api_football",
            competition="allsvenskan",
            season="2026",
            as_of=AS_OF,
        )
        forward = CanonicalIdentityRepository.provider_team_mapping_in_session(
            session,
            provider="api_football",
            competition="allsvenskan",
            season="2026",
            as_of=AS_OF,
        )
    # Forward direction is unambiguous (two distinct provider ids)...
    assert forward == {
        "100": "w2:team:api_football:100",
        "101": "w2:team:api_football:100",
    }
    # ...but naively inverting it would silently keep one source id. The reverse
    # mapping must instead drop the ambiguous canonical team entirely.
    assert reverse == {}


def test_reverse_mapping_respects_validity_window() -> None:
    from sqlalchemy.orm import Session

    engine = _engine()
    _seed(engine, _provider_row(valid_to=datetime(2026, 6, 1, tzinfo=UTC)))
    with Session(engine) as session:
        reverse = CanonicalIdentityRepository.canonical_team_source_mapping_in_session(
            session,
            provider="api_football",
            competition="allsvenskan",
            season="2026",
            as_of=AS_OF,
        )
    assert reverse == {}
