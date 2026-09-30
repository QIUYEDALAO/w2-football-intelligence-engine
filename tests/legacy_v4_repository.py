"""Pinned pre-retirement V4 writer for historical contract tests only.

Production imports the current repository, whose AH/OU append path is closed.
These tests still exercise the complete old writer/consumer against disposable
SQLite artifacts, then test current same-identity retry separately.
"""

from __future__ import annotations

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SHA = "6eb3ffa8cc0a5085d6ace70b9cc926e4d582c9ce"
_NAME = "w2_historical_v4_repository_6eb3ffa8"


def load_historical_module(path: str, name: str):  # type: ignore[no-untyped-def]
    source = subprocess.run(
        ["git", "show", f"{_SHA}:{path}"], cwd=_REPO,
        check=True, capture_output=True, text=True,
    ).stdout
    spec = spec_from_loader(name, loader=None)
    assert spec is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    exec(source, module.__dict__)  # noqa: S102 - immutable Git artifact
    return module


LegacyDynamicPrematchRepository = load_historical_module(
    "src/w2/prematch/repository.py", _NAME
).DynamicPrematchRepository


def install_legacy_v4_writer(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Scope archived writer behavior to one historical test invocation."""
    from w2.prematch.repository import DynamicPrematchRepository

    for method in (
        "append_evaluation_in_session",
        "record_opportunity_without_attempt_in_session",
    ):
        monkeypatch.setattr(
            DynamicPrematchRepository,
            method,
            getattr(LegacyDynamicPrematchRepository, method),
        )
