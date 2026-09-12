"""The one writer of runtime AH settlement facts, driven by persisted rows.

An AH settlement fact answers "what did the Provider observe about this fixture's
result, and at which capture instant". Building one therefore needs two things
that already exist in the database by the time a result has been materialised:

* the pre-kickoff odds bucket the odds captures produced
  (``matchday_market_observations``);
* the terminal capture that observed the fixture finish
  (``matchday_endpoint_captures``, reached from ``results`` or from
  ``canonical_team_match_history``).

This module reads exactly those and nothing else. It never calls a Provider and
never takes a raw payload as an argument -- that is what makes it usable from a
natural worker tick, which must not spend quota on a write-only step. The
controlled recovery path calls this same constructor; it is no longer a second
implementation of the fact.

The source-observed time of a fact is the terminal capture's
``provider_captured_at``. It is never a row clock, never the query clock, and
never the kickoff.

Two provenances, one rule each, both fixed so that one fixture can only ever
produce one fact:

identity
    1. the fixture-identity row, which a natural discovery capture maintains;
    2. otherwise the canonical history row, which the controlled recovery path
       writes for fixtures outside the discovery window.
    A fixture no persisted row describes is refused.

terminal evidence
    1. the ``results`` row, when it carries a capture identity. This is the
       artefact the result-materialisation step itself produced, so it is what a
       natural result refresh has just written;
    2. otherwise the canonical history row, whose capture the recovery path
       records for the same purpose;
    3. otherwise the fixture is refused.

Every refusal returns no fact. There is no partial fact, no defaulted line and
no substituted time.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from w2.historical.runtime_ah_settlement import RuntimeAhSettlementRepository
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import (
    ResultModel,
    RuntimeAhSettlementFactModel,
)
from w2.markets.ah_settlement_fact import (
    TerminalSettlementEvidence,
    build_ah_settlement_fact,
)

MATERIALIZER_SCHEMA_VERSION = "w2.runtime_ah_settlement_materializer.v1"

#: The persisted view a fact's identity was resolved from, stamped on the report
#: so a reader does not have to re-derive which chain described the fixture.
IDENTITY_FIXTURE_ROW = "matchday_fixture_identities"
IDENTITY_HISTORY_ROW = "canonical_team_match_history"

#: The persisted view a fact's terminal result was resolved from.
EVIDENCE_RESULT_ROW = "results"
EVIDENCE_HISTORY_ROW = "canonical_team_match_history"

STATUS_COMPLETE = "COMPLETE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_FAILED = "FAILED"
STATUS_NO_DUE_WORK = "NO_DUE_WORK"
#: The result materialisation this writer depends on did not succeed, so no
#: terminal evidence exists for this round and no fact may be built.
STATUS_SKIPPED = "SKIPPED_RESULT_MATERIALIZATION_FAILED"

FIXTURE_APPENDED = "APPENDED"
FIXTURE_IDEMPOTENT_NO_OP = "IDEMPOTENT_NO_OP"
FIXTURE_REFUSED = "REFUSED"

REFUSAL_FIXTURE_IDENTITY_UNRESOLVED = "AH_SETTLEMENT_FIXTURE_IDENTITY_UNRESOLVED"
REFUSAL_TEAM_MAPPING_MISSING = "AH_SETTLEMENT_TEAM_MAPPING_MISSING"
REFUSAL_TERMINAL_EVIDENCE_MISSING = "AH_SETTLEMENT_TERMINAL_EVIDENCE_MISSING"
REFUSAL_QUOTE_BUCKET_MISSING = "AH_SETTLEMENT_QUOTE_BUCKET_MISSING"
REFUSAL_CAPTURE_IDENTITY_MISSING = "AH_SETTLEMENT_CAPTURE_IDENTITY_MISSING"
REFUSAL_UNEXPECTED_ERROR = "AH_SETTLEMENT_MATERIALIZER_ERROR"

#: The terminal evidence did not survive its own integrity checks. Each names the
#: link that failed, and each is fail-closed: no fact is built.
REFUSAL_RESULT_PAYLOAD_HASH_MISMATCH = "AH_SETTLEMENT_RESULT_PAYLOAD_HASH_MISMATCH"
REFUSAL_CAPTURE_FIXTURE_MISMATCH = "AH_SETTLEMENT_CAPTURE_FIXTURE_MISMATCH"
REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN = "AH_SETTLEMENT_CAPTURE_OWNERSHIP_UNPROVEN"
REFUSAL_FACT_REVISION_CONFLICT = "AH_SETTLEMENT_FACT_REVISION_CONFLICT"

#: Statuses a natural caller treats as a clean writer verdict.
CLEAN_STATUSES = frozenset({STATUS_COMPLETE, STATUS_NO_DUE_WORK})

#: Refusals that mean the evidence chain is *broken*, as opposed to a statement
#: that the data for one fixture is simply not there yet. A run that produced one
#: of these must not report itself as a clean writer: an unprovable chain is a
#: defect to look at, whereas "no pre-kickoff quote bucket" is Tuesday.
INTEGRITY_REFUSAL_CODES = frozenset(
    {
        REFUSAL_RESULT_PAYLOAD_HASH_MISMATCH,
        REFUSAL_CAPTURE_FIXTURE_MISMATCH,
        REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN,
        REFUSAL_FACT_REVISION_CONFLICT,
    }
)

#: Fixture ownership, asked of the stored payload rather than of the capture row.
#: `raw_payload.payload` is `json`, so the cast is what makes it queryable.
_PAYLOAD_CONTAINS_FIXTURE_SQL = """
SELECT EXISTS (
    SELECT 1
      FROM raw_payload rp
     WHERE rp.sha256 = :sha
       AND jsonb_typeof(rp.payload::jsonb -> 'response') = 'array'
       AND EXISTS (
           SELECT 1
             FROM jsonb_array_elements(rp.payload::jsonb -> 'response') AS item
            WHERE item -> 'fixture' ->> 'id' = :provider_fixture_id
       )
)
"""


@dataclass(frozen=True, kw_only=True)
class FixtureIdentityFacts:
    """The six identity values a fact needs, from one persisted source."""

    fixture_id: str
    provider_fixture_id: str
    competition_id: str
    season: str
    kickoff: datetime
    home_provider_team_id: str
    away_provider_team_id: str
    home_w2_team_id: str
    away_w2_team_id: str
    source: str


class RuntimeAhFactMaterializer:
    """Builds and appends runtime AH settlement facts from stored rows only."""

    def __init__(self, *, engine: sa.Engine) -> None:
        self.engine = engine
        self.repository = RuntimeAhSettlementRepository(engine=engine)

    def materialize(self, fixture_ids: Sequence[str]) -> dict[str, Any]:
        requested = _requested_ids(fixture_ids)
        if not requested:
            return empty_report(STATUS_NO_DUE_WORK, requested_count=0)

        identity_rows = self._identity_rows(requested)
        history_rows = self._history_rows(requested)

        details: list[dict[str, Any]] = []
        facts: list[Any] = []
        unexpected_errors = 0

        for requested_id in requested:
            try:
                detail, fact = self._one(
                    requested_id=requested_id,
                    identity_row=identity_rows.get(requested_id),
                    history_rows=history_rows.get(requested_id) or [],
                )
            except Exception as exc:  # noqa: BLE001 - one bad fixture is not an outage
                unexpected_errors += 1
                details.append(
                    _refused(
                        requested_id,
                        REFUSAL_UNEXPECTED_ERROR,
                        detail=f"{type(exc).__name__}:{exc}",
                    )
                )
                continue
            details.append(detail)
            if fact is not None:
                facts.append(fact)

        appended = 0
        idempotent_no_ops = 0
        failure_detail = ""
        if facts:
            existing = self._existing_fact_ids([fact.fact_id for fact in facts])
            try:
                written = self.repository.append_facts(facts)
                appended = int(written["appended"])
                idempotent_no_ops = int(written["idempotent_no_ops"])
            except Exception as exc:  # noqa: BLE001 - the writer reports, never raises
                failure_detail = f"{type(exc).__name__}:{exc}"
            else:
                for detail in details:
                    fact_id = detail.get("fact_id")
                    if not fact_id:
                        continue
                    detail["status"] = (
                        FIXTURE_IDEMPOTENT_NO_OP
                        if fact_id in existing
                        else FIXTURE_APPENDED
                    )

        refusal_codes: dict[str, int] = {}
        for detail in details:
            code = detail.get("refusal_code")
            if code:
                refusal_codes[str(code)] = refusal_codes.get(str(code), 0) + 1

        report = empty_report(
            _status(
                unexpected_errors=unexpected_errors,
                failure_detail=failure_detail,
                refusal_codes=refusal_codes,
            ),
            requested_count=len(requested),
        )
        report.update(
            {
                "ready_fixture_count": len(facts),
                "appended": appended,
                "idempotent_no_ops": idempotent_no_ops,
                "refused_fixture_count": sum(
                    1 for detail in details if detail["status"] == FIXTURE_REFUSED
                ),
                "unexpected_error_count": unexpected_errors,
                "refusal_codes": refusal_codes,
                "fixtures": details,
                "db_writes": appended,
            }
        )
        if failure_detail:
            report["error"] = failure_detail
        return report

    # --- one fixture ------------------------------------------------------
    def _one(
        self,
        *,
        requested_id: str,
        identity_row: MatchdayFixtureIdentityModel | None,
        history_rows: list[CanonicalTeamMatchHistoryModel],
    ) -> tuple[dict[str, Any], Any | None]:
        identity = _identity_facts(
            requested_id=requested_id,
            identity_row=identity_row,
            history_rows=history_rows,
        )
        if identity is None:
            return _refused(requested_id, REFUSAL_FIXTURE_IDENTITY_UNRESOLVED), None
        if not identity.home_w2_team_id or not identity.away_w2_team_id:
            # A fact nobody can consume is not worth writing: F5 reads the fact
            # through the w2 team identity of both sides.
            return (
                _refused(
                    identity.fixture_id,
                    REFUSAL_TEAM_MAPPING_MISSING,
                    provider_fixture_id=identity.provider_fixture_id,
                    identity_source=identity.source,
                ),
                None,
            )

        evidence = self._terminal_evidence(identity=identity, history_rows=history_rows)
        if isinstance(evidence, str):
            # The refusal names which link of the chain is missing, so a reader
            # can tell "the fixture has no terminal result yet" apart from "the
            # result exists but nothing proves which capture observed it".
            return (
                _refused(
                    identity.fixture_id,
                    evidence,
                    provider_fixture_id=identity.provider_fixture_id,
                    identity_source=identity.source,
                ),
                None,
            )
        source, status, home_goals, away_goals, capture = evidence
        capture_id = str(capture["capture_id"] or "")

        observations = self.repository.closing_quote_bucket(
            fixture_id=identity.fixture_id, kickoff=identity.kickoff
        )
        if not observations:
            return (
                _refused(
                    identity.fixture_id,
                    REFUSAL_QUOTE_BUCKET_MISSING,
                    provider_fixture_id=identity.provider_fixture_id,
                    identity_source=identity.source,
                    evidence_source=source,
                ),
                None,
            )

        fact = build_ah_settlement_fact(
            fixture_id=identity.fixture_id,
            provider_fixture_id=identity.provider_fixture_id,
            competition_id=identity.competition_id,
            season=identity.season,
            kickoff=identity.kickoff,
            market_observations=observations,
            settlement=TerminalSettlementEvidence(
                provider_fixture_id=identity.provider_fixture_id,
                status=status,
                home_goals=home_goals,
                away_goals=away_goals,
                endpoint_capture_id=capture_id,
                raw_payload_sha256=str(capture["raw_payload_sha256"] or ""),
                observed_at=capture["provider_captured_at"],
                capture_endpoint=str(capture["endpoint"] or ""),
                capture_status=str(capture["capture_status"] or ""),
            ),
            home_team_provider_id=identity.home_provider_team_id,
            away_team_provider_id=identity.away_provider_team_id,
            home_w2_team_id=identity.home_w2_team_id,
            away_w2_team_id=identity.away_w2_team_id,
        )
        if fact.status != "READY":
            return (
                _refused(
                    identity.fixture_id,
                    str(fact.refusal_code or REFUSAL_UNEXPECTED_ERROR),
                    provider_fixture_id=identity.provider_fixture_id,
                    identity_source=identity.source,
                    evidence_source=source,
                    detail=str(fact.refusal_detail or ""),
                ),
                None,
            )

        # One fixture, one fact. Replaying the same evidence is an idempotent
        # no-op; arriving at a *different* fact means the terminal evidence moved
        # under a row that already exists, and silently appending it would count
        # the same match twice. The store would keep both -- the fact identity
        # includes the capture, so both are "new" -- so the revision rule has to
        # live here, where the fixture is still known.
        existing = self._existing_fact_ids_for_fixture(identity.fixture_id)
        if existing and fact.fact_id not in existing:
            return (
                _refused(
                    identity.fixture_id,
                    REFUSAL_FACT_REVISION_CONFLICT,
                    provider_fixture_id=identity.provider_fixture_id,
                    identity_source=identity.source,
                    evidence_source=source,
                    detail=f"existing={','.join(sorted(existing))}",
                ),
                None,
            )

        return (
            {
                "fixture_id": identity.fixture_id,
                "provider_fixture_id": identity.provider_fixture_id,
                "status": FIXTURE_APPENDED,
                "refusal_code": None,
                "refusal_detail": "",
                "identity_source": identity.source,
                "evidence_source": source,
                "fact_id": fact.fact_id,
                "fact_hash": fact.fact_hash,
                "quote_identity_hash": fact.quote_identity_hash,
                "line": _format_line(fact.line),
                "terminal_status": fact.fixture_status,
                "settlement_capture_id": fact.settlement_capture_id,
                "settlement_payload_sha256": fact.settlement_payload_sha256,
                "settlement_observed_at": _iso(fact.settlement_observed_at),
                "quote_captured_at": _iso(fact.quote_captured_at),
            },
            fact,
        )

    # --- terminal evidence ------------------------------------------------
    def _terminal_evidence(
        self,
        *,
        identity: FixtureIdentityFacts,
        history_rows: list[CanonicalTeamMatchHistoryModel],
    ) -> tuple[str, str, int, int, dict[str, Any]] | str:
        """The terminal result and the capture that observed it.

        Returns the refusal code as a string when the chain cannot be closed, so
        the caller reports which link is missing rather than a single vague
        "unavailable".
        """
        result = self._result_row(identity.fixture_id)
        history = _history_score(history_rows)
        if result is None and history is None:
            return REFUSAL_TERMINAL_EVIDENCE_MISSING

        if result is not None and result["source_capture_id"]:
            capture = self.repository.terminal_capture(result["source_capture_id"])
            if capture is not None and capture["provider_captured_at"]:
                # The result row and the capture it names must be the same payload:
                # a result that cites a capture it did not read from is not
                # terminal evidence for anything, and a hash disagreement is an
                # integrity failure rather than an absence -- so it fails closed
                # instead of falling through to the other chain.
                if str(result["source_payload_sha256"] or "") != str(
                    capture["raw_payload_sha256"] or ""
                ):
                    return REFUSAL_RESULT_PAYLOAD_HASH_MISMATCH
                refusal = self._ownership_refusal(identity=identity, capture=capture)
                if refusal:
                    return refusal
                return (
                    EVIDENCE_RESULT_ROW,
                    str(result["result_status"]),
                    int(result["home_goals"]),
                    int(result["away_goals"]),
                    capture,
                )

        if history is not None and history["endpoint_capture_id"]:
            capture = self.repository.terminal_capture(history["endpoint_capture_id"])
            if capture is not None and capture["provider_captured_at"]:
                refusal = self._ownership_refusal(identity=identity, capture=capture)
                if refusal:
                    return refusal
                return (
                    EVIDENCE_HISTORY_ROW,
                    history["fixture_status"],
                    history["home_goals"],
                    history["away_goals"],
                    capture,
                )
        # A result exists, but nothing identifies the capture that observed it,
        # so there is no source-observed time a fact could honestly carry.
        return REFUSAL_CAPTURE_IDENTITY_MISSING

    # --- evidence integrity ----------------------------------------------
    def _ownership_refusal(
        self, *, identity: FixtureIdentityFacts, capture: dict[str, Any]
    ) -> str | None:
        """Prove the capture observed *this* fixture, or name why it cannot.

        A capture that names a fixture must name this one. A bulk capture names
        none -- every `fixtures`-endpoint capture in production is one -- so its
        stored payload is the proof instead: it has to contain this fixture. No
        ownership, no fact.
        """
        named = str(capture.get("fixture_id") or "")
        if named:
            if named in {identity.fixture_id, identity.provider_fixture_id}:
                return None
            return REFUSAL_CAPTURE_FIXTURE_MISMATCH
        if self._payload_contains_fixture(
            capture=capture, provider_fixture_id=identity.provider_fixture_id
        ):
            return None
        return REFUSAL_CAPTURE_OWNERSHIP_UNPROVEN

    def _payload_contains_fixture(
        self, *, capture: dict[str, Any], provider_fixture_id: str
    ) -> bool:
        """Whether the capture's own stored payload carries this fixture.

        Asked in SQL so the payload itself never crosses into Python: a bulk
        `fixtures` response is large and only its membership matters here.
        """
        sha = str(capture.get("raw_payload_sha256") or "")
        if not sha or not provider_fixture_id:
            return False
        with Session(self.engine) as session:
            return bool(
                session.scalar(
                    sa.text(_PAYLOAD_CONTAINS_FIXTURE_SQL),
                    {"sha": sha, "provider_fixture_id": provider_fixture_id},
                )
            )

    def _result_row(self, fixture_id: str) -> dict[str, Any] | None:
        table = ResultModel
        with Session(self.engine) as session:
            row = session.scalar(sa.select(table).where(table.fixture_id == fixture_id))
        if row is None:
            return None
        return {
            "result_status": row.result_status,
            "home_goals": row.home_goals,
            "away_goals": row.away_goals,
            "source_capture_id": row.source_capture_id,
            "source_payload_sha256": row.source_payload_sha256,
        }

    # --- batch reads ------------------------------------------------------
    def _identity_rows(
        self, requested: list[str]
    ) -> dict[str, MatchdayFixtureIdentityModel]:
        """Map every requested id onto the fixture-identity row it names.

        A canonical fixture id resolves directly. A bare Provider fixture id is
        accepted only when it names exactly one fixture, so an ambiguous id can
        never silently pick one.
        """
        table = MatchdayFixtureIdentityModel
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    sa.select(table).where(
                        sa.or_(
                            table.fixture_id.in_(requested),
                            table.provider_fixture_id.in_(requested),
                        )
                    )
                )
            )
        grouped = _group_by_requested_id(requested, rows, _identity_keys)
        return {requested_id: group[0] for requested_id, group in grouped.items()}

    def _history_rows(
        self, requested: list[str]
    ) -> dict[str, list[CanonicalTeamMatchHistoryModel]]:
        table = CanonicalTeamMatchHistoryModel
        with Session(self.engine) as session:
            rows = list(
                session.scalars(
                    sa.select(table).where(
                        sa.or_(
                            table.fixture_id.in_(requested),
                            table.provider_fixture_id.in_(requested),
                        )
                    )
                )
            )
        return _group_by_requested_id(requested, rows, _history_keys)

    def _existing_fact_ids(self, fact_ids: Iterable[str]) -> set[str]:
        ids = sorted({str(item) for item in fact_ids if item})
        if not ids:
            return set()
        table = RuntimeAhSettlementFactModel
        with Session(self.engine) as session:
            return {
                str(item)
                for item in session.scalars(
                    sa.select(table.fact_id).where(table.fact_id.in_(ids))
                )
            }

    def _existing_fact_ids_for_fixture(self, fixture_id: str) -> set[str]:
        """Every fact already stored for one fixture, whatever its evidence was."""
        table = RuntimeAhSettlementFactModel
        with Session(self.engine) as session:
            return {
                str(item)
                for item in session.scalars(
                    sa.select(table.fact_id).where(table.fixture_id == fixture_id)
                )
            }


def materialize_runtime_ah_settlement_facts(
    *,
    engine: sa.Engine,
    fixture_ids: Sequence[str],
) -> dict[str, Any]:
    """Build and append runtime AH settlement facts for the given fixtures.

    Takes canonical fixture ids or unambiguous Provider fixture ids. Reads only
    persisted captures, market observations and terminal evidence; issues no
    Provider call of any kind.
    """
    return RuntimeAhFactMaterializer(engine=engine).materialize(fixture_ids)


def merge_runtime_ah_fact_reports(reports: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """One report for a task that materialised facts on several branches.

    The verdict is the worst of the branches: a run whose writer failed on any
    branch must not be able to report a clean writer. Refusals are summed rather
    than treated as a failure -- they are statements about the data, and they
    stay visible either way.
    """
    collected = [dict(item) for item in reports if isinstance(item, Mapping)]
    if not collected:
        return empty_report(STATUS_NO_DUE_WORK, requested_count=0)

    refusal_codes: dict[str, int] = {}
    merged = empty_report(STATUS_COMPLETE, requested_count=0)
    for report in collected:
        merged["requested_fixture_count"] += int(
            report.get("requested_fixture_count") or 0
        )
        for key in (
            "ready_fixture_count",
            "appended",
            "idempotent_no_ops",
            "refused_fixture_count",
            "unexpected_error_count",
        ):
            merged[key] += int(report.get(key) or 0)
        for code, count in (report.get("refusal_codes") or {}).items():
            refusal_codes[str(code)] = refusal_codes.get(str(code), 0) + int(count)
        merged["fixtures"].extend(report.get("fixtures") or [])
        if str(report.get("status")) == STATUS_FAILED:
            merged["status"] = STATUS_FAILED
            merged["error"] = report.get("error") or report.get("status")
        elif (
            str(report.get("status")) == STATUS_INCOMPLETE
            and merged["status"] != STATUS_FAILED
        ):
            merged["status"] = STATUS_INCOMPLETE
    merged["refusal_codes"] = refusal_codes
    if merged["status"] == STATUS_COMPLETE and merged["requested_fixture_count"] == 0:
        # No branch had anything to do, so neither did the run. Reporting that as
        # COMPLETE would turn "nothing was due" into "the writer succeeded".
        merged["status"] = STATUS_NO_DUE_WORK
    merged["db_writes"] = merged["appended"]
    return merged


def runtime_ah_fact_writer_status(report: dict[str, Any]) -> str:
    """The writer's own verdict, for a task result to repeat verbatim."""
    status = str(report.get("status") or STATUS_FAILED)
    if status in CLEAN_STATUSES:
        return "PASS"
    if status == STATUS_INCOMPLETE:
        return "PARTIAL"
    return "FAIL"


def writer_status_is_clean(report: dict[str, Any]) -> bool:
    return str(report.get("status")) in CLEAN_STATUSES


# --- helpers --------------------------------------------------------------
def _requested_ids(fixture_ids: Sequence[str]) -> list[str]:
    return sorted({str(item) for item in fixture_ids or () if str(item)})


def _identity_keys(row: MatchdayFixtureIdentityModel) -> tuple[str, str]:
    return str(row.fixture_id), str(row.provider_fixture_id)


def _history_keys(row: CanonicalTeamMatchHistoryModel) -> tuple[str, str]:
    return str(row.fixture_id), str(row.provider_fixture_id)


def _group_by_requested_id[RowT](
    requested: Sequence[str],
    rows: Sequence[RowT],
    accessor: Callable[[RowT], tuple[str, str]],
) -> dict[str, list[RowT]]:
    """Group rows under every requested id that names them.

    A requested id is a canonical fixture id or a bare Provider fixture id. The
    latter only resolves when every row it names agrees on one fixture, so an
    ambiguous id yields nothing rather than an arbitrary pick.
    """
    by_fixture_id: dict[str, list[RowT]] = {}
    by_provider_id: dict[str, list[RowT]] = {}
    for row in rows:
        fixture_id, provider_fixture_id = accessor(row)
        by_fixture_id.setdefault(fixture_id, []).append(row)
        by_provider_id.setdefault(provider_fixture_id, []).append(row)
    resolved: dict[str, list[RowT]] = {}
    for requested_id in requested:
        direct = by_fixture_id.get(requested_id)
        if direct:
            resolved[requested_id] = direct
            continue
        candidates = by_provider_id.get(requested_id) or []
        if len({accessor(row)[0] for row in candidates}) == 1:
            resolved[requested_id] = candidates
    return resolved


def _identity_facts(
    *,
    requested_id: str,
    identity_row: MatchdayFixtureIdentityModel | None,
    history_rows: list[CanonicalTeamMatchHistoryModel],
) -> FixtureIdentityFacts | None:
    """The six identity values a fact needs, from the first source that has them.

    The fixture-identity row is the natural discovery path's own record; the
    canonical history row is what the controlled recovery path writes for
    fixtures the discovery window never covered. Neither is a raw payload.
    """
    if identity_row is not None:
        return FixtureIdentityFacts(
            fixture_id=str(identity_row.fixture_id),
            provider_fixture_id=str(identity_row.provider_fixture_id),
            competition_id=str(identity_row.competition_id),
            season=str(identity_row.season),
            kickoff=identity_row.kickoff_utc,
            home_provider_team_id=str(identity_row.home_provider_team_id),
            away_provider_team_id=str(identity_row.away_provider_team_id),
            home_w2_team_id=str(identity_row.home_w2_team_id or ""),
            away_w2_team_id=str(identity_row.away_w2_team_id or ""),
            source=IDENTITY_FIXTURE_ROW,
        )
    return _identity_from_history(requested_id=requested_id, history_rows=history_rows)


def _identity_from_history(
    *,
    requested_id: str,
    history_rows: list[CanonicalTeamMatchHistoryModel],
) -> FixtureIdentityFacts | None:
    by_side = {str(row.team_side).upper(): row for row in history_rows}
    row = by_side.get("HOME") or by_side.get("AWAY")
    if row is None:
        return None
    home_side = str(row.team_side).upper() == "HOME"
    return FixtureIdentityFacts(
        fixture_id=str(row.fixture_id),
        provider_fixture_id=str(row.provider_fixture_id),
        competition_id=str(row.competition_id),
        season=str(row.season),
        kickoff=row.kickoff_utc,
        home_provider_team_id=(
            str(row.team_provider_id) if home_side else str(row.opponent_provider_id)
        ),
        away_provider_team_id=(
            str(row.opponent_provider_id) if home_side else str(row.team_provider_id)
        ),
        home_w2_team_id=str(row.team_w2_id if home_side else row.opponent_w2_id),
        away_w2_team_id=str(row.opponent_w2_id if home_side else row.team_w2_id),
        source=IDENTITY_HISTORY_ROW,
    )


def _history_score(
    history_rows: list[CanonicalTeamMatchHistoryModel],
) -> dict[str, Any] | None:
    """The terminal score and capture from the home-side history row.

    ``results`` and ``canonical_team_match_history`` were both checked for the
    same fixture; which side the row records decides how its goals read.
    """
    by_side = {str(row.team_side).upper(): row for row in history_rows}
    row = by_side.get("HOME") or by_side.get("AWAY")
    if row is None:
        return None
    home_side = str(row.team_side).upper() == "HOME"
    return {
        "fixture_status": str(row.fixture_status),
        "home_goals": int(row.goals_for) if home_side else int(row.goals_against),
        "away_goals": int(row.goals_against) if home_side else int(row.goals_for),
        "endpoint_capture_id": row.endpoint_capture_id,
    }


def empty_report(status: str, *, requested_count: int = 0, error: str = "") -> dict[str, Any]:
    """A writer report carrying no work, for a caller that could not run it."""
    report: dict[str, Any] = {
        "schema_version": MATERIALIZER_SCHEMA_VERSION,
        "status": status,
        "requested_fixture_count": requested_count,
        "ready_fixture_count": 0,
        "appended": 0,
        "idempotent_no_ops": 0,
        "refused_fixture_count": 0,
        "unexpected_error_count": 0,
        "refusal_codes": {},
        "fixtures": [],
        "db_writes": 0,
        "provider_calls": 0,
    }
    if error:
        report["error"] = error
    return report


def _status(
    *,
    unexpected_errors: int,
    failure_detail: str,
    refusal_codes: Mapping[str, int],
) -> str:
    if failure_detail:
        return STATUS_FAILED
    if unexpected_errors or INTEGRITY_REFUSAL_CODES & set(refusal_codes):
        return STATUS_INCOMPLETE
    return STATUS_COMPLETE


def _refused(
    fixture_id: str,
    code: str,
    *,
    provider_fixture_id: str | None = None,
    identity_source: str | None = None,
    evidence_source: str | None = None,
    detail: str = "",
) -> dict[str, Any]:
    return {
        "fixture_id": fixture_id,
        "provider_fixture_id": provider_fixture_id,
        "status": FIXTURE_REFUSED,
        "refusal_code": code,
        "refusal_detail": detail[:512],
        "identity_source": identity_source,
        "evidence_source": evidence_source,
        "fact_id": None,
        "fact_hash": None,
        "quote_identity_hash": None,
        "line": None,
        "terminal_status": None,
        "settlement_capture_id": None,
        "settlement_payload_sha256": None,
        "settlement_observed_at": None,
        "quote_captured_at": None,
    }


def _format_line(value: Any) -> str | None:
    if value is None:
        return None
    try:
        normalized = value.normalize()
    except AttributeError:
        return str(value)
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()
