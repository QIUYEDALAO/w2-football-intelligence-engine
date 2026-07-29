from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_SURFACES = (
    Path("src/w2"),
    Path("apps"),
    Path("scripts"),
    Path("infra"),
    Path(".github/workflows"),
    Path("pyproject.toml"),
    Path("Dockerfile.python"),
    Path("Dockerfile.web"),
)
LEDGER_RUNTIME_IDENTITIES = (
    "runtime/forward_outcome_ledger",
    "forward_outcome_result_refresh_state.json",
    "W2_FORWARD_OUTCOME_RUNTIME_ROOT",
)
LEGACY_IMPORT_IDENTITIES = (
    "formal_recommendation_snapshots",
    "formal_recommendation_settlements",
)
LEGACY_IMPORT_MODULE = Path("src/w2/tracking/outcome_ledger_repository.py")
RESULT_MATERIALIZER_FILES = (
    Path("src/w2/tracking/outcome_result_refresh.py"),
    Path("src/w2/tracking/outcome_ledger_repository.py"),
)
PROVIDER_IDENTITIES = ("ApiFootballClient", "request_live(", "providers.api_football")
LEGACY_RECOVERY_MANIFEST = "forward_ledger_legacy_recovery.staging.v1.json"


def _files(surfaces: tuple[Path, ...]) -> list[Path]:
    paths: list[Path] = []
    for surface in surfaces:
        if surface.is_file():
            paths.append(surface)
        elif surface.is_dir():
            paths.extend(
                path
                for path in surface.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".sh", ".yml", ".yaml", ".toml"}
            )
    return paths


def _runtime_ledger_violations(surfaces: tuple[Path, ...]) -> list[str]:
    violations: list[str] = []
    for path in _files(surfaces):
        source = path.read_text(encoding="utf-8", errors="ignore")
        for identity in LEDGER_RUNTIME_IDENTITIES:
            if identity in source:
                violations.append(f"{path}:{identity}")
        for identity in LEGACY_IMPORT_IDENTITIES:
            if identity in source and not path.as_posix().endswith(
                LEGACY_IMPORT_MODULE.as_posix()
            ):
                violations.append(f"{path}:{identity}")
    return sorted(violations)


def test_results_is_the_only_writable_final_score_authority() -> None:
    model_source = (ROOT / "src/w2/infrastructure/persistence/models.py").read_text()
    writer_files = [
        path
        for path in _files(tuple(ROOT / item for item in PRODUCTION_SURFACES))
        if not path.as_posix().endswith("infrastructure/persistence/models.py")
        and "ResultModel(" in path.read_text(encoding="utf-8", errors="ignore")
    ]

    assert model_source.count("class ResultModel(") == 1
    assert writer_files == [ROOT / "src/w2/tracking/outcome_ledger_repository.py"]
    assert (
        ROOT / "src/w2/tracking/outcome_ledger_repository.py"
    ).read_text().count("ResultModel(") == 2


def test_runtime_ledger_file_io_is_zero_outside_explicit_importer() -> None:
    surfaces = tuple(ROOT / path for path in PRODUCTION_SURFACES)
    assert _runtime_ledger_violations(surfaces) == []

    business_readers = (
        ROOT / "src/w2/tracking/formal_results.py",
        ROOT / "src/w2/tracking/forward_ledger_performance.py",
        ROOT / "src/w2/tracking/forward_outcome_ledger.py",
        ROOT / "src/w2/tracking/outcome_result_refresh.py",
    )
    for path in business_readers:
        source = path.read_text(encoding="utf-8")
        assert ".glob(" not in source
        assert ".open(" not in source
        assert "read_text(" not in source
        assert "write_text(" not in source


def test_result_materializer_has_no_provider_import_or_live_call() -> None:
    violations = [
        f"{path}:{identity}"
        for path in RESULT_MATERIALIZER_FILES
        for identity in PROVIDER_IDENTITIES
        if identity in (ROOT / path).read_text(encoding="utf-8")
    ]
    assert violations == []


def test_outcome_ledger_has_one_writable_repository_authority() -> None:
    model_source = (
        ROOT / "src/w2/infrastructure/persistence/outcome_ledger_models.py"
    ).read_text(encoding="utf-8")
    repository_source = (
        ROOT / "src/w2/tracking/outcome_ledger_repository.py"
    ).read_text(encoding="utf-8")

    assert model_source.count("class OutcomeLedgerModel(") == 1
    assert repository_source.count("OutcomeLedgerModel(") == 1
    assert "active.add(" in repository_source


def test_legacy_recovery_manifest_is_migration_input_only() -> None:
    forbidden_readers = (
        ROOT / "src/w2/prematch/analysis_calculator.py",
        ROOT / "src/w2/tracking/forward_ledger_performance.py",
        ROOT / "apps/api",
        ROOT / "apps/web",
    )
    violations = [
        str(path)
        for root in forbidden_readers
        for path in ([root] if root.is_file() else root.rglob("*"))
        if path.is_file()
        and LEGACY_RECOVERY_MANIFEST
        in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert violations == []


def test_runtime_ledger_guard_covers_every_production_surface(tmp_path: Path) -> None:
    mutations = (
        ("src/w2/reintroduced.py", "runtime/forward_outcome_ledger"),
        ("apps/reintroduced.py", "forward_outcome_result_refresh_state.json"),
        ("scripts/reintroduced.py", "W2_FORWARD_OUTCOME_RUNTIME_ROOT"),
        ("infra/reintroduced.yml", "formal_recommendation_snapshots"),
        (".github/workflows/reintroduced.yml", "formal_recommendation_settlements"),
        ("pyproject.toml", "runtime/forward_outcome_ledger"),
        ("Dockerfile.python", "W2_FORWARD_OUTCOME_RUNTIME_ROOT"),
        ("Dockerfile.web", "forward_outcome_result_refresh_state.json"),
    )
    surface_names = tuple(str(path) for path in PRODUCTION_SURFACES)
    for index, (relative_path, identity) in enumerate(mutations):
        root = tmp_path / str(index)
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(identity, encoding="utf-8")
        surfaces = tuple(root / name for name in surface_names)
        assert f"{path}:{identity}" in _runtime_ledger_violations(surfaces)
