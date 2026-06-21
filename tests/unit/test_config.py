from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from w2.config import Environment, Settings


def test_environment_config_files_are_separated() -> None:
    for environment in Environment:
        with open(f"config/environments/{environment.value}.yaml", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
        assert payload["environment"] == environment.value
        assert payload["external_api_calls_enabled"] is False
        assert payload["real_recommendation_enabled"] is False


def test_illegal_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="sandbox")


def test_w1_path_dependency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:////Users/liudehua/.openclaw/workspace/w1_world_cup_engine/x.db")

