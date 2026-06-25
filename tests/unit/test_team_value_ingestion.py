from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine

from w2.infrastructure.database import Base
from w2.ingestion.team_value import (
    TeamValueRepository,
    build_team_value_lookup,
    sync_transfermarkt_team_values,
)
from w2.strategy.analysis_score import team_value_signal_from_lookup

NOW = datetime(2026, 6, 25, 12, tzinfo=UTC)


def write_csv(path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return str(path)


def sqlite_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_sync_is_idempotent_and_asof_lookup_does_not_use_future_value(tmp_path) -> None:
    engine = sqlite_engine()
    players = write_csv(
        tmp_path / "players.csv",
        "\n".join(
            [
                "player_id,name,last_season,current_club_id,current_club_name,market_value_in_eur",
                "1,Home A,2026,10,Home FC,100",
                "2,Away A,2026,20,Away FC,80",
            ]
        ),
    )
    valuations = write_csv(
        tmp_path / "player_valuations.csv",
        "\n".join(
            [
                "player_id,date,market_value_in_eur,current_club_name,current_club_id,player_club_domestic_competition_id",
                "1,2026-01-01,100,Home FC,10,L1",
                "2,2026-01-01,80,Away FC,20,L1",
                "1,2026-07-01,1000,Home FC,10,L1",
                "2,2026-07-01,900,Away FC,20,L1",
            ]
        ),
    )
    mappings = write_csv(
        tmp_path / "mappings.csv",
        "\n".join(
            [
                "transfermarkt_club_id,transfermarkt_club_name,w2_team_id,confidence,mapping_source,notes",
                "10,Home FC,w2-home,0.9900,manual,test",
                "20,Away FC,w2-away,0.9900,manual,test",
            ]
        ),
    )

    first = sync_transfermarkt_team_values(
        players_url=players,
        player_valuations_url=valuations,
        mapping_csv=mappings,
        engine=engine,
        now=NOW,
    )
    second = sync_transfermarkt_team_values(
        players_url=players,
        player_valuations_url=valuations,
        mapping_csv=mappings,
        engine=engine,
        now=NOW,
    )

    assert first.observations_inserted == 6
    assert first.mappings_inserted == 2
    assert second.observations_inserted == 0
    assert second.mappings_inserted == 0
    assert first.candidate is False
    assert first.formal_recommendation is False

    repository = TeamValueRepository(engine=engine)
    home = repository.lookup_team_value(
        w2_team_id="w2-home",
        as_of=datetime(2026, 6, 1, tzinfo=UTC),
    )

    assert home is not None
    assert int(home.value_eur) == 100
    assert home.valid_from == datetime(2026, 1, 1, tzinfo=UTC)


def test_unmapped_team_degrades_to_value_data_unavailable(tmp_path) -> None:
    engine = sqlite_engine()
    valuations = write_csv(
        tmp_path / "player_valuations.csv",
        "\n".join(
            [
                "player_id,date,market_value_in_eur,current_club_name,current_club_id,player_club_domestic_competition_id",
                "1,2026-01-01,100,Home FC,10,L1",
            ]
        ),
    )
    mappings = write_csv(
        tmp_path / "mappings.csv",
        "\n".join(
            [
                "transfermarkt_club_id,transfermarkt_club_name,w2_team_id,confidence,mapping_source,notes",
                "10,Home FC,w2-home,0.9900,manual,test",
            ]
        ),
    )

    sync_transfermarkt_team_values(
        players_url=valuations,
        player_valuations_url=valuations,
        mapping_csv=mappings,
        engine=engine,
        now=NOW,
    )

    lookup = build_team_value_lookup(
        home_team_id="w2-home",
        away_team_id="w2-unmapped",
        as_of=datetime(2026, 6, 1, tzinfo=UTC),
        repository=TeamValueRepository(engine=engine),
    )

    assert lookup.status == "VALUE_DATA_UNAVAILABLE"
    assert team_value_signal_from_lookup(lookup) is None


def test_team_value_lookup_builds_low_weight_analysis_factor(tmp_path) -> None:
    engine = sqlite_engine()
    valuations = write_csv(
        tmp_path / "player_valuations.csv",
        "\n".join(
            [
                "player_id,date,market_value_in_eur,current_club_name,current_club_id,player_club_domestic_competition_id",
                "1,2026-01-01,200,Home FC,10,L1",
                "2,2026-01-01,50,Away FC,20,L1",
            ]
        ),
    )
    mappings = write_csv(
        tmp_path / "mappings.csv",
        "\n".join(
            [
                "transfermarkt_club_id,transfermarkt_club_name,w2_team_id,confidence,mapping_source,notes",
                "10,Home FC,w2-home,0.9900,manual,test",
                "20,Away FC,w2-away,0.9900,manual,test",
            ]
        ),
    )

    sync_transfermarkt_team_values(
        players_url=valuations,
        player_valuations_url=valuations,
        mapping_csv=mappings,
        engine=engine,
        now=NOW,
    )
    lookup = build_team_value_lookup(
        home_team_id="w2-home",
        away_team_id="w2-away",
        as_of=datetime(2026, 6, 1, tzinfo=UTC),
        repository=TeamValueRepository(engine=engine),
    )
    signal = team_value_signal_from_lookup(lookup)

    assert lookup.status == "READY"
    assert signal is not None
    assert signal.home == 200
    assert signal.away == 50
    assert "低权重" in (signal.risk or "")
