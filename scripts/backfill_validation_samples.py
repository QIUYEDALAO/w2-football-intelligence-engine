#!/usr/bin/env python
"""PERF-01 阶段2：一次性回填 validation_samples 表全部历史，并逐行对账。

用法：
  python scripts/backfill_validation_samples.py [--reconcile-only] [--check]

- 默认：全量投影 -> 覆盖写入 validation_samples -> 对账（差异必须为 0）。
- --reconcile-only：只对账，不写入（用于上线后抽样对账）。
- --check：对账后打印差异，差异非 0 时退出码非 0（不写库，与 --reconcile-only 等价）。

对账口径：表内每一行与 ``official_funnel_recommendations`` 输出一一对应
（条数、decimal_odds、settlement、profit_units、score、exact_line、selection
全等），差异必须为 0，否则退出码非 0。
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

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


def _apply(sample: ValidationSampleModel, row: dict, now: datetime) -> None:
    sample.competition_id = row.get("competition_id")
    sample.kickoff_utc = _parse_iso_utc(row.get("kickoff_utc"))
    sample.selection = row["selection"]
    sample.exact_line = row["exact_line"]
    sample.decimal_odds = row["decimal_odds"]
    sample.bookmaker_id = row.get("bookmaker_id")
    sample.first_checkpoint = row.get("first_checkpoint")
    sample.final_checkpoint = row.get("final_checkpoint")
    sample.evaluation_id = row["evaluation_id"]
    sample.calibration_identity = row.get("calibration_identity")
    sample.settlement = row["settlement"]
    sample.profit_units = row.get("profit_units")
    sample.score = row.get("score")
    sample.projected_at = now
    sample.settled_at = _parse_iso_utc(row.get("settled_at"))
    sample.evaluated_at = _parse_iso_utc(row.get("evaluated_at"))
    sample.quote_captured_at = _parse_iso_utc(row.get("quote_captured_at"))
    sample.current_ev = row.get("current_ev")
    sample.home_team_label = row.get("home_team_label")
    sample.away_team_label = row.get("away_team_label")
    sample.later_unassessed_checkpoints = row.get("later_unassessed_checkpoints")
    sample.lifecycle_note_zh = row.get("lifecycle_note_zh")


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
    reconcile_only = args.reconcile_only or args.check

    engine = create_engine()
    now = datetime.now(UTC)
    with Session(engine) as session:
        recommendations = _project(session)
        print(f"projected_rows={len(recommendations)}", flush=True)
        if not reconcile_only:
            # 覆盖写入：清空重建（回填是一次性的全量快照）。
            for row in session.scalars(select(ValidationSampleModel)):
                session.delete(row)
            session.flush()
            for row in recommendations:
                sample = ValidationSampleModel(
                    fixture_id=row["fixture_id"],
                    market=row["market"],
                    selection=row["selection"],
                    exact_line=row["exact_line"],
                    decimal_odds=row["decimal_odds"],
                    evaluation_id=row["evaluation_id"],
                    settlement=row["settlement"],
                    projected_at=now,
                )
                _apply(sample, row, now)
                session.add(sample)
            session.commit()
            print(f"written_rows={len(recommendations)}", flush=True)

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
