"""Record the four AH factors of a real production evaluation.

F1R-B delivered the wiring and left it unconnected: `build_production_batch` and
`ForwardFactorObservationStore.append_batch` existed, were tested against rows
shaped exactly like the production projections, and no production path called
them, so `forward_ah_factor_observations` stayed at zero rows. This module is
the connection and nothing else.

What it does
------------
The production dynamic evaluation computes a `FeatureSet` and the authoritative
`team_score` in one place -- `ReadModelService._db_analysis_card_from_fixture`.
That is where the final `FeatureContribution` objects and the weighted score
already exist, so that is where the recorder is called. It:

* re-uses `independent_team_scores_from_contributions` through the F1R-B
  integration, so participation and applied weight are the scoring authority's
  verdict and are not recomputed here;
* re-uses `w2.domain.factor_versions` for the per-factor version, so a caller
  cannot name a computation it did not run;
* re-uses the F1R-B read ports for the source-observed time of each factor;
* calls the accepted `build_production_batch` and `append_batch` unchanged.

What it does not do
-------------------
It computes no score, changes no weight, admits nothing and calls no Provider.
It reads `canonical_team_match_history`, `matchday_endpoint_captures` and the
snapshot rows the factor already consumed, and writes only to
`forward_ah_factor_observations`.

F5 has no provable production source-observed time, so F5 is recorded as an
absence with `applied_weight = 0` and never as a participation. The F1R-B port
refuses to serve it and its refusal code becomes the recorded reason.

The two instants
----------------
The F1P contract needs two of them and needs them distinct:
`evidence_time_utc < evaluated_at_utc` strictly, because a fact that becomes
available at the very instant of evaluation was not knowledge the evaluation
could have used.

* **The information cutoff** is `FeatureContext.as_of` -- the moment the
  evaluation went to look, which is also the latest instant any source it read
  could have been observed. It is the batch's `as_of`, the cutoff the F1R-B
  ports re-check their source times against, and the evidence time of an
  absence (`SOURCE_QUERIED_AT_AS_OF`). It is not invented here: the feature
  builders read up to exactly this instant.
* **The evaluation instant** is when this factor evaluation was performed. It
  carries no default that would let a caller pass the cutoff off as the
  evaluation -- the recording refuses a batch whose evaluation instant is not
  strictly after the cutoff
  (`EVALUATION_INSTANT_NOT_AFTER_INFORMATION_CUTOFF`).

Production builds its card with `as_of = min(evaluated_at, kickoff)`, so for a
pre-kickoff fixture the card's own as-of *is* its evaluation instant and the two
would be equal -- which the contract refuses by design. The card is not asked to
change; the factor batch simply records the instant the factor evaluation
actually ran, which is strictly later than the cutoff it read from, and states
both on every row so the relationship stays auditable.

Recording is once per attempt
-----------------------------
An attempt is the evaluation of one fixture at one information cutoff. The
second recording of the same attempt is an idempotent no-op rather than a
second row set: the accepted store keys idempotency on `observation_id`, which
carries the evaluation instant, so two recordings of one attempt at two
different instants would both be "new". Checking the attempt first restores the
rule the table's own unique index documents -- one original observation per
factor per evaluated attempt -- without touching the accepted store.

Failure behaviour
-----------------
A refusal is reported, not swallowed and not fatal. The evaluation this records
has already been computed and returned by the caller, so aborting it would turn
a recording problem into a workspace outage -- the failure mode this codebase
already paid for once. The refusal carries its machine-readable code into
`ForwardFactorRecorder.outcomes`, which the composition root reports with the
task result, and the batch is refused whole: a refusal writes zero rows.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.domain.factor_versions import factor_computation_version
from w2.infrastructure.persistence import ForwardAhFactorObservationModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
)
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.quant_research.forward_factor_modules import (
    ForwardFactorModules,
    load_modules,
)

logger = logging.getLogger(__name__)

#: The switch. On by default, because a wiring that ships switched off leaves
#: the table at zero rows and F1R-B at PARTIAL for exactly the reason this task
#: exists. Set it to a falsy value to stop the recording without a redeploy.
RECORDING_FLAG = "W2_FORWARD_FACTOR_RECORDING"
FALSY = frozenset({"0", "false", "off", "no", "disabled"})

EVALUATION_IDENTITY_CONTRACT = "w2.analysis-evaluation.v1"
ATTEMPT_IDENTITY_PREFIX = "w2.analysis-evaluation-attempt.v1:"
RECORDING_SCHEMA = "w2.forward_factor_production_recording.v1"

#: The market the F1P contract covers. The dynamic evaluation also projects
#: TOTALS; the factor contract is AH-only and says so.
RECORDED_MARKET = "ASIAN_HANDICAP"

#: How the two instants on a row were arrived at, written into every row's
#: `factor_inputs` so a reader never has to guess why the evaluation instant and
#: the information cutoff differ, or that they were allowed to be equal.
INSTANT_SEMANTICS = {
    "information_cutoff": "FEATURE_CONTEXT_AS_OF",
    "evaluation_instant": "FACTOR_EVALUATION_PERFORMED_AT",
}

#: What F3 is allowed to see. The port refuses a row that still carries a
#: result field, so the event-time projection is built here rather than passing
#: the raw row through.
F3_EVENT_TIME_FIELDS = (
    "history_id",
    "fixture_id",
    "team_w2_id",
    "opponent_w2_id",
    "kickoff_utc",
)

#: The one history source the F1R-B ports can serve. The projection has three:
#: canonical `canonical_team_match_history`, a raw-payload fallback and an xG
#: proxy. A factor whose own declaration names anything else is recorded as an
#: absence rather than bound to canonical rows it never read.
CANONICAL_HISTORY_SOURCE = "canonical_team_match_history"

_XG_SNAPSHOT_FIELDS = (
    "snapshot_id",
    "team_id",
    "as_of_fixture_id",
    "as_of_time",
    "match_count",
    "rolling_xg_for",
    "rolling_xg_against",
    "rolling_goals_for",
    "rolling_goals_against",
    "regression_index",
    "source_system",
)


def recording_enabled() -> bool:
    """The switch, read the way the rest of this codebase reads one."""
    raw = os.environ.get(RECORDING_FLAG)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in FALSY


#: The four things a recording run can be, as one field a task result can carry
#: without a reader having to reconstruct it from counts.
#:
#: DISABLED    the switch is off, so nothing was recorded and nothing was meant
#:             to be
#: UNAVAILABLE no recorder could be built (missing modules, no database), so
#:             every evaluation in this run went unrecorded
#: INCOMPLETE  a recorder ran and at least one evaluation was refused, so the
#:             run wrote fewer rows than it evaluated
#: COMPLETE    every evaluation either wrote its rows or was already recorded
RECORDING_COMPLETE = "COMPLETE"
RECORDING_INCOMPLETE = "INCOMPLETE"
RECORDING_DISABLED = "DISABLED"
RECORDING_UNAVAILABLE = "UNAVAILABLE"
RECORDING_STATUSES = (
    RECORDING_COMPLETE,
    RECORDING_INCOMPLETE,
    RECORDING_DISABLED,
    RECORDING_UNAVAILABLE,
)
#: Worst first. A run that could not record at all is reported as such even if
#: another part of the run simply had the switch off.
RECORDING_STATUS_PRECEDENCE = (
    RECORDING_UNAVAILABLE,
    RECORDING_INCOMPLETE,
    RECORDING_DISABLED,
    RECORDING_COMPLETE,
)


def empty_report(
    *,
    enabled: bool,
    note: str | None = None,
    recording_status: str | None = None,
) -> dict[str, Any]:
    """A report for a run that recorded nothing, with the reason stated."""
    status = recording_status or (
        RECORDING_DISABLED if not enabled else RECORDING_UNAVAILABLE
    )
    if status not in RECORDING_STATUSES:
        raise RecordingRefusal("RECORDING_STATUS_UNKNOWN", str(status))
    report: dict[str, Any] = {
        "schema_version": RECORDING_SCHEMA,
        "enabled": enabled,
        "recording_status": status,
        "recording_incomplete": status == RECORDING_INCOMPLETE,
        "evaluations": 0,
        "status_counts": {},
        "refusal_codes": {},
        "rows_appended": 0,
        "rows_idempotent_no_ops": 0,
    }
    if note:
        report["note"] = note
    return report


def merge_reports(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One report for a call that ran several projection passes."""
    merged = empty_report(
        enabled=any(bool(report.get("enabled")) for report in reports),
        recording_status=RECORDING_COMPLETE,
    )
    merged["recording_status"] = _worst_status(
        str(report.get("recording_status") or RECORDING_COMPLETE) for report in reports
    )
    merged["recording_incomplete"] = merged["recording_status"] == RECORDING_INCOMPLETE
    for report in reports:
        merged["evaluations"] += int(report.get("evaluations") or 0)
        merged["rows_appended"] += int(report.get("rows_appended") or 0)
        merged["rows_idempotent_no_ops"] += int(
            report.get("rows_idempotent_no_ops") or 0
        )
        for key in ("status_counts", "refusal_codes"):
            target = merged[key]
            assert isinstance(target, dict)
            for name, count in (report.get(key) or {}).items():
                target[str(name)] = target.get(str(name), 0) + int(count)
    notes = sorted({str(report["note"]) for report in reports if report.get("note")})
    if len(notes) == 1:
        merged["note"] = notes[0]
    elif notes:
        merged["note"] = "MIXED"
    return merged


def _worst_status(statuses: Iterable[str]) -> str:
    seen = {status for status in statuses if status}
    for status in RECORDING_STATUS_PRECEDENCE:
        if status in seen:
            return status
    return RECORDING_COMPLETE


def _parse_utc(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _now() -> datetime:
    """This recording's clock, in one place.

    It is the default evaluation instant -- the instant this factor evaluation
    was performed -- and it is a named function rather than an inline
    `datetime.now` so a test can pin the instant and get a deterministic row
    out of the production path.
    """
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True)
class EvaluationIdentity:
    """The identity a recorded batch carries.

    Deterministic in the evaluation's own inputs, so replaying the same
    evaluation produces the same observation ids and the store treats it as an
    idempotent no-op instead of appending a second set of rows.
    """

    evaluation_id: str
    attempt_id: str


def evaluation_identity(
    *, fixture_id: str, context: Any
) -> EvaluationIdentity:
    preimage = {
        "contract": EVALUATION_IDENTITY_CONTRACT,
        "hash_domain": str(HashDomain.FUTURE_REFRESH_EVIDENCE),
        "fixture_id": str(fixture_id),
        "competition_id": str(getattr(context, "competition_id", "") or ""),
        "home_team_id": str(getattr(context, "home_team_id", "") or ""),
        "away_team_id": str(getattr(context, "away_team_id", "") or ""),
        "as_of": _iso(context.as_of),
        "kickoff_at": _iso(context.kickoff_at),
        "market": RECORDED_MARKET,
    }
    digest = canonical_sha256(preimage, domain=HashDomain.FUTURE_REFRESH_EVIDENCE)
    return EvaluationIdentity(
        evaluation_id=f"{EVALUATION_IDENTITY_CONTRACT}:{digest}",
        attempt_id=f"{ATTEMPT_IDENTITY_PREFIX}{digest}",
    )


class RecordingRefusal(Exception):
    """A batch-level refusal raised inside the recorder.

    Never propagated to the evaluation: `ForwardFactorRecorder.record` turns it
    into a reported outcome.
    """

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class ForwardFactorRecorder:
    """The production call site's recorder. One per composition root."""

    def __init__(
        self,
        engine: Any,
        *,
        enabled: bool | None = None,
        modules: ForwardFactorModules | None = None,
    ) -> None:
        self.engine = engine
        self.enabled = recording_enabled() if enabled is None else enabled
        self._modules = modules
        self.outcomes: list[dict[str, Any]] = []

    @property
    def modules(self) -> ForwardFactorModules:
        if self._modules is None:
            self._modules = load_modules()
        return self._modules

    # --- read ports ------------------------------------------------------
    def _history_rows(self, *, fixture_id: str, context: Any) -> list[dict[str, Any]]:
        repository = FutureRefreshDbRepository(engine=self.engine)
        return list(
            repository.canonical_match_history_for_teams(
                [str(context.home_team_id), str(context.away_team_id)],
                before=context.as_of,
                limit_per_team=20,
            )
        )

    def _capture_rows(self, capture_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        ids = sorted({str(item) for item in capture_ids if str(item).strip()})
        if not ids:
            return {}
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    select(MatchdayEndpointCaptureModel).where(
                        MatchdayEndpointCaptureModel.capture_id.in_(ids)
                    )
                )
            )
        return {
            row.capture_id: {
                "capture_id": row.capture_id,
                "provider_captured_at": self._aware_utc(row.provider_captured_at),
                "raw_payload_sha256": row.raw_payload_sha256,
                "capture_status": row.capture_status,
            }
            for row in rows
        }

    @staticmethod
    def _aware_utc(value: Any) -> Any:
        """Re-attach UTC to a naive timestamp read straight off a model column.

        `provider_captured_at` is declared timezone aware and every writer
        stores a UTC instant, so this restores the instant rather than guessing
        one -- the accepted observation store reads its own rows back the same
        way, and for the same reason. A driver that returns a naive datetime
        (SQLite does; PostgreSQL does not) would otherwise make the port refuse
        every capture as `SOURCE_TIME_NOT_TIMEZONE_AWARE`, leaving the factor
        table empty in exactly the environments that exercise it.
        """
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    # --- binding construction --------------------------------------------
    def _consumed_history_rows(
        self, rows: Sequence[dict[str, Any]], *, team_id: str, as_of: datetime
    ) -> list[dict[str, Any]]:
        """The rows the rest-fitness builder consumed for one team.

        The builder takes `latest_as_of(history, as_of)` over the rows the
        projection kept, and the projection drops a row whose kickoff does not
        parse or whose goals are missing. That single row is what F3 read; the
        integration re-checks the resulting latest kickoff against the
        contribution's own `observed_at`, so a selection that disagrees with
        the builder refuses the batch rather than recording the wrong source.
        """
        eligible = []
        for row in rows:
            if str(row.get("team_w2_id") or "") != team_id:
                continue
            kickoff = _parse_utc(row.get("kickoff_utc"))
            if kickoff is None or kickoff >= as_of:
                continue
            if row.get("goals_for") is None or row.get("goals_against") is None:
                continue
            eligible.append((kickoff, row))
        if not eligible:
            return []
        return [max(eligible, key=lambda item: item[0])[1]]

    def _h2h_rows(
        self, rows: Sequence[dict[str, Any]], *, home_team_id: str, away_team_id: str,
        as_of: datetime,
    ) -> list[dict[str, Any]]:
        """The meetings the h2h builder consumed: home rows against the away side.

        Mirrors the projection then the builder: the projection keeps only rows
        whose kickoff parses and whose goals are present, the builder keeps
        those with `kickoff_at <= as_of`.
        """
        selected = []
        for row in rows:
            if str(row.get("team_w2_id") or "") != home_team_id:
                continue
            if str(row.get("opponent_w2_id") or "") != away_team_id:
                continue
            kickoff = _parse_utc(row.get("kickoff_utc"))
            if kickoff is None or kickoff > as_of:
                continue
            if row.get("goals_for") is None or row.get("goals_against") is None:
                continue
            selected.append(row)
        return selected

    def _xg_rows(
        self, snapshots: Sequence[dict[str, Any]], *, team_id: str
    ) -> list[dict[str, Any]]:
        """The snapshot the true-xG builder consumed for one team."""
        eligible = [
            (observed, row)
            for row in snapshots
            if str(row.get("team_id") or "") == team_id
            and (observed := _parse_utc(row.get("as_of_time"))) is not None
        ]
        if not eligible:
            return []
        return [max(eligible, key=lambda item: item[0])[1]]

    @staticmethod
    def _canonical_source(contribution: Any) -> bool:
        """Whether the builder itself says it read the canonical history rows.

        The ports serve that source and only that source. Deciding from the
        contribution rather than from the presence of rows in the table keeps a
        proxy factor from being attributed a canonical source it never read.
        """
        return str(getattr(contribution, "source", "") or "") == CANONICAL_HISTORY_SOURCE

    @staticmethod
    def _event_time_projection(row: dict[str, Any]) -> dict[str, Any]:
        return {name: row.get(name) for name in F3_EVENT_TIME_FIELDS}

    def _bindings(
        self,
        *,
        feature_set: Any,
        context: Any,
        history_rows: Sequence[dict[str, Any]],
        xg_snapshots: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        integration = self.modules.integration
        ports = self.modules.ports
        as_of = context.as_of
        contributions = {
            contribution.feature_id: contribution
            for contribution in feature_set.contributions
        }
        def reason_of(factor_id: str) -> str:
            """Why the factor has no usable source, in the builder's own words."""
            contribution = contributions.get(factor_id)
            reason = getattr(contribution, "reason", None)
            status = getattr(getattr(contribution, "status", None), "value", "")
            return str(reason or status or "SOURCE_UNAVAILABLE")

        def absence(factor_id: str, query_identity: str) -> Any:
            return integration.FactorSourceBinding(
                factor_version=factor_computation_version(factor_id),
                records=integration.absence_records(
                    factor_id,
                    query_identity=query_identity,
                    as_of_utc=_iso(as_of),
                    reason=reason_of(factor_id),
                ),
            )

        f3_rows = self._consumed_history_rows(
            history_rows, team_id=str(context.home_team_id), as_of=as_of
        ) + self._consumed_history_rows(
            history_rows, team_id=str(context.away_team_id), as_of=as_of
        )
        f9_rows = self._xg_rows(xg_snapshots, team_id=str(context.home_team_id)) + (
            self._xg_rows(xg_snapshots, team_id=str(context.away_team_id))
        )
        f6_rows = self._h2h_rows(
            history_rows,
            home_team_id=str(context.home_team_id),
            away_team_id=str(context.away_team_id),
            as_of=as_of,
        )

        bindings: dict[str, Any] = {}
        # A real binding needs both the rows the port can serve and the
        # builder's own word that it read that source. Either alone is not
        # enough: rows without the declaration would attribute a source the
        # factor may never have read, and a declaration without rows leaves
        # nothing to hash.
        f3_bound = len(f3_rows) == 2 and self._canonical_source(
            contributions.get("F3_REST_FITNESS")
        )
        bindings["F3_REST_FITNESS"] = (
            integration.FactorSourceBinding(
                factor_version=factor_computation_version("F3_REST_FITNESS"),
                records=ports.rest_fitness_records(
                    [self._event_time_projection(row) for row in f3_rows]
                ),
            )
            if f3_bound
            else absence("F3_REST_FITNESS", "canonical_team_match_history:none")
        )

        # F5 is refused by its port: no production writer emits a canonical AH
        # fact row into the factor path, the table has no reader in src/, its
        # quote time is a pre-match odds capture and `results.confirmed_at` has
        # two writer semantics. The refusal code is the recorded reason.
        try:
            ports.ah_fact_records([])
        except Exception as exc:  # noqa: BLE001 - the port's refusal carries the code
            f5_reason = str(getattr(exc, "code", None) or "F5_AH_FACT_SOURCE_TIME_UNPROVABLE")
        else:  # pragma: no cover - defensive: the port must refuse
            raise RecordingRefusal("F5_SOURCE_PORT_DID_NOT_REFUSE")
        bindings["F5_RECENT_AH_COVER"] = absence(
            "F5_RECENT_AH_COVER", f"canonical_historical_ah_fact:{f5_reason}"
        )

        f6_bound = bool(f6_rows) and self._canonical_source(
            contributions.get("F6_H2H")
        )
        if f6_bound:
            captures = self._capture_rows(
                str(row.get("endpoint_capture_id") or "") for row in f6_rows
            )
            try:
                f6_records = ports.h2h_records(
                    f6_rows,
                    captures={
                        capture_id: ports.endpoint_capture_from_row(row)
                        for capture_id, row in captures.items()
                    },
                )
            except Exception as exc:  # noqa: BLE001 - the port's refusal carries the code
                raise RecordingRefusal(
                    str(getattr(exc, "code", None) or "F6_SOURCE_UNPROVABLE"),
                    str(getattr(exc, "detail", "") or ""),
                ) from exc
            bindings["F6_H2H"] = integration.FactorSourceBinding(
                factor_version=factor_computation_version("F6_H2H"),
                records=f6_records,
            )
        else:
            bindings["F6_H2H"] = absence("F6_H2H", "canonical_team_match_history:h2h:none")

        bindings["F9_TRUE_XG"] = (
            integration.FactorSourceBinding(
                factor_version=factor_computation_version("F9_TRUE_XG"),
                records=ports.true_xg_records(
                    [
                        {name: row.get(name) for name in _XG_SNAPSHOT_FIELDS}
                        for row in f9_rows
                    ]
                ),
            )
            if len(f9_rows) == 2
            else absence("F9_TRUE_XG", "team_xg_rolling_snapshot:none")
        )
        return bindings

    # --- the call site ----------------------------------------------------
    def record(
        self,
        *,
        fixture_id: str,
        feature_set: Any,
        context: Any,
        xg_snapshots: Sequence[dict[str, Any]],
        evaluated_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Record one evaluation's four AH factors, or refuse the whole batch.

        `evaluated_at` is the instant this factor evaluation was performed. It
        is not a default the caller can lean on to pass the information cutoff
        off as an evaluation: when it is omitted the recording takes its own
        instant, and when it is supplied it must be strictly after the cutoff.
        """
        if not self.enabled:
            outcome = {"status": "DISABLED", "fixture_id": str(fixture_id)}
            self.outcomes.append(outcome)
            return outcome
        try:
            outcome = self._record(
                fixture_id=fixture_id,
                feature_set=feature_set,
                context=context,
                xg_snapshots=xg_snapshots,
                evaluated_at=evaluated_at,
            )
        except RecordingRefusal as refusal:
            outcome = {
                "status": "REFUSED",
                "code": refusal.code,
                "detail": refusal.detail,
                "fixture_id": str(fixture_id),
            }
        except Exception as exc:  # noqa: BLE001 - see "Failure behaviour" above
            # Every refusal in the accepted chain carries a machine-readable
            # code; report that one rather than the class that carried it, so a
            # reader of the task result sees the cause and not the wrapper.
            code = str(getattr(exc, "code", "") or "") or exc.__class__.__name__
            detail = str(getattr(exc, "detail", "") or "") or str(exc)
            outcome = {
                "status": "REFUSED",
                "code": code,
                "detail": detail[:512],
                "fixture_id": str(fixture_id),
            }
        if outcome["status"] == "REFUSED":
            logger.warning(
                "forward factor recording refused: fixture=%s code=%s detail=%s",
                outcome["fixture_id"],
                outcome["code"],
                outcome.get("detail", ""),
            )
        self.outcomes.append(outcome)
        return outcome

    def _record(
        self,
        *,
        fixture_id: str,
        feature_set: Any,
        context: Any,
        xg_snapshots: Sequence[dict[str, Any]],
        evaluated_at: datetime | None = None,
    ) -> dict[str, Any]:
        if str(getattr(context, "market", "") or "") not in {"", RECORDED_MARKET}:
            raise RecordingRefusal("EVALUATION_MARKET_OUT_OF_CONTRACT")
        attempted_at = _now()
        evaluation_instant = self._aware_utc(
            evaluated_at if evaluated_at is not None else attempted_at
        )
        cutoff = self._aware_utc(context.as_of)
        # The contract refuses `evidence == evaluated`, and the absence record's
        # evidence *is* the cutoff -- so a cutoff that is not strictly before
        # the evaluation instant cannot carry a batch. Fail closed and say which
        # instant caused it rather than shifting either one.
        if evaluation_instant <= cutoff:
            raise RecordingRefusal(
                "EVALUATION_INSTANT_NOT_AFTER_INFORMATION_CUTOFF",
                f"{_iso(cutoff)}>={_iso(evaluation_instant)}",
            )
        identity = evaluation_identity(fixture_id=fixture_id, context=context)
        recorded = self._recorded_attempt_rows(
            evaluation_id=identity.evaluation_id, attempt_id=identity.attempt_id
        )
        if recorded:
            # An attempt is recorded once. The accepted store's idempotency is
            # keyed on the observation id, which carries the evaluation
            # instant, so re-recording one attempt at a later instant would be
            # "new" to it. The attempt is the thing that must not be duplicated.
            return {
                "status": "IDEMPOTENT_NO_OP",
                "fixture_id": str(fixture_id),
                "evaluation_id": identity.evaluation_id,
                "attempt_id": identity.attempt_id,
                "appended": 0,
                "idempotent_no_ops": recorded,
                "batch_size": len(self.modules.recorder.REQUIRED_FACTORS),
                "source": self.modules.directory.as_posix(),
            }
        history_rows = self._history_rows(fixture_id=fixture_id, context=context)
        bindings = self._bindings(
            feature_set=feature_set,
            context=context,
            history_rows=history_rows,
            xg_snapshots=xg_snapshots,
        )
        batch = self.modules.integration.build_production_batch(
            feature_set=feature_set,
            context=context,
            evaluation_id=identity.evaluation_id,
            attempt_id=identity.attempt_id,
            evaluated_at_utc=_iso(evaluation_instant),
            created_at_utc=_iso(max(_now(), evaluation_instant)),
            bindings=bindings,
        )
        batch = self._state_the_two_instants(
            batch, cutoff=cutoff, evaluation_instant=evaluation_instant
        )
        appended = self.modules.store.ForwardFactorObservationStore(
            self.engine
        ).append_batch(batch)
        return {
            "status": "RECORDED",
            "fixture_id": str(fixture_id),
            "evaluation_id": identity.evaluation_id,
            "attempt_id": identity.attempt_id,
            "appended": int(appended["appended"]),
            "idempotent_no_ops": int(appended["idempotent_no_ops"]),
            "batch_size": int(appended["batch_size"]),
            "source": self.modules.directory.as_posix(),
        }

    def _recorded_attempt_rows(self, *, evaluation_id: str, attempt_id: str) -> int:
        """How many rows this attempt already has, for the once-only rule."""
        with Session(self.engine) as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(ForwardAhFactorObservationModel)
                    .where(
                        ForwardAhFactorObservationModel.evaluation_id == evaluation_id,
                        ForwardAhFactorObservationModel.attempt_id == attempt_id,
                    )
                )
                or 0
            )

    def _state_the_two_instants(
        self,
        batch: list[Any],
        *,
        cutoff: datetime,
        evaluation_instant: datetime,
    ) -> list[Any]:
        """Put both instants on every row, with the semantics that produced them.

        `evaluated_at_utc` is a column, but why it differs from the cutoff the
        batch read is not, and a reader must not have to infer it. The keys go
        into the existing free-form `factor_inputs` map -- the same route the
        accepted recorder uses for `evidence_time_semantics` -- and the batch is
        re-validated afterwards so the delivered rows, not an intermediate set,
        are what the identity was computed over.
        """
        from dataclasses import replace

        extras = {
            "information_cutoff": _iso(cutoff),
            "information_cutoff_semantics": INSTANT_SEMANTICS["information_cutoff"],
            "evaluation_performed_at": _iso(evaluation_instant),
            "evaluation_performed_at_semantics": INSTANT_SEMANTICS["evaluation_instant"],
        }
        return [
            replace(record, factor_inputs={**record.factor_inputs, **extras})
            for record in batch
        ]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        codes: dict[str, int] = {}
        appended = 0
        idempotent = 0
        for outcome in self.outcomes:
            status = str(outcome.get("status") or "UNKNOWN")
            counts[status] = counts.get(status, 0) + 1
            if status == "REFUSED":
                code = str(outcome.get("code") or "UNKNOWN")
                codes[code] = codes.get(code, 0) + 1
            appended += int(outcome.get("appended") or 0)
            idempotent += int(outcome.get("idempotent_no_ops") or 0)
        if not self.enabled:
            status = RECORDING_DISABLED
        elif codes:
            status = RECORDING_INCOMPLETE
        else:
            status = RECORDING_COMPLETE
        return {
            "schema_version": RECORDING_SCHEMA,
            "enabled": self.enabled,
            "recording_status": status,
            "recording_incomplete": status == RECORDING_INCOMPLETE,
            "evaluations": len(self.outcomes),
            "status_counts": counts,
            "refusal_codes": codes,
            "rows_appended": appended,
            "rows_idempotent_no_ops": idempotent,
        }


def build_recorder(engine: Any | None = None) -> ForwardFactorRecorder:
    """The composition root's constructor. Never raises on a missing module.

    A recorder that cannot find the F1R-B modules records nothing and says so;
    it does not take the evaluation down with it.
    """
    if engine is None:
        from w2.infrastructure.database import create_engine

        engine = create_engine()
    return ForwardFactorRecorder(engine)
