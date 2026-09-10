"""F1R-B: read ports that turn production rows into consumed-source records.

The switch is off. `PRODUCTION_CAPTURE_ENABLED` is False and
`LiveSourceReadPort` refuses every call, so nothing here opens a database
connection, contacts a Provider or reaches a VPS. What is wired is the shape:
given the rows production already projects, these ports decide which rows a
factor consumed, what content identifies them and when the source observed
them -- and refuse when that cannot be proven.

Each port mirrors a production read that already exists:

* F3 and F6 read `canonical_team_match_history`, projected by
  `FutureRefreshDbRepository._canonical_match_history_dict`.
* F9 reads `team_xg_rolling_snapshot`, projected by
  `FutureRefreshDbRepository._team_xg_rolling_snapshot_dict`.
* F5 reads canonical AH settlement facts, and cannot be served at all. See
  `ah_fact_records` for the blocking evidence.

Why F6 does not use `canonical_team_match_history.captured_at`
-------------------------------------------------------------
That column is set to `FactorModelRemediation.now` -- the clock at the start of
the materialisation run -- not to when the provider was read. It is therefore
*earlier* than the response that carried the finished result, so using it as an
evidence time would claim the result was knowable before it was. The real
observation time lives one hop away, on the capture the row points at:
`endpoint_capture_id -> matchday_endpoint_captures.provider_captured_at`, and
`_upsert_history_fixtures` binds each history row to the very capture whose
payload contained that finished fixture. A row with no capture fails closed.
"""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CAPTURE_PATH = Path(__file__).resolve().parent / "f1r_b_source_capture.py"
_MODULE_NAME = "w2_f1r_b_source_capture"
if _MODULE_NAME in sys.modules:
    capture = sys.modules[_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_MODULE_NAME, _CAPTURE_PATH)
    assert _spec is not None and _spec.loader is not None
    capture = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE_NAME] = capture
    _spec.loader.exec_module(capture)

ConsumedSourceRecord = capture.ConsumedSourceRecord

#: The wiring switch. F1R-B delivers the integration disabled; turning it on is
#: a separate, separately-approved decision.
PRODUCTION_CAPTURE_ENABLED = False

# Source versions, each the schema string production itself writes.
CANONICAL_TEAM_MATCH_HISTORY_SCHEMA = "CanonicalTeamMatchHistoryV1"
MATCHDAY_ENDPOINT_CAPTURE_SCHEMA = "MatchdayEndpointCaptureV1"
CAPTURED = "CAPTURED"

FIXTURE_EVENT_TIME = "FIXTURE_EVENT_TIME"
PROVIDER_CAPTURE_OF_FINISHED_FIXTURE = "PROVIDER_CAPTURE_OF_FINISHED_FIXTURE"
ROLLING_SNAPSHOT_COMPONENT_AVAILABILITY = "ROLLING_SNAPSHOT_COMPONENT_AVAILABILITY_MAX"

# Anything decided by the result. F3 reads match spacing only, so none of these
# may appear in the content it is hashed over.
RESULT_FIELDS = frozenset({
    "goals_for", "goals_against", "result_identity_hash", "settlement_outcome",
    "home_settlement", "away_settlement", "ah_result", "score", "result_status",
})


class SourcePortError(ValueError):
    """A refusal, carrying the machine-readable code that caused it."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


class LiveSourceReadPort:
    """The production read path, wired and disabled.

    It exists so the integration has one named place to be enabled, and so that
    a test can prove enabling it is a deliberate act rather than a default.
    """

    def __init__(self, *, enabled: bool = PRODUCTION_CAPTURE_ENABLED) -> None:
        self.enabled = enabled

    def read(self, query: str) -> list[dict[str, Any]]:
        if not self.enabled:
            raise SourcePortError("LIVE_CAPTURE_DISABLED", query)
        raise SourcePortError("LIVE_CAPTURE_NOT_AUTHORISED", query)


def _aware_utc(value: object, *, field_name: str) -> datetime:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise SourcePortError("SOURCE_TIME_MISSING", field_name)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise SourcePortError("SOURCE_TIME_UNPARSEABLE", f"{field_name}={value}") from exc
    else:
        raise SourcePortError("SOURCE_TIME_NOT_A_TIMESTAMP", field_name)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SourcePortError("SOURCE_TIME_NOT_TIMEZONE_AWARE", f"{field_name}={value}")
    return parsed.astimezone(UTC)


def _text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or not str(value).strip():
        raise SourcePortError("SOURCE_FIELD_MISSING", key)
    return str(value)


@dataclass(frozen=True, kw_only=True)
class EndpointCapture:
    """The projection of `matchday_endpoint_captures` these ports need."""

    capture_id: str
    provider_captured_at: str
    raw_payload_sha256: str
    capture_status: str


def endpoint_capture_from_row(row: dict[str, Any]) -> EndpointCapture:
    return EndpointCapture(
        capture_id=_text(row, "capture_id"),
        provider_captured_at=_aware_utc(
            row.get("provider_captured_at"), field_name="provider_captured_at"
        ).isoformat(),
        raw_payload_sha256=capture.require_hex64(
            row.get("raw_payload_sha256"), field_name="raw_payload_sha256"
        ),
        capture_status=_text(row, "capture_status"),
    )


# --- F3: match spacing, no result fields ----------------------------------
def _event_time_projection(row: dict[str, Any]) -> dict[str, Any]:
    """What F3 is allowed to see: identity and kickoff, never the result."""
    leaked = sorted(RESULT_FIELDS & {key for key, value in row.items() if value is not None})
    if leaked:
        raise SourcePortError("F3_RESULT_FIELD_IN_EVENT_TIME_INPUT", ",".join(leaked))
    return {
        "schema_version": CANONICAL_TEAM_MATCH_HISTORY_SCHEMA,
        "history_id": _text(row, "history_id"),
        "fixture_id": _text(row, "fixture_id"),
        "team_w2_id": _text(row, "team_w2_id"),
        "opponent_w2_id": _text(row, "opponent_w2_id"),
        "kickoff_utc": _aware_utc(row.get("kickoff_utc"), field_name="kickoff_utc").isoformat(),
    }


def rest_fitness_records(rows: list[dict[str, Any]]) -> list[ConsumedSourceRecord]:
    """F3's consumed set: the rows whose kickoff spacing produced the score.

    Callers pass the *event-time projection* of each consumed row, produced by
    `event_time_projection`, so a result field can never reach F3's content
    hash. The observed time is the fixture event time: "this match kicked off
    at T" is observable at T and needs no result.
    """
    records = []
    for row in rows:
        projection = _event_time_projection(row)
        records.append(ConsumedSourceRecord(
            record_id=projection["history_id"],
            content_sha256=capture.content_sha256(projection),
            source_version=CANONICAL_TEAM_MATCH_HISTORY_SCHEMA,
            observed_at_utc=projection["kickoff_utc"],
            observed_time_semantics=FIXTURE_EVENT_TIME,
        ))
    return records


# --- F6: historical results, timed by the capture that carried them --------
def h2h_records(
    rows: list[dict[str, Any]],
    *,
    captures: dict[str, EndpointCapture],
) -> list[ConsumedSourceRecord]:
    """F6's consumed set: the meetings whose goal difference produced the score.

    The observed time is the provider capture that carried the finished
    fixture, never the kickoff and never the row's materialisation clock.
    """
    records = []
    for row in rows:
        history_id = _text(row, "history_id")
        capture_id = row.get("endpoint_capture_id")
        if capture_id is None or not str(capture_id).strip():
            raise SourcePortError("F6_HISTORY_ROW_HAS_NO_ENDPOINT_CAPTURE", history_id)
        endpoint_capture = captures.get(str(capture_id))
        if endpoint_capture is None:
            raise SourcePortError("F6_ENDPOINT_CAPTURE_NOT_RESOLVED", str(capture_id))
        if endpoint_capture.capture_status != CAPTURED:
            raise SourcePortError(
                "F6_ENDPOINT_CAPTURE_NOT_SUCCESSFUL",
                f"{capture_id}={endpoint_capture.capture_status}")
        observed = _aware_utc(
            endpoint_capture.provider_captured_at, field_name="provider_captured_at")
        kickoff = _aware_utc(row.get("kickoff_utc"), field_name="kickoff_utc")
        if observed <= kickoff:
            # A capture claiming to show a finished fixture at or before its
            # kickoff is incoherent, and a "source time" equal to the kickoff is
            # the kickoff wearing a different name.
            raise SourcePortError("F6_SOURCE_TIME_NOT_AFTER_KICKOFF", history_id)
        content = {
            "schema_version": CANONICAL_TEAM_MATCH_HISTORY_SCHEMA,
            "history_id": history_id,
            "fixture_id": _text(row, "fixture_id"),
            "team_w2_id": _text(row, "team_w2_id"),
            "opponent_w2_id": _text(row, "opponent_w2_id"),
            "kickoff_utc": kickoff.isoformat(),
            "goals_for": int(row["goals_for"]),
            "goals_against": int(row["goals_against"]),
            "result_identity_hash": capture.require_hex64(
                row.get("result_identity_hash"), field_name="result_identity_hash"),
            "source_raw_hash": capture.require_hex64(
                row.get("source_raw_hash"), field_name="source_raw_hash"),
            "history_hash": capture.require_hex64(
                row.get("history_hash"), field_name="history_hash"),
            "endpoint_capture_id": endpoint_capture.capture_id,
            "capture_raw_payload_sha256": endpoint_capture.raw_payload_sha256,
            "provider_captured_at": observed.isoformat(),
        }
        records.append(ConsumedSourceRecord(
            record_id=history_id,
            content_sha256=capture.content_sha256(content),
            source_version=CANONICAL_TEAM_MATCH_HISTORY_SCHEMA,
            observed_at_utc=observed.isoformat(),
            observed_time_semantics=PROVIDER_CAPTURE_OF_FINISHED_FIXTURE,
        ))
    return records


# --- F9: rolling xG snapshots ---------------------------------------------
def true_xg_records(rows: list[dict[str, Any]]) -> list[ConsumedSourceRecord]:
    """F9's consumed set: the rolling snapshots the factor actually read.

    `as_of_time` is not a kickoff and not a write clock. `materialize_rolling_xg`
    sets it to `max(max(component.kickoff_at, component.captured_at))` over the
    selected components -- the latest time at which every component was
    knowable -- so it is a real source-observed time.
    """
    records = []
    for row in rows:
        snapshot_id = _text(row, "snapshot_id")
        observed = _aware_utc(row.get("as_of_time"), field_name="as_of_time")
        content = {
            "schema_version": "TeamXgRollingSnapshotV1",
            "snapshot_id": snapshot_id,
            "team_id": _text(row, "team_id"),
            "as_of_fixture_id": _text(row, "as_of_fixture_id"),
            "as_of_time": observed.isoformat(),
            "match_count": int(row["match_count"]),
            "rolling_xg_for": str(row["rolling_xg_for"]),
            "rolling_xg_against": str(row["rolling_xg_against"]),
            "rolling_goals_for": str(row["rolling_goals_for"]),
            "rolling_goals_against": str(row["rolling_goals_against"]),
            "regression_index": str(row["regression_index"]),
            "source_system": _text(row, "source_system"),
        }
        records.append(ConsumedSourceRecord(
            record_id=snapshot_id,
            content_sha256=capture.content_sha256(content),
            source_version=_text(row, "source_system"),
            observed_at_utc=observed.isoformat(),
            observed_time_semantics=ROLLING_SNAPSHOT_COMPONENT_AVAILABILITY,
        ))
    return records


# --- F5: refused ----------------------------------------------------------
#: Why F5 cannot be served from current production data and code. Each entry is
#: a fact about this repository at the F1R-B baseline, not a judgement.
F5_BLOCKING_EVIDENCE = (
    "NO_PRODUCTION_WRITER_EMITS_CANONICAL_AH_FACT_ROWS_INTO_THE_FACTOR_PATH",
    "CANONICAL_HISTORICAL_AH_FACTS_TABLE_HAS_NO_READER_IN_SRC",
    "CANONICAL_HISTORICAL_AH_FACT_CARRIES_NO_SETTLEMENT_OBSERVATION_TIME",
    "RESULTS_CONFIRMED_AT_HAS_TWO_WRITER_SEMANTICS_AND_NO_DISCRIMINATOR",
)


def ah_fact_records(rows: list[dict[str, Any]]) -> list[ConsumedSourceRecord]:
    """F5 is refused. It is not deferred, defaulted or approximated.

    F5 needs two source times per consumed history fact: when the result became
    available, and when the canonical AH quote/settlement fact became
    available. Neither can be proven at this baseline:

    * `_canonical_ah_rows` admits a row only when its source, source_group and
      collection_status all say `canonical_historical_ah_fact` /
      `CANONICAL_AH_FACT`. No writer in this repository emits those markers
      into `runtime/independent_signal_backfill/raw_payloads/`;
      `write_raw_artifact` stores `{endpoint, captured_at, payload}` with the
      provider payload unchanged.
    * The `canonical_historical_ah_facts` table has no reader anywhere in
      `src/`, so its `quote_captured_at` never reaches a factor. That column is
      the odds capture time in any case: `formal_ah` admits a source only when
      `snapshot_semantics == "CAPTURED_AT"`, which is a pre-match quote
      observation and says nothing about when the settlement was knowable.
    * `results.confirmed_at` has two writers with different meanings -- the
      earliest terminal-status provider capture in `materialize_results`, and
      `datetime.now(UTC)` in the second writer -- and no column distinguishes
      them, so the column alone proves no observation semantic.

    Fail closed is the whole point: substituting a kickoff, an inferred
    full-time, a query time or an unproven `confirmed_at` would manufacture the
    very evidence F1 established does not exist.
    """
    raise SourcePortError(
        "F5_AH_FACT_SOURCE_TIME_UNPROVABLE",
        ",".join(F5_BLOCKING_EVIDENCE) + f"|rows={len(rows)}",
    )


event_time_projection = _event_time_projection
