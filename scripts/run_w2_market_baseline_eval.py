"""W2 market-baseline eval (read-only, offline, $0 provider calls).

Purpose (2026-07 architecture review follow-up):
  1. MODEL phase (local caches only):
     a. Replicate #193 big-5 fitted-lambda numbers from the Understat cache.
     b. NEW: run the exact #193 fit protocol (fitted lambdas + temperature,
        walk-forward, train-only fitting) on the in-season national leagues
        using the cached API-Football statistics xG. The ledger's "~1.05"
        numbers came from the UNFITTED hand-prior model
        (build_walk_forward_predictions -> INDEPENDENT_POISSON stage7.v1),
        so the fitted model has never been evaluated on these leagues.
     c. Emit per-fixture prediction manifests used by the MARKET phase join.
  2. MARKET phase (needs football-data.co.uk CSVs dropped into
     runtime/market_baseline_eval/football_data/ -- see FOOTBALL_DATA_FILES):
     de-vig closing odds, join to the SAME fixtures, and produce the
     per-league "model log loss vs market log loss" table plus a
     market-anchored blend experiment (weight fitted on train rows only).

Red lines respected: no provider calls, no DB writes, no enable, no deploy,
no changes to any live decision path. Everything lands under
runtime/market_baseline_eval/.

Run:
  python3 scripts/run_w2_market_baseline_eval.py --phase model
  python3 scripts/run_w2_market_baseline_eval.py --phase market
  python3 scripts/run_w2_market_baseline_eval.py --phase all
"""

# mypy: ignore-errors
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from w2.backtest.free_tier_2024 import (  # noqa: E402
    MIN_LAMBDA_FIT_SAMPLE,
    _fit_offline_lambda_model,
    _fit_temperature,
    _model_iteration_predictions,
    _offline_model_samples,
    _temperature_scaled_predictions,
    load_fixture_statistics,
    load_historical_fixtures,
    load_understat_fixture_dataset,
)
from w2.competitions.league_whitelist_scope import (  # noqa: E402
    IN_SEASON_NATIONAL_LEAGUES,
    TOP_FIVE_COMPETITIONS,
)
from w2.competitions.registry import CompetitionRegistry  # noqa: E402

OUT_DIR = REPO_ROOT / "runtime" / "market_baseline_eval"
MANIFEST_DIR = OUT_DIR / "manifests"
FOOTBALL_DATA_DIR = OUT_DIR / "football_data"
UNDERSTAT_DIRS = (REPO_ROOT / "runtime" / "w2_understat_model_iter1" / "understat",)
PRO_DAY1_RAW = REPO_ROOT / "runtime" / "w2_pro_day1_provider_data" / "raw"
PRO_DAY1_DIRS = tuple(
    PRO_DAY1_RAW / sub for sub in ("", "fixtures", "statistics", "odds", "lineups")
)

BIG5_SEASONS = ("2023", "2024")
IN_SEASON_SEASONS = ("2024", "2025")
MIN_HISTORY = 5
COLD_START_MATCHES = 6

# football-data.co.uk files the MARKET phase expects (user drops them in
# FOOTBALL_DATA_DIR; filenames must match exactly).
# big-5: per-season files from https://www.football-data.co.uk/mmz4281/<ss>/<code>.csv
# new leagues: cumulative files from https://www.football-data.co.uk/new/<code>.csv
FOOTBALL_DATA_FILES: dict[str, dict[str, object]] = {
    "premier_league": {"kind": "big5", "files": {"2023": "E0_2324.csv", "2024": "E0_2425.csv"}},
    "la_liga": {"kind": "big5", "files": {"2023": "SP1_2324.csv", "2024": "SP1_2425.csv"}},
    "bundesliga": {"kind": "big5", "files": {"2023": "D1_2324.csv", "2024": "D1_2425.csv"}},
    "serie_a": {"kind": "big5", "files": {"2023": "I1_2324.csv", "2024": "I1_2425.csv"}},
    "ligue_1": {"kind": "big5", "files": {"2023": "F1_2324.csv", "2024": "F1_2425.csv"}},
    "brasileirao_serie_a": {"kind": "new", "file": "BRA.csv"},
    "chinese_super_league": {"kind": "new", "file": "CHN.csv"},
    "allsvenskan": {"kind": "new", "file": "SWE.csv"},
    "eliteserien": {"kind": "new", "file": "NOR.csv"},
    "argentina_primera": {"kind": "new", "file": "ARG.csv"},
    "mls": {"kind": "new", "file": "USA.csv"},
}

TEAM_ALIASES = {
    # Understat name -> football-data name (big-5). Fuzzy matching covers the
    # rest; add here only when the unmatched report says so.
    "manchester united": "man united",
    "manchester city": "man city",
    "wolverhampton wanderers": "wolves",
    "nottingham forest": "nottm forest",
    "paris saint germain": "paris sg",
    "athletic club": "ath bilbao",
    "atletico madrid": "ath madrid",
    "real sociedad": "sociedad",
    "real betis": "betis",
    "celta vigo": "celta",
    "rayo vallecano": "vallecano",
    "borussia m gladbach": "mgladbach",
    "borussia monchengladbach": "mgladbach",
    "rasenballsport leipzig": "rb leipzig",
    "eintracht frankfurt": "ein frankfurt",
    "fc cologne": "fc koln",
    "bayer leverkusen": "leverkusen",
    "vfb stuttgart": "stuttgart",
    "ac milan": "milan",
    "saint etienne": "st etienne",
    "parma calcio 1913": "parma",
    "athletic": "ath bilbao",
    "cologne": "fc koln",
    # Brazil: API-Football legacy vs football-data spellings
    "atletico paranaense": "athletico pr",
    "atletico mineiro": "atletico mg",
    "atletico goianiense": "atletico go",
    # Sweden / Norway
    "aik stockholm": "aik",
    "odd ballklubb": "odd",
    # CSL: API-Football legacy sponsor names -> football-data current names
    "chengdu better city": "chengdu rongcheng",
    "dalian zhixing": "dalian yingbo",
    "hangzhou greentown": "zhejiang professional",
    "henan jianye": "henan songshan longmen",
    "meizhou kejia": "meizhou hakka",
    "qingdao jonoon": "qingdao hainiu",
    "qingdao youth island": "qingdao west coast",
    "shanghai sipg": "shanghai port",
    "shandong luneng": "shandong taishan",
    "shijiazhuang y j": "cangzhou",
    "sichuan jiuniu": "shenzhen xinpengcheng",
    "tianjin teda": "tianjin jinmen tiger",
}

GENERIC_TEAM_WORDS = {
    "fc", "cf", "sc", "ac", "afc", "cd", "ca", "club", "clube", "cr", "ec",
    "if", "fk", "bk", "ff", "aif", "ik", "sk", "il", "de", "do", "da",
    "regatas", "esporte", "futebol", "deportivo", "atletico" if False else "zzz",
}


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def log_loss(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        p = max(float(row["probabilities"][row["actual"]]), 1e-12)
        total += -math.log(p)
    return total / len(rows) if rows else float("nan")


def brier(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        for key in ("HOME", "DRAW", "AWAY"):
            y = 1.0 if row["actual"] == key else 0.0
            total += (float(row["probabilities"][key]) - y) ** 2
    return total / len(rows) if rows else float("nan")


def rps(rows: list[dict]) -> float:
    total = 0.0
    for row in rows:
        cum_p = 0.0
        cum_y = 0.0
        acc = 0.0
        for key in ("HOME", "DRAW", "AWAY")[:2]:
            cum_p += float(row["probabilities"][key])
            cum_y += 1.0 if row["actual"] == key else 0.0
            acc += (cum_p - cum_y) ** 2
        total += acc / 2.0
    return total / len(rows) if rows else float("nan")


def ece_top(rows: list[dict], bins: int = 10) -> float:
    """Expected calibration error on the argmax class, 10 equal-width bins."""
    if not rows:
        return float("nan")
    bucketed: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        probs = row["probabilities"]
        top = max(probs, key=lambda k: float(probs[k]))
        p = float(probs[top])
        hit = 1.0 if row["actual"] == top else 0.0
        bucketed[min(int(p * bins), bins - 1)].append((p, hit))
    total = 0.0
    for items in bucketed.values():
        avg_p = sum(p for p, _ in items) / len(items)
        avg_hit = sum(h for _, h in items) / len(items)
        total += abs(avg_p - avg_hit) * len(items)
    return total / len(rows)


def metric_block(rows: list[dict]) -> dict:
    return {
        "n": len(rows),
        "log_loss": round(log_loss(rows), 6) if rows else None,
        "brier": round(brier(rows), 6) if rows else None,
        "rps": round(rps(rows), 6) if rows else None,
        "ece_top": round(ece_top(rows), 6) if rows else None,
    }


# --------------------------------------------------------------------------
# MODEL phase
# --------------------------------------------------------------------------
def fit_and_predict(train_samples, val_samples) -> dict:
    """#193 protocol: fit lambdas on train, temperature on train, apply to val."""
    model = _fit_offline_lambda_model(train_samples)
    train_pred = _model_iteration_predictions(train_samples, model)
    val_pred = _model_iteration_predictions(val_samples, model)
    temperature = _fit_temperature(train_pred["fitted_raw"])
    train_pred["fitted_calibrated"] = _temperature_scaled_predictions(
        train_pred["fitted_raw"], temperature=temperature
    )
    val_pred["fitted_calibrated"] = _temperature_scaled_predictions(
        val_pred["fitted_raw"], temperature=temperature
    )
    return {
        "model": model,
        "temperature": temperature,
        "train": train_pred,
        "validation": val_pred,
    }


def enrich_rows(pred_rows: list[dict], samples, split: str) -> list[dict]:
    """Attach kickoff/team names (needed for the market join) to prediction rows."""
    by_id = {sample.fixture.fixture_id: sample.fixture for sample in samples}
    out = []
    for row in pred_rows:
        fixture = by_id[row["fixture_id"]]
        enriched = dict(row)
        enriched["kickoff_utc"] = fixture.kickoff_utc.isoformat()
        enriched["home_team"] = fixture.home_team
        enriched["away_team"] = fixture.away_team
        enriched["split"] = split
        out.append(enriched)
    return out


def eval_protocol(samples, train_filter, val_filter, protocol: str, competition: str) -> dict:
    train_samples = [s for s in samples if train_filter(s)]
    val_samples = [s for s in samples if val_filter(s)]
    if len(train_samples) < MIN_LAMBDA_FIT_SAMPLE or len(val_samples) < 30:
        return {
            "protocol": protocol,
            "competition": competition,
            "status": "INSUFFICIENT_SAMPLE",
            "train_n": len(train_samples),
            "validation_n": len(val_samples),
        }
    result = fit_and_predict(train_samples, val_samples)
    manifest_rows: list[dict] = []
    for split, samp in (("train", train_samples), ("validation", val_samples)):
        variants = result[split if split == "train" else "validation"]
        base = {
            row["fixture_id"]: dict(row) for row in enrich_rows(
                variants["fitted_calibrated"], samp, split
            )
        }
        for variant in ("baseline_prior", "elo_only", "uniform"):
            for row in variants[variant]:
                base[row["fixture_id"]][f"probabilities_{variant}"] = row["probabilities"]
        manifest_rows.extend(base.values())
    report = {
        "protocol": protocol,
        "competition": competition,
        "status": "OK",
        "temperature": result["temperature"],
        "coefficients": [round(c, 6) for c in result["model"].coefficients],
        "train": {
            "fitted_calibrated": metric_block(result["train"]["fitted_calibrated"]),
        },
        "validation": {
            variant: metric_block(result["validation"][variant])
            for variant in ("fitted_calibrated", "baseline_prior", "elo_only", "uniform")
        },
    }
    return {"report": report, "manifest_rows": manifest_rows}


def run_model_phase() -> dict:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    registry_entries = CompetitionRegistry().entries()
    outputs: list[dict] = []
    manifests: dict[str, list[dict]] = {}

    # --- big-5 (Understat cache, replicating #193/#196) ---
    big5_fixtures, big5_stats = load_understat_fixture_dataset(
        raw_dirs=UNDERSTAT_DIRS,
        seasons=BIG5_SEASONS,
        competitions=list(TOP_FIVE_COMPETITIONS),
    )
    big5_samples = _offline_model_samples(
        fixtures=big5_fixtures, statistics_by_fixture=big5_stats, min_history=MIN_HISTORY
    )
    # P0 replicate: pooled big-5, chronological 70/30 (single split).
    split_at = max(MIN_LAMBDA_FIT_SAMPLE, int(len(big5_samples) * 0.7))
    indexed = {id(s): i for i, s in enumerate(big5_samples)}
    res = eval_protocol(
        big5_samples,
        lambda s: indexed[id(s)] < split_at,
        lambda s: indexed[id(s)] >= split_at,
        "big5_pooled_70_30",
        "big5_pooled",
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["big5_pooled_70_30"] = res["manifest_rows"]

    # P1 cross-season 2023 -> 2024 (primary market-phase protocol for big-5:
    # train fully precedes validation; validation season = 2024/25 CSVs).
    res = eval_protocol(
        big5_samples,
        lambda s: s.fixture.season == "2023",
        lambda s: s.fixture.season == "2024",
        "big5_cross_season_2023_to_2024",
        "big5_pooled",
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["big5_cross_season_2023_to_2024"] = res["manifest_rows"]
        # per-league validation slices
        for competition in TOP_FIVE_COMPETITIONS:
            rows = [
                r for r in res["manifest_rows"]
                if r["competition_id"] == competition and r["split"] == "validation"
            ]
            if rows:
                outputs.append(
                    {
                        "protocol": "big5_cross_season_2023_to_2024",
                        "competition": competition,
                        "status": "OK_SLICE",
                        "validation": {
                            "fitted_calibrated": metric_block(rows),
                            "baseline_prior": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_baseline_prior"]}
                                    for r in rows
                                ]
                            ),
                            "uniform": metric_block(
                                [{**r, "probabilities": r["probabilities_uniform"]} for r in rows]
                            ),
                        },
                    }
                )

    # --- in-season national leagues (API-Football cache; NEW experiment) ---
    stats = load_fixture_statistics(list(PRO_DAY1_DIRS))
    for competition in IN_SEASON_NATIONAL_LEAGUES:
        fixtures = []
        for season in IN_SEASON_SEASONS:
            fixtures.extend(
                load_historical_fixtures(
                    raw_dirs=list(PRO_DAY1_DIRS),
                    entries=registry_entries,
                    season=season,
                    competitions=[competition],
                )
            )
        samples = _offline_model_samples(
            fixtures=fixtures, statistics_by_fixture=stats, min_history=MIN_HISTORY
        )
        by_season = defaultdict(int)
        for s in samples:
            by_season[s.fixture.season] += 1
        # P2 cross-season 2024 -> 2025 (primary; mirrors ledger's cross-season proof)
        res = eval_protocol(
            samples,
            lambda s: s.fixture.season == "2024",
            lambda s: s.fixture.season == "2025",
            "inseason_cross_season_2024_to_2025",
            competition,
        )
        report = res["report"] if "report" in res else res
        report["samples_by_season"] = dict(by_season)
        outputs.append(report)
        if "manifest_rows" in res:
            manifests[f"inseason_cross_2024_2025__{competition}"] = res["manifest_rows"]

    # pooled continuity run (all in-season leagues, matches S10 pooling style)
    all_fixtures = []
    for season in IN_SEASON_SEASONS:
        all_fixtures.extend(
            load_historical_fixtures(
                raw_dirs=list(PRO_DAY1_DIRS),
                entries=registry_entries,
                season=season,
                competitions=list(IN_SEASON_NATIONAL_LEAGUES),
            )
        )
    pooled_samples = _offline_model_samples(
        fixtures=all_fixtures, statistics_by_fixture=stats, min_history=MIN_HISTORY
    )
    res = eval_protocol(
        pooled_samples,
        lambda s: s.fixture.season == "2024",
        lambda s: s.fixture.season == "2025",
        "inseason_pooled_cross_season",
        "inseason_pooled",
    )
    outputs.append(res["report"] if "report" in res else res)
    if "manifest_rows" in res:
        manifests["inseason_pooled_cross_season"] = res["manifest_rows"]
        # Per-league validation slices under the pooled fit (small leagues
        # cannot reach MIN_LAMBDA_FIT_SAMPLE=200 alone; pooling the fit across
        # leagues mirrors how #193 pooled the big-5 fit).
        for competition in IN_SEASON_NATIONAL_LEAGUES:
            rows = [
                r for r in res["manifest_rows"]
                if r["competition_id"] == competition and r["split"] == "validation"
            ]
            if rows:
                outputs.append(
                    {
                        "protocol": "inseason_pooled_fit_league_slice",
                        "competition": competition,
                        "status": "OK_SLICE",
                        "validation": {
                            "fitted_calibrated": metric_block(rows),
                            "baseline_prior": metric_block(
                                [
                                    {**r, "probabilities": r["probabilities_baseline_prior"]}
                                    for r in rows
                                ]
                            ),
                            "uniform": metric_block(
                                [{**r, "probabilities": r["probabilities_uniform"]} for r in rows]
                            ),
                        },
                    }
                )
            # market join should use the pooled-fit manifest for these leagues
            manifests[f"inseason_pooled_fit__{competition}"] = [
                r for r in res["manifest_rows"] if r["competition_id"] == competition
            ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in manifests.items():
        with (MANIFEST_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    report = {
        "schema_version": "w2.market_baseline_eval.model_phase.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "provider_calls": 0,
        "notes": [
            "big5 source: Understat cache (runtime/w2_understat_model_iter1).",
            "in-season source: API-Football Pro day1 cache (fixtures + statistics xG).",
            "fitted model protocol identical to #193: train-only lambda fit + temperature.",
            "Ledger's in-season ~1.05 came from the unfitted hand-prior walk-forward model;"
            " the fitted numbers here are the first like-for-like comparison.",
        ],
        "results": outputs,
    }
    (OUT_DIR / "model_phase_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    return report


# --------------------------------------------------------------------------
# MARKET phase
# --------------------------------------------------------------------------
def normalize_name(name: str, *, drop_generic_words: bool = True) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ")
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    words = text.split()
    if drop_generic_words:
        words = [word for word in words if word not in GENERIC_TEAM_WORDS]
    return " ".join(words).strip()


def canonical(name: str) -> str:
    # Alias lookup must run before generic-word removal too, otherwise names
    # like "Athletic Club" / "FC Cologne" lose their distinguishing word
    # before they can be aliased.
    full = normalize_name(name, drop_generic_words=False)
    if full in TEAM_ALIASES:
        return normalize_name(TEAM_ALIASES[full])
    norm = normalize_name(name)
    return normalize_name(TEAM_ALIASES.get(norm, norm))


def parse_fd_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def load_football_data_rows(competition: str, spec: dict, seasons: list[str]) -> list[dict]:
    rows: list[dict] = []
    if spec["kind"] == "big5":
        for season, filename in spec["files"].items():
            if season not in seasons:
                continue
            path = FOOTBALL_DATA_DIR / filename
            if not path.exists():
                continue
            rows.extend(_read_fd_csv(path, season=season, big5=True))
    else:
        path = FOOTBALL_DATA_DIR / str(spec["file"])
        if path.exists():
            rows.extend(
                r for r in _read_fd_csv(path, season=None, big5=False) if r["season"] in seasons
            )
    return rows


def _read_fd_csv(path: Path, *, season: str | None, big5: bool) -> list[dict]:
    out: list[dict] = []
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        for record in csv.DictReader(fh):
            record = {k.strip(): (v or "").strip() for k, v in record.items() if k}
            date = parse_fd_date(record.get("Date", ""))
            if date is None:
                continue
            home = record.get("HomeTeam") or record.get("Home") or ""
            away = record.get("AwayTeam") or record.get("Away") or ""
            goals_h = record.get("FTHG") or record.get("HG")
            goals_a = record.get("FTAG") or record.get("AG")
            if not home or not away or goals_h in ("", None) or goals_a in ("", None):
                continue
            odds, odds_source = None, None
            for prefix, label in (("PSC", "pinnacle_closing"), ("AvgC", "avg_closing"),
                                  ("PS", "pinnacle"), ("Avg", "avg"), ("B365C", "b365_closing"),
                                  ("B365", "b365")):
                try:
                    trio = (
                        float(record.get(f"{prefix}H", "")),
                        float(record.get(f"{prefix}D", "")),
                        float(record.get(f"{prefix}A", "")),
                    )
                    if all(v > 1.0 for v in trio):
                        odds, odds_source = trio, label
                        break
                except (TypeError, ValueError):
                    continue
            if odds is None:
                continue
            inv = [1.0 / v for v in odds]
            overround = sum(inv)
            out.append(
                {
                    "date": date,
                    "season": season or record.get("Season", ""),
                    "home_raw": home,
                    "away_raw": away,
                    "home": canonical(home),
                    "away": canonical(away),
                    "result": "HOME" if int(goals_h) > int(goals_a) else
                              "AWAY" if int(goals_h) < int(goals_a) else "DRAW",
                    "market_probabilities": {
                        "HOME": inv[0] / overround,
                        "DRAW": inv[1] / overround,
                        "AWAY": inv[2] / overround,
                    },
                    "overround": overround,
                    "odds_source": odds_source,
                }
            )
    return out


def fuzzy_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    if a and b and (a in b or b in a) and min(len(a), len(b)) >= 5:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.78


def join_manifest_to_market(
    manifest_rows: list[dict], market_rows: list[dict]
) -> tuple[list[dict], dict]:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for row in market_rows:
        by_date[row["date"].strftime("%Y-%m-%d")].append(row)
    joined, unmatched, result_conflicts = [], [], 0
    for row in manifest_rows:
        kickoff = datetime.fromisoformat(str(row["kickoff_utc"]))
        home, away = canonical(row["home_team"]), canonical(row["away_team"])
        candidates = []
        for delta in (0, -1, 1):
            key = (kickoff + timedelta(days=delta)).strftime("%Y-%m-%d")
            candidates.extend(by_date.get(key, []))
        match = None
        for cand in candidates:
            if fuzzy_equal(home, cand["home"]) and fuzzy_equal(away, cand["away"]):
                match = cand
                break
        if match is None:
            unmatched.append({"home": row["home_team"], "away": row["away_team"],
                              "kickoff": str(row["kickoff_utc"])})
            continue
        if match["result"] != row["actual"]:
            result_conflicts += 1  # wrong join guard: drop
            continue
        merged = dict(row)
        merged["market_probabilities"] = match["market_probabilities"]
        merged["overround"] = match["overround"]
        merged["odds_source"] = match["odds_source"]
        joined.append(merged)
    diagnostics = {
        "manifest_rows": len(manifest_rows),
        "joined": len(joined),
        "unmatched": len(unmatched),
        "result_conflicts_dropped": result_conflicts,
        "join_rate": round(len(joined) / len(manifest_rows), 4) if manifest_rows else None,
        "unmatched_examples": unmatched[:12],
    }
    return joined, diagnostics


def blend_probs(p_model: dict, p_market: dict, w: float) -> dict:
    blended = {
        k: max(float(p_model[k]), 1e-12) ** (1 - w) * max(float(p_market[k]), 1e-12) ** w
        for k in ("HOME", "DRAW", "AWAY")
    }
    total = sum(blended.values())
    return {k: v / total for k, v in blended.items()}


def eval_market_league(joined: list[dict]) -> dict:
    train = [r for r in joined if r["split"] == "train"]
    val = [r for r in joined if r["split"] == "validation"]
    if len(val) < 30:
        return {
            "status": "INSUFFICIENT_JOINED_VALIDATION",
            "train_n": len(train),
            "val_n": len(val),
        }

    def rows_with(rows, key) -> list[dict]:
        return [{**r, "probabilities": r[key]} for r in rows]

    # blend weight fit on train only
    best_w, best_ll = 0.0, float("inf")
    if len(train) >= 50:
        for step in range(0, 21):
            w = step / 20.0
            ll = log_loss(
                [
                    {**r, "probabilities": blend_probs(
                        r["probabilities"], r["market_probabilities"], w)}
                    for r in train
                ]
            )
            if ll < best_ll:
                best_ll, best_w = ll, w
    else:
        best_w = None

    val_model = metric_block(val)
    val_market = metric_block(rows_with(val, "market_probabilities"))
    val_prior = metric_block(rows_with(val, "probabilities_baseline_prior"))
    out = {
        "status": "OK",
        "train_n": len(train),
        "validation_n": len(val),
        "odds_source": val[0]["odds_source"] if val else None,
        "mean_overround": round(sum(r["overround"] for r in val) / len(val), 4),
        "validation": {
            "fitted_calibrated": val_model,
            "market_devig": val_market,
            "baseline_prior": val_prior,
            "uniform": metric_block(rows_with(val, "probabilities_uniform")),
        },
        "gap_model_minus_market_log_loss": (
            round(val_model["log_loss"] - val_market["log_loss"], 6)
            if val_model["log_loss"] is not None and val_market["log_loss"] is not None
            else None
        ),
    }
    if best_w is not None:
        blended_val = [
            {**r, "probabilities": blend_probs(
                r["probabilities"], r["market_probabilities"], best_w)}
            for r in val
        ]
        out["blend"] = {
            "w_market_fit_on_train": best_w,
            "validation_blend": metric_block(blended_val),
        }
    # cold-start slice: either team has < COLD_START_MATCHES prior matches that
    # season (within the manifest ordering, which is walk-forward).
    season_counts: dict[tuple[str, str], int] = defaultdict(int)
    cold_rows, warm_rows = [], []
    for r in sorted(val + train, key=lambda x: str(x["kickoff_utc"])):
        season = r["season"]
        h_key, a_key = (season, r["home_team"]), (season, r["away_team"])
        is_cold = season_counts[h_key] < COLD_START_MATCHES or (
            season_counts[a_key] < COLD_START_MATCHES
        )
        if r["split"] == "validation":
            (cold_rows if is_cold else warm_rows).append(r)
        season_counts[h_key] += 1
        season_counts[a_key] += 1
    if cold_rows and warm_rows:
        out["cold_start"] = {
            "cold_n": len(cold_rows),
            "model_cold": metric_block(cold_rows),
            "market_cold": metric_block(rows_with(cold_rows, "market_probabilities")),
            "model_warm": metric_block(warm_rows),
            "market_warm": metric_block(rows_with(warm_rows, "market_probabilities")),
        }
    return out


def run_market_phase() -> dict:
    if not FOOTBALL_DATA_DIR.exists() or not any(FOOTBALL_DATA_DIR.glob("*.csv")):
        return {
            "status": "WAITING_FOR_DATA",
            "message": (
                f"Drop football-data.co.uk CSVs into {FOOTBALL_DATA_DIR} "
                "(see FOOTBALL_DATA_FILES in this script for expected names)."
            ),
        }
    results = {}
    # big-5: use the cross-season manifest (validation season 2024 = 2024/25 CSVs)
    manifest_path = MANIFEST_DIR / "big5_cross_season_2023_to_2024.jsonl"
    if manifest_path.exists():
        rows = [json.loads(line) for line in manifest_path.open()]
        for competition in TOP_FIVE_COMPETITIONS:
            spec = FOOTBALL_DATA_FILES.get(competition)
            comp_rows = [r for r in rows if r["competition_id"] == competition]
            if not spec or not comp_rows:
                continue
            market_rows = load_football_data_rows(competition, spec, list(BIG5_SEASONS))
            if not market_rows:
                results[competition] = {"status": "CSV_MISSING"}
                continue
            joined, diagnostics = join_manifest_to_market(comp_rows, market_rows)
            evaluation = eval_market_league(joined)
            evaluation["join"] = diagnostics
            results[competition] = evaluation
    # in-season leagues
    for competition in IN_SEASON_NATIONAL_LEAGUES:
        manifest_path = MANIFEST_DIR / f"inseason_pooled_fit__{competition}.jsonl"
        spec = FOOTBALL_DATA_FILES.get(competition)
        if not manifest_path.exists() or spec is None:
            continue
        rows = [json.loads(line) for line in manifest_path.open()]
        market_rows = load_football_data_rows(competition, spec, list(IN_SEASON_SEASONS))
        if not market_rows:
            results[competition] = {"status": "CSV_MISSING"}
            continue
        joined, diagnostics = join_manifest_to_market(rows, market_rows)
        evaluation = eval_market_league(joined)
        evaluation["join"] = diagnostics
        results[competition] = evaluation

    report = {
        "schema_version": "w2.market_baseline_eval.market_phase.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "provider_calls": 0,
        "devig_method": "proportional (1/odds normalized); overround reported",
        "results": results,
    }
    (OUT_DIR / "market_phase_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str)
    )
    _write_summary_md(report)
    return report


def _write_summary_md(report: dict) -> None:
    lines = [
        "# W2 模型 vs 市场基准对照(去 vig 收盘)",
        "",
        f"生成时间:{report['generated_at']}  ·  devig:proportional  ·  只读/零 provider calls",
        "",
        "| 联赛 | n(val joined) | 模型 LL | 市场 LL | 差距 "
        "| blend LL (w_mkt) | 先验 LL | join 率 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for comp, res in report["results"].items():
        if res.get("status") != "OK":
            lines.append(f"| {comp} | — | — | — | — | — | — | {res.get('status')} |")
            continue
        v = res["validation"]
        blend = res.get("blend", {})
        blend_text = (
            f"{blend.get('validation_blend', {}).get('log_loss', '—')}"
            f" (w={blend.get('w_market_fit_on_train', '—')})"
            if blend else "—"
        )
        lines.append(
            f"| {comp} | {v['fitted_calibrated']['n']} "
            f"| {v['fitted_calibrated']['log_loss']} "
            f"| {v['market_devig']['log_loss']} "
            f"| {res['gap_model_minus_market_log_loss']:+.4f} "
            f"| {blend_text} "
            f"| {v['baseline_prior']['log_loss']} "
            f"| {res['join']['join_rate']} |"
        )
    (OUT_DIR / "W2_MARKET_BASELINE_SUMMARY.md").write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("model", "market", "all"), default="all")
    args = parser.parse_args()
    if args.phase in ("model", "all"):
        report = run_model_phase()
        print(json.dumps(_model_digest(report), indent=2, ensure_ascii=False))
    if args.phase in ("market", "all"):
        report = run_market_phase()
        if report.get("status") == "WAITING_FOR_DATA":
            print(report["message"])
        else:
            print((OUT_DIR / "W2_MARKET_BASELINE_SUMMARY.md").read_text())
    return 0


def _model_digest(report: dict) -> list[dict]:
    digest = []
    for item in report["results"]:
        if item.get("status") not in ("OK", "OK_SLICE"):
            digest.append(item)
            continue
        entry = {
            "protocol": item["protocol"],
            "competition": item["competition"],
            "val_fitted": item["validation"]["fitted_calibrated"],
            "val_prior": item["validation"].get("baseline_prior"),
        }
        digest.append(entry)
    return digest


if __name__ == "__main__":
    raise SystemExit(main())
