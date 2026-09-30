#!/usr/bin/env python
"""Read-only reconciliation of historical V4 validation samples.

用法：
  python scripts/backfill_validation_samples.py [--reconcile-only] [--check]

- 默认：拒绝旧 AH/OU 样本写入。
- --reconcile-only：只对账，不写入（用于上线后抽样对账）。
- --check：对账后打印差异，差异非 0 时退出码非 0（不写库，与 --reconcile-only 等价）。

对账口径：表内每一行与 ``official_funnel_recommendations`` 输出一一对应
（条数、decimal_odds、settlement、profit_units、score、exact_line、selection
全等），差异必须为 0，否则退出码非 0。
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.dynamic_prematch_models import ValidationSampleModel
from w2.prematch.candidate_notifications import (
    _active_competitions,
    _official_recommendations,
    _parse_iso_utc,
)

_FIELDS = (
    "competition_id",
    "kickoff_utc",
    "selection",
    "exact_line",
    "decimal_odds",
    "bookmaker_id",
    "first_checkpoint",
    "final_checkpoint",
    "evaluation_id",
    "calibration_identity",
    "settlement",
    "profit_units",
    "score",
    "settled_at",
)


def _project(session: Session) -> list[dict]:
    active = _active_competitions(session)
    return _official_recommendations(session, active_competitions=active)


def _normalize(value: object, field: str) -> object:
    if value is None:
        return None
    if field in ("decimal_odds", "profit_units"):
        return float(value)
    if field in ("kickoff_utc", "settled_at", "evaluated_at", "quote_captured_at"):
        return _parse_iso_utc(value) if isinstance(value, str) else value
    return value


def reconcile(session: Session, recommendations: list[dict]) -> list[str]:
    rows = list(session.scalars(select(ValidationSampleModel)))
    table = {(r.fixture_id, r.market): r for r in rows}
    proj = {(r["fixture_id"], r["market"]): r for r in recommendations}
    diffs: list[str] = []
    if set(table) != set(proj):
        only_table = sorted(set(table) - set(proj))
        only_proj = sorted(set(proj) - set(table))
        diffs.append(f"KEYS_DIFFER only_table={only_table} only_proj={only_proj}")
    for key in sorted(set(table) & set(proj)):
        t = table[key]
        p = proj[key]
        for field in _FIELDS:
            tv = _normalize(getattr(t, field), field)
            pv = _normalize(p.get(field), field)
            if tv != pv:
                diffs.append(f"{key} {field}: table={tv!r} proj={pv!r}")
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reconcile-only", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not (args.reconcile_only or args.check):
        print("LEGACY_AH_OU_VALIDATION_WRITER_RETIRED", file=sys.stderr)
        return 2

    engine = create_engine()
    with Session(engine) as session:
        recommendations = _project(session)
        print(f"projected_rows={len(recommendations)}", flush=True)
        diffs = reconcile(session, recommendations)
        if diffs:
            print(f"RECONCILE_DIFFS={len(diffs)}", flush=True)
            for diff in diffs[:50]:
                print(f"  {diff}", flush=True)
            return 1
        print("RECONCILE_OK diffs=0", flush=True)
        return 0


if __name__ == "__main__":
    sys.exit(main())
