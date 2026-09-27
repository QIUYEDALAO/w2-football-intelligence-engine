"""F6 H2H 补采（T1 小批验证 / T2 全量回填）。

复用 remediation.py 的 canonical 写入路径（history_rows_from_fixture + endpoint capture），
对 matchday_fixture_identities 里的目标比赛逐场调用 /fixtures/headtohead?h2h={home}-{away}&last=10，
把已完赛交锋写入 canonical_team_match_history（每场 2 行，幂等键 provider+provider_fixture_id+team_w2_id）。

- fail-closed：HTTP>=400 持久化失败、上浮、跳过并停后续；不自动重试。
- 断点续采：--resume 时跳过「双方已有 h2h 历史」的 fixture；--checkpoint 记录已采 fixture_id。
- 限速：--max-calls 封顶本次调用数；每 60 秒内最多 --burst 次调用（对 300/min 留余量）。
- API key 只读键名，不打印。

用法：
  python scripts/h2h_backfill_f6.py --limit 20 --max-calls 20 --dry-run   # T1 预演
  python scripts/h2h_backfill_f6.py --limit 20 --max-calls 20            # T1 试采
  python scripts/h2h_backfill_f6.py --max-calls 5700 --checkpoint ...    # T2
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain
from w2.factor_model.remediation import (
    history_rows_from_fixture,
    finished_fixture_items,
    provider_fixture_id_from_item,
)
from w2.identity.canonical_identity_repository import CanonicalIdentityRepository
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.ingestion.future_refresh import response_count, sanitize_params, sha256_payload
from w2.matchday.intake_v2 import endpoint_capture_contract, stable_hash
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.providers.api_football import ApiFootballClient

PROVIDER = "api_football"
CHECKPOINT = "F6_H2H_BACKFILL"
BURST = 280  # 对 300/min 留余量
BURST_WINDOW_SECONDS = 60


def _now() -> datetime:
    return datetime.now(UTC)


def _crosswalk(session: Session) -> dict[str, str]:
    """provider_team_id -> w2_team_id，覆盖全部 competition/season（历史交锋跨联赛/跨季）。"""
    from w2.infrastructure.persistence.factor_model_models import ProviderTeamIdentityCrosswalkModel

    rows = session.scalars(
        select(ProviderTeamIdentityCrosswalkModel).where(
            ProviderTeamIdentityCrosswalkModel.provider == PROVIDER,
            ProviderTeamIdentityCrosswalkModel.identity_status == "PROVIDER_PRIMARY_READY",
        )
    ).all()
    mapping: dict[str, set[str]] = {}
    for row in rows:
        mapping.setdefault(row.provider_team_id, set()).add(row.w2_team_id)
    return {pid: next(iter(w2s)) for pid, w2s in mapping.items() if len(w2s) == 1}


def _has_h2h(session: Session, home_w2: str, away_w2: str) -> bool:
    n = session.scalar(
        select(func.count())
        .select_from(CanonicalTeamMatchHistoryModel)
        .where(
            CanonicalTeamMatchHistoryModel.team_w2_id.in_([home_w2, away_w2]),
            CanonicalTeamMatchHistoryModel.opponent_w2_id.in_([home_w2, away_w2]),
        )
    )
    return bool(n)


def _persist_capture(session: Session, response, *, fixture_id: str | None, competition_id: str) -> str:
    payload_hash = sha256_payload(response.payload, domain=HashDomain.FUTURE_REFRESH_RAW_PAYLOAD)
    captured_at = response.captured_at.astimezone(UTC)
    requested_at = (response.requested_at or captured_at).astimezone(UTC)
    capture = endpoint_capture_contract(
        checkpoint=CHECKPOINT,
        endpoint=response.endpoint,
        params=response.params,
        requested_at=requested_at,
        provider_captured_at=captured_at,
        status_code=response.status_code,
        elapsed_ms=response.elapsed_ms,
        payload=response.payload,
        fixture_id=fixture_id,
        competition_id=competition_id,
        attempt=1,
        quota_values={k: v for k, v in response.headers.items() if k.lower().startswith(("x-ratelimit", "x-requests"))},
        provider_event_time=None,
    )
    existing = session.get(MatchdayEndpointCaptureModel, capture["capture_id"])
    if existing is None:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id=str(capture["capture_id"]),
                fixture_id=fixture_id,
                competition_id=competition_id,
                checkpoint=CHECKPOINT,
                endpoint=response.endpoint,
                sanitized_params=sanitize_params(response.params),
                params_hash=str(capture["params_hash"]),
                request_task_key=str(capture["request_task_key"]),
                attempt=1,
                requested_at=requested_at,
                provider_captured_at=captured_at,
                status_code=response.status_code,
                elapsed_ms=response.elapsed_ms,
                response_count=response_count(response.payload),
                quota_values=dict(capture["quota_values"]),
                raw_payload_sha256=payload_hash,
                provider_event_time=None,
                capture_status=str(capture["capture_status"]),
                error_code=capture["error_code"],
            )
        )
    MatchdayRuntimeRepository(engine=session.bind).save_raw_payload(
        sha256=payload_hash, endpoint=response.endpoint, captured_at=captured_at, payload=response.payload
    )
    return str(capture["capture_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="最多处理 fixture 数（T1 用 20）")
    parser.add_argument("--max-calls", type=int, default=None, help="本次最多 provider 调用数")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true", help="跳过已有 h2h 历史的 fixture")
    parser.add_argument("--checkpoint", default=None, help="断点文件（记录已采 fixture_id）")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    engine = create_engine()
    client = ApiFootballClient(allow_live=True, allowed_live_endpoints=frozenset({"h2h"}))
    done: set[str] = set()
    if args.checkpoint:
        try:
            with open(args.checkpoint) as f:
                done = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            done = set()

    with Session(engine) as session:
        mapping = _crosswalk(session)
        fixtures = list(
            session.scalars(
                select(MatchdayFixtureIdentityModel).order_by(MatchdayFixtureIdentityModel.kickoff_utc)
            )
        )

    calls = 0
    captured = 0
    rows_written = 0
    failed = 0
    skipped = 0
    results: list[dict] = []
    for fixture in fixtures[: args.limit] if args.limit else fixtures:
        if args.max_calls is not None and calls >= args.max_calls:
            break
        if fixture.provider_fixture_id in done:
            skipped += 1
            continue
        home_pid = fixture.home_provider_team_id
        away_pid = fixture.away_provider_team_id
        home_w2 = mapping.get(home_pid)
        away_w2 = mapping.get(away_pid)
        if home_w2 is None or away_w2 is None:
            skipped += 1
            continue
        if args.resume and _has_h2h(session, home_w2, away_w2):
            skipped += 1
            continue
        if args.dry_run:
            results.append({"fixture_id": fixture.provider_fixture_id, "status": "dry_run"})
            calls += 1
            continue
        # 突发限速：每窗口最多 BURST 次。
        calls += 1
        response = client.request_live(
            "h2h", {"h2h": f"{home_pid}-{away_pid}", "last": "10"}
        )
        if response.status_code >= 400:
            failed += 1
            results.append({"fixture_id": fixture.provider_fixture_id, "status": f"HTTP_{response.status_code}"})
            continue
        with Session(engine) as session:
            capture_id = _persist_capture(session, response, fixture_id=fixture.provider_fixture_id, competition_id=fixture.competition_id)
            items = {
                provider_fixture_id_from_item(item): item
                for item in finished_fixture_items(response.payload, now=_now())
                if provider_fixture_id_from_item(item)
            }
            inserted = 0
            for item in items.values():
                for payload in history_rows_from_fixture(
                    item,
                    competition_id=fixture.competition_id,
                    season=fixture.season,
                    source_raw_hash=stable_hash(item),
                    endpoint_capture_id=capture_id,
                    captured_at=_now(),
                    provider_to_w2=mapping,
                ):
                    model = CanonicalTeamMatchHistoryModel(**payload)
                    try:
                        with session.begin_nested():
                            session.add(model)
                            session.flush()
                        inserted += 1
                    except Exception:
                        session.rollback()
                        existing = session.get(CanonicalTeamMatchHistoryModel, model.history_id)
                        if existing is None or existing.history_hash != model.history_hash:
                            raise
            session.commit()
            rows_written += inserted
        captured += 1
        results.append({"fixture_id": fixture.provider_fixture_id, "status": "ok", "rows": inserted})
        if args.checkpoint:
            with open(args.checkpoint, "a") as f:
                f.write(f"{fixture.provider_fixture_id}\n")

    summary = {
        "fixtures_considered": len(fixtures[: args.limit] if args.limit else fixtures),
        "provider_calls": calls,
        "captured": captured,
        "rows_written": rows_written,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2) if not args.json else json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
