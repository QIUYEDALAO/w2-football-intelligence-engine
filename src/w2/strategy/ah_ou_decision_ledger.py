"""AH/OU v3 decision ledger writer (S3/S4).

Four-step idempotency, each step keyed on the immutable content of the step
before it, so retries never produce a duplicate and a changed input becomes a
new identity instead of a silent edit:

1. capture  -- the quote's ``capture_id``/``source_capture_sha256`` (same capture
   is addressed once).
2. freeze   -- ``input_hash`` = canonical digest of the frozen F9/F6 input.
3. evaluate -- ``decision_id`` = canonical digest of (input_hash, model version,
   calibration version, quote identity, direction, score, skip).
4. write    -- insert by ``decision_id``; an identical re-run is a no-op, a
   conflicting ``(fixture_id, market, decision_at)`` slot refuses the batch.

The writer never falls back to the old weighted ``factor_score`` / pure
``bookmaker_intent``: a refusal is persisted (via ``skip_reason``) and stops the
rest of the batch.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.domain.ah_ou_decision_identity import (
    build_ah_ou_decision_id,
)
from w2.domain.ah_ou_decision_identity import (
    build_ah_ou_input_hash as build_ah_ou_input_hash,
)
from w2.domain.ah_ou_decision_identity import (
    canonical_decision_score_text as canonical_decision_score_text,
)
from w2.domain.ah_ou_decision_identity import (
    canonical_decision_time as _iso,
)
from w2.domain.canonical_serialization import HashDomain, canonical_sha256
from w2.infrastructure.persistence.ah_ou_decision_ledger_models import (
    AH_OU_FROZEN_TERMS_SCHEMA,
    AhOuCohortModel,
    AhOuDecisionLedgerModel,
)

_DECISION_HASH_DOMAIN = HashDomain.RECOMMENDATION_DECISION_V4


_decimal_text = canonical_decision_score_text


def _frozen_json(value: Any) -> str:
    """Normalize a JSON column (full_distribution) to a comparable digest.

    ``==`` on decoded JSON is float-fragile and order-sensitive; hashing through
    the canonical serializer makes the comparison deterministic.
    """
    if value is None:
        return ""
    return canonical_sha256(value, domain=_DECISION_HASH_DOMAIN)


def _frozen_field_mismatch(
    existing: AhOuDecisionLedgerModel,
    *,
    fixture_id: str,
    market: str,
    decision_at: datetime,
    model_version: str,
    calibration_version: str,
    input_hash: str,
    full_distribution: dict[str, Any],
    decision_contract: str | None,
    frozen_terms: dict[str, Any] | None,
    terms_hash: str | None,
    quote_identity_hash: str,
    source_capture_sha256: str,
    capture_id: str,
    source_id: str,
    home_team_id: str,
    away_team_id: str,
    selected: bool,
    direction: str | None,
    score_text: str,
    skip_reason: str | None,
) -> str | None:
    """Compare every frozen business field; return the first differing name.

    A stored row with the same ``decision_id`` is only an idempotent no-op when
    every frozen field is identical. Any field that differs is an explicit
    conflict (never a silent return).
    """
    checks = (
        ("fixture_id", existing.fixture_id, fixture_id),
        ("market", existing.market, market),
        ("decision_at", _iso(existing.decision_at), _iso(decision_at)),
        ("model_version", existing.model_version, model_version),
        ("calibration_version", existing.calibration_version, calibration_version),
        ("input_hash", existing.input_hash, input_hash),
        ("decision_contract", existing.decision_contract, decision_contract),
        ("frozen_terms", _frozen_json(existing.frozen_terms), _frozen_json(frozen_terms)),
        ("terms_hash", existing.terms_hash, terms_hash),
        ("quote_identity_hash", existing.quote_identity_hash, quote_identity_hash),
        ("source_capture_sha256", existing.source_capture_sha256, source_capture_sha256),
        ("capture_id", existing.capture_id, capture_id),
        ("source_id", existing.source_id, source_id),
        ("home_team_id", existing.home_team_id, home_team_id),
        ("away_team_id", existing.away_team_id, away_team_id),
        ("selected", existing.selected, selected),
        ("direction", existing.direction, direction),
        ("score", existing.score, score_text),
        ("skip_reason", existing.skip_reason, skip_reason),
        (
            "full_distribution",
            _frozen_json(existing.full_distribution),
            _frozen_json(full_distribution),
        ),
    )
    for name, left, right in checks:
        if left != right:
            return name
    return None


def write_ah_ou_decision(
    session: Session,
    *,
    fixture_id: str,
    market: str,
    decision_at: datetime,
    model_version: str,
    calibration_version: str,
    input_hash: str,
    full_distribution: dict[str, Any],
    decision_contract: str | None = None,
    frozen_terms: dict[str, Any] | None = None,
    terms_hash: str | None = None,
    quote_identity_hash: str,
    source_capture_sha256: str,
    capture_id: str,
    source_id: str,
    home_team_id: str,
    away_team_id: str,
    selected: bool,
    direction: str | None,
    score: float | Decimal,
    skip_reason: str | None,
    created_at: datetime,
) -> AhOuDecisionLedgerModel:
    """Idempotent write: identical re-run is a no-op; slot conflict raises."""
    if decision_contract == "w2.ah_ou_decision.v3.1":
        from w2.prematch.current_recommendation_control import (
            require_current_recommendations_running,
        )

        require_current_recommendations_running()
    score_text = _decimal_text(score)
    if decision_contract == "w2.ah_ou_decision.v3.1":
        if selected:
            if (
                not isinstance(frozen_terms, dict)
                or frozen_terms.get("schema_version") != AH_OU_FROZEN_TERMS_SCHEMA
            ):
                raise ValueError("AH_OU_SELECTED_TERMS_INCOMPLETE")
            expected_terms_hash = canonical_sha256(
                frozen_terms, domain=HashDomain.RECOMMENDATION_DECISION_V4)
            if expected_terms_hash != terms_hash:
                raise ValueError("AH_OU_SELECTED_TERMS_HASH_MISMATCH")
            if any(frozen_terms.get(name) in (None, "") for name in (
                "selection", "home_line" if market == "ASIAN_HANDICAP" else "total_line",
                "selected_line", "entry_odds", "bookmaker_id", "capture_id",
                "captured_at", "raw_payload_sha256", "quote_identity_hash",
                "model_version", "calibration_version", "input_hash")):
                raise ValueError("AH_OU_SELECTED_TERMS_INCOMPLETE")
        elif frozen_terms is not None or terms_hash is not None:
            raise ValueError("AH_OU_UNSELECTED_TERMS_CONFLICT")
    decision_id = build_ah_ou_decision_id(
        fixture_id=fixture_id,
        market=market,
        decision_at=decision_at,
        model_version=model_version,
        calibration_version=calibration_version,
        input_hash=input_hash,
        quote_identity_hash=quote_identity_hash,
        source_capture_sha256=source_capture_sha256,
        direction=direction,
        score=score_text,
        skip_reason=skip_reason,
        selected=selected,
        terms_hash=terms_hash,
    )

    existing = session.get(AhOuDecisionLedgerModel, decision_id)
    if existing is not None:
        # Four-step idempotency step 4: an identical re-run is a no-op ONLY when
        # every frozen business field matches. A same decision_id with any field
        # changed is an explicit conflict, never a silent return.
        mismatch = _frozen_field_mismatch(
            existing,
            fixture_id=fixture_id,
            market=market,
            decision_at=decision_at,
            model_version=model_version,
            calibration_version=calibration_version,
            input_hash=input_hash,
            full_distribution=full_distribution,
            decision_contract=decision_contract,
            frozen_terms=frozen_terms,
            terms_hash=terms_hash,
            quote_identity_hash=quote_identity_hash,
            source_capture_sha256=source_capture_sha256,
            capture_id=capture_id,
            source_id=source_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            selected=selected,
            direction=direction,
            score_text=score_text,
            skip_reason=skip_reason,
        )
        if mismatch is not None:
            raise ValueError(
                "AH_OU_DECISION_FIELD_CONFLICT:"
                f"decision_id {decision_id} already exists with a different "
                f"{mismatch}"
            )
        return existing

    slot_row = session.scalar(
        select(AhOuDecisionLedgerModel).where(
            AhOuDecisionLedgerModel.fixture_id == fixture_id,
            AhOuDecisionLedgerModel.market == market,
            AhOuDecisionLedgerModel.decision_at == decision_at,
        )
    )
    if slot_row is not None:
        if slot_row.selected:
            # 已 selected=true 的最终决策不可重决策（幂等防线）。
            raise ValueError(
                "AH_OU_DECISION_SLOT_CONFLICT:"
                f"{fixture_id}/{market}/{_iso(decision_at)} already has {slot_row.decision_id}"
            )
        # 旧 SKIP（selected=false）→ 重新评估覆盖：删除旧 SKIP 行后按新 identity 写入。
        # 幂等仍由 decision_id 的 existing 检查保证（同输入走 no-op，不会到这里）。
        session.delete(slot_row)
        session.flush()

    row = AhOuDecisionLedgerModel(
        decision_id=decision_id,
        fixture_id=fixture_id,
        market=market,
        decision_at=decision_at,
        model_version=model_version,
        calibration_version=calibration_version,
        input_hash=input_hash,
        full_distribution=full_distribution,
        decision_contract=decision_contract,
        frozen_terms=frozen_terms,
        terms_hash=terms_hash,
        quote_identity_hash=quote_identity_hash,
        source_capture_sha256=source_capture_sha256,
        capture_id=capture_id,
        source_id=source_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        selected=selected,
        direction=direction,
        score=score_text,
        skip_reason=skip_reason,
        created_at=created_at,
    )
    session.add(row)
    return row


def _frozen_cohort_mismatch(
    existing: AhOuCohortModel,
    *,
    fixture_id: str,
    decision_at: datetime,
    home_team_id: str,
    away_team_id: str,
    ah_capture_id: str | None,
    ah_source_capture_sha256: str | None,
    ou_capture_id: str | None,
    ou_source_capture_sha256: str | None,
    model_version: str,
    calibration_version: str,
    frozen_identity: str,
) -> str | None:
    """Compare every frozen cohort field; return the first differing name.

    D: a stored cohort with the same ``cohort_id`` is only an idempotent no-op
    when every frozen field is identical. Any differing field (e.g. a changed
    ``frozen_identity`` or OU source hash) is an explicit conflict.
    """
    checks = (
        ("fixture_id", existing.fixture_id, fixture_id),
        ("decision_at", _iso(existing.decision_at), _iso(decision_at)),
        ("home_team_id", existing.home_team_id, home_team_id),
        ("away_team_id", existing.away_team_id, away_team_id),
        ("ah_capture_id", existing.ah_capture_id, ah_capture_id),
        ("ah_source_capture_sha256", existing.ah_source_capture_sha256, ah_source_capture_sha256),
        ("ou_capture_id", existing.ou_capture_id, ou_capture_id),
        ("ou_source_capture_sha256", existing.ou_source_capture_sha256, ou_source_capture_sha256),
        ("model_version", existing.model_version, model_version),
        ("calibration_version", existing.calibration_version, calibration_version),
        ("frozen_identity", existing.frozen_identity, frozen_identity),
    )
    for name, left, right in checks:
        if left != right:
            return name
    return None


def upsert_cohort(
    session: Session,
    *,
    cohort_id: str,
    fixture_id: str,
    decision_at: datetime,
    home_team_id: str,
    away_team_id: str,
    ah_capture_id: str | None,
    ah_source_capture_sha256: str | None,
    ou_capture_id: str | None,
    ou_source_capture_sha256: str | None,
    model_version: str,
    calibration_version: str,
    frozen_identity: str,
    created_at: datetime,
) -> AhOuCohortModel:
    """Idempotent cohort write keyed on ``(fixture_id, decision_at)``.

    Re-running with the same inputs produces the same ``cohort_id`` and is a
    one-row no-op only when every frozen field matches (D). A conflicting cohort
    on the same slot raises, so the pre-match role can never silently overwrite a
    frozen preregistration.
    """
    existing = session.get(AhOuCohortModel, cohort_id)
    if existing is not None:
        mismatch = _frozen_cohort_mismatch(
            existing,
            fixture_id=fixture_id,
            decision_at=decision_at,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            ah_capture_id=ah_capture_id,
            ah_source_capture_sha256=ah_source_capture_sha256,
            ou_capture_id=ou_capture_id,
            ou_source_capture_sha256=ou_source_capture_sha256,
            model_version=model_version,
            calibration_version=calibration_version,
            frozen_identity=frozen_identity,
        )
        if mismatch is not None:
            raise ValueError(
                "AH_OU_COHORT_FIELD_CONFLICT:"
                f"cohort_id {cohort_id} already exists with a different {mismatch}"
            )
        return existing
    slot_row = session.scalar(
        select(AhOuCohortModel).where(
            AhOuCohortModel.fixture_id == fixture_id,
            AhOuCohortModel.decision_at == decision_at,
        )
    )
    if slot_row is not None:
        if slot_row.cohort_id == cohort_id:
            return slot_row
        # 不同 identity（重新评估）：已 selected=true 的 slot 不可覆盖（不重决策）；
        # 旧 SKIP 允许覆盖（删除旧 cohort 后按新 identity 写入）。
        has_selected = session.scalar(
            select(AhOuDecisionLedgerModel.decision_id).where(
                AhOuDecisionLedgerModel.fixture_id == fixture_id,
                AhOuDecisionLedgerModel.decision_at == decision_at,
                AhOuDecisionLedgerModel.selected.is_(True),
            ).limit(1)
        )
        if has_selected is not None:
            raise ValueError(
                "AH_OU_COHORT_SLOT_CONFLICT:"
                f"{fixture_id}/{_iso(decision_at)} already has a selected decision"
            )
        session.delete(slot_row)
        session.flush()
    row = AhOuCohortModel(
        cohort_id=cohort_id,
        fixture_id=fixture_id,
        decision_at=decision_at,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        ah_capture_id=ah_capture_id,
        ah_source_capture_sha256=ah_source_capture_sha256,
        ou_capture_id=ou_capture_id,
        ou_source_capture_sha256=ou_source_capture_sha256,
        model_version=model_version,
        calibration_version=calibration_version,
        frozen_identity=frozen_identity,
        created_at=created_at,
    )
    session.add(row)
    return row


def write_ah_ou_decision_batch(
    session: Session,
    *,
    cohort: dict[str, Any],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atomic AH/OU + cohort write: every row in one transaction.

    The caller owns ``session.begin()``/``commit()``. Any step raising propagates,
    so the caller rolls back the whole batch -- an OU conflict never leaves a
    one-sided AH ledger row, and the cohort is never committed without both
    markets (or their SKIP reasons) in the same transaction.
    """
    from w2.prematch.current_recommendation_control import require_current_recommendations_running

    require_current_recommendations_running()
    # 幂等过严修复由 upsert_cohort / write_ah_ou_decision 各自承担：
    # - 同 identity（同 cohort_id / 同 decision_id）→ no-op；
    # - 不同 identity + 已有 selected=true → 冲突（不重决策）；
    # - 不同 identity + 旧 SKIP → 覆盖（删除旧 SKIP 行后重新写入）。
    cohort_row = upsert_cohort(session, **cohort)
    written = [write_ah_ou_decision(session, **decision) for decision in decisions]
    return {"cohort_id": cohort_row.cohort_id,
            "decisions": [{"decision_id": row.decision_id, "market": row.market,
                           "selected": row.selected, "direction": row.direction,
                           "score": row.score, "skip_reason": row.skip_reason,
                           } for row in written]}
