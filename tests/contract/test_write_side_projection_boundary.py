from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
WRITE_ENTRYPOINT = ROOT / "src/w2/ingestion/future_refresh.py"
WRITE_PROJECTOR = ROOT / "src/w2/prematch/read_model_projection.py"
WORKER_COMPOSITION_ROOT = ROOT / "apps/worker/celery_app.py"
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


def _module_path(module: str) -> Path | None:
    candidate = SRC_ROOT / f"{module.replace('.', '/')}.py"
    if candidate.is_file():
        return candidate
    package = SRC_ROOT / module.replace(".", "/") / "__init__.py"
    return package if package.is_file() else None


def _prematch_projection_graph() -> dict[Path, set[str]]:
    pending = [WRITE_PROJECTOR]
    graph: dict[Path, set[str]] = {}
    while pending:
        path = pending.pop()
        if path in graph:
            continue
        imports = _imports(path)
        graph[path] = imports
        for module in imports:
            if not module.startswith("w2.prematch"):
                continue
            target = _module_path(module)
            if target is not None:
                pending.append(target)
    return graph


def test_future_refresh_write_path_has_no_api_import() -> None:
    assert not {module for module in _imports(WRITE_ENTRYPOINT) if module.startswith("w2.api")}


def test_write_projector_lives_outside_api_without_compatibility_shim() -> None:
    assert WRITE_PROJECTOR.is_file()
    assert all(not path.exists() for path in OLD_API_PROJECTORS)
    source = WRITE_PROJECTOR.read_text(encoding="utf-8")
    assert "class AnalysisCardCanaryMaterializer" in source
    assert "def write_frozen_analysis_artifacts" in source
    assert "def materialize_projection_events" in source


def test_recursive_projection_production_graph_has_no_api_dependency() -> None:
    graph = _prematch_projection_graph()
    assert WRITE_PROJECTOR in graph
    assert not {
        f"{path.relative_to(ROOT)} -> {module}"
        for path, imports in graph.items()
        for module in imports
        if module.startswith("w2.api")
    }


def test_worker_composition_root_injects_current_reader_explicitly() -> None:
    projector_tree = ast.parse(WRITE_PROJECTOR.read_text(encoding="utf-8"))
    materialize = next(
        node
        for node in projector_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "materialize_projection_events"
    )
    keyword_defaults = dict(
        zip(
            (argument.arg for argument in materialize.args.kwonlyargs),
            materialize.args.kw_defaults,
            strict=True,
        )
    )
    assert keyword_defaults["repository"] is None
    assert keyword_defaults["calculate_analysis_card"] is None
    worker_source = WORKER_COMPOSITION_ROOT.read_text(encoding="utf-8")
    assert "materialize_public_artifacts=_materialize_shadow_projection_events" in worker_source
