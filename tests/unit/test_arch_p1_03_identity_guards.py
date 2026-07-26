"""ARCH-P1-03 M2A static guards: the legacy team/player crosswalk ORM classes
must not be referenced on the runtime surface (src/apps/scripts/infra) except
their three declarations in models.py, which are temporarily allowed until M4.
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = ("src", "apps", "scripts", "infra")
_ALLOWLIST = _ROOT / "src" / "w2" / "infrastructure" / "persistence" / "models.py"

# TeamIdentityCrosswalkModel is a substring of ProviderTeamIdentityCrosswalkModel
# (the authority), so its pattern must exclude the Provider-prefixed name.
_LEGACY_PATTERNS = {
    "FootballDataTeamCrosswalkModel": re.compile(r"\bFootballDataTeamCrosswalkModel\b"),
    "PlayerIdentityCrosswalkModel": re.compile(r"\bPlayerIdentityCrosswalkModel\b"),
    "TeamIdentityCrosswalkModel": re.compile(r"(?<!Provider)\bTeamIdentityCrosswalkModel\b"),
}


def _runtime_py_files() -> list[Path]:
    files: list[Path] = []
    for name in _SCAN_DIRS:
        base = _ROOT / name
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if "/migrations/" in path.as_posix():
                continue
            if path == _ALLOWLIST:
                continue
            files.append(path)
    return files


def test_legacy_crosswalk_runtime_references_are_zero() -> None:
    offenders: dict[str, list[str]] = {}
    for path in _runtime_py_files():
        text = path.read_text(encoding="utf-8")
        for cls, pattern in _LEGACY_PATTERNS.items():
            if pattern.search(text):
                offenders.setdefault(cls, []).append(path.relative_to(_ROOT).as_posix())
    assert offenders == {}, f"legacy crosswalk runtime references: {offenders}"


# The canonical id is minted exactly once, at controlled seeding time, inside
# canonical_team_payload(). Every resolution path must go through
# CanonicalIdentityRepository instead of rebuilding an id from a provider id.
_SEEDING_MINT_FILE = _ROOT / "src" / "w2" / "factor_model" / "remediation.py"
_MINT_CALLER = "canonical_team_payload"


def test_runtime_canonical_id_from_provider_construction_is_zero() -> None:
    # (a) No literal "w2:team:<provider>:" construction outside the mint.
    literal = re.compile(r'f?"w2:team:')
    # (b) No call to the mint helper outside its definition and canonical_team_payload.
    call = re.compile(r"\bstable_w2_team_id\s*\(")
    offenders: list[str] = []
    for path in _runtime_py_files():
        text = path.read_text(encoding="utf-8")
        if path == _SEEDING_MINT_FILE:
            # Only the mint helper itself and canonical_team_payload may construct.
            mint_region = text.split(f"def {_MINT_CALLER}")[0].split("def stable_w2_team_id")[0]
            if literal.search(mint_region) or call.search(mint_region):
                offenders.append(f"{path.relative_to(_ROOT)}:pre-mint-region")
            continue
        if literal.search(text) or call.search(text):
            offenders.append(path.relative_to(_ROOT).as_posix())
    assert offenders == [], f"runtime canonical-id-from-provider construction: {offenders}"


def test_provider_id_model_primary_reads_are_zero() -> None:
    """Model-facing snapshot/history/rating/xG reads must key on canonical W2 ids."""
    model_read = re.compile(
        r"(TeamXgRollingSnapshotModel|TeamXgMatchModel|TeamRatingSnapshotModel"
        r"|CanonicalTeamMatchHistoryModel)\.\w+\s*==\s*[\w.]*provider_team_id"
    )
    offenders = [
        path.relative_to(_ROOT).as_posix()
        for path in _runtime_py_files()
        if model_read.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"provider-id model primary reads: {offenders}"


def test_legacy_crosswalk_orm_declarations_are_exactly_three() -> None:
    text = _ALLOWLIST.read_text(encoding="utf-8")
    declared = [
        cls
        for cls in _LEGACY_PATTERNS
        if re.search(rf"class {cls}\b", text)
    ]
    # TEMPORARY_ALLOWED_UNTIL_M4: schema/metadata declarations only, no runtime use.
    assert sorted(declared) == sorted(_LEGACY_PATTERNS), declared
    assert len(declared) == 3


def test_no_new_identity_authority_table_declared() -> None:
    # NEW_IDENTITY_TABLE_COUNT = 0: no identity table beyond the known set.
    models = _ALLOWLIST.read_text(encoding="utf-8")
    factor_path = _ROOT / "src" / "w2" / "infrastructure" / "persistence" / "factor_model_models.py"
    factor = factor_path.read_text(encoding="utf-8")
    known_identity_tables = {
        "canonical_teams",
        "provider_team_identity_crosswalks",
        "player_identity_mappings",
        "team_identity_crosswalks",
        "football_data_team_crosswalks",
        "player_identity_crosswalks",
    }
    pattern = r'__tablename__ = "([a-z_]*(?:identity|crosswalk|canonical_teams)[a-z_]*)"'
    declared_identity_tables = set(re.findall(pattern, models + factor))
    assert declared_identity_tables <= known_identity_tables, (
        f"unexpected new identity table(s): {declared_identity_tables - known_identity_tables}"
    )
