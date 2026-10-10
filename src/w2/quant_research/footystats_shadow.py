"""FootyStats 影子采集与报告（指令书 I 任务 A.1/A.3/A.4）。

三个必须说清的口径陷阱，全部由实测响应得出，不是推测：

1. **``odds_comparison`` 只存在于 ``match`` 详情端点**。``league-matches`` 与
   ``todays-matches`` 的响应里连这个键都没有（1.2 MB 响应内 0 命中）。
   所以「odds_comparison 非空率」只能由详情端点测量；在别的端点上它既不是
   0% 也不是 100%，而是**未观测**，数据库里存 NULL 而不是 False。
2. **未开赛比赛的 xG 是 0，不是 null**。直接在 ``league-matches`` 上按
   「非空即有效」统计，会把未开赛比赛算成 100% xG 覆盖。因此
   ``has_full_xg`` 强制要求 ``status == 'complete'``。
3. **FootyStats 没有亚盘**。``odds_comparison`` 的 13 个市场里只有
   1X2 / 大小球 / BTTS / 让球零封 / 角球，无 Asian Handicap、无让球线。
   这与「AH 主源仍走 API-Football 逐场 Pinnacle」的裁决一致。

xG 发布时滞的口径：我们只能观测到「Provider 何时已经发布了 xG」，观测精度
受轮询间隔限制。``xg_first_observed_at - ft_first_observed_at`` 是时滞的**上界
估计**，报告里同时给出轮询间隔，避免把观测精度当成 Provider 的真实延迟。
"""
from __future__ import annotations

import json
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from w2.quant_research import footystats_identity as identity
from w2.quant_research.footystats_client import FootyStatsClient
from w2.quant_research.footystats_shadow_models import (
    MAPPING_MAPPED,
    FsFixtureModel,
    FsLeagueSeasonModel,
    FsRawPayloadModel,
    FsTeamModel,
)

#: 抽取后的业务字段：upsert 与 ``fixture_sha256`` 用**同一份**取值，
#: 否则哈希覆盖的就不是真正落库的内容。
FIXTURE_BUSINESS_FIELDS = (
    "fs_match_id",
    "fs_season_id",
    "kickoff_utc",
    "status",
    "home_team_id",
    "away_team_id",
    "home_team_name",
    "away_team_name",
    "home_goals",
    "away_goals",
    "has_full_xg",
    "has_ft_result_odds",
    "has_ou25_odds",
)

_TOP_LEVEL_FT_RESULT = ("odds_ft_1", "odds_ft_x", "odds_ft_2")

#: 实测已知状态。**只有 ``complete`` 算完赛**，其余一律不算——这是 fail-closed
#: 的方向：把未知状态当成「未完赛」只会保守地少算覆盖率，不会假报覆盖。
#: 因此这里不做硬校验（硬校验会在 Provider 新增状态时直接掐断采集），
#: 而是把未知状态作为 blocker 显式留痕，让人看见。
KNOWN_FIXTURE_STATUSES = frozenset({"complete", "incomplete", "suspended"})

#: 映射抽检的确定性种子：同一份数据、同一个种子 ⇒ 同一批 100 场，
#: 验收方可以原样复现而不是"再看一遍实施方的截图"。
MAPPING_SAMPLE_SEED = 20261010
MAPPING_SAMPLE_SIZE = 100
MAPPING_PASS_THRESHOLD = 0.99


def _present(value: Any) -> bool:
    return value is not None and value != ""


def _int_or_none(value: Any) -> int | None:
    if not _present(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pinnacle_in(odds_comparison: Any) -> bool:
    if not isinstance(odds_comparison, dict) or not odds_comparison:
        return False
    for lines in odds_comparison.values():
        if not isinstance(lines, dict):
            continue
        for bookmakers in lines.values():
            if isinstance(bookmakers, dict) and any(
                str(name).strip().casefold() == "pinnacle" for name in bookmakers
            ):
                return True
    return False


def extract_fixture_fields(row: dict[str, Any], *, observed_at: datetime) -> dict[str, Any] | None:
    """把一条 FootyStats 比赛行抽成业务字段；关键身份缺失时返回 None（拒绝写入）。"""
    match_id = _int_or_none(row.get("id"))
    season_id = _int_or_none(row.get("competition_id"))
    home_id = _int_or_none(row.get("homeID"))
    away_id = _int_or_none(row.get("awayID"))
    raw_date = row.get("date_unix")
    status = str(row.get("status") or "")
    if match_id is None or season_id is None or home_id is None or away_id is None:
        return None
    if not status or not _present(raw_date):
        return None
    kickoff = datetime.fromtimestamp(float(raw_date), tz=UTC)
    complete = status == "complete"
    home_xg = _int_or_none(row.get("team_a_xg")) if complete else None
    away_xg = _int_or_none(row.get("team_b_xg")) if complete else None
    # 占位 0 的识别：未完赛一律 None；完赛但 xG 恒为 0 的行仍按 0 记录，
    # 因为它确实可能是一场 0 xG 的比赛，不做二次猜测。
    has_full_xg = complete and home_xg is not None and away_xg is not None
    return {
        "fs_match_id": match_id,
        "fs_season_id": season_id,
        "kickoff_utc": kickoff,
        "status": status,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team_name": str(row.get("home_name") or ""),
        "away_team_name": str(row.get("away_name") or ""),
        # 未完赛的 0 是占位，不是比分。
        "home_goals": _int_or_none(row.get("homeGoalCount")) if complete else None,
        "away_goals": _int_or_none(row.get("awayGoalCount")) if complete else None,
        "has_full_xg": has_full_xg,
        "has_ft_result_odds": all(_present(row.get(name)) for name in _TOP_LEVEL_FT_RESULT),
        "has_ou25_odds": _present(row.get("odds_ft_over25")),
    }


@dataclass
class SyncResult:
    endpoint: str
    fixtures_seen: int = 0
    fixtures_written: int = 0
    fixtures_rejected: int = 0
    teams_written: int = 0
    teams_conflicted: list[str] = field(default_factory=list)
    matched: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    season_unmapped: int = 0
    blockers: list[str] = field(default_factory=list)


class FootyStatsShadowCollector:
    """把 FootyStats 响应落到 ``fs_*`` 旁路表，并同时完成 fixture 交叉映射。"""

    def __init__(
        self,
        engine: Engine,
        client: FootyStatsClient,
        *,
        now: Callable[[], datetime] | None = None,
        fixture_index: identity.FixtureIndex | None = None,
    ) -> None:
        self._engine = engine
        self._client = client
        self._now = now or (lambda: datetime.now(UTC))
        self._fixture_index = fixture_index
        self._crosswalk: identity.TeamCrosswalk = {}

    # ── league 层 ───────────────────────────────────────────────────────────
    def sync_league_seasons(self) -> int:
        """把 league-list 中**被映射到**的赛季写进 ``fs_league_season``。"""
        payload = self._client.request("league-list").payload
        league_map = identity.load_league_map()
        wanted = {mapping.fs_season_id: mapping for mapping in league_map.values()}
        now = self._now()
        written = 0
        with Session(self._engine) as session, session.begin():
            for row in payload.get("data") or []:
                if not isinstance(row, dict):
                    continue
                for season in row.get("season") or []:
                    if not isinstance(season, dict):
                        continue
                    season_id = _int_or_none(season.get("id"))
                    mapping = wanted.get(season_id) if season_id is not None else None
                    if mapping is None:
                        continue
                    existing = session.get(FsLeagueSeasonModel, season_id)
                    if existing is None:
                        session.add(
                            FsLeagueSeasonModel(
                                fs_season_id=season_id,
                                fs_league_name=str(row.get("league_name") or ""),
                                fs_name=str(row.get("name") or ""),
                                fs_country=str(row.get("country") or ""),
                                season_year=_int_or_none(season.get("year")) or 0,
                                competition_id=mapping.competition_id,
                                mapping_status=MAPPING_MAPPED,
                                mapping_method="REVIEWED_LEAGUE_MAP",
                                first_seen_at=now,
                                last_seen_at=now,
                            )
                        )
                    else:
                        existing.last_seen_at = now
                    written += 1
        return written

    def league_scope(self) -> dict[int, str]:
        """``fs_season_id -> competition_id``，只含已映射的赛季。"""
        return {
            mapping.fs_season_id: mapping.competition_id
            for mapping in identity.load_league_map().values()
        }

    # ── fixture 层 ──────────────────────────────────────────────────────────
    def sync_league_matches(self, season_ids: Sequence[int]) -> list[SyncResult]:
        scope = self.league_scope()
        results = []
        for season_id in season_ids:
            rows: list[dict[str, Any]] = []
            blockers: list[str] = []
            digest: str | None = None
            page = 1
            while True:
                params = {"league_id": str(season_id), "season": "2026"}
                if page > 1:
                    params["p"] = str(page)
                response = self._client.request("league-matches", params)
                pager = response.payload.get("pager") or {}
                returned_page = _int_or_none(pager.get("current_page"))
                if page > 1 and returned_page != page:
                    # 分页参数不被识别时**不能**把第一页当成全量：
                    # 宁可显式留 blocker，也不静默截断。
                    blockers.append(
                        f"PAGINATION_NOT_ADVANCING:season={season_id}:wanted={page}:got={returned_page}"
                    )
                    break
                rows.extend(response.rows)
                digest = response.payload_sha256
                max_page = _int_or_none((response.payload.get("pager") or {}).get("max_page")) or 1
                if page >= max_page:
                    break
                page += 1
            results.append(
                self._write_response(
                    endpoint="league-matches",
                    rows=rows,
                    competition_id=scope.get(season_id),
                    payload_sha256=digest,
                    blockers=blockers,
                )
            )
        return results

    def sync_todays_matches(self, day: date) -> SyncResult:
        response = self._client.request("todays-matches", {"date": day.isoformat()})
        return self._write_response(
            endpoint="todays-matches",
            rows=response.rows,
            competition_id=None,
            payload_sha256=response.payload_sha256,
        )

    def sync_match_details(self, match_ids: Sequence[int]) -> list[SyncResult]:
        results = []
        for match_id in match_ids:
            response = self._client.request("match", {"match_id": str(match_id)})
            data = response.payload.get("data")
            rows = [data] if isinstance(data, dict) else []
            results.append(
                self._write_response(
                    endpoint="match",
                    rows=rows,
                    competition_id=None,
                    payload_sha256=response.payload_sha256,
                    odds_comparison_observed=True,
                )
            )
        return results

    def replay_raw_payloads(self) -> list[SyncResult]:
        """从已留档的原始响应重建 ``fs_team`` / ``fs_fixture``，**零 Provider 调用**。

        ``fs_raw_payload`` 是取证材料，解析规则却会随实现演进。没有重放路径，
        每次改解析或改映射都要重新烧配额，且「同一批原始数据重算一遍」变成
        不可复现。重放不重算 ``fixture_sha256`` 之外的任何结论性字段——
        映射由后续的交叉表 + remap 重新决定。
        """
        results: list[SyncResult] = []
        with Session(self._engine) as session:
            payloads = [
                (row.payload_sha256, row.endpoint, row.body)
                for row in session.scalars(
                    select(FsRawPayloadModel).order_by(FsRawPayloadModel.first_seen_at)
                )
            ]
        for digest, endpoint, body in payloads:
            try:
                document = json.loads(body)
            except ValueError:
                continue
            data = document.get("data") if isinstance(document, dict) else None
            if isinstance(data, dict):
                rows = [data]
            elif isinstance(data, list):
                rows = [row for row in data if isinstance(row, dict)]
            else:
                continue
            results.append(
                self._write_response(
                    endpoint=endpoint,
                    rows=rows,
                    competition_id=None,
                    payload_sha256=digest,
                    odds_comparison_observed=endpoint == "match",
                )
            )
        return results

    def resolve_team_crosswalk(self) -> dict[str, Any]:
        """建立/刷新球队层交叉表，并把结论写回 ``fs_team``。

        fixture 层依赖它按 provider team id 精确对齐，所以必须在 remap 之前跑。
        """
        season_by_competition = {
            mapping.competition_id: mapping.fs_season_id
            for mapping in identity.load_league_map().values()
        }
        with Session(self._engine) as session:
            fs_refs = [
                identity.FsTeamRef(
                    fs_season_id=row.fs_season_id,
                    fs_team_id=row.fs_team_id,
                    name=row.fs_team_name,
                )
                for row in session.scalars(select(FsTeamModel))
            ]
        production_teams = identity.load_production_teams(self._engine)
        mappings = identity.build_team_crosswalk(
            production_teams, fs_refs, season_by_competition=season_by_competition
        )
        crosswalk = identity.crosswalk_lookup(mappings)
        resolved = {
            (mapping.competition_id, mapping.fs_team_id): mapping for mapping in mappings
        }
        with Session(self._engine) as session, session.begin():
            for row in session.scalars(select(FsTeamModel)):
                mapping = resolved.get((str(row.competition_id or ""), row.fs_team_id))
                row.matched_provider_team_id = mapping.provider_team_id if mapping else None
                row.match_method = mapping.method if mapping else None
                row.match_confidence = mapping.confidence if mapping else None
        self._crosswalk = crosswalk
        production_team_total = sum(len(teams) for teams in production_teams.values())
        resolved_provider_ids = {mapping.provider_team_id for mapping in mappings}
        resolved_fs_keys = {
            (mapping.competition_id, mapping.fs_season_id, mapping.fs_team_id)
            for mapping in mappings
        }
        competition_by_season = {
            season_id: competition_id
            for competition_id, season_id in season_by_competition.items()
        }
        fs_by_competition: dict[str, list[identity.FsTeamRef]] = {}
        for ref in fs_refs:
            competition_id = competition_by_season.get(ref.fs_season_id)
            if competition_id is not None:
                fs_by_competition.setdefault(competition_id, []).append(ref)
        per_competition: dict[str, dict[str, Any]] = {}
        for competition_id, teams in sorted(production_teams.items()):
            refs = fs_by_competition.get(competition_id, [])
            unresolved_production = sorted(
                team.name for team in teams if team.provider_team_id not in resolved_provider_ids
            )
            unresolved_fs = sorted(
                ref.name
                for ref in refs
                if (competition_id, ref.fs_season_id, ref.fs_team_id) not in resolved_fs_keys
            )
            per_competition[competition_id] = {
                "production_teams": len(teams),
                "footystats_teams": len(refs),
                # 两侧队数是否相等 + 残余是否 1:1，是「强制配对」判据的两个前提。
                # 报出来才能发现「用别名表掩盖了真实的名单缺口」。
                "counts_equal": len(teams) == len(refs),
                "unresolved_production": unresolved_production,
                "unresolved_footystats": unresolved_fs,
                "residual_forced_pairing": (
                    len(unresolved_production) == 1 and len(unresolved_fs) == 1
                ),
            }
        return {
            "production_teams": production_team_total,
            "fs_teams": len(fs_refs),
            "crosswalk_resolved": len(crosswalk),
            "team_resolution_rate": (
                len(crosswalk) / production_team_total if production_team_total else 0.0
            ),
            "method_breakdown": _counts(mapping.method for mapping in mappings),
            "per_competition": per_competition,
        }

    def remap_existing(self) -> SyncResult:
        """对已落库的 fs_fixture 重新跑一遍映射，**不发起任何 Provider 调用**。

        映射规则是会迭代的（队名口径每改一次都要重跑），而原始 payload 已经
        留档。没有这条路径，每改一次规则就要重烧一遍配额，也会让「同一批数据
        换个规则重算」这件事变得不可复现。
        """
        result = SyncResult(endpoint="remap")
        now = self._now()
        with Session(self._engine) as session, session.begin():
            records = list(
                session.scalars(
                    select(FsFixtureModel).where(FsFixtureModel.competition_id.is_not(None))
                )
            )
            for record in records:
                self._apply_match(record, now, result)
        return result

    def resolve_mapping_collisions(self) -> list[str]:
        """同一个生产 fixture 被多条 FootyStats 行认领时，**全部撤回**为未映射。

        队名规则是放宽过的（词首前缀 / 首字母），放宽必然带来误配风险。唯一性
        约束是它的对偶：一条生产 fixture 只能被一场 FootyStats 比赛认领，
        冲突时不是「留第一条」，而是两条都不认——宁可不映射，不可错映射。
        """
        collisions: list[str] = []
        with Session(self._engine) as session, session.begin():
            duplicated = session.execute(
                select(FsFixtureModel.matched_fixture_id, func.count())
                .where(FsFixtureModel.matched_fixture_id.is_not(None))
                .group_by(FsFixtureModel.matched_fixture_id)
                .having(func.count() > 1)
            ).all()
            for fixture_id, count in duplicated:
                claimants = list(
                    session.scalars(
                        select(FsFixtureModel).where(
                            FsFixtureModel.matched_fixture_id == fixture_id
                        )
                    )
                )
                ids = sorted(row.fs_match_id for row in claimants)
                collisions.append(
                    f"MAPPING_COLLISION:fixture={fixture_id}:count={count}:fs_match_ids={ids}"
                )
                for row in claimants:
                    row.matched_fixture_id = None
                    row.match_method = identity.METHOD_NONE
                    row.match_confidence = identity.CONFIDENCE_AMBIGUOUS
        return collisions

    # ── 落库 ────────────────────────────────────────────────────────────────
    def _write_response(
        self,
        *,
        endpoint: str,
        rows: Sequence[dict[str, Any]],
        competition_id: str | None,
        payload_sha256: str | None,
        odds_comparison_observed: bool = False,
        blockers: Sequence[str] = (),
    ) -> SyncResult:
        now = self._now()
        result = SyncResult(endpoint=endpoint, blockers=list(blockers))
        league_scope = self.league_scope()
        with Session(self._engine) as session, session.begin():
            for row in rows:
                result.fixtures_seen += 1
                fields = extract_fixture_fields(row, observed_at=now)
                if fields is None:
                    result.fixtures_rejected += 1
                    continue
                if fields["status"] not in KNOWN_FIXTURE_STATUSES:
                    marker = f"UNKNOWN_FIXTURE_STATUS:{fields['status']}"
                    if marker not in result.blockers:
                        result.blockers.append(marker)
                resolved_competition = competition_id or league_scope.get(fields["fs_season_id"])
                if resolved_competition is None:
                    result.season_unmapped += 1
                result.teams_written += self._upsert_teams(
                    session, row, fields["fs_season_id"], resolved_competition, now, result
                )
                self._upsert_fixture(
                    session,
                    fields=fields,
                    competition_id=resolved_competition,
                    now=now,
                    payload_sha256=payload_sha256,
                    endpoint=endpoint,
                    result=result,
                    odds_comparison=row.get("odds_comparison"),
                    odds_comparison_observed=odds_comparison_observed,
                )
                result.fixtures_written += 1
        return result

    def _upsert_teams(
        self,
        session: Session,
        row: dict[str, Any],
        season_id: int,
        competition_id: str | None,
        now: datetime,
        result: SyncResult,
    ) -> int:
        pairs = (
            (_int_or_none(row.get("homeID")), str(row.get("home_name") or "")),
            (_int_or_none(row.get("awayID")), str(row.get("away_name") or "")),
        )
        written = 0
        for team_id, name in pairs:
            if team_id is None or not name:
                continue
            normalized = identity.normalize_team_name(name)
            if not normalized:
                result.teams_conflicted.append(f"EMPTY_NORMALIZED_NAME:{season_id}:{team_id}")
                continue
            # 同赛季同名消歧：不同 fs_team_id 归一化撞名时不猜，留冲突由人裁决。
            # 更新路径也必须查：归一化规则一收紧，原本不同的两个名字可能
            # 塌到同一个 normalized_name 上，那时改列会直接撞唯一约束。
            clash = session.execute(
                select(FsTeamModel.fs_team_id).where(
                    FsTeamModel.fs_season_id == season_id,
                    FsTeamModel.normalized_name == normalized,
                    FsTeamModel.fs_team_id != team_id,
                )
            ).scalar_one_or_none()
            if clash is not None:
                result.teams_conflicted.append(
                    f"SEASON_NAME_COLLISION:{season_id}:{normalized}:{clash}!={team_id}"
                )
                existing = session.get(
                    FsTeamModel, {"fs_season_id": season_id, "fs_team_id": team_id}
                )
                if existing is not None:
                    existing.fs_team_name = name
                    existing.last_seen_at = now
                continue
            existing = session.get(FsTeamModel, {"fs_season_id": season_id, "fs_team_id": team_id})
            if existing is not None:
                existing.fs_team_name = name
                existing.normalized_name = normalized
                existing.last_seen_at = now
                written += 1
                continue
            session.add(
                FsTeamModel(
                    fs_season_id=season_id,
                    fs_team_id=team_id,
                    fs_team_name=name,
                    normalized_name=normalized,
                    competition_id=competition_id,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            written += 1
        return written

    def _upsert_fixture(
        self,
        session: Session,
        *,
        fields: dict[str, Any],
        competition_id: str | None,
        now: datetime,
        payload_sha256: str | None,
        endpoint: str,
        result: SyncResult,
        odds_comparison: Any = None,
        odds_comparison_observed: bool = False,
    ) -> None:
        digest = identity.fixture_sha256(
            {name: str(fields[name]) for name in FIXTURE_BUSINESS_FIELDS}
        )
        # ``odds_comparison_observed`` 与 ``odds_comparison`` 是两件事：
        # 前者说「这次响应来自能暴露比较赔率的端点」，后者是那个字段的值。
        # 混在一起会把「调了 match 但该字段缺失」记成「从没调过 match」。
        has_comparison = (
            odds_comparison is not None if odds_comparison_observed else None
        )
        has_pinnacle = (
            _pinnacle_in(odds_comparison)
            if odds_comparison_observed and odds_comparison is not None
            else (False if odds_comparison_observed else None)
        )
        record = session.get(FsFixtureModel, fields["fs_match_id"])
        if record is None:
            record = FsFixtureModel(
                **fields,
                competition_id=competition_id,
                # 完赛锚点只在该场**首次被观察到为完赛**时落一次。
                ft_first_observed_at=now if fields["status"] == "complete" else None,
                xg_first_observed_at=now if fields["has_full_xg"] else None,
                fixture_sha256=digest,
                payload_sha256=payload_sha256,
                has_odds_comparison=has_comparison,
                has_pinnacle_comparison=has_pinnacle,
                odds_source_endpoint=endpoint if odds_comparison_observed else None,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(record)
        else:
            for name in FIXTURE_BUSINESS_FIELDS:
                setattr(record, name, fields[name])
            if competition_id is not None:
                record.competition_id = competition_id
            if payload_sha256 is not None:
                record.payload_sha256 = payload_sha256
            record.fixture_sha256 = digest
            record.last_seen_at = now
            if record.ft_first_observed_at is None and fields["status"] == "complete":
                record.ft_first_observed_at = now
            if record.xg_first_observed_at is None and fields["has_full_xg"]:
                record.xg_first_observed_at = now
            # 比较赔率的可观测性**只升不降**。`league-matches` / `todays-matches`
            # 的响应里根本没有 `odds_comparison` 这个键，如果允许它们覆盖，
            # 一场先抓过 match 详情的比赛会在下一次整季/当日同步时被"降级"回
            # 「观测不到比较赔率」——实测中 20 场这样被抓没的。这不是精度问题，
            # 是把已经拿到的证据抹掉。
            if odds_comparison_observed and record.odds_source_endpoint != "match":
                record.has_odds_comparison = has_comparison
                record.has_pinnacle_comparison = has_pinnacle
                record.odds_source_endpoint = endpoint
        if competition_id is not None:
            self._apply_match(record, now, result)

    def _apply_match(self, record: FsFixtureModel, now: datetime, result: SyncResult) -> None:
        match = identity.match_fixture(
            self._fixture_index or {},
            self._crosswalk,
            competition_id=record.competition_id,
            kickoff_utc=record.kickoff_utc,
            home_team_id=record.home_team_id,
            away_team_id=record.away_team_id,
            home_goals=record.home_goals,
            away_goals=record.away_goals,
        )
        if match.matched_fixture_id is None and match.candidate_count > 1:
            result.ambiguous += 1
        elif match.matched_fixture_id is None:
            result.unmatched += 1
        else:
            result.matched += 1
        record.matched_fixture_id = match.matched_fixture_id
        record.match_method = match.method
        record.match_confidence = match.confidence


# ── 报告 ─────────────────────────────────────────────────────────────────────
class FootyStatsShadowReporter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def mapping_report(
        self,
        *,
        sample_size: int = MAPPING_SAMPLE_SIZE,
        seed: int = MAPPING_SAMPLE_SEED,
    ) -> dict[str, Any]:
        """映射准确率报告。

        **分母是生产 fixture，不是 FootyStats 整季。** FootyStats 的
        ``league-matches`` 返回整季（含数月前已完赛、生产从未采集过的比赛），
        拿它当分母算出的「命中率」量的是「生产覆盖了多少整季」，不是
        「映射准不准」。真正的可判据总体是：生产身份表里存在于已映射联赛的
        fixture，FootyStats 能否把它找出来。

        另附**比分交叉校验**：命中且双方都有比分时，比分是否一致。队名规则
        （词首前缀 / 首字母）是放宽过的，比分一致是独立于队名规则的第二个
        证据；不一致的场次逐条进报告，由人裁决。
        """
        with Session(self._engine) as session:
            fs_rows = list(
                session.scalars(
                    select(FsFixtureModel).where(FsFixtureModel.competition_id.is_not(None))
                )
            )
            production = [
                dict(record)
                for record in session.execute(
                    text(
                        """
                        SELECT fixture_id,
                               competition_id,
                               kickoff_utc,
                               home_provider_team_id,
                               away_provider_team_id,
                               payload -> 'teams' -> 'home' ->> 'name' AS home_name,
                               payload -> 'teams' -> 'away' ->> 'name' AS away_name,
                               payload -> 'goals' ->> 'home' AS home_goals,
                               payload -> 'goals' ->> 'away' AS away_goals,
                               fixture_status
                          FROM matchday_fixture_identities
                        """
                    )
                ).mappings()
            ]
        matched_by_production = {
            str(row.matched_fixture_id): row
            for row in fs_rows
            if row.matched_fixture_id is not None
        }
        in_scope_competitions = {str(row.competition_id) for row in fs_rows}
        reference = [
            row for row in production if str(row["competition_id"]) in in_scope_competitions
        ]
        reference.sort(key=lambda row: str(row["fixture_id"]))
        crosswalked = {
            (str(row.competition_id), str(row.matched_provider_team_id))
            for row in self._crosswalked_teams()
        }
        unmatched_reasons = [
            {
                "fixture_id": str(row["fixture_id"]),
                "competition_id": str(row["competition_id"]),
                "kickoff_utc": row["kickoff_utc"].astimezone(UTC).isoformat(),
                "production_status": row["fixture_status"],
                "production_home": row["home_name"],
                "production_away": row["away_name"],
                # 区分「映射没做到」与「FootyStats 根本没有这一场」：
                # 前者是我们的缺陷，后者是对侧覆盖/状态差异，责任不同。
                "reason": (
                    "TEAM_NOT_CROSSWALKED"
                    if (str(row["competition_id"]), str(row["home_provider_team_id"]))
                    not in crosswalked
                    or (str(row["competition_id"]), str(row["away_provider_team_id"]))
                    not in crosswalked
                    else row["fixture_status"] + "_NO_FOOTYSTATS_COUNTERPART"
                ),
            }
            for row in reference
            if str(row["fixture_id"]) not in matched_by_production
        ]

        # 固定种子的伪随机只用于"可复现地挑同一批抽检样本"，
        # 不用于任何安全目的：验收方用同一个种子能拿到同一批 100 场。
        rng = random.Random(seed)  # noqa: S311
        sample = rng.sample(reference, min(sample_size, len(reference))) if reference else []
        sample_rows = [
            self._sample_row(row, matched_by_production.get(str(row["fixture_id"])))
            for row in sorted(sample, key=lambda item: str(item["fixture_id"]))
        ]

        sampled = len(sample_rows)
        sample_matched = sum(1 for row in sample_rows if row["fs_match_id"] is not None)
        accuracy = (sample_matched / sampled) if sampled else 0.0
        agrees = sum(1 for row in sample_rows if row["score_verdict"] == "AGREES")
        verdicts = _counts(row["score_verdict"] for row in sample_rows)
        return {
            "contract": "w2.footystats_mapping_report.v3",
            "denominator": "PRODUCTION_FIXTURE_IDENTITIES_IN_MAPPED_COMPETITIONS",
            "sample_seed": seed,
            "sample_size": sample_size,
            "footystats_fixtures_in_scope": len(fs_rows),
            "footystats_fixtures_matched": len(matched_by_production),
            "production_reference_fixtures": len(reference),
            "production_fixtures_total": len(production),
            "production_competitions_not_in_scope": sorted(
                {str(row["competition_id"]) for row in production} - in_scope_competitions
            ),
            "production_recall": (
                len(matched_by_production) / len(reference) if reference else 0.0
            ),
            "unmatched_reason_breakdown": _counts(
                row["reason"] for row in unmatched_reasons
            ),
            "unmatched": unmatched_reasons,
            "sampled": sampled,
            "sampled_matched": sample_matched,
            "sampled_accuracy": accuracy,
            "pass_threshold": MAPPING_PASS_THRESHOLD,
            "pass": sampled > 0 and accuracy >= MAPPING_PASS_THRESHOLD,
            "sample_score_verdicts": verdicts,
            "sample_score_agree_rate": (agrees / sampled) if sampled else 0.0,
            "confidence_breakdown": _counts(row["match_confidence"] for row in sample_rows),
            "method_breakdown": _counts(row["match_method"] for row in sample_rows),
            "mismatches": [row for row in sample_rows if row["fs_match_id"] is None],
            "sample": sample_rows,
        }

    def _crosswalked_teams(self) -> list[Any]:
        with Session(self._engine) as session:
            return list(
                session.scalars(
                    select(FsTeamModel).where(
                        FsTeamModel.matched_provider_team_id.is_not(None)
                    )
                )
            )

    @staticmethod
    def _sample_row(
        production_row: dict[str, Any], fs_row: FsFixtureModel | None
    ) -> dict[str, Any]:
        production_goals = (
            _int_or_none(production_row["home_goals"]),
            _int_or_none(production_row["away_goals"]),
        )
        fs_goals = (
            (fs_row.home_goals, fs_row.away_goals) if fs_row is not None else (None, None)
        )
        if fs_row is None:
            verdict = "NOT_MATCHED"
        elif None in production_goals or None in fs_goals:
            verdict = "SCORE_UNKNOWN"
        elif production_goals == fs_goals:
            verdict = "AGREES"
        else:
            verdict = "DIFFERS"
        return {
            "fixture_id": str(production_row["fixture_id"]),
            "competition_id": str(production_row["competition_id"]),
            "kickoff_utc": production_row["kickoff_utc"].astimezone(UTC).isoformat(),
            "production_home": production_row["home_name"],
            "production_away": production_row["away_name"],
            "production_goals": list(production_goals),
            "production_status": production_row["fixture_status"],
            "fs_match_id": fs_row.fs_match_id if fs_row is not None else None,
            "footystats_home": fs_row.home_team_name if fs_row is not None else None,
            "footystats_away": fs_row.away_team_name if fs_row is not None else None,
            "footystats_goals": list(fs_goals),
            "match_method": fs_row.match_method if fs_row is not None else None,
            "match_confidence": fs_row.match_confidence if fs_row is not None else None,
            "score_verdict": verdict,
        }

    def coverage_report(self) -> list[dict[str, Any]]:
        """逐联赛覆盖：xG / 顶层 1X2 / 大小球 2.5 / odds_comparison / Pinnacle。"""
        with Session(self._engine) as session:
            rows = list(
                session.scalars(
                    select(FsFixtureModel).order_by(FsFixtureModel.competition_id)
                )
            )
        grouped: dict[str, list[FsFixtureModel]] = {}
        for row in rows:
            if row.competition_id:
                grouped.setdefault(row.competition_id, []).append(row)
        report = []
        for competition_id, items in sorted(grouped.items()):
            report.append(_coverage_row(competition_id, items))
        return report

    def profile_report(self) -> dict[str, Any]:
        """数据剖面：状态分布与规模，用于发现「Provider 新增了状态值」。"""
        with Session(self._engine) as session:
            status_rows = session.execute(
                select(FsFixtureModel.status, func.count()).group_by(FsFixtureModel.status)
            ).all()
            total = session.scalar(select(func.count()).select_from(FsFixtureModel)) or 0
            seasons = session.scalar(
                select(func.count(func.distinct(FsFixtureModel.fs_season_id)))
            )
            competitions = session.scalar(
                select(func.count(func.distinct(FsFixtureModel.competition_id)))
            )
        breakdown = {str(row[0]): int(row[1]) for row in status_rows}
        return {
            "contract": "w2.footystats_profile_report.v1",
            "fixtures": int(total),
            "distinct_seasons": int(seasons or 0),
            "distinct_competitions": int(competitions or 0),
            "status_breakdown": breakdown,
            "unknown_statuses": sorted(set(breakdown) - KNOWN_FIXTURE_STATUSES),
            "known_statuses": sorted(KNOWN_FIXTURE_STATUSES),
        }

    def xg_lag_report(self) -> dict[str, Any]:
        with Session(self._engine) as session:
            rows = list(
                session.scalars(
                    select(FsFixtureModel).where(FsFixtureModel.ft_first_observed_at.is_not(None))
                )
            )
            last_poll = session.scalar(select(func.max(FsFixtureModel.last_seen_at)))
        tracked = [
            row
            for row in rows
            if row.xg_first_observed_at is not None and row.ft_first_observed_at is not None
        ]
        lags = sorted(
            (row.xg_first_observed_at - row.ft_first_observed_at).total_seconds()
            for row in tracked
        )
        pending = [row.fs_match_id for row in rows if row.xg_first_observed_at is None]
        return {
            "contract": "w2.footystats_xg_lag_report.v1",
            "complete_observed": len(rows),
            "tracked_with_xg": len(lags),
            "p50_seconds": _percentile(lags, 0.50),
            "p90_seconds": _percentile(lags, 0.90),
            "min_seconds": lags[0] if lags else None,
            "max_seconds": lags[-1] if lags else None,
            "still_without_xg": pending[:20],
            "last_observed_at": last_poll.astimezone(UTC).isoformat() if last_poll else None,
            "resolution_caveat": (
                "时滞是「首次观测到完赛」到「首次观测到两队 xG 齐」的差，"
                "因此它是 Provider 真实发布延迟的**上界**，精度受轮询间隔限制；"
                "同一轮抓取里既完赛又有 xG 的场次其真实延迟不可分辨，记 0。"
            ),
        }


def _counts(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return counts


def _percentile(sorted_values: Sequence[float], quantile: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = quantile * (len(sorted_values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    fraction = position - lower
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * fraction


def _rate(numerator: int, denominator: int) -> float | None:
    return (numerator / denominator) if denominator else None


def _coverage_row(competition_id: str, items: Sequence[FsFixtureModel]) -> dict[str, Any]:
    complete = [row for row in items if row.status == "complete"]
    comparison_observed = [row for row in items if row.has_odds_comparison is not None]
    return {
        "competition_id": competition_id,
        "fixtures": len(items),
        "complete_fixtures": len(complete),
        "xg_non_null_on_complete": _rate(
            sum(1 for row in complete if row.has_full_xg), len(complete)
        ),
        "ft_result_odds_non_null": _rate(
            sum(1 for row in items if row.has_ft_result_odds), len(items)
        ),
        "ou25_odds_non_null": _rate(
            sum(1 for row in items if row.has_ou25_odds), len(items)
        ),
        "odds_comparison_observed": len(comparison_observed),
        "odds_comparison_non_null": _rate(
            sum(1 for row in comparison_observed if row.has_odds_comparison),
            len(comparison_observed),
        ),
        "pinnacle_in_comparison": _rate(
            sum(1 for row in comparison_observed if row.has_pinnacle_comparison),
            len(comparison_observed),
        ),
        "matched_fixtures": sum(1 for row in items if row.matched_fixture_id is not None),
        # 分母是 FootyStats 的**整季**，所以这个比率量的是「生产身份表覆盖了
        # 该赛季多少」，不是「映射准不准」——千万别当映射准确率读。
        # 映射准确率见 mapping_report（分母为生产 fixture，抽检 100 场）。
        "production_overlap_rate": _rate(
            sum(1 for row in items if row.matched_fixture_id is not None), len(items)
        ),
    }
