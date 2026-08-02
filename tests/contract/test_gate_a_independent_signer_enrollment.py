from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRUST = ROOT / "config/policies/gate_a_authorization_trust.v1.json"
SIGNER_KEY_ID = "w2-gate-a-signer-aef8c11a9e88657a"
RETIRED_KEY_ID = "gate-a-independent-approval-2026-01"
PRODUCTION_IMPLEMENTER = "xg3750150@gmail.com"


def _trust() -> dict[str, object]:
    return json.loads(TRUST.read_text(encoding="utf-8"))


def test_independent_signer_public_key_is_a_valid_ed25519_key() -> None:
    entry = _trust()["trusted_ed25519_keys"][SIGNER_KEY_ID]
    raw = base64.b64decode(entry["public_key_base64"], validate=True)
    assert len(raw) == 32


def test_independent_signer_fingerprint_matches_the_public_key() -> None:
    entry = _trust()["trusted_ed25519_keys"][SIGNER_KEY_ID]
    raw = base64.b64decode(entry["public_key_base64"], validate=True)
    assert hashlib.sha256(raw).hexdigest() == entry["public_key_sha256"]


def test_independent_signer_is_enrolled_and_enabled() -> None:
    trust = _trust()
    entry = trust["trusted_ed25519_keys"][SIGNER_KEY_ID]
    assert entry["custody_status"] == trust["required_authorization_custody_status"]
    assert entry["authorization_enabled"] is True
    assert entry["signer_role"] != entry["executor_role"]
    assert entry["custody_scope"] == "SINGLE_USE_ONE_CANARY_THEN_PRIVATE_KEY_DELETED"


def test_enrollment_does_not_claim_os_user_isolation() -> None:
    """The signer and executor share an OS user; only the role separation is real."""
    entry = _trust()["trusted_ed25519_keys"][SIGNER_KEY_ID]
    assert entry["custody_boundary"] == "ROLE_SEPARATION_ONLY_NOT_OS_USER_ISOLATION"
    assert entry["owner_accepted_simplification"] is True


def test_retired_codex_key_stays_disabled() -> None:
    entry = _trust()["trusted_ed25519_keys"][RETIRED_KEY_ID]
    assert entry["authorization_enabled"] is False
    assert entry["custody_status"] != _trust()["required_authorization_custody_status"]


def test_repository_holds_no_private_key_and_no_authorization() -> None:
    trust = _trust()
    assert trust["private_keys_present"] is False
    assert trust["real_canary_authorization_created"] is False
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert not [name for name in tracked if name.endswith((".key", ".pem"))]
    marker = "PRIVATE" + " KEY"
    hits = [
        name
        for name in subprocess.run(
            ["git", "grep", "-l", marker],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        if name != str(Path(__file__).relative_to(ROOT))
    ]
    assert hits == []


def test_signer_git_author_differs_from_production_implementer() -> None:
    author = subprocess.run(
        ["git", "log", "-1", "--format=%ae", "--", str(TRUST.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert author
    assert author != PRODUCTION_IMPLEMENTER
