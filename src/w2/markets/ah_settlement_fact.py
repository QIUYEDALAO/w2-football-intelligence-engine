"""Runtime Asian-Handicap settlement facts, built from Provider captures.

This module is the only constructor of a runtime AH settlement fact. It does not
choose a line and it does not settle anything itself: it composes the three
authorities that already exist and refuses when any of them cannot answer.

* the canonical line is whatever ``select_canonical_ah_mainline`` returns for the
  pre-kickoff bucket (policy ``canonical_bookmaker_mainline_majority_v1``);
* the quote identity (capture id, payload sha256, quote identity hash) is
  whatever ``project_quote_identity`` returns for that line's two sides;
* the settlement outcome is whatever ``settle_asian_handicap`` returns for the
  observed final score at that line.

The source-observed time of a fact is the *Provider capture instant* of the
terminal result, never a row clock, never the query clock and never the kickoff.
``results.confirmed_at`` is not read here at all: it has two writers with
different semantics and cannot stand in for an observation time.

Every refusal returns no fact. There is no partial fact, no defaulted line and
no substituted time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from w2.domain.canonical_serialization import (
    HashDomain,
    SerializerVersion,
    canonical_sha256,
)
from w2.domain.odds import settle_asian_handicap
from w2.markets.asian_handicap_mainline import (
    CANONICAL_AH_MAINLINE_POLICY,
    select_canonical_ah_mainline,
)
from w2.markets.quote_identity import project_quote_identity

RUNTIME_AH_SETTLEMENT_SCHEMA = "w2.runtime_ah_settlement_fact.v1"
RUNTIME_AH_SETTLEMENT_POLICY = CANONICAL_AH_MAINLINE_POLICY
RUNTIME_AH_SETTLEMENT_HASH_CONTRACT = "w2.runtime_ah_settlement_fact_hash.v1"
RUNTIME_AH_SETTLEMENT_RECORD_KIND = "runtime_ah_settlement_fact"

#: Every digest here goes through the one canonical serializer authority.
#:
#: `src/w2/domain/canonical_serialization.py` is fingerprint-bound by the
#: ADR-0019 oracle handoff, so it is not modified and no market-specific domain
#: is invented for it. `FUTURE_REFRESH_EVIDENCE` at serializer version V2 is the
#: authorised domain for this evidence. `PREMATCH_READ_MODEL_GENERIC` is not
#: used. No `json.dumps`, `hashlib` or second serializer appears in this module;
#: the authority guard enforces that.
_HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
_HASH_VERSION = SerializerVersion.V2


def _digest(preimage: dict[str, Any]) -> str:
    return canonical_sha256(preimage, domain=_HASH_DOMAIN, version=_HASH_VERSION)

# The source-observed-time semantics a runtime AH fact can carry. A fact whose
# observation instant is anything else is not built at all.
SETTLEMENT_OBSERVED_AT_SEMANTICS = "PROVIDER_CAPTURE_OF_TERMINAL_RESULT"

TERMINAL_FIXTURE_STATUSES = frozenset({"FT", "AET", "PEN"})

F5_UNPROVABLE_CODE = "F5_AH_FACT_SOURCE_TIME_UNPROVABLE"

REFUSAL_NOT_TERMINAL = "AH_SETTLEMENT_NOT_TERMINAL"
REFUSAL_SETTLEMENT_CAPTURE_MISSING = "AH_SETTLEMENT_CAPTURE_IDENTITY_MISSING"
REFUSAL_SETTLEMENT_PAYLOAD_MISSING = "AH_SETTLEMENT_PAYLOAD_HASH_MISSING"
REFUSAL_SETTLEMENT_NOT_AFTER_KICKOFF = "AH_SETTLEMENT_NOT_AFTER_KICKOFF"
REFUSAL_FIXTURE_IDENTITY_MISMATCH = "AH_FIXTURE_IDENTITY_MISMATCH"
REFUSAL_MAINLINE_UNAVAILABLE = "AH_MAINLINE_UNAVAILABLE"
REFUSAL_QUOTE_NOT_BEFORE_KICKOFF = "AH_QUOTE_NOT_BEFORE_KICKOFF"
REFUSAL_QUOTE_IDENTITY_INCOMPLETE = "AH_QUOTE_IDENTITY_INCOMPLETE"
REFUSAL_QUOTE_CAPTURE_MISSING = "AH_QUOTE_CAPTURE_IDENTITY_MISSING"
REFUSAL_QUOTE_PAYLOAD_MISSING = "AH_QUOTE_PAYLOAD_HASH_MISSING"
REFUSAL_SCORE_UNAVAILABLE = "AH_SETTLEMENT_SCORE_UNAVAILABLE"


@dataclass(frozen=True, kw_only=True)
class TerminalSettlementEvidence:
    """The terminal result as the Provider capture observed it.

    ``observed_at`` is the capture's ``provider_captured_at`` -- when the
    Provider said the fixture had finished. It is deliberately a required field
    with no default, so no caller can build a fact without stating when the
    result was observed.

    ``capture_endpoint`` and ``capture_status`` are required so the evidence can
    only be assembled from the ``fixtures`` capture row itself. There is no
    ``confirmed_at`` field: the column has two writers with different meanings
    and cannot carry an observation semantic, so the type refuses to accept one
    at all rather than validating it later.
    """

    provider_fixture_id: str
    status: str
    home_goals: int
    away_goals: int
    endpoint_capture_id: str
    raw_payload_sha256: str
    observed_at: datetime
    capture_endpoint: str
    capture_status: str


TERMINAL_CAPTURE_ENDPOINT = "fixtures"
TERMINAL_CAPTURE_STATUS = "CAPTURED"

REFUSAL_SETTLEMENT_WRONG_ENDPOINT = "AH_SETTLEMENT_CAPTURE_WRONG_ENDPOINT"
REFUSAL_SETTLEMENT_CAPTURE_NOT_SUCCESSFUL = "AH_SETTLEMENT_CAPTURE_NOT_SUCCESSFUL"


@dataclass(frozen=True, kw_only=True)
class AhSettlementFact:
    status: str
    refusal_code: str | None = None
    refusal_detail: str | None = None

    fact_id: str | None = None
    fact_hash: str | None = None
    source_set_hash: str | None = None
    canonical_key: str | None = None
    hash_contract: str = RUNTIME_AH_SETTLEMENT_HASH_CONTRACT
    policy: str = RUNTIME_AH_SETTLEMENT_POLICY
    schema_version: str = RUNTIME_AH_SETTLEMENT_SCHEMA

    fixture_id: str | None = None
    provider_fixture_id: str | None = None
    competition_id: str | None = None
    season: str | None = None
    kickoff_utc: datetime | None = None

    home_team_provider_id: str | None = None
    away_team_provider_id: str | None = None
    home_w2_team_id: str | None = None
    away_w2_team_id: str | None = None

    line: Decimal | None = None
    home_price: float | None = None
    away_price: float | None = None

    quote_captured_at: datetime | None = None
    quote_capture_ids: tuple[str, ...] = ()
    quote_payload_sha256s: tuple[str, ...] = ()
    quote_identity_hash: str | None = None
    quote_identity_status: str | None = None
    selected_bookmakers: tuple[str, ...] = ()

    settlement_capture_id: str | None = None
    settlement_payload_sha256: str | None = None
    settlement_observed_at: datetime | None = None
    settlement_observed_at_semantics: str | None = None
    fixture_status: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None

    home_settlement: str | None = None
    away_settlement: str | None = None
    result_identity_hash: str | None = None

    source_observed_at: datetime | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hash_contract": self.hash_contract,
            "policy": self.policy,
            "fact_id": self.fact_id,
            "fact_hash": self.fact_hash,
            "source_set_hash": self.source_set_hash,
            "canonical_key": self.canonical_key,
            "fixture_id": self.fixture_id,
            "provider_fixture_id": self.provider_fixture_id,
            "competition_id": self.competition_id,
            "season": self.season,
            "kickoff_utc": _iso(self.kickoff_utc),
            "home_team_provider_id": self.home_team_provider_id,
            "away_team_provider_id": self.away_team_provider_id,
            "home_w2_team_id": self.home_w2_team_id,
            "away_w2_team_id": self.away_w2_team_id,
            "line": None if self.line is None else _format_decimal(self.line),
            "home_price": self.home_price,
            "away_price": self.away_price,
            "quote_captured_at": _iso(self.quote_captured_at),
            "quote_capture_ids": list(self.quote_capture_ids),
            "quote_payload_sha256s": list(self.quote_payload_sha256s),
            "quote_identity_hash": self.quote_identity_hash,
            "quote_identity_status": self.quote_identity_status,
            "selected_bookmakers": list(self.selected_bookmakers),
            "settlement_capture_id": self.settlement_capture_id,
            "settlement_payload_sha256": self.settlement_payload_sha256,
            "settlement_observed_at": _iso(self.settlement_observed_at),
            "settlement_observed_at_semantics": self.settlement_observed_at_semantics,
            "fixture_status": self.fixture_status,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "home_settlement": self.home_settlement,
            "away_settlement": self.away_settlement,
            "result_identity_hash": self.result_identity_hash,
            "source_observed_at": _iso(self.source_observed_at),
        }


def _refuse(code: str, detail: str = "") -> AhSettlementFact:
    return AhSettlementFact(status="REFUSED", refusal_code=code, refusal_detail=detail[:512])


def build_ah_settlement_fact(
    *,
    fixture_id: str,
    provider_fixture_id: str,
    competition_id: str,
    season: str,
    kickoff: datetime,
    market_observations: list[dict[str, Any]],
    settlement: TerminalSettlementEvidence,
    home_team_provider_id: str,
    away_team_provider_id: str,
    home_w2_team_id: str = "",
    away_w2_team_id: str = "",
) -> AhSettlementFact:
    """Build one immutable AH settlement fact, or refuse.

    The quote side is read from ``market_observations`` -- already scoped to this
    fixture's pre-kickoff bucket by the caller. The settlement side comes from
    ``settlement``, which must carry the capture identity and the capture
    instant the terminal result was observed at.
    """
    kickoff_utc = _as_utc(kickoff)
    if kickoff_utc is None:
        return _refuse(REFUSAL_FIXTURE_IDENTITY_MISMATCH, "kickoff missing")

    status = str(settlement.status or "").strip().upper()
    if status not in TERMINAL_FIXTURE_STATUSES:
        return _refuse(REFUSAL_NOT_TERMINAL, status)
    if str(settlement.capture_endpoint) != TERMINAL_CAPTURE_ENDPOINT:
        return _refuse(REFUSAL_SETTLEMENT_WRONG_ENDPOINT, settlement.capture_endpoint)
    if str(settlement.capture_status) != TERMINAL_CAPTURE_STATUS:
        return _refuse(REFUSAL_SETTLEMENT_CAPTURE_NOT_SUCCESSFUL, settlement.capture_status)
    if not settlement.endpoint_capture_id:
        return _refuse(REFUSAL_SETTLEMENT_CAPTURE_MISSING, "endpoint_capture_id empty")
    if not settlement.raw_payload_sha256:
        return _refuse(REFUSAL_SETTLEMENT_PAYLOAD_MISSING, "raw_payload_sha256 empty")
    observed_at = _as_utc(settlement.observed_at)
    if observed_at is None:
        return _refuse(REFUSAL_SETTLEMENT_CAPTURE_MISSING, "provider_captured_at missing")
    if observed_at <= kickoff_utc:
        # A terminal result cannot have been observed before the match started.
        return _refuse(REFUSAL_SETTLEMENT_NOT_AFTER_KICKOFF, observed_at.isoformat())
    if str(settlement.provider_fixture_id) != str(provider_fixture_id):
        return _refuse(
            REFUSAL_FIXTURE_IDENTITY_MISMATCH,
            f"quote fixture {provider_fixture_id} != settlement {settlement.provider_fixture_id}",
        )

    selected = select_canonical_ah_mainline(
        observations=market_observations,
        fixture_id=fixture_id,
        target=kickoff_utc,
        kickoff=kickoff_utc,
    )
    if selected.status != "READY" or selected.line is None or selected.captured_at is None:
        return _refuse(REFUSAL_MAINLINE_UNAVAILABLE, selected.status)
    quote_captured_at = _as_utc(selected.captured_at)
    if quote_captured_at is None or quote_captured_at >= kickoff_utc:
        return _refuse(REFUSAL_QUOTE_NOT_BEFORE_KICKOFF, str(selected.captured_at))

    line = Decimal(str(selected.line))
    identity = project_quote_identity(
        market="ASIAN_HANDICAP",
        selected_line=line,
        authoritative_rows=selected.authoritative_quote_rows,
    )
    if identity.get("identity_status") != "COMPLETE":
        blockers = ",".join(str(item) for item in identity.get("blockers") or [])
        return _refuse(REFUSAL_QUOTE_IDENTITY_INCOMPLETE, blockers)

    quote_capture_ids = _side_capture_ids(selected.authoritative_quote_rows)
    quote_payload_sha256s = _side_payload_hashes(selected.authoritative_quote_rows)
    # Both selections of one bookmaker come from the same odds capture, so the
    # distinct sets normally collapse to a single element. The requirement is
    # per-side completeness, not two distinct values.
    missing_captures = _sides_missing(selected.authoritative_quote_rows, "capture_id")
    if missing_captures:
        return _refuse(REFUSAL_QUOTE_CAPTURE_MISSING, ",".join(missing_captures))
    missing_payloads = _sides_missing(
        selected.authoritative_quote_rows, "raw_payload_sha256"
    )
    if missing_payloads:
        return _refuse(REFUSAL_QUOTE_PAYLOAD_MISSING, ",".join(missing_payloads))

    try:
        home_settlement = settle_asian_handicap(
            settlement.home_goals, settlement.away_goals, "HOME", line
        ).value
        away_settlement = settle_asian_handicap(
            settlement.home_goals, settlement.away_goals, "AWAY", -line
        ).value
    except (ValueError, InvalidOperation) as exc:
        return _refuse(REFUSAL_SCORE_UNAVAILABLE, str(exc))

    quote_identity_hash = str(identity.get("quote_identity_hash") or "")
    selected_bookmakers = sorted(
        str(item) for item in (selected.selected_bookmakers or [])
    )
    selected_line_text = _format_decimal(line)
    quote_ids = sorted(quote_capture_ids)
    quote_payloads = sorted(quote_payload_sha256s)
    quote_observed_text = quote_captured_at.isoformat()
    settlement_observed_text = observed_at.isoformat()
    contract = {
        "schema_version": RUNTIME_AH_SETTLEMENT_SCHEMA,
        "hash_contract": RUNTIME_AH_SETTLEMENT_HASH_CONTRACT,
        "record_kind": RUNTIME_AH_SETTLEMENT_RECORD_KIND,
    }

    # The consumed source set: the two captures this fact rests on, and nothing
    # else. A change to either side changes this digest.
    source_set_hash = _digest(
        {
            **contract,
            "source_role": "consumed_source_set",
            "quote_capture_ids": quote_ids,
            "quote_payload_sha256s": quote_payloads,
            "quote_captured_at": quote_observed_text,
            "settlement_capture_id": settlement.endpoint_capture_id,
            "settlement_payload_sha256": settlement.raw_payload_sha256,
            "settlement_observed_at": settlement_observed_text,
        }
    )
    fact_id = _digest(
        {
            **contract,
            "source_role": "fact_identity",
            "fixture_id": fixture_id,
            "provider_fixture_id": provider_fixture_id,
            "competition_id": competition_id,
            "season": season,
            "canonical_mainline_policy": RUNTIME_AH_SETTLEMENT_POLICY,
            "selected_line": selected_line_text,
            "quote_capture_ids": quote_ids,
            "settlement_capture_id": settlement.endpoint_capture_id,
        }
    )
    result_identity_hash = _digest(
        {
            **contract,
            "source_role": "terminal_result",
            "fixture_id": fixture_id,
            "provider_fixture_id": provider_fixture_id,
            "terminal_status": status,
            "final_score": {"home": settlement.home_goals, "away": settlement.away_goals},
            "settlement_capture_id": settlement.endpoint_capture_id,
            "settlement_payload_sha256": settlement.raw_payload_sha256,
        }
    )
    # The full record preimage: every field the fact is identified by.
    fact_hash = _digest(
        {
            **contract,
            "source_role": "fact",
            "fact_id": fact_id,
            "source_set_hash": source_set_hash,
            "fixture_id": fixture_id,
            "provider_fixture_id": provider_fixture_id,
            "competition_id": competition_id,
            "season": season,
            "kickoff_utc": kickoff_utc.isoformat(),
            "home_team_provider_id": home_team_provider_id,
            "away_team_provider_id": away_team_provider_id,
            "canonical_mainline_policy": RUNTIME_AH_SETTLEMENT_POLICY,
            "canonical_mainline_policy_version": "v1",
            "selected_line": selected_line_text,
            "selected_bookmakers": selected_bookmakers,
            "quote_capture_ids": quote_ids,
            "quote_payload_sha256s": quote_payloads,
            "quote_identity_hash": quote_identity_hash,
            "quote_captured_at": quote_observed_text,
            "settlement_capture_id": settlement.endpoint_capture_id,
            "settlement_payload_sha256": settlement.raw_payload_sha256,
            "settlement_observed_at": settlement_observed_text,
            "settlement_observed_at_semantics": SETTLEMENT_OBSERVED_AT_SEMANTICS,
            "terminal_status": status,
            "final_score": {"home": settlement.home_goals, "away": settlement.away_goals},
            "home_settlement": home_settlement,
            "away_settlement": away_settlement,
            "result_identity_hash": result_identity_hash,
        }
    )
    return AhSettlementFact(
        status="READY",
        fact_id=fact_id,
        fact_hash=fact_hash,
        canonical_key=fact_id,
        source_set_hash=source_set_hash,
        fixture_id=fixture_id,
        provider_fixture_id=provider_fixture_id,
        competition_id=competition_id,
        season=season,
        kickoff_utc=kickoff_utc,
        home_team_provider_id=home_team_provider_id,
        away_team_provider_id=away_team_provider_id,
        home_w2_team_id=home_w2_team_id or None,
        away_w2_team_id=away_w2_team_id or None,
        line=line,
        home_price=selected.home_price,
        away_price=selected.away_price,
        quote_captured_at=quote_captured_at,
        quote_capture_ids=tuple(sorted(quote_capture_ids)),
        quote_payload_sha256s=tuple(sorted(quote_payload_sha256s)),
        quote_identity_hash=quote_identity_hash,
        quote_identity_status="COMPLETE",
        selected_bookmakers=tuple(
            sorted(str(item) for item in (selected.selected_bookmakers or []))
        ),
        settlement_capture_id=settlement.endpoint_capture_id,
        settlement_payload_sha256=settlement.raw_payload_sha256,
        settlement_observed_at=observed_at,
        settlement_observed_at_semantics=SETTLEMENT_OBSERVED_AT_SEMANTICS,
        fixture_status=status,
        home_goals=settlement.home_goals,
        away_goals=settlement.away_goals,
        home_settlement=home_settlement,
        away_settlement=away_settlement,
        result_identity_hash=result_identity_hash,
        # F5's source-observed time is the instant the terminal result was
        # observed by the Provider capture -- nothing else.
        source_observed_at=observed_at,
    )


def _side_capture_ids(rows: dict[str, dict[str, Any]] | None) -> list[str]:
    values: set[str] = set()
    for row in (rows or {}).values():
        value = str(row.get("capture_id") or "")
        if value:
            values.add(value)
    return sorted(values)


def _sides_missing(rows: dict[str, dict[str, Any]] | None, field: str) -> list[str]:
    """Sides whose authoritative quote row does not carry ``field``."""
    missing: list[str] = []
    for side, row in (rows or {}).items():
        if not str(row.get(field) or ""):
            missing.append(str(side).upper())
    if not rows:
        missing.append(f"MISSING_{field.upper()}")
    return sorted(missing)


def _side_payload_hashes(rows: dict[str, dict[str, Any]] | None) -> list[str]:
    values: set[str] = set()
    for row in (rows or {}).values():
        value = str(row.get("raw_payload_sha256") or "")
        if value:
            values.add(value)
    return sorted(values)


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat()


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f")
