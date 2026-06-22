from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class TemporalStatus(StrEnum):
    PREMATCH_LIVE = "PREMATCH_LIVE"
    PREMATCH_LOCKED = "PREMATCH_LOCKED"
    POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH = (
        "POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH"
    )
    POSTMATCH_SETTLEMENT = "POSTMATCH_SETTLEMENT"
    INVALID_POST_KICKOFF_INPUT = "INVALID_POST_KICKOFF_INPUT"


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"naive datetime rejected: {value}")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, kw_only=True)
class TemporalContext:
    source_snapshot_id: str
    source_captured_at: datetime
    source_phase: str
    kickoff_utc: datetime
    valuation_generated_at: datetime
    projector_generated_at: datetime
    locked_before_kickoff: bool
    recomputed_after_kickoff: bool
    temporal_status: TemporalStatus

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "source_snapshot_id": self.source_snapshot_id,
            "source_captured_at": self.source_captured_at.isoformat(),
            "source_phase": self.source_phase,
            "kickoff_utc": self.kickoff_utc.isoformat(),
            "valuation_generated_at": self.valuation_generated_at.isoformat(),
            "projector_generated_at": self.projector_generated_at.isoformat(),
            "locked_before_kickoff": self.locked_before_kickoff,
            "recomputed_after_kickoff": self.recomputed_after_kickoff,
            "temporal_status": self.temporal_status.value,
        }


def classify_temporal_status(
    *,
    source_captured_at: datetime,
    kickoff_utc: datetime,
    valuation_generated_at: datetime,
    source_phase: str,
    settlement: bool = False,
) -> TemporalStatus:
    source_captured_at = source_captured_at.astimezone(UTC)
    kickoff_utc = kickoff_utc.astimezone(UTC)
    valuation_generated_at = valuation_generated_at.astimezone(UTC)
    if settlement:
        return TemporalStatus.POSTMATCH_SETTLEMENT
    if source_captured_at >= kickoff_utc:
        return TemporalStatus.INVALID_POST_KICKOFF_INPUT
    if valuation_generated_at >= kickoff_utc:
        return TemporalStatus.POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH
    if source_phase in {"T-30m", "T-10m", "CLOSING"}:
        return TemporalStatus.PREMATCH_LOCKED
    return TemporalStatus.PREMATCH_LIVE


def temporal_context_from_manifest(
    *,
    snapshot_id: str,
    manifest: dict[str, object],
    valuation_generated_at: datetime | None = None,
    projector_generated_at: datetime | None = None,
) -> TemporalContext:
    source_captured_at = parse_utc(str(manifest["captured_at_utc"]))
    kickoff_utc = parse_utc(str(manifest["kickoff_utc"]))
    generated = valuation_generated_at or datetime.now(UTC)
    projected = projector_generated_at or datetime.now(UTC)
    status = classify_temporal_status(
        source_captured_at=source_captured_at,
        kickoff_utc=kickoff_utc,
        valuation_generated_at=generated,
        source_phase=str(manifest.get("phase", "")),
    )
    return TemporalContext(
        source_snapshot_id=snapshot_id,
        source_captured_at=source_captured_at,
        source_phase=str(manifest.get("phase", "")),
        kickoff_utc=kickoff_utc,
        valuation_generated_at=generated.astimezone(UTC),
        projector_generated_at=projected.astimezone(UTC),
        locked_before_kickoff=source_captured_at < kickoff_utc,
        recomputed_after_kickoff=generated.astimezone(UTC) >= kickoff_utc,
        temporal_status=status,
    )
