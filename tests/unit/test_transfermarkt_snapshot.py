from __future__ import annotations

import gzip
from datetime import UTC, datetime

from w2.lineups.transfermarkt import load_player_snapshot


def test_transfermarkt_snapshot_is_hashed_normalized_and_typed() -> None:
    payload = gzip.compress(
        b"player_id,name,current_club_id,current_club_name,current_club_domestic_competition_id,position,sub_position,market_value_in_eur\n"
        b"1,Jose Alvarez,10,Example FC,GB1,Midfield,Central Midfield,5000000\n"
    )
    snapshot = load_player_snapshot(
        observed_at=datetime(2026, 7, 11, tzinfo=UTC),
        compressed=payload,
    )
    assert len(snapshot.rows) == 1
    assert snapshot.rows[0]["normalized_name"] == "josealvarez"
    assert str(snapshot.rows[0]["market_value_eur"]) == "5000000"
    assert len(snapshot.source_sha256) == 64
