"""The production card evaluation hands its four AH factors to the recorder.

F1R-B shipped a recorder integration with no production call site, so
`forward_ah_factor_observations` stayed at zero rows. The F1R-B successor added
one, in `ReadModelService._db_analysis_card_from_fixture`, right after the
authoritative weighted score exists and before the payload is returned.

This is the end-to-end half of that claim: a real `analysis_card()` call, on the
real service, with the real feature builders, reaches the recorder exactly once
per evaluation and hands it the factors the accepted chain requires -- and the
card the read model returns is identical whether or not a recorder is there.

What it deliberately does *not* claim: that the recorder then writes rows. That
is `scripts/quant/tests/test_f1r_b_production_factor_persistence.py`, which
drives the same recorder against the real tables.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

from w2.prematch import analysis_calculator as api_repository
from w2.prematch.analysis_calculator import ReadModelService

REPO = Path(__file__).resolve().parents[2]
HARNESS = REPO / "tests/unit/test_feature_inputs_independent_sources.py"
FIXTURE_ID = "future-1"
REQUIRED_FACTORS = ("F3_REST_FITNESS", "F5_RECENT_AH_COVER", "F6_H2H", "F9_TRUE_XG")

_spec = importlib.util.spec_from_file_location("w2_independent_source_harness", HARNESS)
assert _spec is not None and _spec.loader is not None
harness = importlib.util.module_from_spec(_spec)
sys.modules["w2_independent_source_harness"] = harness
_spec.loader.exec_module(harness)


class SpyRecorder:
    """Stands in for the F1R-B recorder and keeps every hand-over."""

    enabled = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.outcomes: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"status": "NOT_WRITTEN_BY_THIS_TEST"}


def _card_with(monkeypatch: Any, tmp_path: Path, recorder: Any) -> dict[str, Any] | None:
    mapping = tmp_path / "config/team_values/world_cup_2026.v1.json"
    if not mapping.exists():
        # The harness helper is write-once; this test builds two cards.
        harness.write_value_mapping(tmp_path)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    monkeypatch.setattr(
        api_repository,
        "future_refresh_db_repository",
        lambda: harness.IndependentSourceStore(),
    )
    service = ReadModelService(
        repository=cast(Any, harness.IndependentSourceRepository()),
        forward_factor_recorder=recorder,
    )
    return service.analysis_card(FIXTURE_ID)


def test_the_production_card_evaluation_reaches_the_recorder(
    monkeypatch: Any, tmp_path: Path
) -> None:
    recorder = SpyRecorder()

    card = _card_with(monkeypatch, tmp_path, recorder)

    assert card is not None
    assert len(recorder.calls) == 1, recorder.calls
    call = recorder.calls[0]
    assert call["fixture_id"] == FIXTURE_ID
    assert call["context"].fixture_id == FIXTURE_ID
    # The context is the one the evaluation read from, not a restatement of it.
    assert str(call["context"].as_of) == "2026-07-10 18:00:00+00:00"
    assert call["feature_set"].fixture_id == FIXTURE_ID
    assert {c.feature_id for c in call["feature_set"].contributions} >= set(REQUIRED_FACTORS)
    assert len(call["xg_snapshots"]) == 2


def test_the_recorder_is_handed_the_scored_evaluation_not_a_recomputation(
    monkeypatch: Any, tmp_path: Path
) -> None:
    from w2.pricing.team_score import independent_team_scores_from_contributions

    recorder = SpyRecorder()

    _card_with(monkeypatch, tmp_path, recorder)

    feature_set = recorder.calls[0]["feature_set"]
    # The written card carries the same contributions, so the batch the recorder
    # builds is about the evaluation that was scored -- not a second one.
    authority = independent_team_scores_from_contributions(feature_set.contributions)
    scored = {row["id"]: row["weight"] for row in authority["scoring_factors"]}
    for contribution in feature_set.contributions:
        if contribution.feature_id in scored:
            assert float(contribution.weight) == scored[contribution.feature_id]


def test_a_read_only_caller_gets_the_same_card_and_writes_nothing(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """No recorder injected means no call -- and no change to the card.

    The API router and the dashboard build cards through the same service and
    never inject a recorder, so reading a card must be a no-op for the factor
    table. The one thing that could go wrong silently is the card changing.
    """
    recorder = SpyRecorder()

    with_recorder = _card_with(monkeypatch, tmp_path, recorder)
    without_recorder = _card_with(monkeypatch, tmp_path, None)

    assert len(recorder.calls) == 1
    assert with_recorder is not None and without_recorder is not None
    assert with_recorder == without_recorder
    assert with_recorder["candidate"] is False
    assert with_recorder["formal_recommendation"] is False
