"""生成并复核 FootyStats league 层映射（指令书 I 任务 A.2 的 league 层）。

为什么需要这个脚本：league 映射是三层身份映射里唯一**没有可推导公共键**的一层。
FootyStats 的 ``season.id`` 与 api_football 的 league id 属于不同域，猜不出来，
只能由「(国家, 联赛名, 赛季年)」三元组对齐后**人工复核**。把对齐过程写成脚本，
是为了让复核对象是可重放的产物，而不是一段手打的 JSON。

赛季年口径来自我们自己的权威配置 ``season_naming_policy``：

* ``single_calendar_year`` → FootyStats year ``"2026"``
* ``starting_calendar_year`` → FootyStats year ``"20262027"``

FootyStats 对跨年赛季用「起始年+结束年」拼接标签，所以 2026/27 赛季在它的
catalog 里是 ``20262027``，不是 ``2026``。

``MANUAL_RESOLUTIONS`` 里的 8 条是精确三元组**对不上**的联赛：我们的名字是
官方全名或赞助商名（如 "Jupiler Pro League"），FootyStats 用的是俗称
（"Pro League"）。这 8 条逐条按 (国家, 赛季年) 在 catalog 内人工挑选，理由写在
``evidence`` 里。它们仍是**假设**，由任务 A 的 fixture 交叉映射做经验证伪：
season id 取错的国家/级别，日期+主客键一场都对不上。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from w2.infrastructure.database import create_engine  # noqa: E402
from w2.quant_research import footystats_identity as identity  # noqa: E402
from w2.quant_research.footystats_client import FootyStatsClient  # noqa: E402

MAP_CONTRACT = "w2.footystats_league_map.v1"
DEFAULT_OUT = _REPO_ROOT / "config/quant/footystats_league_map.v1.json"

SEASON_YEAR_BY_POLICY = {
    "single_calendar_year": "2026",
    "starting_calendar_year": "20262027",
}

#: 精确三元组对不上的 8 条：`competition_id -> (fs_league_name, fs_season_id, evidence)`。
MANUAL_RESOLUTIONS: dict[str, tuple[str, int, str]] = {
    "argentina_primera": (
        "Primera División",
        16571,
        "我方 name='Liga Profesional de Futbol'（赛事官方全名）；FootyStats 用俗称 "
        "'Primera División'。同国同年另有 Prim B/ Prim C/ 杯赛与女足，仅此条为顶级联赛。",
    ),
    "belgium_jupiler_pro_league": (
        "Pro League",
        17171,
        "我方 name='Jupiler Pro League'（赞助商名）；FootyStats 用 'Pro League'。"
        "比利时同年其余条目为 First Division B / Super Cup / 女足。",
    ),
    "brasileirao_serie_a": (
        "Serie A",
        16544,
        "我方 name='Campeonato Brasileiro Serie A'；FootyStats 巴西同年 'Serie A' 唯一，"
        "与巴西 'Serie B' (16783) / 'Serie C' (16947) 区分靠级别名。",
    ),
    "croatia_hnl": (
        "Prva HNL",
        17087,
        "我方 name='HNL'；FootyStats 克罗地亚顶级联赛为 'Prva HNL'（另有 Druga HNL "
        "为次级）。",
    ),
    "czech_republic_liga": (
        "First League",
        17157,
        "我方 name='Czech Liga'；FootyStats 捷克顶级联赛为 'First League'，次级为 'FNL'。",
    ),
    "greece_super_league_1": (
        "Super League",
        17356,
        "我方 name='Super League 1'；FootyStats 希腊顶级联赛为 'Super League'，"
        "次级为 'Super League 2'。",
    ),
    "mls": (
        "MLS",
        16504,
        "我方 country='United States'，FootyStats country='USA'；name='Major League "
        "Soccer' 对应 FootyStats 'MLS'。同类干扰项 MLS Next Pro / Leagues Cup 已排除。",
    ),
    "primeira_liga": (
        "Liga NOS",
        17217,
        "我方 name='Primeira Liga'（通称）；FootyStats 葡萄牙顶级联赛为 'Liga NOS'"
        "（赞助商名），次级为 'LigaPro'。",
    ),
}


def _catalog_index(payload: dict[str, Any]) -> dict[tuple[str, str, str], list[int]]:
    index: dict[tuple[str, str, str], list[int]] = {}
    for row in payload.get("data") or []:
        if not isinstance(row, dict):
            continue
        country = str(row.get("country") or "")
        league_name = identity.normalize_team_name(str(row.get("league_name") or ""))
        for season in row.get("season") or []:
            if not isinstance(season, dict):
                continue
            index.setdefault(
                (country, league_name, str(season.get("year"))), []
            ).append(int(season["id"]))
    return index


def _competitions() -> list[dict[str, Any]]:
    root = _REPO_ROOT / "config/competitions"
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.json"))
    ]


def build(payload: dict[str, Any], *, source_sha256: str) -> dict[str, Any]:
    index = _catalog_index(payload)
    mappings: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for competition in _competitions():
        competition_id = str(competition["competition_id"])
        if competition_id == "world_cup_2026":
            # 不参与本季联赛白名单（world_cup scope_group 被 whitelist 排除）。
            continue
        policy = str(competition.get("season_naming_policy") or "")
        season_year = SEASON_YEAR_BY_POLICY.get(policy)
        if season_year is None:
            unresolved.append(f"{competition_id}:SEASON_POLICY_UNKNOWN:{policy}")
            continue
        country = str(competition.get("country") or "")
        name = identity.normalize_team_name(str(competition.get("name") or ""))
        candidates = index.get((country, name, season_year), [])
        manual = MANUAL_RESOLUTIONS.get(competition_id)
        if len(candidates) == 1:
            fs_season_id = candidates[0]
            fs_league_name = str(competition["name"])
            method = "EXACT_TRIPLE"
            evidence = (
                f"FootyStats league-list 中 (country={country!r}, league_name="
                f"{competition['name']!r}, year={season_year!r}) 唯一命中。"
            )
        elif manual is not None:
            fs_league_name, fs_season_id, evidence = manual
            method = "MANUAL_REVIEW"
        else:
            unresolved.append(
                f"{competition_id}:CANDIDATES={candidates}:NAME={competition.get('name')!r}"
            )
            continue
        mappings.append(
            {
                "competition_id": competition_id,
                "fs_season_id": fs_season_id,
                "fs_league_name": fs_league_name,
                "fs_country": country,
                "fs_season_year": season_year,
                "api_football_league_id": str(
                    (competition.get("provider_mapping") or {}).get(
                        "api_football_league_id"
                    )
                    or ""
                ),
                "season_naming_policy": policy,
                "mapping_method": method,
                "reviewed_by": "w2-implementer",
                "evidence": evidence,
            }
        )
    return {
        "contract": MAP_CONTRACT,
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog_source": "footystats:league-list",
        "catalog_payload_sha256": source_sha256,
        "season_year_by_policy": SEASON_YEAR_BY_POLICY,
        "review_status": "IMPLEMENTER_REVIEWED_PENDING_INDEPENDENT_ACCEPTANCE",
        "verification_required": [
            "fixture_cross_check_accuracy>=0.99",
            "independent_20_fixture_recheck",
        ],
        "unresolved": unresolved,
        "mappings": sorted(mappings, key=lambda row: row["competition_id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="build FootyStats league map")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=None,
        help="离线复用已保存的 league-list 响应，避免重复消耗配额",
    )
    args = parser.parse_args()

    if args.catalog is not None:
        payload = json.loads(args.catalog.read_text(encoding="utf-8"))
        source_sha = identity.canonical_sha256(
            payload, domain=identity.HASH_DOMAIN
        )
    else:
        client = FootyStatsClient(create_engine())
        response = client.request("league-list")
        payload = response.payload
        source_sha = response.payload_sha256

    document = build(payload, source_sha256=source_sha)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"FOOTYSTATS_LEAGUE_MAP_WRITTEN path={args.out} mappings={len(document['mappings'])}")
    for item in document["unresolved"]:
        print(f"  UNRESOLVED {item}")
    return 0 if not document["unresolved"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
