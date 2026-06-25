from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from w2.domain.time import require_utc


class AsOfTimed(Protocol):
    @property
    def observed_at(self) -> datetime:
        pass


class AsOfLeakageError(ValueError):
    pass


@dataclass(frozen=True, kw_only=True)
class AsOfCheck:
    status: str
    rows_checked: int
    blocked_rows: int
    diagnostics: tuple[str, ...]


def assert_not_future(observed_at: datetime, as_of: datetime, *, label: str) -> datetime:
    observed = require_utc(observed_at, f"{label}.observed_at")
    cutoff = require_utc(as_of, "as_of")
    if observed > cutoff:
        raise AsOfLeakageError(f"AS_OF_LEAKAGE:{label}")
    return observed


def latest_as_of[TAsOfTimed: AsOfTimed](
    rows: list[TAsOfTimed],
    as_of: datetime,
) -> TAsOfTimed | None:
    cutoff = require_utc(as_of, "as_of")
    eligible = [row for row in rows if require_utc(row.observed_at, "observed_at") <= cutoff]
    if not eligible:
        return None
    return max(eligible, key=lambda row: require_utc(row.observed_at, "observed_at"))


def check_no_future_rows(rows: list[AsOfTimed], as_of: datetime, *, label: str) -> AsOfCheck:
    cutoff = require_utc(as_of, "as_of")
    blocked = [
        row for row in rows if require_utc(row.observed_at, f"{label}.observed_at") > cutoff
    ]
    return AsOfCheck(
        status="PASS" if not blocked else "FAIL",
        rows_checked=len(rows),
        blocked_rows=len(blocked),
        diagnostics=tuple(f"AS_OF_LEAKAGE:{label}" for _ in blocked),
    )
