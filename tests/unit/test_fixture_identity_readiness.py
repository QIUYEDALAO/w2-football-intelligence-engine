"""Unit tests for the canonical fixture-identity readiness gate.

These lock the fail-closed contract: the AH/OU decision card must only proceed on
the canonical (w2) team-id domain when the fixture identity is fully resolved. Any
of the three attack vectors — missing identity row, missing w2 team id, or an
alias conflict — must report not-ready, so `_db_analysis_card_from_fixture` refuses
to fall back to the provider team-id domain.
"""
from __future__ import annotations

from typing import Any

import pytest

from w2.prematch.analysis_calculator import ReadModelService


@pytest.mark.parametrize(
    "identity, expected",
    [
        pytest.param(None, False, id="missing-identity-row"),
        pytest.param(
            {"status": "READY", "home_w2_team_id": None, "away_w2_team_id": "A"},
            False,
            id="missing-home-w2-team-id",
        ),
        pytest.param(
            {"status": "READY", "home_w2_team_id": "H", "away_w2_team_id": None},
            False,
            id="missing-away-w2-team-id",
        ),
        pytest.param(
            {
                "status": "FIXTURE_ID_ALIAS_CONFLICT",
                "home_w2_team_id": "H",
                "away_w2_team_id": "A",
            },
            False,
            id="alias-conflict",
        ),
        pytest.param(
            {"status": "READY", "home_w2_team_id": "H", "away_w2_team_id": "A"},
            True,
            id="ready",
        ),
    ],
)
def test_canonical_fixture_identity_ready(
    identity: dict[str, Any] | None, expected: bool,
) -> None:
    assert (
        ReadModelService._canonical_fixture_identity_ready(None, identity)  # noqa: SLF001
        is expected
    )
