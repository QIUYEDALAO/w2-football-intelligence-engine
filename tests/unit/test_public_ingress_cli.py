from __future__ import annotations

import subprocess
from pathlib import Path


def test_public_ingress_cli_reuses_release_sync_verifier() -> None:
    source = Path("scripts/check_public_ingress.py").read_text(encoding="utf-8")
    assert "verify_release_sync.py" in source
    assert "subprocess.run(command" in source


def test_public_ingress_cli_help_loads() -> None:
    completed = subprocess.run(
        ["python3", "scripts/check_public_ingress.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--base-url" in completed.stdout
    assert "--allow-empty-data" in completed.stdout
