from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from w2.domain.time import require_utc


@dataclass(frozen=True, kw_only=True)
class MarketSnapshot:
    fixture_id: str
    market: str
    selection: str
    price: Decimal
    captured_at: datetime
    snapshot_semantics: str
    line: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True, kw_only=True)
class MovementFeatures:
    status: str
    first_seen_to_current: float | None
    recent_move: float | None
    velocity: float | None
    acceleration: float | None
    main_line_change: float | None
    diagnostics: tuple[str, ...]


class MovementFeatureBuilder:
    def build(self, snapshots: list[MarketSnapshot]) -> MovementFeatures:
        if any(snapshot.snapshot_semantics != "CAPTURED_AT" for snapshot in snapshots):
            return MovementFeatures(
                status="CALIBRATION_REQUIRED",
                first_seen_to_current=None,
                recent_move=None,
                velocity=None,
                acceleration=None,
                main_line_change=None,
                diagnostics=("MOVEMENT_DISABLED_FOR_NON_CAPTURED_AT",),
            )
        if len(snapshots) < 2:
            return MovementFeatures(
                status="WATCH_ONLY",
                first_seen_to_current=None,
                recent_move=None,
                velocity=None,
                acceleration=None,
                main_line_change=None,
                diagnostics=("INSUFFICIENT_SNAPSHOTS",),
            )
        ordered = sorted(snapshots, key=lambda snapshot: snapshot.captured_at)
        prices = [float(snapshot.price) for snapshot in ordered]
        hours = [
            max(
                (ordered[index].captured_at - ordered[index - 1].captured_at).total_seconds()
                / 3600,
                1e-9,
            )
            for index in range(1, len(ordered))
        ]
        moves = [prices[index] - prices[index - 1] for index in range(1, len(prices))]
        velocities = [move / hour for move, hour in zip(moves, hours, strict=True)]
        acceleration = None
        if len(velocities) >= 2:
            acceleration = velocities[-1] - velocities[-2]
        line_values = [float(snapshot.line) for snapshot in ordered if snapshot.line is not None]
        main_line_change = line_values[-1] - line_values[0] if len(line_values) >= 2 else None
        return MovementFeatures(
            status="WARN_ONLY",
            first_seen_to_current=prices[-1] - prices[0],
            recent_move=moves[-1],
            velocity=velocities[-1],
            acceleration=acceleration,
            main_line_change=main_line_change,
            diagnostics=("CALIBRATION_REQUIRED", "LINEUP_BEFORE_AFTER_HOOK_REGISTERED"),
        )
