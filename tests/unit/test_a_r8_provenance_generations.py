"""A-R8-02: three provenance generations, full-module replay from Git history.

A-R5 (d1a3eced): no content-profile marker, digest-only provenance.
A-R6 (fa275b3f): no marker, but provenance already carries analysis_evidence content.
A-R7+ (current): explicit content profile marker + content.

Each generation is materialized by the full read_model_projection module from that
commit (not just _dynamic_evaluations), written by that module's writer, read back
by the current reader, then retried through the real repository -- asserting the
same-identity retry is idempotent and the historical representation is preserved.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import types
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.legacy_v4_repository import install_legacy_v4_writer

from w2.infrastructure.persistence.dynamic_prematch_models import DynamicPrematchEvaluationModel
from w2.prematch import read_model_projection as current
from w2.prematch.repository import DynamicPrematchRepository, _version_from_payload

REPO = Path(__file__).resolve().parents[2]
A_R5_SHA = "d1a3eced371780c9bbd997a06d5263572e6feaa4"
A_R6_SHA = "fa275b3f2073629633a94c66fd7bee98b56445f6"
MODULE_PATH = "src/w2/prematch/read_model_projection.py"

# Import helpers from the A-R5/A-R7 real-chain test without running its tests.
import runpy  # noqa: E402

_real = runpy.run_path(str(REPO / "tests/unit/test_a_r5_real_chain.py"))


def _load_historical_module(sha: str, name: str) -> types.ModuleType:
    source = subprocess.run(
        ["git", "show", f"{sha}:{MODULE_PATH}"],
        cwd=REPO,
        check=True,
        capture_output=True,
    ).stdout.decode()
    spec = importlib.util.spec_from_loader(name, loader=None)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclasses defined in the module can resolve their
    # own module namespace during class creation.
    sys.modules[name] = module
    exec(source, module.__dict__)  # noqa: S102 - load a fixed Git commit's module for replay
    return module


def _historical_write(module: types.ModuleType, engine: Any, artifact: Any) -> None:
    """The pinned historical producer writes; current consumer retries later."""
    with pytest.MonkeyPatch.context() as patch:
        install_legacy_v4_writer(patch)
        module.write_frozen_analysis_artifacts(engine, [artifact])


def _materializer(module: types.ModuleType, engine: Any) -> Any:
    def calculate(repository: Any, fixture_id: str, evaluated_at: datetime):
        del repository, evaluated_at
        if fixture_id != _real["FIXTURE_ID"]:
            return None
        import copy

        return copy.deepcopy(_real["_flat_card"]())

    return module.AnalysisCardCanaryMaterializer(
        _real["ScopedRepository"](),
        calculate_analysis_card=calculate,
        build_scoreline_reference=lambda card, version, quote_identity: {
            "source": "formal_simulation",
            "scoreline_projection": {
                "status": "READY",
                "decision_hash": version.identity_hash,
                "top3": [{"scoreline": "1-0"}],
            },
        },
        clock=lambda: _real["EVALUATED_AT"],
    )


def _build_shadow(engine: Any, module: types.ModuleType) -> tuple[Any, Any]:
    """Build the canary -> capture -> opportunity -> shadow chain with a given module."""
    materializer = _materializer(module, engine)
    artifact = materializer.build(
        _real["FIXTURE_ID"], evaluated_at=_real["EVALUATED_AT"], source_event=None
    )
    _historical_write(module, engine, artifact)
    reader = _real["ReadModelService"](repository=_real["FrozenReaderRepository"](engine))
    card = reader.public_analysis_card_bounded(
        _real["FIXTURE_ID"], use_frozen_canary=True
    )
    simulation = card.get("simulation") or {}
    model_forecast_card = {
        **card,
        "simulation": {"status": simulation.get("status"), "simulation": simulation},
    }
    _real["run_model_forecast_capture"](
        {"cards": [model_forecast_card]},
        repository=_real["ModelForecastLedgerRepository"](engine),
        captured_at=_real["CAPTURED_AT"],
        dry_run=False,
        write_db=True,
    )
    with Session(engine) as session:
        capture = session.scalar(select(_real["ModelForecastCaptureModel"]))
        capture_hash = capture.capture_identity_hash
        model_input_hash = capture.model_input_manifest_hash
    context = _real["EvaluationOpportunityContext"](
        model_forecast_capture_identity_hash=capture_hash,
        model_input_hash=model_input_hash,
        evaluation_policy_version=_real["CURRENT_EVALUATION_POLICY"],
        evaluation_slot_id="T3_ODDS",
        scheduled_checkpoint_at=_real["EVALUATED_AT"],
        checkpoint_plan_identity="plan-1",
        source_event_identity="event-1",
    )
    bound = materializer.build(
        _real["FIXTURE_ID"],
        evaluated_at=_real["EVALUATED_AT"],
        source_event=_real["_event"]((context,)),
    )
    return materializer, bound


def _write_and_read_back(engine: Any, module: types.ModuleType, artifact: Any) -> Any:
    _historical_write(module, engine, artifact)
    with Session(engine) as session:
        rows = list(
            session.scalars(select(DynamicPrematchEvaluationModel)).all()
        )
    assert rows
    return [_version_from_payload(dict(row.payload)) for row in rows]


def _new_engine():
    engine = _real["_engine"]()
    _real["_seed_xg"](engine)
    _real["_seed_quote_pair"](engine)
    return engine


def test_r8_02_three_generations_content_and_idempotency() -> None:
    r5 = _load_historical_module(A_R5_SHA, "w2_r5_read_model_projection")
    r6 = _load_historical_module(A_R6_SHA, "w2_r6_read_model_projection")

    # A-R5: digest-only.
    engine = _new_engine()
    _, artifact = _build_shadow(engine, r5)
    assert all(
        "analysis_evidence" not in ev.producer_input_provenance
        for ev in artifact.evaluations
    )
    evals = _write_and_read_back(engine, r5, artifact)
    assert all("analysis_evidence" not in ev.producer_input_provenance for ev in evals)

    # A-R6: no marker, but content carried.
    engine = _new_engine()
    _, artifact = _build_shadow(engine, r6)
    assert all(
        "analysis_evidence" in ev.producer_input_provenance
        for ev in artifact.evaluations
    )
    evals = _write_and_read_back(engine, r6, artifact)
    assert all("analysis_evidence" in ev.producer_input_provenance for ev in evals)
    # Read-time replay (no DB) of a marker-less artifact is digest-only; the write
    # path decides from the actually-frozen evaluation payload (see the old->new
    # retry test below) and re-attaches the content.
    current_read = current.validate_frozen_analysis_payload(
        _real["FIXTURE_ID"], artifact.payload
    )
    assert all(
        "analysis_evidence" not in ev.producer_input_provenance
        for ev in current_read.evaluations
    )

    # A-R7+: explicit profile + content.
    engine = _new_engine()
    _, artifact = _build_shadow(engine, current)
    assert all(
        "analysis_evidence" in ev.producer_input_provenance
        for ev in artifact.evaluations
    )
    evals = _write_and_read_back(engine, current, artifact)
    assert all("analysis_evidence" in ev.producer_input_provenance for ev in evals)


def test_r8_02_same_identity_retry_idempotent_per_generation() -> None:
    r5 = _load_historical_module(A_R5_SHA, "w2_r5_read_model_projection_r")
    r6 = _load_historical_module(A_R6_SHA, "w2_r6_read_model_projection_r")

    for name, module in (("r5", r5), ("r6", r6), ("r7", current)):
        engine = _new_engine()
        _, artifact = _build_shadow(engine, module)
        _historical_write(module, engine, artifact)
        with Session(engine) as session:
            row = session.scalar(select(DynamicPrematchEvaluationModel))
        evaluation = _version_from_payload(dict(row.payload))

        repository = DynamicPrematchRepository(engine)
        with Session(engine) as session:
            prior, created = repository.append_evaluation_in_session(
                session, evaluation
            )
            session.commit()
        assert created is False, name
        assert prior.evaluation_id == evaluation.evaluation_id, name


def test_r8_02_a_r6_unmarked_content_old_to_new_retry() -> None:
    """A-R6 marker-less content: old module writes, current reader replays the same
    artifact, the frozen content is re-attached and the retry stays idempotent."""
    r6 = _load_historical_module(A_R6_SHA, "w2_r6_read_model_projection_oldnew")
    engine = _new_engine()
    _, artifact = _build_shadow(engine, r6)

    # Old (A-R6) module writes with content.
    _historical_write(r6, engine, artifact)

    # Current reader replays the marker-less artifact; the write path re-attaches
    # the frozen content so the retry does not conflict.
    current.write_frozen_analysis_artifacts(engine, [artifact])

    with Session(engine) as session:
        row = session.scalar(select(DynamicPrematchEvaluationModel))
    evaluation = _version_from_payload(dict(row.payload))
    assert "analysis_evidence" in evaluation.producer_input_provenance

    repository = DynamicPrematchRepository(engine)
    with Session(engine) as session:
        prior, created = repository.append_evaluation_in_session(session, evaluation)
        session.commit()
    assert created is False
    assert prior.evaluation_id == evaluation.evaluation_id
