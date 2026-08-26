"""Data loading for the EV-SE drift study.

Extraction is read-only and reproducible. To refresh the local cache:

  ssh -i ~/.ssh/id_ed25519_w2_hk root@45.207.194.97 \
    "docker exec w2-staging-postgres-1 psql -U w2_user -d w2 -XAt -c \"
     BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
     COPY (SELECT fixture_id, team_id, kickoff_at, captured_at, xg_for, xg_against,
                  source_system
           FROM team_xg_match ORDER BY team_id, kickoff_at) TO STDOUT WITH (FORMAT csv);
     ROLLBACK;\"" > team_xg_match.csv

League and season come from the frozen Gate-1 corpus (never from live tables), so the
join is point-in-time stable.
"""

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))
from ev_se_drift_alpha import HOLDOUT_CUTOFF, build_windows, make_pairs, parse_ts

CSV = os.environ.get("W2_XG_CSV", "team_xg_match.csv")
CORPUS = os.environ.get(
    "W2_CORPUS",
    "/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/reports"
    "/factor_model_v2/gate1_history_backfill_20260822T055041929427Z/factor_history_corpus.json",
)
CORPUS_SHA256 = "80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2"

LEAGUE = {
    "128": "argentina_primera", "39": "premier_league", "135": "serie_a", "140": "la_liga",
    "61": "ligue_1", "78": "bundesliga", "88": "eredivisie", "94": "primeira_liga",
    "253": "mls", "71": "brasileirao_serie_a", "103": "eliteserien",
    "113": "allsvenskan", "169": "chinese_super_league",
}


Series = list[tuple[float, float]]


def load(
    component: str, *, estimation_only: bool = True
) -> dict[tuple[str, str, str], Series]:
    key: dict[tuple[str, str], tuple[str, str]] = {}
    for row in json.load(open(CORPUS))["history_rows"]:
        key[(row["provider_fixture_id"], row["team_id"])] = (
            row["provider_league_id"],
            row["season"],
        )
    col = 4 if component == "attack" else 5
    series: dict[tuple[str, str, str], Series] = {}
    for line in open(CSV):
        p = line.rstrip("\n").split(",")
        if len(p) != 7 or p[0] in ("BEGIN", "ROLLBACK"):
            continue
        if estimation_only and p[2] >= HOLDOUT_CUTOFF:
            continue
        meta = key.get((p[0], p[1]))
        if meta is None:
            continue
        league = LEAGUE.get(meta[0])
        if league is None:
            continue
        series.setdefault((league, p[1], meta[1]), []).append((parse_ts(p[2]), float(p[col])))
    return series


def pairs_for(component: str, size: int) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for (league, team, season), s in load(component).items():
        if len(s) < size:
            continue
        wins = build_windows(s, team=team, league=league, season=season, size=size)
        out.setdefault(league, []).extend(make_pairs(wins, same_season_only=True))
    return out
