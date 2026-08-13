"""ARCH-P1-03 static guards for the canonical identity authority."""

from __future__ import annotations

import ast
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
    "PlayerIdentityCrosswalkV1": re.compile(r"\bPlayerIdentityCrosswalkV1\b"),
    "build_player_crosswalk": re.compile(r"\bbuild_player_crosswalk\b"),
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


# The canonical id is minted exactly once, at controlled seeding time
# (W2_EXTERNAL_DECISION_V2: CONTROLLED_CANONICAL_TEAM_ID_MINT_APPROVED). Every
# resolution path must go through CanonicalIdentityRepository instead of
# rebuilding an id from a provider id. Enforced by AST, not text scanning.
_MINT_HELPER = "stable_w2_team_id"  # may hold the single "w2:team:" literal
_MINT_CALLER = "canonical_team_payload"  # may make the single mint call
_CANONICAL_TEAM_ID_PREFIX = "w2:team:"
# The allowlist binds file AND function AND construction kind, so the same
# function name in another module is a violation, not an escape hatch.
_MINT_FILE = "src/w2/identity/canonical_identity_repository.py"
_APPROVED_MINT_SITES = {
    (_MINT_FILE, _MINT_CALLER, "mint_call"),
    (_MINT_FILE, _MINT_HELPER, "literal"),
}


class _ConstructionVisitor(ast.NodeVisitor):
    """Collect canonical-id construction sites with their enclosing function."""

    def __init__(self) -> None:
        self.scope: list[str] = []
        self.sites: list[tuple[str, str]] = []  # (enclosing_function, kind)

    def _enclosing(self) -> str:
        return self.scope[-1] if self.scope else "<module>"

    def _visit_scoped(self, node: ast.AST) -> None:
        self.scope.append(node.name)  # type: ignore[attr-defined]
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = _visit_scoped  # type: ignore[assignment]
    visit_AsyncFunctionDef = _visit_scoped  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        name = getattr(func, "id", None) or getattr(func, "attr", None)
        if name == _MINT_HELPER:
            self.sites.append((self._enclosing(), "mint_call"))
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and node.value.startswith(_CANONICAL_TEAM_ID_PREFIX):
            self.sites.append((self._enclosing(), "literal"))
        self.generic_visit(node)


def construction_sites_in_source(source: str, *, file: str) -> list[tuple[str, str, str]]:
    """(file, enclosing_function, kind) for every construction site in ``source``."""
    visitor = _ConstructionVisitor()
    visitor.visit(ast.parse(source))
    return [(file, enclosing, kind) for enclosing, kind in visitor.sites]


def _construction_sites() -> list[tuple[str, str, str]]:
    sites: list[tuple[str, str, str]] = []
    for path in _runtime_py_files():
        rel = path.relative_to(_ROOT).as_posix()
        sites.extend(construction_sites_in_source(path.read_text(encoding="utf-8"), file=rel))
    return sites


def test_runtime_canonical_id_from_provider_construction_is_zero() -> None:
    """Exact-count AST guard: zero construction outside the approved mint."""
    violations = [
        ":".join(site) for site in _construction_sites() if site not in _APPROVED_MINT_SITES
    ]
    assert violations == [], f"runtime canonical-id-from-provider construction: {violations}"


def test_controlled_mint_is_exactly_one_call_and_one_literal() -> None:
    """The approved mint must not silently multiply either."""
    sites = _construction_sites()
    assert sites.count((_MINT_FILE, _MINT_CALLER, "mint_call")) == 1, sites
    assert sites.count((_MINT_FILE, _MINT_HELPER, "literal")) == 1, sites


def test_mint_allowlist_does_not_leak_to_the_same_function_name_elsewhere() -> None:
    """A same-named function in another module must not inherit the allowlist."""
    impostor = (
        "def canonical_team_payload(pid):\n"
        "    return stable_w2_team_id(pid)\n"
        "def stable_w2_team_id(pid):\n"
        '    return "w2:team:api_football:" + pid\n'
    )
    sites = construction_sites_in_source(impostor, file="src/w2/other_module.py")
    violations = [site for site in sites if site not in _APPROVED_MINT_SITES]
    # Identical function names, different file -> every site is a violation.
    assert len(violations) == len(sites) == 2, sites


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


def test_legacy_crosswalk_orm_declarations_are_zero() -> None:
    text = _ALLOWLIST.read_text(encoding="utf-8")
    declared = [cls for cls in _LEGACY_PATTERNS if re.search(rf"class {cls}\b", text)]
    assert declared == []


def test_legacy_crosswalk_table_names_are_absent_from_runtime() -> None:
    table_patterns = {
        "team_identity_crosswalks": re.compile(r"(?<!provider_)team_identity_crosswalks\b"),
        "football_data_team_crosswalks": re.compile(r"\bfootball_data_team_crosswalks\b"),
        "player_identity_crosswalks": re.compile(r"\bplayer_identity_crosswalks\b"),
    }
    offenders = {
        table: [
            path.relative_to(_ROOT).as_posix()
            for path in _runtime_py_files()
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        for table, pattern in table_patterns.items()
    }
    assert offenders == {table: [] for table in table_patterns}


def test_no_new_identity_authority_table_declared() -> None:
    # NEW_IDENTITY_TABLE_COUNT = 0: no identity table beyond the known set.
    models = _ALLOWLIST.read_text(encoding="utf-8")
    factor_path = _ROOT / "src" / "w2" / "infrastructure" / "persistence" / "factor_model_models.py"
    factor = factor_path.read_text(encoding="utf-8")
    known_identity_tables = {
        "canonical_teams",
        "provider_team_identity_crosswalks",
        "player_identity_mappings",
    }
    pattern = r'__tablename__ = "([a-z_]*(?:identity|crosswalk|canonical_teams)[a-z_]*)"'
    declared_identity_tables = set(re.findall(pattern, models + factor))
    assert declared_identity_tables <= known_identity_tables, (
        f"unexpected new identity table(s): {declared_identity_tables - known_identity_tables}"
    )
