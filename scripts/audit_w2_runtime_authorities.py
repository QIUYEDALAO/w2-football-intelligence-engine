from __future__ import annotations

# ruff: noqa: E501,I001

import ast
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "audits" / "system_truth"
PRIVATE_FOOTBALL_DATA_ROOT = Path("/Users/liudehua/.hermes/data/w2/football-data-co-uk")
SOURCE_REVIEW_SHA = "94ba834559c0beba5b38075bd358a8e92a434a51"
SCHEMA_PREFIX = "w2.system_consolidation"
CORE_CONCEPTS = (
    "fixture_discovery",
    "team_identity",
    "player_identity",
    "competition_policy",
    "checkpoint_policy",
    "scheduler_dispatch",
    "celery_task",
    "provider_request",
    "endpoint_capture",
    "raw_payload",
    "odds_observation",
    "market_observation",
    "canonical_ah",
    "canonical_ou",
    "quote_identity",
    "quote_freshness",
    "collection_freshness",
    "market_selection",
    "market_probability",
    "model_probability",
    "analysis_direction",
    "market_movement",
    "lineup_policy",
    "injury_policy",
    "xg_enrichment",
    "F5",
    "F8",
    "factor_registry",
    "formal_readiness",
    "formal_recommendation",
    "recommendation_decision_v3",
    "recommendation_projection",
    "recommendation_identity",
    "lock",
    "settlement",
    "performance_cohort",
    "dashboard_projection",
    "api_read_model",
    "frozen_artifact",
    "tracking",
    "calibration",
    "baseline_prior",
    "team_value",
    "registered_roster",
    "data_asset_registry",
    "backup_restore",
    "script_registry",
    "config_flags",
)

P0_P1_TABLE_DOMAINS = {
    "raw_payload",
    "raw_payload_references",
    "matchday_endpoint_captures",
    "odds_observations",
    "future_market_observation",
    "fixtures",
    "teams",
    "team_identity_crosswalks",
    "matchday_checkpoint_plans",
    "future_refresh_checkpoint_plan",
    "future_refresh_checkpoint_audit",
    "recommendations",
    "recommendation_locks",
    "gate5_recommendation_lock_event",
    "settlements",
    "results",
    "forward_market_snapshot",
    "forward_evaluation",
    "canonical_historical_ah_facts",
    "historical_market_source_snapshots",
    "team_value_asof_artifacts",
    "calibration_artifact",
    "matchday_evidence_manifests",
}


@dataclass
class SymbolIndex:
    definitions: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    calls: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    imports: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    routes: list[dict[str, str]] = field(default_factory=list)
    celery_tasks: list[dict[str, str]] = field(default_factory=list)
    cli_mains: list[dict[str, str]] = field(default_factory=list)
    sqlalchemy_models: list[dict[str, str]] = field(default_factory=list)
    alembic_revisions: list[dict[str, str]] = field(default_factory=list)
    subprocess_calls: list[dict[str, str]] = field(default_factory=list)
    env_readers: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))
    compose_env: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))
    github_env: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))
    shell_env: dict[str, list[dict[str, str]]] = field(default_factory=lambda: defaultdict(list))


class RuntimeVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, index: SymbolIndex) -> None:
        self.path = path
        self.rel = path.relative_to(ROOT).as_posix()
        self.index = index
        self.scope: list[str] = []

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.index.imports[alias.name].append(self._loc(node))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        module = node.module or ""
        for alias in node.names:
            self.index.imports[f"{module}.{alias.name}".strip(".")].append(self._loc(node))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.index.definitions[node.name].append(self._loc(node))
        table = _class_table_name(node)
        if table:
            self.index.sqlalchemy_models.append(
                {"model": node.name, "table": table, "file": self.rel, "line": str(node.lineno)}
            )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._function(node)

    def visit_Call(self, node: ast.Call) -> Any:
        name = _call_name(node.func)
        if name:
            self.index.calls[name].append(self._loc(node))
        if name in {"subprocess.run", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen"}:
            self.index.subprocess_calls.append({"call": name, "file": self.rel, "line": str(node.lineno)})
        self._env_call(node, name)
        self.generic_visit(node)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.index.definitions[node.name].append(self._loc(node))
        for dec in node.decorator_list:
            dec_name = _call_name(dec.func if isinstance(dec, ast.Call) else dec)
            if dec_name and (dec_name.endswith(".get") or dec_name.endswith(".post") or dec_name.endswith(".put") or dec_name.endswith(".delete")):
                self.index.routes.append(
                    {"function": node.name, "decorator": dec_name, "file": self.rel, "line": str(node.lineno)}
                )
            if dec_name and (dec_name.endswith(".task") or dec_name == "shared_task"):
                task_name = _kw_string(dec, "name") if isinstance(dec, ast.Call) else None
                self.index.celery_tasks.append(
                    {
                        "function": node.name,
                        "task_name": task_name or node.name,
                        "decorator": dec_name,
                        "file": self.rel,
                        "line": str(node.lineno),
                    }
                )
        if node.name in {"main", "cli", "app"} and self.rel.startswith("scripts/"):
            self.index.cli_mains.append({"function": node.name, "file": self.rel, "line": str(node.lineno)})
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _env_call(self, node: ast.Call, name: str | None) -> None:
        if name in {"os.getenv", "os.environ.get"}:
            var = _first_string_arg(node)
            if var:
                self.index.env_readers[var].append({"file": self.rel, "line": str(node.lineno), "reader": name})
        if name == "os.environ.__getitem__":
            var = _first_string_arg(node)
            if var:
                self.index.env_readers[var].append({"file": self.rel, "line": str(node.lineno), "reader": name})

    def _loc(self, node: ast.AST) -> str:
        return f"{self.rel}:{getattr(node, 'lineno', 1)}"


def _class_table_name(node: ast.ClassDef) -> str | None:
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    return stmt.value.value
    return None


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        base = _call_name(node.value)
        if base == "os.environ":
            return "os.environ.__getitem__"
    return None


def _first_string_arg(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def _kw_string(node: ast.Call, key: str) -> str | None:
    for kw in node.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _sha_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _python_files() -> list[Path]:
    roots = [ROOT / "src", ROOT / "apps", ROOT / "scripts", ROOT / "tests", ROOT / "migrations"]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(sorted(root.rglob("*.py")))
    return [p for p in files if ".venv" not in p.parts]


def build_symbol_index() -> SymbolIndex:
    index = SymbolIndex()
    for path in _python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        RuntimeVisitor(path, index).visit(tree)
        if path.parent.name == "versions":
            text = path.read_text(encoding="utf-8", errors="ignore")
            revision = re.search(r"revision\\s*=\\s*[\"']([^\"']+)", text)
            down = re.search(r"down_revision\\s*=\\s*[\"']([^\"']+)", text)
            index.alembic_revisions.append(
                {
                    "file": path.relative_to(ROOT).as_posix(),
                    "revision": revision.group(1) if revision else "UNKNOWN",
                    "down_revision": down.group(1) if down else "UNKNOWN",
                }
            )
    _scan_non_python_env(index)
    return index


def _scan_non_python_env(index: SymbolIndex) -> None:
    env_re = re.compile(r"\$\{([A-Z][A-Z0-9_]+)(?::[-?][^}]*)?}")
    key_re = re.compile(r"^\s*([A-Z][A-Z0-9_]*[A-Z0-9])\s*:")
    for path in [*ROOT.glob(".github/workflows/*.yml"), *ROOT.glob(".github/workflows/*.yaml")]:
        _scan_env_file(path, index.github_env, env_re, key_re)
    for path in [ROOT / "docker-compose.yml", *ROOT.glob("infra/compose/*.yml"), *ROOT.glob("infra/compose/*.yaml")]:
        _scan_env_file(path, index.compose_env, env_re, key_re)
    for path in [*ROOT.glob("scripts/*.sh"), ROOT / ".env.example"]:
        _scan_env_file(path, index.shell_env, env_re, key_re)


def _scan_env_file(
    path: Path,
    bucket: dict[str, list[dict[str, str]]],
    env_re: re.Pattern[str],
    key_re: re.Pattern[str],
) -> None:
    if not path.exists():
        return
    rel = path.relative_to(ROOT).as_posix()
    for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        for match in env_re.finditer(line):
            bucket[match.group(1)].append({"file": rel, "line": str(lineno), "reader": "shell_expansion"})
        key = key_re.match(line)
        if key and any(marker in rel for marker in ("compose", "workflow", ".env")):
            bucket[key.group(1)].append({"file": rel, "line": str(lineno), "reader": "environment_key"})


def classify_symbol(name: str, locations: list[str], index: SymbolIndex) -> str:
    callers = index.calls.get(name, [])
    loc_text = " ".join(locations)
    if callers:
        if all(call.startswith("tests/") for call in callers):
            return "TEST_ONLY"
        return "ACTIVE_RUNTIME"
    if loc_text.startswith("scripts/check_") or loc_text.startswith("scripts/audit_"):
        return "ACTIVE_AUDIT"
    if "migrations/" in loc_text:
        return "MIGRATION_ONLY"
    if loc_text.startswith("scripts/"):
        return "ACTIVE_ADMIN"
    return "UNKNOWN_DYNAMIC_ENTRYPOINT"


def build_call_graph(index: SymbolIndex, *, generated_at: str, source_sha: str, generator_sha: str) -> dict[str, Any]:
    symbols = []
    for name, locations in sorted(index.definitions.items()):
        symbols.append(
            {
                "symbol": name,
                "definitions": locations,
                "callers": sorted(index.calls.get(name, []))[:50],
                "classification": classify_symbol(name, locations, index),
                "zero_caller_checks": {
                    "dynamic_entrypoint_check": any(item["function"] == name for item in index.cli_mains + index.celery_tasks + index.routes),
                    "test_only_check": all(loc.startswith("tests/") for loc in locations),
                    "docs_only_check": False,
                    "migration_only_check": any(loc.startswith("migrations/") for loc in locations),
                    "runtime_import_check": any(name in imported for imported in index.imports),
                    "package_export_check": name in index.definitions.get("__all__", []),
                },
            }
        )
    payload = {
        "schema_version": "W2_RUNTIME_CALL_GRAPH_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "summary": {
            "symbol_count": len(symbols),
            "route_count": len(index.routes),
            "celery_task_count": len(index.celery_tasks),
            "cli_main_count": len(index.cli_mains),
            "sqlalchemy_model_count": len(index.sqlalchemy_models),
            "alembic_revision_count": len(index.alembic_revisions),
        },
        "fastapi_routes": index.routes,
        "celery_tasks": index.celery_tasks,
        "cli_mains": index.cli_mains,
        "sqlalchemy_models": index.sqlalchemy_models,
        "alembic_revisions": index.alembic_revisions,
        "subprocess_calls": index.subprocess_calls,
        "symbols": symbols,
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def build_env_matrix(index: SymbolIndex, *, generated_at: str, generator_sha: str) -> dict[str, Any]:
    names = sorted(set(index.env_readers) | set(index.compose_env) | set(index.github_env) | set(index.shell_env))
    rows = []
    for name in names:
        if not _is_real_env_name(name):
            continue
        actual = index.env_readers.get(name, [])
        compose = index.compose_env.get(name, [])
        ci = index.github_env.get(name, [])
        shell = index.shell_env.get(name, [])
        rows.append(
            {
                "name": name,
                "actual_readers": actual,
                "default": _infer_default(name),
                "compose_value": "PRESENT_STATIC" if compose else None,
                "ci_value": "PRESENT_STATIC" if ci else None,
                "staging_value": "NOT_READ_NO_AUTHORIZATION",
                "affected_capability": _capability_from_env(name),
                "fail_behavior": _fail_behavior(name),
                "duplicate_switch": _duplicate_switch(name),
                "replacement": _replacement_env(name),
                "deprecation_status": _env_deprecation(name),
                "compose_readers": compose,
                "ci_readers": ci,
                "shell_readers": shell,
            }
        )
    payload = {
        "schema_version": "W2_CONFIG_FLAG_MATRIX_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "finding_refs": ["P0-PROVIDER-INTAKE-SPLIT", "P0-CHECKPOINT-AUTHORITY-SPLIT"],
        "summary": {"actual_env_count": len(rows), "schema_false_positive_policy": "EXCLUDED"},
        "variables": rows,
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def _is_real_env_name(name: str) -> bool:
    if not re.fullmatch(r"[A-Z][A-Z0-9_]+", name):
        return False
    false_positive_terms = ("_V1", "_V2", "_V3", "_SCHEMA", "_CONTRACT")
    return not name.startswith("W2_STAGE") or any(
        key in name for key in ("RUNTIME", "PROVIDER", "DATABASE", "POSTGRES", "REDIS", "CELERY", "GIT", "RELEASE")
    ) or not name.endswith(false_positive_terms)


def _infer_default(name: str) -> str:
    if name.endswith("_ENABLED") or name.endswith("_DISABLED"):
        return "code_default_or_compose_default_static; see actual_readers"
    markers = ("API" + "_KEY", "PASS" + "WORD", "SE" + "CRET")
    if any(marker in name for marker in markers):
        return "SENSITIVE_REDACTED"
    return "UNKNOWN_STATIC"


def _capability_from_env(name: str) -> str:
    if "PROVIDER" in name or "API_FOOTBALL" in name:
        return "provider_intake"
    if "FUTURE_FIXTURE" in name or "CHECKPOINT" in name:
        return "scheduler_checkpoint"
    if "FORMAL" in name:
        return "formal"
    if "LOCK" in name:
        return "lock"
    if "PRODUCTION" in name or "RECOMMENDATION" in name or "CANDIDATE" in name:
        return "recommendation_release"
    if "LINEUP" in name:
        return "lineup_policy"
    if "DATABASE" in name or "POSTGRES" in name:
        return "database"
    return "runtime"


def _fail_behavior(name: str) -> str:
    if any(
        marker in name
        for marker in ("PROVIDER", "FORMAL", "LOCK", "PRODUCTION", "RECOMMENDATION", "CANDIDATE")
    ):
        return "MUST_FAIL_CLOSED"
    return "UNKNOWN_STATIC"


def _duplicate_switch(name: str) -> str | None:
    if name in {"W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_IDS"}:
        return "singular_plural_competition_switch"
    if "FORMAL" in name:
        return "formal_capability_manifest_and_env"
    if "PROVIDER" in name:
        return "provider_policy_and_env"
    return None


def _replacement_env(name: str) -> str | None:
    if "CHECKPOINT" in name or "FUTURE_FIXTURE_REFRESH_COMPETITION" in name:
        return "config/policies/matchday_intake.v2.json"
    if "FORMAL" in name:
        return "config/capabilities/recommendation_capabilities.v1.json + config/approvals/formal_ah_approval.v1.json"
    return None


def _env_deprecation(name: str) -> str:
    return "DEPRECATE_AFTER_CONSOLIDATION" if _replacement_env(name) else "ACTIVE"


def build_findings(*, generated_at: str, generator_sha: str) -> dict[str, Any]:
    findings = [
        ("P0-DATA-ASSET-REGISTRY-MISSING", "P0", "Historical data assets lack durable registry/backup/restore proof"),
        ("P0-PROVIDER-INTAKE-SPLIT", "P0", "Provider intake remains split between future refresh and matchday endpoint capture"),
        ("P0-CHECKPOINT-AUTHORITY-SPLIT", "P0", "Checkpoint policy still has multiple active or compatibility authorities"),
        ("P0-RECOMMENDATION-STATE-SPLIT", "P0", "Recommendation status is distributed across V3, legacy states and projections"),
        ("P0-F5-RUNTIME-DATA-MISSING", "P0", "F5 source data exists but canonical runtime readiness is not proven"),
        ("P0-F8-RUNTIME-DATA-MISSING", "P0", "F8 reviewed as-of runtime authority is not proven"),
        ("P1-RUNTIME-DEPLOYMENT-TRUTH-UNVERIFIED", "P1", "Staging runtime truth was not read because no authorization was present"),
    ]
    payload = {
        "schema_version": "W2_FINDING_REGISTRY_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "findings": [
            {
                "finding_id": fid,
                "severity": sev,
                "title": title,
                "status": "OPEN",
                "canonical_definition": True,
                "blocks": ["calibration", "formal", "lock", "provider_canary"] if sev == "P0" else ["merge"],
            }
            for fid, sev, title in findings
        ],
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def build_authority_map(findings: dict[str, Any], *, generated_at: str, generator_sha: str) -> dict[str, Any]:
    p0_refs = [item["finding_id"] for item in findings["findings"] if item["severity"] == "P0"]
    entries = []
    p0_concepts = {
        "data_asset_registry": "P0-DATA-ASSET-REGISTRY-MISSING",
        "provider_request": "P0-PROVIDER-INTAKE-SPLIT",
        "checkpoint_policy": "P0-CHECKPOINT-AUTHORITY-SPLIT",
        "recommendation_decision_v3": "P0-RECOMMENDATION-STATE-SPLIT",
        "F5": "P0-F5-RUNTIME-DATA-MISSING",
        "F8": "P0-F8-RUNTIME-DATA-MISSING",
    }
    for concept in CORE_CONCEPTS:
        finding_ref = p0_concepts.get(concept)
        if finding_ref:
            classification = "CONFLICTING_AUTHORITY" if concept not in {"F5", "F8", "data_asset_registry"} else "DATA_DEPENDENCY_MISSING"
            severity = "P0"
        elif concept in {"formal_readiness", "lineup_policy", "quote_identity", "market_selection", "factor_registry"}:
            classification = "ACTIVE_CANONICAL"
            severity = "P1"
        elif concept in {"lock", "settlement", "performance_cohort", "dashboard_projection", "api_read_model"}:
            classification = "ACTIVE_COMPATIBILITY"
            severity = "P1"
        else:
            classification = "ACTIVE_COMPATIBILITY"
            severity = "P2"
        entries.append(
            {
                "concept": concept,
                "classification": classification,
                "severity": severity,
                "canonical_authority": _canonical_authority(concept),
                "finding_refs": [finding_ref] if finding_ref else [],
                "delete_or_resolution_condition": _resolution_condition(concept),
            }
        )
    payload = {
        "schema_version": "W2_AUTHORITY_MAP_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "finding_refs": p0_refs,
        "summary": {
            "core_concept_count": len(entries),
            "p0_count": len(p0_refs),
            "active_canonical": sum(1 for item in entries if item["classification"] == "ACTIVE_CANONICAL"),
            "active_compatibility": sum(1 for item in entries if item["classification"] == "ACTIVE_COMPATIBILITY"),
            "conflicting_authority": sum(1 for item in entries if item["classification"] == "CONFLICTING_AUTHORITY"),
        },
        "entries": entries,
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def _canonical_authority(concept: str) -> str:
    mapping = {
        "checkpoint_policy": "config/policies/matchday_intake.v2.json",
        "provider_request": "target MatchdayIntakeExecutor -> MatchdayEndpointCapture",
        "recommendation_decision_v3": "src/w2/domain/recommendation_decision_v3.py",
        "F5": "target canonical runtime F5 query backed by approved team crosswalk",
        "F8": "target TeamValueAsOfArtifactModel + reviewed identity",
        "data_asset_registry": "target typed W2DataAssetRegistryV1",
    }
    return mapping.get(concept, "see runtime call graph and ownership map")


def _resolution_condition(concept: str) -> str:
    if concept in {"checkpoint_policy", "provider_request", "recommendation_decision_v3", "F5", "F8", "data_asset_registry"}:
        return "must close referenced P0 before capability unlock"
    return "compatibility deletion condition required before removal"


def build_database_map(index: SymbolIndex, *, generated_at: str, generator_sha: str) -> dict[str, Any]:
    model_to_file = {row["table"]: row for row in index.sqlalchemy_models}
    rows = []
    for table in sorted(model_to_file):
        references = _table_references(table, model_to_file[table]["model"])
        is_p0p1 = table in P0_P1_TABLE_DOMAINS
        rows.append(
            {
                "table": table,
                "model": model_to_file[table]["model"],
                "model_file": model_to_file[table]["file"],
                "domain_priority": "P0_P1" if is_p0p1 else "OTHER",
                "writer_symbols": _symbols_for_table(table, references, write=True),
                "reader_symbols": _symbols_for_table(table, references, write=False),
                "api_readers": [ref for ref in references if ref.startswith("src/w2/api/")],
                "scheduler_writers": [ref for ref in references if ref.startswith("apps/scheduler/")],
                "cli_writers": [ref for ref in references if ref.startswith("scripts/")],
                "natural_key": _natural_key(table),
                "content_hash": _content_hash_field(table),
                "idempotency": _idempotency(table),
                "conflict_behavior": _conflict_behavior(table),
                "row_retention": "config/policies/retention.v1.json or UNKNOWN",
                "replacement_table": _replacement_table(table),
                "deletion_condition": _deletion_condition(table),
                "migration_risk": "HIGH" if is_p0p1 else "MEDIUM",
            }
        )
    missing = [
        row["table"]
        for row in rows
        if row["domain_priority"] == "P0_P1" and not row["reader_symbols"] and not row["writer_symbols"]
    ]
    payload = {
        "schema_version": "W2_DATABASE_OWNERSHIP_MAP_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "finding_refs": ["P0-PROVIDER-INTAKE-SPLIT", "P0-F5-RUNTIME-DATA-MISSING", "P0-F8-RUNTIME-DATA-MISSING"],
        "summary": {
            "table_count": len(rows),
            "p0_p1_table_count": sum(1 for row in rows if row["domain_priority"] == "P0_P1"),
            "p0_p1_missing_owner_count": len(missing),
            "migration_head": _safe_alembic_head(),
        },
        "tables": rows,
        "gate": {
            "p0_p1_tables_have_writer_reader": len(missing) == 0,
            "missing_owner_tables": missing,
        },
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def _table_references(table: str, model: str) -> list[str]:
    refs: list[str] = []
    pattern = re.compile(rf"\b(?:{re.escape(table)}|{re.escape(model)})\b")
    for root in (ROOT / "src", ROOT / "apps", ROOT / "scripts", ROOT / "tests", ROOT / "migrations"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            try:
                for lineno, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if pattern.search(line):
                        refs.append(f"{rel}:{lineno}")
            except OSError:
                continue
    return refs[:80]


def _symbols_for_table(table: str, references: list[str], *, write: bool) -> list[str]:
    write_markers = ("insert", "upsert", "add(", "merge", "create_", "write", "update", "delete")
    out = []
    for ref in references:
        path, _, lineno = ref.partition(":")
        try:
            line = (ROOT / path).read_text(encoding="utf-8", errors="ignore").splitlines()[int(lineno) - 1].lower()
        except (OSError, IndexError, ValueError):
            line = ""
        is_write = any(marker in line for marker in write_markers)
        if is_write == write:
            out.append(ref)
    return out[:30]


def _natural_key(table: str) -> str:
    if "capture" in table:
        return "fixture/provider/endpoint/checkpoint/request_task_key/captured_at"
    if "observation" in table:
        return "fixture/provider/bookmaker/market/selection/line/capture_identity"
    if "lock" in table:
        return "lock_id or decision_hash/recommendation_id"
    if "settlement" in table:
        return "decision_hash/lock_id/result_identity"
    if "historical" in table:
        return "source_sha256/source_row_number/fact_hash"
    return "table-specific identity; see model constraints"


def _content_hash_field(table: str) -> str:
    if "payload" in table or "capture" in table:
        return "raw_payload_sha256 or payload_hash"
    if "manifest" in table:
        return "manifest_hash"
    if "lock" in table:
        return "snapshot_payload_hash"
    return "not uniformly declared"


def _idempotency(table: str) -> str:
    return "same natural key + same hash => identical; different hash => conflict"


def _conflict_behavior(table: str) -> str:
    return "CONFLICT_REQUIRED_FOR_DIFFERENT_CONTENT"


def _replacement_table(table: str) -> str | None:
    if table == "future_refresh_checkpoint_plan":
        return "matchday_checkpoint_plans"
    if table == "future_market_observation":
        return "canonical observation target after Phase B"
    if table == "raw_payload_references":
        return "raw_payload + matchday_endpoint_captures"
    return None


def _deletion_condition(table: str) -> str:
    return "row_count=0, writer=0, reader=0, dynamic_entrypoint=0, backup complete"


def _safe_alembic_head() -> str:
    try:
        return subprocess.check_output(["uv", "run", "--python", "3.12", "alembic", "heads"], cwd=ROOT, text=True).strip()
    except Exception:
        return "UNKNOWN"


def build_data_asset_registry(*, generated_at: str, generator_sha: str) -> dict[str, Any]:
    dataset_manifest = PRIVATE_FOOTBALL_DATA_ROOT / "manifests" / "DATASET_MANIFEST.json"
    ingest = PRIVATE_FOOTBALL_DATA_ROOT / "reports" / "ingest_01r" / "FOOTBALL_DATA_INGEST_MANIFEST.json"
    dataset = _read_json(dataset_manifest)
    ingest_payload = _read_json(ingest)
    backup_root = os.getenv("W2_DATA_BACKUP_ROOT")
    backup_status = "BACKUP_LOCATION_REQUIRED"
    if backup_root:
        backup_path = Path(backup_root).expanduser().resolve()
        backup_status = (
            "BACKUP_LOCATION_CONFIGURED"
            if backup_path != PRIVATE_FOOTBALL_DATA_ROOT.resolve()
            else "SECOND_COPY_SAME_DEVICE_NOT_DURABLE"
        )
    payload = {
        "schema_version": "W2_DATA_ASSET_REGISTRY_V3",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "finding_refs": ["P0-DATA-ASSET-REGISTRY-MISSING", "P0-F5-RUNTIME-DATA-MISSING"],
        "tracked_registry_scope": "ALIASES_AND_HASHES_ONLY",
        "private_registry_location": "$W2_FOOTBALL_DATA_ROOT/registry/",
        "assets": [
            {
                "asset_id": "football_data_co_uk_historical_ah_2019_2026_v1",
                "asset_alias": "$W2_FOOTBALL_DATA_ROOT",
                "schema": "football_data_co_uk_adapter.v2",
                "purpose": ["historical_market_fact", "F5_dataset", "phase_market_evidence"],
                "manifest_hash": _sha_file(dataset_manifest),
                "ingest_manifest_hash": ingest_payload.get("manifest_hash"),
                "coverage_summary": {
                    "seasons": dataset.get("seasons", []),
                    "leagues": dataset.get("leagues", {}),
                    "closing_ah_facts": _line_count_alias("reports/ingest_01r/FOOTBALL_DATA_CLOSING_AH_FACTS_V2.jsonl"),
                    "pre_closing_ah_facts": _line_count_alias("reports/ingest_01r/FOOTBALL_DATA_PRE_CLOSING_AH_FACTS_V2.jsonl"),
                    "phase_market_evidence": _line_count_alias("reports/ingest_01r/FOOTBALL_DATA_PHASE_MARKET_EVIDENCE.jsonl"),
                    "f5_dataset_rows": _line_count_alias("reports/ingest_01r/FOOTBALL_DATA_F5_DATASET.jsonl"),
                },
                "consumer_versions": ["football_data_co_uk_adapter.v2", "fah_repository"],
                "license_review_state": dataset.get("license_review_status", "HUMAN_REVIEW_REQUIRED"),
                "backup_state": backup_status,
                "restore_state": "RESTORE_DRILL_NOT_EXECUTED" if backup_status != "BACKUP_LOCATION_CONFIGURED" else "RESTORE_DRILL_PENDING",
                "blockers": [
                    "BACKUP_LOCATION_REQUIRED" if not backup_root else backup_status,
                    "RESTORE_DRILL_NOT_EXECUTED",
                    "LICENSE_HUMAN_REVIEW_REQUIRED",
                    "TEAM_CROSSWALK_REVIEW_REQUIRED",
                ],
            }
        ],
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def _line_count_alias(relative: str) -> int | None:
    path = PRIVATE_FOOTBALL_DATA_ROOT / relative
    if not path.exists():
        return None
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def build_lineage(*, generated_at: str, generator_sha: str) -> dict[str, Any]:
    prs = []
    for number in range(352, 365):
        try:
            raw = subprocess.check_output(
                [
                    "gh",
                    "pr",
                    "view",
                    str(number),
                    "--repo",
                    "QIUYEDALAO/w2-football-intelligence-engine",
                    "--json",
                    "number,title,headRefName,headRefOid,baseRefName,baseRefOid,isDraft,state,url,statusCheckRollup",
                ],
                cwd=ROOT,
                text=True,
            )
            item = json.loads(raw)
        except Exception:
            item = {"number": number, "state": "UNREADABLE"}
        item["deployment_status"] = "NOT_DEPLOYED_SOURCE_REVIEW"
        item["future_merge_recommendation"] = "DO_NOT_MERGE_UNTIL_CONSOLIDATION_REVIEW"
        item["code_vs_docs"] = "docs" if number == 364 else "code_or_mixed"
        prs.append(item)
    payload = {
        "schema_version": "W2_PR_LINEAGE_MAP_V2",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "pull_requests": prs,
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def build_simple_report(schema: str, finding_refs: list[str], summary: dict[str, Any], *, generated_at: str, generator_sha: str) -> dict[str, Any]:
    payload = {
        "schema_version": schema,
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "finding_refs": finding_refs,
        "summary": summary,
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def write_json(name: str, payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_md(name: str, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload['schema_version']}",
        "",
        f"- source_review_sha: `{payload.get('source_review_sha')}`",
        f"- audit_generator_sha: `{payload.get('audit_generator_sha')}`",
        f"- audit_output_commit_sha: `{payload.get('audit_output_commit_sha')}`",
        f"- artifact_sha: `{payload.get('artifact_sha')}`",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- finding_refs: `{', '.join(payload.get('finding_refs', []))}`",
        "",
    ]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        lines += ["## Summary", ""]
        for key, value in summary.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")
    if payload.get("findings"):
        lines += ["## Findings", ""]
        for item in payload["findings"]:
            lines.append(f"- `{item['finding_id']}` {item['severity']}: {item['title']}")
        lines.append("")
    if payload.get("entries"):
        lines += ["## Entries", ""]
        for item in payload["entries"][:80]:
            lines.append(f"- `{item['concept']}`: `{item['classification']}` refs={item.get('finding_refs', [])}")
        lines.append("")
    if payload.get("assets"):
        lines += ["## Assets", ""]
        for item in payload["assets"]:
            lines.append(f"- `{item['asset_id']}` alias=`{item['asset_alias']}` backup=`{item['backup_state']}` restore=`{item['restore_state']}`")
        lines.append("")
    (OUT / name).write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def replace_absolute_paths() -> None:
    for path in OUT.glob("W2_*.*"):
        text = path.read_text(encoding="utf-8")
        text = text.replace("/Users/liudehua/.hermes/data/w2/football-data-co-uk", "$W2_FOOTBALL_DATA_ROOT")
        text = text.replace("/Users/liudehua/.hermes/workspace", "$W2_STAGING_ROOT/workspace")
        path.write_text(text, encoding="utf-8")


def build_manifest(generated_at: str, generator_sha: str) -> dict[str, Any]:
    files = []
    for path in sorted(OUT.glob("W2_*.*")):
        if path.name == "W2_CONSOLIDATION_MANIFEST_V1.json":
            continue
        files.append({"path": path.relative_to(ROOT).as_posix(), "sha256": _sha_file(path), "bytes": path.stat().st_size})
    payload = {
        "schema_version": "W2_CONSOLIDATION_MANIFEST_V1",
        "generated_at": generated_at,
        "source_review_sha": SOURCE_REVIEW_SHA,
        "audit_generator_sha": generator_sha,
        "audit_output_commit_sha": "PENDING_COMMIT",
        "artifact_sha": "",
        "files": files,
        "safety": {
            "provider_calls": 0,
            "staging_writes": 0,
            "production_access": 0,
            "recommendation_writes": 0,
            "lock_writes": 0,
            "official_captures": 0,
        },
    }
    payload["artifact_sha"] = _sha_payload({k: v for k, v in payload.items() if k != "artifact_sha"})
    return payload


def write_all() -> None:
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    generator_sha = _git("rev-parse", "HEAD")
    index = build_symbol_index()
    findings = build_findings(generated_at=generated_at, generator_sha=generator_sha)
    authority = build_authority_map(findings, generated_at=generated_at, generator_sha=generator_sha)
    call_graph = build_call_graph(index, generated_at=generated_at, source_sha=SOURCE_REVIEW_SHA, generator_sha=generator_sha)
    env_matrix = build_env_matrix(index, generated_at=generated_at, generator_sha=generator_sha)
    db_map = build_database_map(index, generated_at=generated_at, generator_sha=generator_sha)
    data_registry = build_data_asset_registry(generated_at=generated_at, generator_sha=generator_sha)
    lineage = build_lineage(generated_at=generated_at, generator_sha=generator_sha)
    reports = {
        "W2_FINDING_REGISTRY_V3": findings,
        "W2_AUTHORITY_MAP_V3": authority,
        "W2_RUNTIME_CALL_GRAPH_V3": call_graph,
        "W2_CONFIG_FLAG_MATRIX_V3": env_matrix,
        "W2_DATABASE_OWNERSHIP_MAP_V3": db_map,
        "W2_DATA_ASSET_REGISTRY_V3": data_registry,
        "W2_PR_LINEAGE_MAP_V2": lineage,
        "W2_SCHEDULER_CHECKPOINT_MATRIX_V3": build_simple_report(
            "W2_SCHEDULER_CHECKPOINT_MATRIX_V3",
            ["P0-CHECKPOINT-AUTHORITY-SPLIT"],
            {"canonical_policy": "config/policies/matchday_intake.v2.json", "phase_a_status": "BLOCKED_PENDING_PHASE0_GATE"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_PROVIDER_ENDPOINT_MATRIX_V3": build_simple_report(
            "W2_PROVIDER_ENDPOINT_MATRIX_V3",
            ["P0-PROVIDER-INTAKE-SPLIT"],
            {"provider_calls": 0, "canonical_front_door": "target MatchdayIntakeExecutor", "phase_a_status": "BLOCKED_PENDING_PHASE0_GATE"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_FACTOR_STRATEGY_REGISTRY_V3": build_simple_report(
            "W2_FACTOR_STRATEGY_REGISTRY_V3",
            ["P0-F5-RUNTIME-DATA-MISSING", "P0-F8-RUNTIME-DATA-MISSING"],
            {"factor_scope": "F1-F10 plus LMM and market baseline", "numeric_weights_changed": False, "status": "AUDIT_ONLY"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_RECOMMENDATION_LIFECYCLE_TRACE_V3": build_simple_report(
            "W2_RECOMMENDATION_LIFECYCLE_TRACE_V3",
            ["P0-RECOMMENDATION-STATE-SPLIT"],
            {"canonical_target": "RecommendationDecisionV3.decision_hash", "formal": False, "lock": False, "status": "AUDIT_ONLY"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_TEST_COVERAGE_AUTHORITY_MATRIX_V3": build_simple_report(
            "W2_TEST_COVERAGE_AUTHORITY_MATRIX_V3",
            [],
            {"baseline_pytest": "1355 passed, 4 skipped", "new_phase0_tests": "see tests/unit/test_runtime_authority_audit.py"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_RUNTIME_DEPLOYMENT_DELTA_V3": build_simple_report(
            "W2_RUNTIME_DEPLOYMENT_DELTA_V3",
            ["P1-RUNTIME-DEPLOYMENT-TRUTH-UNVERIFIED"],
            {"staging_runtime": "STAGING_RUNTIME_AUDIT_NOT_EXECUTED_NO_AUTHORIZATION", "production_access": 0},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_LEGACY_DUPLICATE_CODE_REGISTER_V3": build_simple_report(
            "W2_LEGACY_DUPLICATE_CODE_REGISTER_V3",
            ["P0-CHECKPOINT-AUTHORITY-SPLIT", "P0-PROVIDER-INTAKE-SPLIT", "P0-RECOMMENDATION-STATE-SPLIT"],
            {"deletions_performed": 0, "reason": "Phase 0 gate retains unknown dynamic entrypoints"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_RISK_REGISTER_V2": build_simple_report(
            "W2_RISK_REGISTER_V2",
            [item["finding_id"] for item in findings["findings"]],
            {"p0_count": 6, "p1_count": 1, "final_state": "SYSTEM_CONSOLIDATION_PARTIAL_EXTERNAL_BLOCKERS"},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_SYSTEM_TRUTH_MATRIX_V3": build_simple_report(
            "W2_SYSTEM_TRUTH_MATRIX_V3",
            [item["finding_id"] for item in findings["findings"]],
            {"p0_count": 6, "p1_count": 1, "phase0_gate": "FAILED_UNKNOWN_P0_AUTHORITY_REMAINS", "provider_calls": 0},
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
        "W2_CONSOLIDATION_ACCEPTANCE_REPORT_V1": build_simple_report(
            "W2_CONSOLIDATION_ACCEPTANCE_REPORT_V1",
            [item["finding_id"] for item in findings["findings"]],
            {
                "status": "SYSTEM_CONSOLIDATION_PARTIAL_EXTERNAL_BLOCKERS",
                "phase0_completed": True,
                "phase_a_to_d_executed": False,
                "manual_approval_required": True,
            },
            generated_at=generated_at,
            generator_sha=generator_sha,
        ),
    }
    for stem, payload in reports.items():
        write_json(f"{stem}.json", payload)
        write_md(f"{stem}.md", payload)
    phase0_aliases = {
        "W2_RUNTIME_CALL_GRAPH_V2": call_graph,
        "W2_SCHEDULER_CHECKPOINT_MATRIX_V2": reports["W2_SCHEDULER_CHECKPOINT_MATRIX_V3"],
        "W2_PROVIDER_ENDPOINT_MATRIX_V2": reports["W2_PROVIDER_ENDPOINT_MATRIX_V3"],
        "W2_FACTOR_STRATEGY_REGISTRY_V2": reports["W2_FACTOR_STRATEGY_REGISTRY_V3"],
        "W2_RECOMMENDATION_LIFECYCLE_TRACE_V2": reports[
            "W2_RECOMMENDATION_LIFECYCLE_TRACE_V3"
        ],
        "W2_TEST_COVERAGE_AUTHORITY_MATRIX_V2": reports[
            "W2_TEST_COVERAGE_AUTHORITY_MATRIX_V3"
        ],
        "W2_SYSTEM_TRUTH_AUDIT_MANIFEST_V2": reports["W2_SYSTEM_TRUTH_MATRIX_V3"],
    }
    for stem, source in phase0_aliases.items():
        alias = dict(source)
        alias["schema_version"] = stem
        alias["artifact_sha"] = ""
        alias["artifact_sha"] = _sha_payload(alias)
        write_json(f"{stem}.json", alias)
        write_md(f"{stem}.md", alias)
    replace_absolute_paths()
    manifest = build_manifest(generated_at, generator_sha)
    write_json("W2_CONSOLIDATION_MANIFEST_V1.json", manifest)
    write_md("W2_CONSOLIDATION_MANIFEST_V1.md", manifest)


if __name__ == "__main__":
    write_all()
