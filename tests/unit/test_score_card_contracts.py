from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from w2.strategy.score_card import ScoreCard, build_score_card, render_score_card

ROOT = Path(__file__).resolve().parents[2]


def test_score_card_schema_exposes_versioned_scenarios_contract() -> None:
    schema = ScoreCard.model_json_schema()

    assert schema["properties"]["schema_version"]["const"] == "W2_SCORE_CARD_V1"
    assert "scenarios" in schema["required"]
    assert schema["properties"]["candidate"]["const"] is False
    assert schema["properties"]["formal_recommendation"]["const"] is False


def test_skip_card_has_no_score_scenarios() -> None:
    card = build_score_card(
        score_matrix={(1, 1): 0.4, (2, 1): 0.3},
        decision="SKIP",
        primary_direction="HOME",
    )

    assert card.primary_direction is None
    assert card.scenarios == []
    assert card.candidate is False
    assert card.formal_recommendation is False


def test_main_card_rejects_wrong_direction_score_bucket() -> None:
    with pytest.raises(ValidationError, match="MAIN score scenario bucket"):
        ScoreCard.model_validate(
            {
                "decision": "MAIN",
                "primary_direction": "HOME",
                "candidate": False,
                "formal_recommendation": False,
                "scenarios": [
                    {
                        "role": "MAIN",
                        "scoreline": "1-1",
                        "home_score": 1,
                        "away_score": 1,
                        "score_direction": "DRAW",
                        "probability": 0.32,
                        "conditional_probability": 1.0,
                    }
                ],
            }
        )


def test_skip_card_rejects_any_score_scenario() -> None:
    with pytest.raises(ValidationError, match="SKIP score card must not carry scenarios"):
        ScoreCard.model_validate(
            {
                "decision": "SKIP",
                "primary_direction": None,
                "candidate": False,
                "formal_recommendation": False,
                "scenarios": [
                    {
                        "role": "MAIN",
                        "scoreline": "0-0",
                        "home_score": 0,
                        "away_score": 0,
                        "score_direction": "DRAW",
                        "probability": 0.1,
                    }
                ],
            }
        )


def test_no_complete_matrix_means_no_score_scenarios() -> None:
    with pytest.raises(ValueError, match="complete score_matrix is required"):
        build_score_card(score_matrix=None, decision="MAIN", primary_direction="HOME")


def test_main_card_uses_direction_consistent_bucket_not_global_top() -> None:
    card = build_score_card(
        score_matrix={
            (1, 1): 0.30,
            (2, 1): 0.18,
            (1, 0): 0.12,
            (0, 1): 0.10,
        },
        decision="MAIN",
        primary_direction="HOME",
        limit=2,
    )

    assert [row.scoreline for row in card.scenarios] == ["2-1", "1-0"]
    assert {row.score_direction for row in card.scenarios} == {"HOME"}


def test_score_card_renderer_uses_compliant_label() -> None:
    rendered = render_score_card(
        build_score_card(
            score_matrix={(2, 1): 0.6, (1, 1): 0.4},
            decision="MAIN",
            primary_direction="HOME",
        )
    )

    assert "W2 research review" in rendered
    assert "DeepSeek AI" not in rendered


def test_legacy_ai_card_text_renderer_uses_compliant_label() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/render_ai_card_text.py", "examples/skip/card.json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "W2 Research Review" in result.stdout
    assert "DeepSeek AI" not in result.stdout
