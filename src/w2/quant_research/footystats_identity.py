"""FootyStats 三层身份映射（指令书 I 任务 A.2）。

三层口径不同，不能互相替代：

* **league**：FootyStats 的 ``season.id`` ↔ W2 ``competition_id``。两边都没有
  可推导的公共键，所以这一层是**人工复核过的静态映射**
  （``config/quant/footystats_league_map.v1.json``），不是模糊匹配的产物。
* **team**：名称归一化只用于**缩小候选**，消歧范围是 ``fs_season_id``。
  归一化会把 "FC"/"CF" 这类法人后缀去掉，因此跨联赛同名是预期内的，
  同联赛同名才是需要人工裁决的冲突。
* **fixture**：``(competition_id, UTC 日期, 归一化主队, 归一化客队)`` 精确键，
  不中再放宽 ±1 天。比分只作**交叉校验**，不作为键——把比分当键会让
  「改了比分的那一场」从「已映射」变成「未映射」，把数据变更伪装成映射失败。

交叉校验结论写进 ``match_confidence``：比分一致=HIGH、来源无比分=UNKNOWN、
比分不一致=LOW。LOW 不静默丢弃，进报告由人裁决。
"""
from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from w2.domain.canonical_serialization import (
    CURRENT_SERIALIZER_VERSION,
    HashDomain,
    canonical_sha256,
)

HASH_DOMAIN = HashDomain.FUTURE_REFRESH_EVIDENCE
SERIALIZER_VERSION = str(CURRENT_SERIALIZER_VERSION)
FIXTURE_CONTRACT = "w2.footystats_fixture.v1"

LEAGUE_MAP_PATH = Path(__file__).resolve().parents[3] / "config/quant/footystats_league_map.v1.json"
TEAM_ALIAS_PATH = (
    Path(__file__).resolve().parents[3] / "config/quant/footystats_team_alias.v1.json"
)

METHOD_EXACT = "DATE_TEAM_KEY"
METHOD_WINDOW = "DATE_TEAM_KEY_WINDOW_1D"
METHOD_NONE = "UNMATCHED"

CONFIDENCE_SCORE_AGREES = "SCORE_AGREES"
CONFIDENCE_SCORE_UNKNOWN = "SCORE_UNKNOWN"
CONFIDENCE_SCORE_DIFFERS = "SCORE_DIFFERS"
CONFIDENCE_AMBIGUOUS = "AMBIGUOUS_MULTIPLE_CANDIDATES"

#: 俱乐部形式词。**首尾都剥**（"FC Copenhagen" 与 "Copenhagen" 必须能对齐），
#: 但不允许把名字剥成空——"AIK"、"IF" 在 Nordic 联赛里本身就是队名。
_LEGAL_FORM_TOKENS = frozenset(
    {
        "fc", "cf", "ac", "afc", "sc", "sv", "tsv", "vfb", "vfl", "bsc", "fsv",
        "as", "ss", "ssc", "us", "usc", "cs", "ca", "cd", "sd", "rc", "rcd",
        # 注意："aik" 不在表内——AIK 是瑞典球队**本身的队名**，把它当形式词剥掉
        # 会让 "AIK Stockholm" 变成 "stockholm"、"AIK" 变成回退的 "aik"，两边对不上。
        "if", "ff", "bk", "fk", "sk", "ik", "gif", "hk",
        "nk", "hnk", "kaa", "rsc", "scr", "agf", "ob", "spvgg", "gg",
        "club", "calcio", "futbol", "football", "sport", "sports", "sportif",
        "de", "do", "da", "del", "la", "el", "the", "of", "and", "und",
    }
)


def _strip_legal_forms(tokens: list[str]) -> list[str]:
    """丢弃俱乐部形式词与纯数字词（**任意位置**），但绝不把名字丢成空。

    两个来源的差别不只是首尾后缀，而是「夹在中间的功能词」：
    "Unión de Santa Fe" vs "Union Santa Fe"、"Grasshopper Club Zürich"。
    只剥首尾治不了这一类。

    纯数字词（"1."、"1899"、"05"、"98"）是成立年份，一方有一方没有
    （"1. FC Köln" vs "FC Köln"），留着会挡住对齐。

    "AIK"、"IF"、"FF" 在 Nordic 联赛里本身就是队名：全部丢完则回退原样，
    绝不返回空串。
    """
    substantive = [
        token
        for token in tokens
        if token not in _LEGAL_FORM_TOKENS and not token.isdigit()
    ]
    return substantive or tokens


#: NFKD **不会**拆开这些字母（ø、æ、ł、ß 是独立字母，不是「基字母 + 变音符」）。
#: 不做这一步，"Tromsø" 与 "Tromso" 会永远对不上——实测北欧联赛大面积踩这个坑。
#: 键是小写，必须在 casefold 之后替换。
_TRANSLITERATE = {
    "ø": "o", "æ": "ae", "å": "a", "ä": "a", "ö": "o", "ü": "u", "ß": "ss",
    "ł": "l", "đ": "d", "ð": "d", "þ": "th", "ı": "i", "ñ": "n", "ç": "c",
}


def normalize_team_name(name: str) -> str:
    """球队名归一化：NFC → 去变音符 → 转写特殊字母 → 小写 → 去标点 → 去功能词。"""
    if not name:
        return ""
    text_value = unicodedata.normalize("NFC", str(name)).strip()
    decomposed = unicodedata.normalize("NFKD", text_value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = stripped.casefold()
    for source, target in _TRANSLITERATE.items():
        folded = folded.replace(source, target)
    kept = [ch if (ch.isalnum() or ch.isspace()) else " " for ch in folded]
    return " ".join(_strip_legal_forms("".join(kept).split()))


#: 同一个俱乐部的两种写法。**只列实测出现的**，不做猜测性扩充：
#: 每加一条都等于放宽匹配，必须由真实的错配证据驱动。
TOKEN_ALIASES = {
    "utd": "united",
    "wolves": "wolverhampton",
    "westbrom": "westbromwich",
    "jrs": "juniors",
    "mg": "mineiro",
}

MATCH_LEVEL_REVIEWED = "REVIEWED_ALIAS"
MATCH_LEVEL_EXACT = "EXACT"
MATCH_LEVEL_ALIAS = "ALIAS"
MATCH_LEVEL_ACRONYM = "ACRONYM"
MATCH_LEVEL_TOKEN_EQ = "TOKEN_EQ"  # noqa: S105 - 匹配级别标签，不是凭据
MATCH_LEVEL_PREFIX = "TOKEN_PREFIX"
MATCH_LEVEL_SUBSET = "TOKEN_SUBSET"

#: 由强到弱。多候选时**先取最强档**，同档才谈歧义：
#: 精确命中不应被一个较弱的子集命中拖进歧义而双双落空。
_LEVEL_ORDER = (
    MATCH_LEVEL_REVIEWED,
    MATCH_LEVEL_EXACT,
    MATCH_LEVEL_ALIAS,
    MATCH_LEVEL_ACRONYM,
    MATCH_LEVEL_TOKEN_EQ,
    MATCH_LEVEL_PREFIX,
    MATCH_LEVEL_SUBSET,
)


def _acronym_of(tokens: list[str]) -> str:
    return "".join(token[0] for token in tokens)


#: 词首比较的最短长度。"rb" 这种 2 字母缩写不是 "rasenballsport" 的前缀，
#: 放进来只会制造噪音命中。
_MIN_PREFIX_LENGTH = 4


def _token_matches(left_token: str, right_token: str) -> bool:
    """token 级比较：相等，或只差一个复数尾。

    **不再放行「任意词首重合」**。曾经用 ``long.startswith(short)``，结果
    "Plate"（River Plate）与 "Platense" 词首重合 5 个字符被判成同一队，
    两个来源里毫不相干的两家俱乐部因此互相认领，把各自正确的 EXACT 命中一起
    拖进歧义而双双落空。缩写（"Independ."）不靠这条规则兜，走人工复核表。
    """
    if left_token == right_token:
        return True
    shorter, longer = (
        (left_token, right_token)
        if len(left_token) <= len(right_token)
        else (right_token, left_token)
    )
    if len(shorter) < _MIN_PREFIX_LENGTH:
        return False
    return longer in (shorter + "s", shorter + "es")


def team_names_compatible(fs_name: str, production_name: str) -> str | None:
    """判定两个来源的队名是否指同一支球队；返回匹配级别或 None。

    四个级别都是**确定性、可解释**的字符串规则，没有编辑距离、没有概率阈值——
    每一次命中都能说清「为什么算同一队」：

    * ``EXACT``   归一化后完全相同；
    * ``ALIAS``   经 ``TOKEN_ALIASES`` 展开后相同（Wolverhampton Wanderers ↔ Wolves）；
    * ``ACRONYM`` 一边是单 token，且恰为另一边各 token 首字母（QPR ↔ Queens Park Rangers）；
    * ``TOKEN_PREFIX`` 短名按序是长名的**词首前缀**（Birmingham ↔ Birmingham City、
      Preston ↔ Preston North End、West Brom ↔ West Bromwich Albion）。

    刻意不做「任意子集包含」（例如 Manchester ↔ Manchester City 若只看首词会误配，
    靠调用方的唯一性裁决兜底；真正的同城两支球队同场出现时必然产生多候选）。
    """
    left = normalize_team_name(fs_name)
    right = normalize_team_name(production_name)
    if not left or not right:
        return None
    if left == right:
        return MATCH_LEVEL_EXACT
    left_tokens = [TOKEN_ALIASES.get(token, token) for token in left.split()]
    right_tokens = [TOKEN_ALIASES.get(token, token) for token in right.split()]
    if left_tokens == right_tokens:
        return MATCH_LEVEL_ALIAS
    if len(left_tokens) == 1 and len(right_tokens) > 1:
        if left_tokens[0] == _acronym_of(right_tokens):
            return MATCH_LEVEL_ACRONYM
    if len(right_tokens) == 1 and len(left_tokens) > 1:
        if right_tokens[0] == _acronym_of(left_tokens):
            return MATCH_LEVEL_ACRONYM
    short, long_ = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    if len(left_tokens) == len(right_tokens) and all(
        _token_matches(left_tokens[index], right_tokens[index])
        for index in range(len(left_tokens))
    ):
        # 词数相同但词面有出入：Djurgårdens ↔ Djurgården、Grasshoppers ↔ Grasshopper。
        # 单 token 对单 token 也走这里——之前的 PREFIX/SUBSET 都要求词数不同，
        # 导致「两边都是单个词」的情况一片空白。
        return MATCH_LEVEL_TOKEN_EQ
    if len(short) < len(long_) and all(
        _token_matches(token, long_[index]) for index, token in enumerate(short)
    ):
        return MATCH_LEVEL_PREFIX
    if len(short) < len(long_) and _is_ordered_subset(short, long_):
        return MATCH_LEVEL_SUBSET
    return None


def _hit_rank(level: str, fs_name: str, provider_name: str) -> tuple[int, int]:
    """命中排序键 ``(级别强度, 对齐位次)``，越小越强。

    对齐位次专门区分「首词对齐」与「末词对齐」：面对 FS ``Inter Milan``，
    ``Inter``（首词）必须胜过 ``Milan``（末词），否则会把 AC Milan 错配到
    Inter Milan 上——两家俱乐部的名字在归一化后共享了 ``milan`` 这个词，
    只比词形是分不开的。
    """
    fs_tokens = normalize_team_name(fs_name).split()
    provider_tokens = normalize_team_name(provider_name).split()
    if not fs_tokens or not provider_tokens:
        return (_LEVEL_ORDER.index(level), 9)
    short, long_ = (
        (fs_tokens, provider_tokens)
        if len(fs_tokens) <= len(provider_tokens)
        else (provider_tokens, fs_tokens)
    )
    if short == long_:
        alignment = 0
    elif _token_matches(short[0], long_[0]):
        alignment = 1
    elif _token_matches(short[-1], long_[-1]):
        alignment = 3
    else:
        alignment = 2
    return (_LEVEL_ORDER.index(level), alignment)


def _is_ordered_subset(short: list[str], long_: list[str]) -> bool:
    """短名的每个 token 按序是长名某个 token 的词首前缀（允许中间跳过）。

    覆盖 "Salzburg" ⊂ "Red Bull Salzburg"、"Lyon" ⊂ "Olympique Lyonnais"、
    "Marseille" ⊂ "Olympique de Marseille" 这类「正式名带冠词/城市/地区」的写法。

    放宽必然带来误配风险，所以它由**双向唯一性**兜底：候选不唯一时不写结论。
    典型代价是同城两队（AC Milan / Inter Milan 之于 "Milan"）会因多候选而拒绝，
    这比随便挑一个更可接受——拒绝会出现在未映射清单里，错配不会。
    """
    position = 0
    for token in short:
        while position < len(long_) and not _token_matches(token, long_[position]):
            position += 1
        if position == len(long_):
            return False
        position += 1
    return True


def utc_date(value: datetime | int | float | str) -> date:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        return moment.astimezone(UTC).date()
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC).date()
    return datetime.fromtimestamp(float(value), tz=UTC).date()


def fixture_sha256(row: Mapping[str, Any]) -> str:
    """一场 FootyStats 比赛自身业务内容的 canonical 哈希。"""
    return canonical_sha256(
        {
            "contract": FIXTURE_CONTRACT,
            "hash_domain": str(HASH_DOMAIN),
            "serializer_version": SERIALIZER_VERSION,
            "fixture": dict(row),
        },
        domain=HASH_DOMAIN,
    )


# ── 生产侧只读端口 ───────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ProductionFixture:
    fixture_id: str
    competition_id: str
    kickoff_utc: datetime
    home_provider_team_id: str
    away_provider_team_id: str
    home_name: str
    away_name: str
    home_goals: int | None
    away_goals: int | None


@dataclass(frozen=True)
class ProductionTeam:
    competition_id: str
    provider_team_id: str
    name: str


@dataclass(frozen=True)
class TeamMapping:
    """一支 FootyStats 球队 ↔ 一支 api_football 球队的对齐结论。"""

    competition_id: str
    fs_season_id: int
    fs_team_id: int
    provider_team_id: str | None
    method: str
    confidence: str


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


FixtureIndex = dict[tuple[str, date], list[ProductionFixture]]


def load_production_fixture_index(
    engine: Engine, *, competition_ids: Iterable[str] | None = None
) -> FixtureIndex:
    """读取生产 fixture 身份（只读），按 `(联赛, UTC 日期) -> 候选` 建索引。

    读的是既有 ``matchday_fixture_identities``：本模块不造第二个 fixture 身份，
    只把 FootyStats 的行指到它的既有 ``fixture_id`` 上。

    桶键刻意**不含队名**：两个来源的队名写法系统性不同（api_football 用简称
    "Birmingham"，FootyStats 用全称 "Birmingham City"），按名字做精确键只会
    把所有场次都判成未命中。队名比对改在候选集内用可解释规则完成。
    """
    sql = """
        SELECT fixture_id,
               competition_id,
               kickoff_utc,
               home_provider_team_id,
               away_provider_team_id,
               payload -> 'teams' -> 'home' ->> 'name' AS home_name,
               payload -> 'teams' -> 'away' ->> 'name' AS away_name,
               payload -> 'goals' ->> 'home' AS home_goals,
               payload -> 'goals' ->> 'away' AS away_goals
          FROM matchday_fixture_identities
    """
    params: dict[str, Any] = {}
    if competition_ids is not None:
        sql += " WHERE competition_id = ANY(:competition_ids)"
        params["competition_ids"] = list(competition_ids)
    index: FixtureIndex = {}
    with engine.connect() as connection:
        for record in connection.execute(text(sql), params).mappings():
            kickoff: datetime = record["kickoff_utc"]
            row = ProductionFixture(
                fixture_id=str(record["fixture_id"]),
                competition_id=str(record["competition_id"]),
                kickoff_utc=kickoff,
                home_provider_team_id=str(record["home_provider_team_id"] or ""),
                away_provider_team_id=str(record["away_provider_team_id"] or ""),
                home_name=str(record["home_name"] or ""),
                away_name=str(record["away_name"] or ""),
                home_goals=_int_or_none(record["home_goals"]),
                away_goals=_int_or_none(record["away_goals"]),
            )
            index.setdefault((row.competition_id, utc_date(kickoff)), []).append(row)
    return index


def load_production_teams(engine: Engine) -> dict[str, list[ProductionTeam]]:
    """生产侧球队清单（只读）：``competition_id -> [(provider_team_id, name)]``。

    名字取自 fixture payload（api_football 的写法），与 fixture 上的
    ``home/away_provider_team_id`` 同源，供球队层交叉表对齐使用。
    """
    sql = """
        SELECT competition_id,
               home_provider_team_id AS team_id,
               payload -> 'teams' -> 'home' ->> 'name' AS name
          FROM matchday_fixture_identities
         WHERE home_provider_team_id <> ''
        UNION
        SELECT competition_id,
               away_provider_team_id AS team_id,
               payload -> 'teams' -> 'away' ->> 'name' AS name
          FROM matchday_fixture_identities
         WHERE away_provider_team_id <> ''
    """
    teams: dict[str, dict[str, str]] = {}
    with engine.connect() as connection:
        for record in connection.execute(text(sql)).mappings():
            competition_id = str(record["competition_id"])
            team_id = str(record["team_id"])
            name = str(record["name"] or "")
            teams.setdefault(competition_id, {}).setdefault(team_id, name)
    return {
        competition_id: [
            ProductionTeam(competition_id=competition_id, provider_team_id=team_id, name=name)
            for team_id, name in sorted(by_id.items())
        ]
        for competition_id, by_id in teams.items()
    }


# ── 映射判定 ─────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FixtureMatch:
    matched_fixture_id: str | None
    method: str
    confidence: str
    candidate_count: int


@dataclass(frozen=True)
class FsTeamRef:
    fs_season_id: int
    fs_team_id: int
    name: str


#: ``(competition_id, fs_team_id) -> provider_team_id``。fixture 层据此按
#: **id** 精确对齐，不再逐场猜队名。
TeamCrosswalk = dict[tuple[str, int], str]


def load_team_alias() -> dict[str, list[tuple[str, str, str]]]:
    """加载人工复核的球队别名表。

    返回 ``competition_id -> [(归一化 fs 名, 归一化 provider 名, 判据)]``。

    加载即做两项**唯一性校验**，不合法直接抛错而不是静默取第一条：
    同一 ``(联赛, fs 名)`` 只能指一个 provider 队；同一联赛内 ``provider 名``
    也只能出现一次。别名表一旦重复，等于把裁决权交给 JSON 顺序，必须挡住。
    """
    if not TEAM_ALIAS_PATH.exists():
        return {}
    document = json.loads(TEAM_ALIAS_PATH.read_text(encoding="utf-8"))
    seen_fs: set[tuple[str, str]] = set()
    seen_provider: set[tuple[str, str]] = set()
    table: dict[str, list[tuple[str, str, str]]] = {}
    for entry in document.get("entries") or []:
        competition_id = str(entry["competition_id"])
        fs_name = normalize_team_name(str(entry["footystats_name"]))
        provider_name = normalize_team_name(str(entry["provider_name"]))
        if not fs_name or not provider_name:
            raise ValueError(f"别名表归一化后为空: {entry!r}")
        if (competition_id, fs_name) in seen_fs:
            raise ValueError(f"别名表重复的 footystats_name: {competition_id}/{fs_name}")
        if (competition_id, provider_name) in seen_provider:
            raise ValueError(f"别名表重复的 provider_name: {competition_id}/{provider_name}")
        seen_fs.add((competition_id, fs_name))
        seen_provider.add((competition_id, provider_name))
        table.setdefault(competition_id, []).append(
            (fs_name, provider_name, str(entry.get("evidence") or ""))
        )
    return table


def build_team_crosswalk(
    production_teams: Mapping[str, Sequence[ProductionTeam]],
    fs_teams: Sequence[FsTeamRef],
    *,
    season_by_competition: Mapping[str, int],
) -> list[TeamMapping]:
    """球队层交叉表：每个 (联赛, FootyStats 球队) 只裁决一次。

    为什么先把球队对齐、再对齐 fixture：队名不可靠是**系统性**的（简称 / 全称 /
    缩写），逐场拿名字去猜会把同一个球队的错误重复 N 次。球队层裁决一次，
    fixture 层就能用 provider team id 做精确键，把「映射准确率」变成可归因的
    球队级问题（少数未对齐球队 → 逐条人工补齐即可）。

    唯一性双向成立才算命中：一个生产球队只能对一个 fs 球队，反之亦然，
    否则判 AMBIGUOUS、不写结论。
    """
    fs_by_competition: dict[str, list[FsTeamRef]] = {}
    for ref in fs_teams:
        competition_id = _competition_of_season(ref.fs_season_id, season_by_competition)
        if competition_id is not None:
            fs_by_competition.setdefault(competition_id, []).append(ref)

    alias_table = load_team_alias()

    # 候选对：每一对（生产球队, fs 球队）连同它的强度与对齐位次。
    pairs: list[tuple[str, int, str, str, tuple[int, int]]] = []
    for competition_id, teams in production_teams.items():
        candidates_for_league = fs_by_competition.get(competition_id, [])
        if not candidates_for_league:
            continue
        aliases = alias_table.get(competition_id, [])
        for team in teams:
            # 人工复核结论优先于字符串规则：规则是启发式，复核是裁决。
            reviewed = [
                (ref, MATCH_LEVEL_REVIEWED)
                for fs_name, provider_name, _ in aliases
                for ref in candidates_for_league
                if normalize_team_name(ref.name) == fs_name
                and normalize_team_name(team.name) == provider_name
            ]
            hits = reviewed or [
                (ref, level)
                for ref in candidates_for_league
                if (level := team_names_compatible(ref.name, team.name)) is not None
            ]
            for ref, level in hits:
                pairs.append(
                    (
                        competition_id,
                        ref.fs_team_id,
                        team.provider_team_id,
                        level,
                        _hit_rank(level, ref.name, team.name),
                    )
                )

    # 第一遍（fs 侧）：同一支 fs 球队被多个生产球队认领时，只留最强的一个；
    # 同强度并列才作废。第二遍（生产侧）同理反向。两遍都过才写结论。
    #
    # 顺序很重要：单侧过滤会把「精确命中」和「较弱命中」一起判成歧义而双双落空
    # （Los Angeles FC 的精确命中被 Los Angeles Galaxy 的弱命中拖下水）。
    best_by_fs: dict[tuple[str, int], tuple[tuple[int, int], str, str]] = {}
    for competition_id, fs_team_id, provider_team_id, level, rank in pairs:
        key = (competition_id, fs_team_id)
        current = best_by_fs.get(key)
        if current is None or rank < current[0]:
            best_by_fs[key] = (rank, provider_team_id, level)
        elif rank == current[0] and provider_team_id != current[1]:
            best_by_fs[key] = (rank, "", level)
    best_by_provider: dict[tuple[str, str], tuple[tuple[int, int], int, str]] = {}
    for (competition_id, fs_team_id), (rank, provider_team_id, level) in best_by_fs.items():
        if not provider_team_id:
            continue
        key = (competition_id, provider_team_id)
        current = best_by_provider.get(key)
        if current is None or rank < current[0]:
            best_by_provider[key] = (rank, fs_team_id, level)
        elif rank == current[0] and fs_team_id != current[1]:
            best_by_provider[key] = (rank, -1, level)

    mappings: list[TeamMapping] = []
    for (competition_id, provider_team_id), (_, fs_team_id, level) in sorted(
        best_by_provider.items()
    ):
        if fs_team_id < 0:
            continue
        ref = next(
            item
            for item in fs_by_competition[competition_id]
            if item.fs_team_id == fs_team_id
        )
        mappings.append(
            TeamMapping(
                competition_id=competition_id,
                fs_season_id=ref.fs_season_id,
                fs_team_id=fs_team_id,
                provider_team_id=provider_team_id,
                method=f"TEAM_NAME:{level}",
                confidence=level,
            )
        )
    return mappings


def _competition_of_season(
    fs_season_id: int, season_by_competition: Mapping[str, int]
) -> str | None:
    for competition_id, season_id in season_by_competition.items():
        if season_id == fs_season_id:
            return competition_id
    return None


def crosswalk_lookup(mappings: Iterable[TeamMapping]) -> TeamCrosswalk:
    return {
        (mapping.competition_id, mapping.fs_team_id): str(mapping.provider_team_id)
        for mapping in mappings
        if mapping.provider_team_id
    }


def match_fixture(
    index: Mapping[tuple[str, date], list[ProductionFixture]],
    crosswalk: Mapping[tuple[str, int], str],
    *,
    competition_id: str | None,
    kickoff_utc: datetime,
    home_team_id: int,
    away_team_id: int,
    home_goals: int | None,
    away_goals: int | None,
) -> FixtureMatch:
    """把一个 FootyStats 比赛映射到既有生产 fixture_id。

    **键是 provider team id，不是队名**：队名已在 ``build_team_crosswalk`` 里
    裁决过。只有唯一候选才算命中；多候选是 AMBIGUOUS（须人工裁决）。
    """
    if not competition_id:
        return FixtureMatch(None, METHOD_NONE, CONFIDENCE_AMBIGUOUS, 0)
    home_provider_id = crosswalk.get((competition_id, home_team_id))
    away_provider_id = crosswalk.get((competition_id, away_team_id))
    if not home_provider_id or not away_provider_id:
        return FixtureMatch(None, "TEAM_NOT_CROSSWALKED", CONFIDENCE_AMBIGUOUS, 0)

    kickoff_date = utc_date(kickoff_utc)
    days = (kickoff_date, kickoff_date - timedelta(days=1), kickoff_date + timedelta(days=1))
    for offset, method in ((0, METHOD_EXACT), (1, METHOD_WINDOW)):
        candidates = [
            candidate
            for day in (days[:1] if offset == 0 else days[1:])
            for candidate in index.get((competition_id, day), [])
            if candidate.home_provider_team_id == home_provider_id
            and candidate.away_provider_team_id == away_provider_id
        ]
        if not candidates:
            continue
        if len(candidates) > 1:
            return FixtureMatch(None, method, CONFIDENCE_AMBIGUOUS, len(candidates))
        candidate = candidates[0]
        return FixtureMatch(
            candidate.fixture_id,
            method,
            _score_confidence(candidate, home_goals, away_goals),
            1,
        )
    return FixtureMatch(None, METHOD_NONE, CONFIDENCE_AMBIGUOUS, 0)


def _score_confidence(
    candidate: ProductionFixture, home_goals: int | None, away_goals: int | None
) -> str:
    if (
        candidate.home_goals is None
        or candidate.away_goals is None
        or home_goals is None
        or away_goals is None
    ):
        return CONFIDENCE_SCORE_UNKNOWN
    if (candidate.home_goals, candidate.away_goals) == (home_goals, away_goals):
        return CONFIDENCE_SCORE_AGREES
    return CONFIDENCE_SCORE_DIFFERS


# ── league 层：人工复核过的静态映射 ──────────────────────────────────────────
@dataclass(frozen=True)
class LeagueMapping:
    competition_id: str
    fs_season_id: int
    fs_league_name: str
    fs_country: str
    api_football_league_id: str
    reviewed_by: str
    evidence: str


def load_league_map(path: Path | None = None) -> dict[int, LeagueMapping]:
    """读取已复核的 league 映射；文件缺失或条目残缺即 fail closed。"""
    resolved = path or LEAGUE_MAP_PATH
    document = json.loads(resolved.read_text(encoding="utf-8"))
    entries = document.get("mappings")
    if document.get("contract") != "w2.footystats_league_map.v1" or not isinstance(entries, list):
        raise ValueError(f"FOOTYSTATS_LEAGUE_MAP_MALFORMED:{resolved}")
    result: dict[int, LeagueMapping] = {}
    for raw in entries:
        mapping = LeagueMapping(
            competition_id=str(raw["competition_id"]),
            fs_season_id=int(raw["fs_season_id"]),
            fs_league_name=str(raw["fs_league_name"]),
            fs_country=str(raw["fs_country"]),
            api_football_league_id=str(raw.get("api_football_league_id") or ""),
            reviewed_by=str(raw.get("reviewed_by") or ""),
            evidence=str(raw.get("evidence") or ""),
        )
        if not mapping.competition_id or not mapping.reviewed_by or not mapping.evidence:
            raise ValueError(f"FOOTYSTATS_LEAGUE_MAP_ENTRY_INCOMPLETE:{raw}")
        if mapping.fs_season_id in result:
            raise ValueError(f"FOOTYSTATS_LEAGUE_MAP_DUPLICATE_SEASON:{mapping.fs_season_id}")
        result[mapping.fs_season_id] = mapping
    if not result:
        raise ValueError("FOOTYSTATS_LEAGUE_MAP_EMPTY")
    return result
