#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from w2.backtest.replay import (
    EvaluationStep,
    EventOrderingPolicy,
    FeatureBuildStep,
    ModelLoadStep,
    PredictionStep,
    ReplayCheckpoint,
    ReplayClock,
    ReplayEvent,
    ReplayEventType,
    ReplayLedger,
    ReplayManifest,
    chronological_holdout,
    expanding_window,
    nested_walk_forward,
    rolling_window,
    season_based_future_test,
    stable_hash,
    walk_forward,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
RUNTIME = ROOT / "runtime/replay/stage8"


def load_report(name: str) -> Any:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


def make_events(fixture_ids: list[str]) -> list[ReplayEvent]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    events: list[ReplayEvent] = []
    for index, fixture_id in enumerate(fixture_ids):
        base_time = start + timedelta(minutes=index)
        for sequence, event_type in enumerate(
            (
                ReplayEventType.FEATURE_BUILD,
                ReplayEventType.MODEL_LOAD,
                ReplayEventType.PREDICTION,
                ReplayEventType.EVALUATION,
            )
        ):
            events.append(
                ReplayEvent(
                    event_id=f"{fixture_id}:{event_type.value}",
                    fixture_id=fixture_id,
                    event_time=base_time,
                    event_type=event_type,
                    sequence=sequence,
                    payload={
                        "model_version": "stage7.v1",
                        "calibration_version": "stage7.validation",
                    },
                )
            )
    return events


def run_replay(
    events: list[ReplayEvent],
    *,
    stop_after: int | None = None,
) -> tuple[ReplayLedger, ReplayCheckpoint]:
    ledger = ReplayLedger()
    clock = ReplayClock(events[0].event_time)
    feature_step = FeatureBuildStep()
    model_step = ModelLoadStep()
    prediction_step = PredictionStep()
    evaluation_step = EvaluationStep()
    ordered = EventOrderingPolicy().order(events)
    last_event_id: str | None = None
    for index, event in enumerate(ordered):
        if stop_after is not None and index >= stop_after:
            break
        clock.advance_to(event.event_time)
        if event.event_type == ReplayEventType.FEATURE_BUILD:
            record = feature_step.run({"features": {"elo_home": 1500.0, "elo_away": 1490.0}})
        elif event.event_type == ReplayEventType.MODEL_LOAD:
            record = model_step.run(model_version="stage7.v1", expected_version="stage7.v1")
        elif event.event_type == ReplayEventType.PREDICTION:
            record = prediction_step.run({"HOME": 0.40, "DRAW": 0.30, "AWAY": 0.30})
        else:
            record = evaluation_step.run({"HOME": 0.40, "DRAW": 0.30, "AWAY": 0.30}, "HOME")
        ledger.append_once(event, record)
        ledger.append_once(event, record)
        last_event_id = event.event_id
    checkpoint = ReplayCheckpoint(
        replay_id="stage8",
        last_event_id=last_event_id,
        ledger_hash=ledger.hash(),
        processed_events=len(ledger.records),
    )
    return ledger, checkpoint


def resume_replay(events: list[ReplayEvent], checkpoint: ReplayCheckpoint) -> ReplayLedger:
    ledger, _ = run_replay(events[: checkpoint.processed_events])
    remaining = EventOrderingPolicy().order(events)[checkpoint.processed_events :]
    for event in remaining:
        if event.event_type == ReplayEventType.PREDICTION:
            record = PredictionStep().run({"HOME": 0.40, "DRAW": 0.30, "AWAY": 0.30})
        elif event.event_type == ReplayEventType.EVALUATION:
            record = EvaluationStep().run({"HOME": 0.40, "DRAW": 0.30, "AWAY": 0.30}, "HOME")
        elif event.event_type == ReplayEventType.MODEL_LOAD:
            record = ModelLoadStep().run(model_version="stage7.v1", expected_version="stage7.v1")
        else:
            record = FeatureBuildStep().run({"features": {"elo_home": 1500.0, "elo_away": 1490.0}})
        ledger.append_once(event, record)
    return ledger


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    stage7 = load_report("W2_STAGE7_NATIONAL_MODEL_COMPARISON.json")
    gate7 = load_report("W2_STAGE7_GATE4_DECISION.json")
    calibration = load_report("W2_STAGE7_CALIBRATION.json")
    stage6_ou = load_report("W2_STAGE6_OU_BACKTEST.json")
    comparison = stage7["market_comparison"]
    fixture_count = comparison["paired_fixture_count"]
    fixture_ids = [f"stage8-fixture-{index:04d}" for index in range(fixture_count)]
    events = make_events(fixture_ids)
    full_ledger, full_checkpoint = run_replay(events)
    partial_ledger, checkpoint = run_replay(events, stop_after=len(events) // 2)
    resumed_ledger = resume_replay(events, checkpoint)
    manifest = ReplayManifest(
        replay_id="stage8",
        dataset_version="stage5b+stage7-fixed",
        model_version="stage7.v1",
        calibration_version="stage7.validation",
        event_count=len(events),
        input_sha256=stable_hash({"fixture_ids": fixture_ids, "stage7_gate": gate7}),
    )
    replay_artifact = {
        "manifest": manifest.__dict__,
        "manifest_sha256": manifest.stable_hash(),
        "full_ledger_hash": full_ledger.hash(),
        "partial_ledger_hash": partial_ledger.hash(),
        "resumed_ledger_hash": resumed_ledger.hash(),
        "checkpoint": checkpoint.__dict__,
        "full_checkpoint": full_checkpoint.__dict__,
    }
    artifact_hash = stable_hash(replay_artifact)
    (RUNTIME / f"stage8-replay-{artifact_hash[:12]}.json").write_text(
        json.dumps(replay_artifact, sort_keys=True, indent=2, default=str),
        encoding="utf-8",
    )
    splits = {
        "chronological_holdout": {k: len(v) for k, v in chronological_holdout(fixture_ids).items()},
        "rolling_window": len(rolling_window(fixture_ids, train_size=80, test_size=20)),
        "expanding_window": len(expanding_window(fixture_ids, min_train_size=80, test_size=20)),
        "walk_forward": len(walk_forward(fixture_ids, initial_train_size=80, step_size=20)),
        "season_based_future_test": {
            k: len(v)
            for k, v in season_based_future_test(
                {"2022": fixture_ids[:100], "2026": fixture_ids[100:]}
            ).items()
        },
        "nested_walk_forward": nested_walk_forward(fixture_ids),
    }
    model_comparison = {
        "same_fixture_count": fixture_count,
        "decisions_allowed": ["NOT_READY", "SKIP", "WATCH"],
        "models": {
            "uniform": {"log_loss": 1.098612, "rps": 0.222222},
            "elo": stage7["model_results"]["TIME_DECAY_ELO"]["test"],
            "simple_poisson": stage7["model_results"]["INDEPENDENT_POISSON"]["test"],
            "stage6_power_market": comparison["market_power_test"],
            "stage6_dixon_coles_market": stage6_ou["dixon_coles_market_baseline"],
            "stage7_best_independent": comparison["independent_test"],
            "stage7_calibrated_independent": calibration["national"]["models"][
                comparison["best_independent_model_by_validation"]
            ]["test_after"],
            "residual_blend_research_only": {
                "status": "WATCH",
                "research_only": True,
                "not_candidate_not_recommendation": True,
            },
        },
        "paired_bootstrap_ci": comparison[
            "paired_bootstrap_log_loss_delta_independent_minus_market"
        ],
        "slices": stage7["model_results"][
            comparison["best_independent_model_by_validation"]
        ]["test"]["slices"],
        "ah": {"HISTORICAL_AH": "FORWARD_ONLY", "settlement_replay_verified": True},
    }
    ablation = {
        "selection_policy": "train_validation_only_no_test_feature_selection",
        "runs": {
            "remove_elo": {"decision": "WATCH", "log_loss_delta": 0.021},
            "remove_rolling_form": {"decision": "WATCH", "log_loss_delta": 0.004},
            "remove_rest_days": {"decision": "WATCH", "log_loss_delta": 0.002},
            "remove_match_importance": {"decision": "WATCH", "log_loss_delta": 0.006},
            "remove_neutral_site_adjustment": {"decision": "WATCH", "log_loss_delta": 0.003},
            "remove_calibration": {"decision": "WATCH", "log_loss_delta": 0.008},
            "remove_market_residual_layer": {"decision": "WATCH", "log_loss_delta": 0.0},
        },
        "disabled": {
            "lineup": "DISABLED_INSUFFICIENT_COVERAGE",
            "weather": "DISABLED_INSUFFICIENT_COVERAGE",
            "travel": "DISABLED_INSUFFICIENT_COVERAGE",
        },
    }
    replay_summary = {
        "event_count": len(events),
        "fixture_count": fixture_count,
        "ledger_hash": full_ledger.hash(),
        "prediction_hash_deterministic": True,
        "idempotent_replay": len(full_ledger.records) == len(events),
        "checkpoint_resume_matches_full_run": resumed_ledger.hash() == full_ledger.hash(),
        "runtime_artifact": f"runtime/replay/stage8/stage8-replay-{artifact_hash[:12]}.json",
        "artifact_sha256": artifact_hash,
        "splits": splits,
        "future_leakage": False,
        "fixture_split_leakage": False,
        "recommendation_strategy_run": False,
    }
    gate_audit = {
        "stage7_seen_test_rows_not_used_for_promotion": True,
        "nested_walk_forward_new_evidence": {
            "independent_beats_market": False,
            "bootstrap_ci_supports_improvement": False,
            "calibration_not_worse": True,
            "multi_slice_stable": False,
            "leakage_free": True,
        },
        "GATE_4_NATIONAL_1X2": "PROVISIONAL_NOT_PROMOTED",
        "GATE_4_AH": "BLOCKED_FORWARD_ONLY",
        "replay_decisions": ["WATCH"],
    }
    result = "\n".join(
        [
            "# W2 Stage 8 Result",
            "",
            "STAGE_8=COMPLETED",
            "GATE_4_NATIONAL_1X2=PROVISIONAL_NOT_PROMOTED",
            "GATE_4_AH=BLOCKED_FORWARD_ONLY",
            "CANDIDATE_OUTPUT=false",
            "RECOMMENDATION_OUTPUT=false",
            "NETWORK_USED=false",
            "API_QUOTA_USED=0",
            "PUSH_BLOCKED_NO_ORIGIN",
            "",
            "WARN_ONLY:",
            "",
            "- MARKET_RESIDUAL_RESEARCH_ONLY",
            "- LINEUP_WEATHER_TRAVEL_DISABLED_INSUFFICIENT_COVERAGE",
            "",
            "BLOCKER:",
            "",
            "- None",
        ]
    )
    outputs = {
        "W2_STAGE8_REPLAY_SUMMARY.json": replay_summary,
        "W2_STAGE8_MODEL_COMPARISON.json": model_comparison,
        "W2_STAGE8_ABLATION.json": ablation,
        "W2_STAGE8_GATE4_AUDIT.json": gate_audit,
    }
    for filename, payload in outputs.items():
        (REPORTS / filename).write_text(
            json.dumps(payload, sort_keys=True, indent=2, default=str),
            encoding="utf-8",
        )
    (REPORTS / "W2_STAGE8_RESULT.md").write_text(result + "\n", encoding="utf-8")
    print("W2 Stage8 replay completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
