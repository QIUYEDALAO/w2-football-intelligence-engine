"""Explicit, one-shot production forward-clock registration after release readback.

Usage: python -m w2.tracking.start_forward_clock --revision <deployed 40-char SHA>
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import create_engine
from w2.tracking.forward_evidence import register_forward_clock


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    with Session(create_engine()) as session:
        now = session.scalar(select(func.clock_timestamp()))
        if now is None:
            raise RuntimeError("FORWARD_CLOCK_DATABASE_TIME_UNAVAILABLE")
        row = register_forward_clock(session, started_at=now, code_revision=args.revision)
        session.commit()
        print(f"{row.clock_id} {row.started_at.isoformat()} {row.code_revision}")


if __name__ == "__main__":
    main()
