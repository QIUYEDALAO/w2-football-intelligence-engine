#!/usr/bin/env python3
"""Build pre-result V1 closing-market predictions from frozen PIT xG rows.

This module deliberately reads only the Football-Data market columns needed for
the preregistered closing benchmark.  Result columns are never accessed.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from w2.domain.five_state_pricing import (
    SettlementDistribution,
    cashflow_price_edge,
    expected_value,
    fair_decimal_odds,
)
from w2.domain.odds import settle_asian_handicap, settle_total_goals
from w2.markets.devig import DevigMethod, devig
from w2.strategy.simulate import _exact_score_matrix_with_uncertainty

COMPETITION_FILES = {
    "premier_league": "E0",
    "la_liga": "SP1",
    "bundesliga": "D1",
    "serie_a": "I1",
    "ligue_1": "F1",
}
MODEL_VERSION = "w2.v1.historical_closing_blindtest.models.v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _name(value: str) -> str:
    aliases = {
        "manchesterunited": "manunited",
        "manchestercity": "mancity",
        "parissaintgermain": "parissg",
        "internazionale": "intermilan",
        "inter": "intermilan",
        "borussiamonchengladbach": "monchengladbach",
        "mgladbach": "monchengladbach",
        "athleticclub": "athbilbao",
        "athleticbilbao": "athbilbao",
        "athleticclubbilbao": "athbilbao",
        "atleticomadrid": "athmadrid",
        "atleticomadrids": "athmadrid",
        "realbetis": "betis",
        "stadebrestois29": "brest",
        "hellasverona": "verona",
        "asroma": "roma",
        "acmilan": "milan",
        "fsvmainz05": "mainz",
        "eintrachtfrankfurt": "einfrankfurt",
        "1fckoln": "fckoln",
        "fcaugsburg": "augsburg",
        "celtavigo": "celta",
        "celta": "celta",
        "fckoln": "fckoln",
        "fcheidenheim": "heidenheim",
        "svdarmstadt98": "darmstadt",
        "1899hoffenheim": "hoffenheim",
        "vflbochum": "bochum",
        "vflwolfsburg": "wolfsburg",
        "vfbstuttgart": "stuttgart",
        "borussiadortmund": "dortmund",
        "scfreiburg": "freiburg",
        "bayerleverkusen": "leverkusen",
        "clermontfoot": "clermont",
        "psg": "psg",
        "parissg": "psg",
    }
    normalized = re.sub(r"[^a-z0-9]", "", value.lower())
    return aliases.get(normalized, normalized)


def _same_team(left: str, right: str) -> bool:
    left_name, right_name = _name(left), _name(right)
    return (
        left_name == right_name
        or difflib.SequenceMatcher(None, left_name, right_name).ratio() >= 0.78
    )


def _float(row: dict[str, str], key: str) -> float | None:
    value = (row.get(key) or "").strip()
    try:
        return float(value) if value else None
    except ValueError:
        return None


def _market_rows(source_root: Path, competition: str) -> list[dict[str, Any]]:
    path = source_root / "extracted" / "2324" / f"{COMPETITION_FILES[competition]}.csv"
    rows: list[dict[str, Any]] = []
    with path.open(encoding="latin1", newline="") as handle:
        for row in csv.DictReader(handle):
            date = (row.get("Date") or "").strip()
            time = (row.get("Time") or "").strip() or "12:00"
            try:
                local = datetime.strptime(f"{date} {time}", "%d/%m/%Y %H:%M")
            except ValueError:
                continue
            ah_line = _float(row, "AHCh")
            ah_home = _float(row, "PCAHH")
            ah_away = _float(row, "PCAHA")
            total_over = _float(row, "PC>2.5")
            total_under = _float(row, "PC<2.5")
            if ah_line is None or ah_home is None or ah_away is None:
                continue
            if total_over is None or total_under is None:
                continue
            rows.append(
                {
                    "competition": competition,
                    "date": local.date().isoformat(),
                    "kickoff_at": local.replace(tzinfo=ZoneInfo("Europe/London"))
                    .astimezone(UTC)
                    .isoformat(),
                    "home": row.get("HomeTeam", "").strip(),
                    "away": row.get("AwayTeam", "").strip(),
                    "ah_line": ah_line,
                    "ah_home_odds": ah_home,
                    "ah_away_odds": ah_away,
                    "totals_line": 2.5,
                    "totals_over_odds": total_over,
                    "totals_under_odds": total_under,
                }
            )
    return rows


def _score_matrix(home: float, away: float) -> dict[tuple[int, int], float]:
    return _exact_score_matrix_with_uncertainty(
        home, away, sigma_home=0.0, sigma_away=0.0, rho=0.0, max_goals=12
    )


def _dist(
    matrix: dict[tuple[int, int], float], market: str, selection: str, line: float
) -> dict[str, Decimal]:
    totals = {name: Decimal("0") for name in ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS")}
    for (home, away), probability in matrix.items():
        outcome = (
            settle_asian_handicap(home, away, selection, Decimal(str(line)))
            if market == "ASIAN_HANDICAP"
            else settle_total_goals(home + away, selection, Decimal(str(line)))
        )
        totals[outcome.value] += Decimal(str(probability))
    total = sum(totals.values(), Decimal("0"))
    return {key: value / total for key, value in totals.items()}


def _dist_json(value: dict[str, Decimal]) -> dict[str, str]:
    return {
        key: str(probability.quantize(Decimal("0.000000000001")))
        for key, probability in value.items()
    }


def _quote_eval(
    matrix: dict[tuple[int, int], float], market: str, selection: str, line: float, odds: float
) -> dict[str, Any]:
    distribution = _dist(matrix, market, selection, line)
    five_state = SettlementDistribution(
        full_win_probability=distribution["WIN"],
        half_win_probability=distribution["HALF_WIN"],
        push_probability=distribution["PUSH"],
        half_loss_probability=distribution["HALF_LOSS"],
        full_loss_probability=distribution["LOSS"],
    )
    fair = fair_decimal_odds(five_state)
    value = expected_value(Decimal(str(odds)), five_state)
    return {
        "selection": selection,
        "line": line,
        "decimal_odds": odds,
        "settlement_distribution": _dist_json(distribution),
        "model_fair_decimal_odds": str(fair),
        "ev": str(value),
        "cashflow_price_edge": str(cashflow_price_edge(Decimal(str(odds)), fair)),
    }


def _lambdas(values: dict[str, float], arm: str) -> tuple[float, float]:
    raw_total = (
        values["home_for"] + values["away_for"] + values["home_against"] + values["away_against"]
    ) / 2.0
    raw_delta = (
        0.30
        + 0.5 * (values["home_for"] - values["away_for"])
        + 0.5 * (values["away_against"] - values["home_against"])
    )
    if arm == "production":
        total = min(max(raw_total, 1.35), 4.40)
        delta = raw_delta
    else:
        total = min(max(0.885958 + 0.701191 * raw_total, 1.35), 4.40)
        if arm == "totals_candidate":
            delta = raw_delta
        elif arm == "ah_candidate":
            home_component = 0.30
            attack_component = 0.5 * (values["home_for"] - values["away_for"])
            defence_component = 0.5 * (values["away_against"] - values["home_against"])
            current_share = min(max((total + raw_delta) / (2.0 * total), 1e-9), 1.0 - 1e-9)
            eta = (
                math.log(current_share / (1.0 - current_share))
                + (
                    0.208545 * home_component
                    + 0.663475 * attack_component
                    - 0.112027 * defence_component
                )
                / total
            )
            share = 1.0 / (1.0 + math.exp(-eta))
            return round(min(max(total * share, 0.15), 4.25), 6), round(
                min(max(total * (1.0 - share), 0.15), 4.25), 6
            )
        else:
            raise ValueError(f"unknown model arm: {arm}")
    return round(min(max((total + delta) / 2.0, 0.15), 4.25), 6), round(
        min(max((total - delta) / 2.0, 0.15), 4.25), 6
    )


def build(
    manifest_path: Path,
    xg_path: Path,
    source_root: Path,
    protocol_path: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture_rows = [
        row for competition in manifest["competitions"].values() for row in competition["fixtures"]
    ]
    fixture_rows.sort(key=lambda row: (row["kickoff_at"], row["fixture_id"]))
    xg_rows = [
        json.loads(line)
        for line in xg_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(xg_rows) != len(fixture_rows) or any(row["status"] != "COMPLETE" for row in xg_rows):
        raise ValueError("xg input is not complete for every frozen fixture")
    history: dict[str, list[tuple[datetime, float, float, str]]] = defaultdict(list)
    for row in xg_rows:
        kickoff = _dt(row["kickoff_at"])
        history[row["home_team_id"]].append(
            (kickoff, float(row["home_xg"]), float(row["away_xg"]), row["fixture_id"])
        )
        history[row["away_team_id"]].append(
            (kickoff, float(row["away_xg"]), float(row["home_xg"]), row["fixture_id"])
        )
    for values in history.values():
        values.sort(key=lambda item: (item[0], item[3]))
    market_by_comp = {
        competition: _market_rows(source_root, competition) for competition in COMPETITION_FILES
    }
    predictions: list[dict[str, Any]] = []
    ambiguous = 0
    missing_market = 0
    for fixture in fixture_rows:
        kickoff = _dt(fixture["kickoff_at"])
        candidates = []
        for row in market_by_comp[fixture["competition"]]:
            if abs((_dt(row["kickoff_at"]).date() - kickoff.date()).days) > 1:
                continue
            if _same_team(row["home"], fixture["home_team_name"]) and _same_team(
                row["away"], fixture["away_team_name"]
            ):
                candidates.append(row)
        if len(candidates) > 1:
            ambiguous += 1
            continue
        if not candidates:
            missing_market += 1
            continue
        market = candidates[0]
        home_history = [value for value in history[fixture["home_team_id"]] if value[0] < kickoff][
            -5:
        ]
        away_history = [value for value in history[fixture["away_team_id"]] if value[0] < kickoff][
            -5:
        ]
        if len(home_history) < 5 or len(away_history) < 5:
            continue
        values = {
            "home_for": sum(item[1] for item in home_history) / 5,
            "home_against": sum(item[2] for item in home_history) / 5,
            "away_for": sum(item[1] for item in away_history) / 5,
            "away_against": sum(item[2] for item in away_history) / 5,
        }
        arms: dict[str, Any] = {}
        for arm in ("production", "ah_candidate", "totals_candidate"):
            home_lambda, away_lambda = _lambdas(values, arm)
            matrix = _score_matrix(home_lambda, away_lambda)
            ah_home = _quote_eval(
                matrix, "ASIAN_HANDICAP", "HOME", market["ah_line"], market["ah_home_odds"]
            )
            ah_away = _quote_eval(
                matrix, "ASIAN_HANDICAP", "AWAY", -market["ah_line"], market["ah_away_odds"]
            )
            over = _quote_eval(
                matrix, "TOTALS", "OVER", market["totals_line"], market["totals_over_odds"]
            )
            under = _quote_eval(
                matrix, "TOTALS", "UNDER", market["totals_line"], market["totals_under_odds"]
            )
            arms[arm] = {
                "lambda_home": home_lambda,
                "lambda_away": away_lambda,
                "score_matrix": [
                    {"home_goals": h, "away_goals": a, "probability": round(p, 12)}
                    for (h, a), p in sorted(matrix.items())
                ],
                "market_quotes": {
                    "ASIAN_HANDICAP": {
                        "line_home": market["ah_line"],
                        "home": ah_home,
                        "away": ah_away,
                    },
                    "TOTALS": {"line": market["totals_line"], "over": over, "under": under},
                },
                "devig_market_probability": {
                    "ASIAN_HANDICAP": devig(
                        {
                            "HOME": Decimal(str(market["ah_home_odds"])),
                            "AWAY": Decimal(str(market["ah_away_odds"])),
                        },
                        DevigMethod.PROPORTIONAL,
                    ).probabilities,
                    "TOTALS": devig(
                        {
                            "OVER": Decimal(str(market["totals_over_odds"])),
                            "UNDER": Decimal(str(market["totals_under_odds"])),
                        },
                        DevigMethod.PROPORTIONAL,
                    ).probabilities,
                },
            }
        predictions.append(
            {
                "fixture_id": fixture["fixture_id"],
                "competition": fixture["competition"],
                "kickoff_at": fixture["kickoff_at"],
                "home_team": fixture["home_team_name"],
                "away_team": fixture["away_team_name"],
                "pit_xg": values,
                "market": market,
                "models": arms,
            }
        )
    if ambiguous:
        raise ValueError(f"ambiguous market mappings: {ambiguous}")
    return {
        "schema": "w2.v1.historical_closing_blindtest.predictions.v1",
        "status": "FROZEN_BEFORE_TARGET_RESULT_READ",
        "model_version": MODEL_VERSION,
        "source_sha256": {"manifest": _sha(manifest_path), "xg": _sha(xg_path)},
        "protocol_sha256": _sha(protocol_path) if protocol_path else None,
        "market_source": str(source_root),
        "market_source_sha256": {
            competition: _sha(source_root / "extracted" / "2324" / f"{file_name}.csv")
            for competition, file_name in COMPETITION_FILES.items()
        },
        "fixed_models": {
            "production": {"home_advantage_goals": 0.30},
            "ah_candidate": {
                "home_adjustment": 0.208545,
                "attack_adjustment": 0.663475,
                "defence_adjustment": -0.112027,
                "total_goals_intercept": 0.885958,
                "total_goals_scale": 0.701191,
            },
            "totals_candidate": {
                "home_advantage_goals": 0.30,
                "total_goals_intercept": 0.885958,
                "total_goals_scale": 0.701191,
            },
        },
        "result_columns_read": [],
        "fixture_count": len(predictions),
        "excluded": {
            "missing_market_columns": missing_market,
            "ambiguous_market_mapping": ambiguous,
        },
        "predictions": predictions,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--xg", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = build(args.manifest, args.xg, args.source_root, args.protocol)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"fixture_count": payload["fixture_count"], "status": payload["status"]}, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
