"""FootyStats 影子试点的旁路表（指令书 I 任务 A）。

设计边界（硬约束）：

* 只新增旁路表，**不改写任何生产表、不接入任何生产链**；
* 生产 fixture / team 身份仍然只有一份（``matchday_fixture_identities``、
  ``teams``、``canonical_teams``）。本模块的 ``fs_*`` 行承载的是
  **Provider 侧 id 与交叉映射证据**，不是第二套 canonical identity：
  ``fs_fixture.matched_fixture_id`` 指向生产 ``fixture_id``，
  未命中时为空而不是另造一个。
* 原始 payload 按 canonical sha256 去重留档；每次调用另记 ``fs_request_log``
  （去重会把重复 payload 折叠，若不单独记调用次数，配额计账会漏计）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import uuid_str

SHADOW_CONTRACT_VERSION = "w2.footystats_shadow.v1"

# 映射状态：MAPPED 才可作为下游对齐依据；AMBIGUOUS/UNMAPPED 必须人工复核后才改。
MAPPING_MAPPED = "MAPPED"
MAPPING_AMBIGUOUS = "AMBIGUOUS"
MAPPING_UNMAPPED = "UNMAPPED"


class FsRequestLogModel(Base):
    """每一次 Provider 调用的账（配额实测口径的唯一来源）。

    去重后的 ``fs_raw_payload`` 会折叠重复响应，因此调用次数不能从它反推。
    """

    __tablename__ = "fs_request_log"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_fs_request_log_identity"),
        Index("ix_fs_request_log_requested_at", "requested_at"),
        Index("ix_fs_request_log_endpoint", "endpoint", "requested_at"),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    request_params: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    request_limit: Mapped[int | None] = mapped_column(Integer)
    request_remaining: Mapped[int | None] = mapped_column(Integer)
    payload_sha256: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    contract_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=SHADOW_CONTRACT_VERSION
    )


class FsRawPayloadModel(Base):
    """按 canonical sha256 去重的原始响应体。"""

    __tablename__ = "fs_raw_payload"
    __table_args__ = (Index("ix_fs_raw_payload_endpoint", "endpoint", "first_seen_at"),)

    payload_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FsLeagueSeasonModel(Base):
    """FootyStats league-season 身份与其到 W2 competition_id 的映射。

    ``fs_season_id`` 是 FootyStats 的赛季粒度主键（league-list 的
    ``season[].id``），也是 ``league-matches`` 的入参 ``league_id``。
    """

    __tablename__ = "fs_league_season"
    __table_args__ = (
        Index("ix_fs_league_season_competition", "competition_id"),
        # 自然键必须含国家：同名联赛跨国家真实存在（Germany 与 Austria 的
        # "Bundesliga" 在同一赛季年里同时存在），只用 (名字, 年) 会误判为重复。
        UniqueConstraint(
            "fs_country",
            "fs_league_name",
            "season_year",
            name="uq_fs_league_season_natural",
        ),
    )

    fs_season_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fs_league_name: Mapped[str] = mapped_column(String(128), nullable=False)
    fs_name: Mapped[str] = mapped_column(String(160), nullable=False)
    fs_country: Mapped[str] = mapped_column(String(96), nullable=False)
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)
    competition_id: Mapped[str | None] = mapped_column(String(128))
    mapping_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=MAPPING_UNMAPPED
    )
    mapping_method: Mapped[str | None] = mapped_column(String(64))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FsTeamModel(Base):
    """FootyStats 球队身份 + 名称归一化结果。

    消歧范围是 ``(fs_season_id, normalized_name)``：跨联赛的同名球队
    （如各级联赛共有的 "Reserves"）不能互相覆盖。
    """

    __tablename__ = "fs_team"
    __table_args__ = (
        UniqueConstraint(
            "fs_season_id", "normalized_name", name="uq_fs_team_season_normalized"
        ),
        Index("ix_fs_team_scope", "fs_season_id", "fs_team_id"),
    )

    fs_season_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fs_team_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fs_team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False)
    competition_id: Mapped[str | None] = mapped_column(String(128))
    #: 跨源球队对齐的**唯一权威结论**：本行球队对应哪个 api_football 球队 id。
    #: fixture 层靠这张表按 id 精确对齐，而不是每场都拿队名去猜——
    #: 队名不可靠是系统性的（简称/全称/缩写），一个球队只需裁决一次。
    matched_provider_team_id: Mapped[str | None] = mapped_column(String(64))
    match_method: Mapped[str | None] = mapped_column(String(64))
    match_confidence: Mapped[str | None] = mapped_column(String(32))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FsFixtureModel(Base):
    """FootyStats 赛程/赛果行 + 交叉映射 + xG 发布时滞锚点。

    ``matched_fixture_id`` 命中时必须是生产 ``matchday_fixture_identities.fixture_id``
    的既有取值；本表不产生新的 fixture 身份。
    """

    __tablename__ = "fs_fixture"
    __table_args__ = (
        Index("ix_fs_fixture_season_kickoff", "fs_season_id", "kickoff_utc"),
        Index("ix_fs_fixture_competition_kickoff", "competition_id", "kickoff_utc"),
        Index("ix_fs_fixture_matched", "matched_fixture_id"),
    )

    fs_match_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fs_season_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    competition_id: Mapped[str | None] = mapped_column(String(128))
    kickoff_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    home_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    away_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    home_team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    away_team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    #: xG 只在 status=='complete' 时才可能是有意义的观测。
    #: 未完赛的行各自带 ``team_a_xg = 0``（占位，不是 null），
    #: 若按「非空即有效」统计会把未开赛比赛算成 100% 覆盖。
    has_full_xg: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 顶层赔率拆成两个可独立复核的口径，而不是一个「有没有赔率」的合成布尔：
    #: ``odds_ft_1/x/2`` 三个同时非空才算 1X2 齐；``odds_ft_over25`` 单独算大小球。
    has_ft_result_odds: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_ou25_odds: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: ``odds_comparison`` 只出现在 ``match`` 详情端点：``league-matches`` /
    #: ``todays-matches`` 的响应里根本没有这个键。所以 NULL 表示「该来源端点
    #: 不提供此字段」，False 表示「提供了但为空」——两者不能合并成同一个值。
    has_odds_comparison: Mapped[bool | None] = mapped_column(Boolean)
    #: ``odds_comparison`` 的庄家矩阵里是否出现 Pinnacle（口径同名匹配）。
    #: 同样只有 ``match`` 详情端点可判，NULL = 未观测。
    has_pinnacle_comparison: Mapped[bool | None] = mapped_column(Boolean)
    odds_source_endpoint: Mapped[str | None] = mapped_column(String(64))
    # xG 发布时滞：完赛首次被观察到 → 两队 xG 首次同时非空。
    ft_first_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    xg_first_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    matched_fixture_id: Mapped[str | None] = mapped_column(String(128))
    match_method: Mapped[str | None] = mapped_column(String(64))
    match_confidence: Mapped[str | None] = mapped_column(String(32))
    # fixture 级去重/变更检测：本行自身业务内容的 canonical sha256。
    fixture_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # 来源证据：本行是从哪个原始响应体推导出来的。
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
