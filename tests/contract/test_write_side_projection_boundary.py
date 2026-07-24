from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WRITE_ENTRYPOINT = ROOT / "src/w2/ingestion/future_refresh.py"
WRITE_PROJECTOR = ROOT / "src/w2/prematch/read_model_projection.py"
OLD_API_PROJECTORS = (
    ROOT / "src/w2/api/frozen_analysis.py",
    ROOT / "src/w2/api/dashboard_read_models.py",
)


def _imports(path: Path) -> set[str]:
    modules: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_future_refresh_write_path_has_no_api_import() -> None:
    assert not {module for module in _imports(WRITE_ENTRYPOINT) if module.startswith("w2.api")}


def test_write_projector_lives_outside_api_without_compatibility_shim() -> None:
    assert WRITE_PROJECTOR.is_file()
    assert all(not path.exists() for path in OLD_API_PROJECTORS)
    source = WRITE_PROJECTOR.read_text(encoding="utf-8")
    assert "class AnalysisCardCanaryMaterializer" in source
    assert "def write_frozen_analysis_artifacts" in source
    assert "def materialize_projection_events" in source
