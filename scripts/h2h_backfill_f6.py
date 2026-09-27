"""F6 H2H 补采（T1 小批验证 / T2 全量回填）—— 对象为回测场次清单 CSV。

复用 remediation.py 的 canonical 写入路径（history_rows_from_fixture + endpoint capture），
对 CSV 的每行（home_team_id/away_team_id 为 Football-API team id）调用
/fixtures/headtohead?h2h={home}-{away}&last=10，把已完赛交锋写入 canonical_team_match_history
（每场 2 行，幂等键 provider+provider_fixture_id+team_w2_id）。

- team_id -> team_w2_id：CanonicalIdentityRepository 全局 crosswalk（跨联赛/跨季）。
- league -> competition_id：league_season 表 provider_league_id 映射（历史交锋按各自联赛落库）。
- fail-closed：HTTP>=400 持久化失败、上浮、跳过并停后续；不自动重试。
- 断点续采：--checkpoint 记录已采 fixture_id；重跑跳过已采。
- 限速：--max-calls 封顶日配额；每 60 秒内最多 --burst 次（默认 280，对 300/min 留余量）。
- API key 只读键名，不打印。

用法：
  python scripts/h2h_backfill_f6.py --csv <清单.csv> --limit 20 --max-calls 20 --dry-run
  python scripts/h2h_backfill_f6.py --csv <清单.csv> --max-calls 5700 --checkpoint /tmp/h2h_done.txt
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from w2.domain.canonical_serialization import HashDomain
from w2.factor_model.remediation import (
    finished_fixture_items,
    history_rows_from_fixture,
    provider_fixture_id_from_item,
)
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamMatchHistoryModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayEndpointCaptureModel
from w2.ingestion.future_refresh import response_count, sanitize_params, sha256_payload
from w2.matchday.intake_v2 import endpoint_capture_contract, stable_hash
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.providers.api_football import ApiFootballClient

PROVIDER = "api_football"
CHECKPOINT = "F6_H2H_BACKFILL"
DEFAULT_BURST = 280
BURST_WINDOW_SECONDS = 60


def _now() -> datetime:
    return datetime.now(UTC)


def _load_rows(csv_path: str) -> list[dict[str, str]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _crosswalk(session: Session) -> dict[str, str]:
    """provider_team_id -> w2_team_id，覆盖全部 competition/season（历史交锋跨联赛/跨季）。"""
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


def _league_mapping(session: Session) -> dict[str, str]:
    """api_football_league_id -> competition_id。"""
    mapping: dict[str, str] = {}
    for row in session.scalars(select(LeagueSeasonModel)):
        payload = row.payload or {}
        lid = str(payload.get("provider_league_id") or "").strip()
        if lid:
            mapping.setdefault(lid, row.competition_id)
    return mapping


def _persist_capture(
    session: Session, response, *, fixture_id: str | None, competition_id: str
) -> str:
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
        quota_values={
            k: v
            for k, v in response.headers.items()
            if k.lower().startswith(("x-ratelimit", "x-requests"))
        },
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
        sha256=payload_hash,
        endpoint=response.endpoint,
        captured_at=captured_at,
        payload=response.payload,
    )
    return str(capture["capture_id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-calls", type=int, default=None)
    parser.add_argument("--burst", type=int, default=DEFAULT_BURST)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--checkpoint", default=None)
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
        league_to_comp = _league_mapping(session)

    rows = _load_rows(args.csv)
    if args.limit is not None:
        rows = rows[: args.limit]

    calls = 0
    captured = 0
    rows_written = 0
    failed = 0
    skipped = 0
    window_start = time.monotonic()
    window_calls = 0
    results: list[dict] = []

    for row in rows:
        if args.max_calls is not None and calls >= args.max_calls:
            break
        fixture_id = row["fixture_id"]
        if fixture_id in done:
            skipped += 1
            continue
        home_pid = row["home_team_id"]
        away_pid = row["away_team_id"]
        if args.dry_run:
            calls += 1
            results.append({"fixture_id": fixture_id, "status": "dry_run"})
            continue
        # 突发限速：窗口内达到 burst 则等待窗口重置。
        if window_calls >= args.burst:
            elapsed = time.monotonic() - window_start
            if elapsed < BURST_WINDOW_SECONDS:
                time.sleep(BURST_WINDOW_SECONDS - elapsed)
            window_start = time.monotonic()
            window_calls = 0
        calls += 1
        window_calls += 1
        response = client.request_live("h2h", {"h2h": f"{home_pid}-{away_pid}", "last": "10"})
        if response.status_code >= 400:
            failed += 1
            results.append({"fixture_id": fixture_id, "status": f"HTTP_{response.status_code}"})
            continue
        with Session(engine) as session:
            capture_id = _persist_capture(
                session,
                response,
                fixture_id=fixture_id,
                competition_id=row.get("league") or "",
            )
            items = {
                provider_fixture_id_from_item(item): item
                for item in finished_fixture_items(response.payload, now=_now())
                if provider_fixture_id_from_item(item)
            }
            inserted = 0
            for item in items.values():
                lg = item.get("league") or {}
                lid = str(lg.get("id") or "").strip()
                season = str(lg.get("season") or "").strip()
                competition_id = league_to_comp.get(lid, row.get("league") or "")
                for payload in history_rows_from_fixture(
                    item,
                    competition_id=competition_id,
                    season=season,
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
                    except IntegrityError:
                        # 已存在（幂等键 history_id）：不覆盖、不报错（含 T1 残留的跨批重叠）。
                        pass
            session.commit()
            rows_written += inserted
        captured += 1
        results.append({"fixture_id": fixture_id, "status": "ok", "rows": inserted})
        if args.checkpoint:
            with open(args.checkpoint, "a") as f:
                f.write(f"{fixture_id}\n")

    summary = {
        "fixtures_considered": len(rows),
        "provider_calls": calls,
        "captured": captured,
        "rows_written": rows_written,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
