from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_legacy_decision_allowlist.py"


def test_legacy_decision_allowlist_is_complete_and_excludes_authoritative_paths() -> None:
    spec = importlib.util.spec_from_file_location("legacy_decision_governance", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main() == 0
