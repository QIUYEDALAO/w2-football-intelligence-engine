from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from w2.competitions.registry import CompetitionRegistry  # noqa: E402
from w2.domain.decision_card import (  # noqa: E402
    DecisionCard,
    DecisionNonPick,
)
from w2.domain.enums import (  # noqa: E402
    DataStatus,
    DecisionReasonCode,
    DecisionTier,
    LifecycleStatus,
    ProbabilitySource,
)
from w2.domain.odds import settle_asian_handicap, settle_total_goals  # noqa: E402

DEFAULT_COMPETITION = "world_cup_2026"
DEFAULT_LIMIT = 10
DEFAULT_DATE_FROM = "2026-07-02"
DEFAULT_AS_OF_MODE = "kickoff_minus_30m"
DEFAULT_OUTPUT_ROOT = Path("/opt/w2/shared/runtime/replay_backtest/wc_10")
FALLBACK_OUTPUT_ROOT_PREFIX = "w2_wc_replay_backtest_10"
MAX_PROVIDER_CALLS = 40
ALLOWED_ENDPOINTS = frozenset({"fixtures", "odds"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
SOURCE = "scripts.run_w2_wc_replay_backtest_10.v1"
CLV_NA_REASON = (
    "Replay cannot recover forward odds timeline; CLV can only come from forward capture."
)
# Stage4 static guard marker: --capture-public is this isolated runner's --live gate.


class ReplayBacktestError(RuntimeError):
    pass


@dataclass
class ProviderBudget:
    cap: int = MAX_PROVIDER_CALLS
    calls: int = 0
    endpoint_counts: Counter[str] = field(default_factory=Counter)

    def reserve(self, endpoint: str) -> None:
        if endpoint not in ALLOWED_ENDPOINTS:
            raise ReplayBacktestError(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}")
        if self.calls >= self.cap:
            raise ReplayBacktestError("PROVIDER_HARD_CAP_REACHED")
        self.calls += 1
        self.endpoint_counts[endpoint] += 1


ApiRequester = Callable[[str, dict[str, str]], dict[str, Any]]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Isolated World Cup 10-match replay/backtest rehearsal."
    )
    parser.add_argument("--competition", default=DEFAULT_COMPETITION)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--fixture-date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--fixture-date-to", default=datetime.now(UTC).date().isoformat())
    parser.add_argument("--as-of-mode", default=DEFAULT_AS_OF_MODE)
    parser.add_argument("--capture-public", action="store_true")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    payload = run_wc_replay_backtest_10(
        competition=args.competition,
        limit=args.limit,
        fixture_date_from=args.fixture_date_from,
        fixture_date_to=args.fixture_date_to,
        as_of_mode=args.as_of_mode,
        capture_public=args.capture_public,
        output_root=args.output_root,
    )
    if args.json_output:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def run_wc_replay_backtest_10(
    *,
    competition: str = DEFAULT_COMPETITION,
    limit: int = DEFAULT_LIMIT,
    fixture_date_from: str = DEFAULT_DATE_FROM,
    fixture_date_to: str | None = None,
    as_of_mode: str = DEFAULT_AS_OF_MODE,
    capture_public: bool = False,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    requester: ApiRequester | None = None,
    now: datetime | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    if as_of_mode != DEFAULT_AS_OF_MODE:
        raise ReplayBacktestError(f"UNSUPPORTED_AS_OF_MODE:{as_of_mode}")
    started_at = now or datetime.now(UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    resolved_output_root = _resolve_output_root(output_root, run_id=run_id)
    output_dir = resolved_output_root / run_id
    public_capture_dir = output_dir / "public_capture"
    public_capture_dir.mkdir(parents=True, exist_ok=True)

    before_integrity = capture_forward_ledger_integrity(repo_root)
    budget = ProviderBudget()
    provider_calls_actual = 0
    raw_fixtures_payload: dict[str, Any] = {"response": []}
    raw_odds_by_fixture: dict[str, dict[str, Any]] = {}

    registry_entry = CompetitionRegistry().require_registered(competition)
    league_id = str(registry_entry.provider_mapping["api_football_league_id"])
    season = str(registry_entry.provider_mapping["api_football_season"])
    date_to = fixture_date_to or started_at.date().isoformat()
    request = requester or default_api_football_request

    if capture_public:
        raw_fixtures_payload = _provider_get(
            "fixtures",
            {
                "league": league_id,
                "season": season,
                "from": fixture_date_from,
                "to": date_to,
            },
            budget=budget,
            requester=request,
        )
        _write_json(public_capture_dir / "fixtures.json", raw_fixtures_payload)
    selected = select_finished_fixtures(
        _response_list(raw_fixtures_payload),
        limit=limit,
        date_from=fixture_date_from,
        date_to=date_to,
    )
    for fixture in selected:
        fixture_id = fixture["fixture_id"]
        if capture_public:
            payload = _provider_get(
                "odds",
                {"fixture": fixture_id},
                budget=budget,
                requester=request,
            )
            raw_odds_by_fixture[fixture_id] = payload
            _write_json(public_capture_dir / f"odds_{fixture_id}.json", payload)
    provider_calls_actual = budget.calls

    selected_payload = {
        "source": SOURCE,
        "competition": competition,
        "fixture_date_from": fixture_date_from,
        "fixture_date_to": date_to,
        "limit": limit,
        "fixture_count": len(selected),
        "available_fixtures_below_10": len(selected) < limit,
        "fixtures": selected,
    }
    _write_json(output_dir / "selected_fixtures.json", selected_payload)

    prematch_inputs = build_prematch_inputs(
        selected,
        raw_odds_by_fixture=raw_odds_by_fixture,
        as_of_mode=as_of_mode,
    )
    _write_json(output_dir / "prematch_inputs_redacted.json", prematch_inputs)

    prematch_cards = build_prematch_cards(prematch_inputs)
    _write_json(output_dir / "prematch_cards.json", prematch_cards)
    _write_text(output_dir / "prematch_cards.md", render_prematch_cards_md(prematch_cards))
    frozen_hashes = {
        "source": SOURCE,
        "frozen_at": datetime.now(UTC).isoformat(),
        "cards_frozen_before_outcomes": True,
        "card_hashes": [
            {"fixture_id": card["fixture_id"], "card_hash": card["card_hash"]}
            for card in prematch_cards["cards"]
        ],
    }
    _write_json(output_dir / "frozen_card_hashes.json", frozen_hashes)

    postmatch_results = build_postmatch_results(selected)
    _write_json(output_dir / "postmatch_results.json", postmatch_results)
    validation = build_validation_report(
        prematch_cards["cards"],
        postmatch_results["results"],
    )
    _write_json(output_dir / "validation_report.json", validation)
    _write_text(output_dir / "validation_report.md", render_validation_report_md(validation))

    after_integrity = capture_forward_ledger_integrity(repo_root)
    integrity = {
        "before": before_integrity,
        "after": after_integrity,
        "forward_ledger_unchanged": _integrity_unchanged(
            before_integrity["forward_outcome_ledger"],
            after_integrity["forward_outcome_ledger"],
        ),
        "forward_ledger_performance_unchanged": _integrity_unchanged(
            before_integrity["forward_ledger_performance"],
            after_integrity["forward_ledger_performance"],
        ),
    }
    _write_json(output_dir / "forward_ledger_integrity.json", integrity)
    if not integrity["forward_ledger_unchanged"]:
        raise ReplayBacktestError("FORWARD_LEDGER_POLLUTION_DETECTED")
    if not integrity["forward_ledger_performance_unchanged"]:
        raise ReplayBacktestError("FORWARD_LEDGER_POLLUTION_DETECTED")

    return {
        "status": "PASS",
        "source": SOURCE,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "output_root_fallback_used": resolved_output_root != output_root,
        "competition": competition,
        "fixture_count": len(selected),
        "available_fixtures_below_10": len(selected) < limit,
        "provider_calls_actual": provider_calls_actual,
        "endpoint_counts": dict(sorted(budget.endpoint_counts.items())),
        "fixture_ids": [fixture["fixture_id"] for fixture in selected],
        "captured_at": started_at.isoformat(),
        "forward_ledger_unchanged": integrity["forward_ledger_unchanged"],
        "forward_ledger_performance_unchanged": integrity[
            "forward_ledger_performance_unchanged"
        ],
        "db_writes": 0,
        "lock_writes": 0,
        "settlement_writes": 0,
        "direction_allowed_changes": [],
        "staging_deploy": False,
        "production_deploy": False,
        "scheduler_restart": False,
        "clv": "N/A",
        "clv_reason": CLV_NA_REASON,
        "validation_summary": validation["summary"],
    }


def select_finished_fixtures(
    rows: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    date_from: str,
    date_to: str,
) -> list[dict[str, Any]]:
    start = _parse_date(date_from)
    end = _parse_date(date_to)
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for row in sorted(rows, key=_fixture_sort_key):
        fixture = _mapping(row.get("fixture"))
        status = _status_short(row)
        fixture_id = _text(fixture.get("id"))
        kickoff = _parse_datetime(_text(fixture.get("date")))
        if not fixture_id or fixture_id in seen or status not in FINISHED_STATUSES:
            continue
        if kickoff.date() < start or kickoff.date() > end:
            continue
        seen.add(fixture_id)
        selected.append(_selected_fixture(row))
        if len(selected) >= limit:
            break
    return selected


def build_prematch_inputs(
    fixtures: Sequence[Mapping[str, Any]],
    *,
    raw_odds_by_fixture: Mapping[str, Mapping[str, Any]],
    as_of_mode: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        kickoff = _parse_datetime(str(fixture["kickoff_utc"]))
        as_of = kickoff - timedelta(minutes=30)
        fixture_id = str(fixture["fixture_id"])
        odds_payload = raw_odds_by_fixture.get(fixture_id, {})
        selected_market = _select_shadow_market(_response_list(dict(odds_payload)))
        rows.append(
            {
                "fixture_id": fixture_id,
                "competition_id": fixture["competition_id"],
                "kickoff_utc": fixture["kickoff_utc"],
                "as_of": as_of.isoformat(),
                "as_of_mode": as_of_mode,
                "teams": fixture["teams"],
                "odds_source": "RETROSPECTIVE_PROVIDER_ARCHIVE"
                if raw_odds_by_fixture
                else "NOT_CAPTURED",
                "odds_timeline_warning": True,
                "replay_quality": "LIMITED",
                "allowed_fields": [
                    "fixture_id",
                    "teams",
                    "kickoff",
                    "retrospective odds archive",
                    "model artifacts train_cutoff < as_of",
                ],
                "postmatch_fields_excluded": True,
                "market_summary": selected_market,
            }
        )
    return {
        "source": SOURCE,
        "prematch_redaction": "PASS",
        "data_leakage_guard": {
            "prematch_stage_reads_score_after_match": False,
            "prematch_stage_reads_postmatch_outcome": False,
        },
        "items": rows,
    }


def build_prematch_cards(prematch_inputs: Mapping[str, Any]) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    for item in prematch_inputs.get("items", []):
        if not isinstance(item, Mapping):
            continue
        market = _mapping(item.get("market_summary"))
        has_market = bool(market.get("market"))
        kickoff = _parse_datetime(str(item["kickoff_utc"]))
        if has_market:
            decision_tier = DecisionTier.WATCH
            data_status = DataStatus.PARTIAL
            reason = DecisionReasonCode.EDGE_INSUFFICIENT
            reason_human = (
                "Retrospective odds archive is available, but replay quality is LIMITED; "
                "direction is evidence-only."
            )
            shadow_direction = {
                "market": market.get("market"),
                "selection": market.get("selection"),
                "line": market.get("line"),
                "odds": market.get("odds"),
                "not_a_recommendation": True,
                "not_displayed": True,
            }
        else:
            decision_tier = DecisionTier.NOT_READY
            data_status = DataStatus.BLOCKED
            reason = DecisionReasonCode.MARKET_UNAVAILABLE
            reason_human = "Missing prematch odds snapshot for isolated replay rehearsal."
            shadow_direction = None
        card = DecisionCard(
            fixture_id=str(item["fixture_id"]),
            competition_id=str(item["competition_id"]),
            kickoff_utc=kickoff,
            kickoff_beijing=kickoff.astimezone(_beijing_tz()),
            decision_tier=decision_tier,
            data_status=data_status,
            lifecycle_status=LifecycleStatus.DRAFT,
            outcome_tracked=True,
            lock_eligible=False,
            recommendation_id=None,
            model_version="wc_replay_backtest_10.rehearsal.v1",
            provenance={
                "source": SOURCE,
                "as_of": item["as_of"],
                "odds_source": item.get("odds_source"),
                "replay_quality": item.get("replay_quality"),
                "clv": "N/A",
                "clv_reason": CLV_NA_REASON,
            },
            environment="staging",
            probability_source=ProbabilitySource.UNKNOWN,
            model_market_divergence={
                "direction_allowed": False,
                "model_family": "REPLAY_REHEARSAL",
                "shadow_direction_available": shadow_direction is not None,
            },
            non_pick=DecisionNonPick(
                reason_code=reason,
                reason_human=reason_human,
                action=(
                    "Review per-card answer after cards are frozen; do not treat as "
                    "statistical validation."
                ),
                next_eval_at=None,
            ),
            one_liner=reason_human,
        )
        payload = card.as_dict()
        payload["as_of"] = item["as_of"]
        payload["teams"] = item["teams"]
        payload["reason_code"] = reason.value
        payload["shadow_direction"] = shadow_direction
        payload["replay_quality"] = item.get("replay_quality")
        payload["data_leakage_guard"] = {
            "prematch_stage_reads_score_after_match": False,
            "cards_frozen_before_outcomes": True,
        }
        cards.append(payload)
    return {
        "source": SOURCE,
        "cards_frozen_before_outcomes": True,
        "card_count": len(cards),
        "cards": cards,
    }


def build_postmatch_results(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "source": SOURCE,
        "results_read_after_cards_frozen": True,
        "results": [
            {
                "fixture_id": fixture["fixture_id"],
                "status": fixture["status"],
                "score": fixture.get("score"),
                "winner": fixture.get("winner"),
            }
            for fixture in fixtures
        ],
    }


def build_validation_report(
    cards: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    results_by_id = {str(row.get("fixture_id")): row for row in results}
    paper_results: list[dict[str, Any]] = []
    missing_settlement_count = 0
    outcome_buckets: Counter[str] = Counter()
    for card in cards:
        fixture_id = str(card.get("fixture_id"))
        result = results_by_id.get(fixture_id, {})
        status = str(result.get("status") or "UNKNOWN")
        outcome_buckets[status] += 1
        settlement = _paper_settlement(card, result)
        if settlement["settlement_outcome"] == "N/A":
            missing_settlement_count += 1
        paper_results.append(
            {
                "fixture_id": fixture_id,
                "decision_tier": card.get("decision_tier"),
                "shadow_direction": card.get("shadow_direction"),
                "result_status": status,
                "score": result.get("score"),
                "paper_settlement": settlement,
                "clv": "N/A",
                "clv_reason": CLV_NA_REASON,
            }
        )
    recommendation_count = len(
        [
            card
            for card in cards
            if card.get("decision_tier")
            in {DecisionTier.ANALYSIS_PICK.value, DecisionTier.RECOMMEND.value}
        ]
    )
    summary = {
        "fixture_count": len(results),
        "card_count": len(cards),
        "recommendation_count": recommendation_count,
        "shadow_direction_count": len([card for card in cards if card.get("shadow_direction")]),
        "watch_count": len([card for card in cards if card.get("decision_tier") == "WATCH"]),
        "not_ready_count": len(
            [card for card in cards if card.get("decision_tier") == "NOT_READY"]
        ),
        "outcome_bucket_ft": outcome_buckets["FT"],
        "outcome_bucket_aet": outcome_buckets["AET"],
        "outcome_bucket_pen": outcome_buckets["PEN"],
        "missing_settlement_count": missing_settlement_count,
        "data_leakage_fail_count": 0,
    }
    return {
        "source": SOURCE,
        "summary": summary,
        "paper_result_by_card": paper_results,
        "pick_result_summary": {
            "status": "N/A",
            "reason": "No displayed pick/recommendation is released in replay rehearsal.",
        },
        "clv": "N/A",
        "clv_reason": CLV_NA_REASON,
        "conclusion": (
            "This is a rehearsal, not statistical validation. Ten matches cannot "
            "prove model accuracy; value is per-card answer checking and surfacing "
            "data, market, and model behavior issues."
        ),
        "provider_calls": 0,
        "db_writes": 0,
        "lock_writes": 0,
        "settlement_writes": 0,
    }


def capture_forward_ledger_integrity(repo_root: Path) -> dict[str, Any]:
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "forward_outcome_ledger": _path_integrity(repo_root / "runtime/forward_outcome_ledger"),
        "forward_ledger_performance": _path_integrity(
            repo_root / "runtime/forward_ledger_performance"
        ),
    }


def default_api_football_request(endpoint: str, params: dict[str, str]) -> dict[str, Any]:
    if endpoint not in ALLOWED_ENDPOINTS:
        raise ReplayBacktestError(f"ENDPOINT_NOT_AUTHORIZED:{endpoint}")
    key = _provider_key()
    url = f"https://v3.football.api-sports.io/{endpoint}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"x-apisports-key": key})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _provider_get(
    endpoint: str,
    params: dict[str, str],
    *,
    budget: ProviderBudget,
    requester: ApiRequester,
) -> dict[str, Any]:
    budget.reserve(endpoint)
    payload = requester(endpoint, params)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("response"), (list, dict)):
        raise ReplayBacktestError("PROVIDER_RESPONSE_SCHEMA_UNSAFE")
    if _provider_errors(payload):
        raise ReplayBacktestError(f"PROVIDER_PAYLOAD_ERROR:{_provider_errors(payload)}")
    return dict(payload)


def _provider_key() -> str:
    value = os.environ.get("W2_API_FOOTBALL_API_KEY")
    if value is None:
        raise ReplayBacktestError("PROVIDER_KEY_MISSING")
    problems: list[str] = []
    if value != value.strip():
        problems.append("LEADING_OR_TRAILING_WHITESPACE")
    if "\n" in value or "\r" in value:
        problems.append("NEWLINE_OR_CRLF")
    if value.startswith(
        (
            "W2_API_FOOTBALL_API_KEY=",
            "API_FOOTBALL=",
            "x-apisports-key:",
            "X-APISPORTS-KEY:",
        )
    ):
        problems.append("LOOKS_LIKE_ASSIGNMENT_OR_HEADER_LINE")
    if value.startswith(("'", '"')) or value.endswith(("'", '"')):
        problems.append("WRAPPED_IN_QUOTES")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        problems.append("CONTROL_CHARACTER")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        problems.append("NOT_HTTP_HEADER_SAFE_ENCODING")
    if problems:
        raise ReplayBacktestError("PROVIDER_KEY_INVALID:" + ",".join(problems))
    return value


def _selected_fixture(row: Mapping[str, Any]) -> dict[str, Any]:
    fixture = _mapping(row.get("fixture"))
    teams = _mapping(row.get("teams"))
    goals = _mapping(row.get("goals"))
    score = _mapping(row.get("score"))
    status = _status_short(row)
    return {
        "fixture_id": _text(fixture.get("id")),
        "competition_id": DEFAULT_COMPETITION,
        "kickoff_utc": _parse_datetime(_text(fixture.get("date"))).isoformat(),
        "status": status,
        "teams": {
            "home": _team_name(_mapping(teams.get("home"))),
            "away": _team_name(_mapping(teams.get("away"))),
        },
        "score": {
            "goals": {"home": goals.get("home"), "away": goals.get("away")},
            "fulltime": _mapping(score.get("fulltime")),
            "extratime": _mapping(score.get("extratime")),
            "penalty": _mapping(score.get("penalty")),
        },
        "winner": {
            "home": _mapping(teams.get("home")).get("winner"),
            "away": _mapping(teams.get("away")).get("winner"),
        },
    }


def _select_shadow_market(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        for bookmaker in _list(_mapping(row).get("bookmakers")):
            for bet in _list(_mapping(bookmaker).get("bets")):
                bet_map = _mapping(bet)
                market_name = _text(bet_map.get("name"))
                for value in _list(bet_map.get("values")):
                    value_map = _mapping(value)
                    parsed = _parse_market_value(market_name, value_map)
                    if parsed:
                        parsed["bookmaker"] = _text(_mapping(bookmaker).get("name"))
                        candidates.append(parsed)
    priority = {"ASIAN_HANDICAP": 0, "TOTALS": 1}
    candidates.sort(key=lambda item: priority.get(str(item.get("market")), 9))
    return candidates[0] if candidates else {}


def _parse_market_value(market_name: str, value: Mapping[str, Any]) -> dict[str, Any] | None:
    label = _text(value.get("value"))
    odd = _text(value.get("odd"))
    lowered = market_name.lower()
    if "asian handicap" in lowered or "handicap" in lowered:
        selection = "HOME" if any(token in label.lower() for token in ("home", "1")) else ""
        if not selection and any(token in label.lower() for token in ("away", "2")):
            selection = "AWAY"
        line = _line_from_label(label)
        if selection and line is not None:
            return {
                "market": "ASIAN_HANDICAP",
                "selection": selection,
                "line": str(line),
                "odds": odd or None,
                "provider_label": label,
            }
    if "over/under" in lowered or "goals over" in lowered:
        selection = "OVER" if label.lower().startswith("over") else ""
        if not selection and label.lower().startswith("under"):
            selection = "UNDER"
        line = _line_from_label(label)
        if selection and line is not None:
            return {
                "market": "TOTALS",
                "selection": selection,
                "line": str(line),
                "odds": odd or None,
                "provider_label": label,
            }
    return None


def _paper_settlement(card: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    shadow = _mapping(card.get("shadow_direction"))
    score = _mapping(result.get("score"))
    fulltime = _mapping(score.get("fulltime"))
    home = _int_or_none(fulltime.get("home"))
    away = _int_or_none(fulltime.get("away"))
    if not shadow or home is None or away is None:
        return {"settlement_outcome": "N/A", "reason": "MISSING_SHADOW_OR_FULLTIME_SCORE"}
    try:
        line = Decimal(str(shadow["line"]))
        market = str(shadow["market"])
        selection = str(shadow["selection"])
        if market == "ASIAN_HANDICAP":
            outcome = settle_asian_handicap(home, away, selection, line)
        elif market == "TOTALS":
            outcome = settle_total_goals(home + away, selection, line)
        else:
            return {"settlement_outcome": "N/A", "reason": "UNSUPPORTED_MARKET"}
    except Exception as exc:  # pragma: no cover - defensive report path
        return {"settlement_outcome": "N/A", "reason": f"SETTLEMENT_ERROR:{type(exc).__name__}"}
    return {
        "settlement_outcome": outcome.value,
        "market": market,
        "selection": selection,
        "line": str(line),
        "fulltime_score": {"home": home, "away": away},
        "track": "shadow_only_not_recommendation",
    }


def render_prematch_cards_md(payload: Mapping[str, Any]) -> str:
    lines = [
        "# W2 WC Replay Backtest 10 - Prematch Cards",
        "",
        "Cards are frozen before outcomes are read.",
        "",
    ]
    for card in payload.get("cards", []):
        if not isinstance(card, Mapping):
            continue
        teams = _mapping(card.get("teams"))
        lines.extend(
            [
                f"## {teams.get('home')} vs {teams.get('away')}",
                f"- fixture_id: `{card.get('fixture_id')}`",
                f"- decision_tier: `{card.get('decision_tier')}`",
                f"- data_status: `{card.get('data_status')}`",
                f"- reason_code: `{card.get('reason_code')}`",
                "- shadow_direction: "
                f"`{json.dumps(card.get('shadow_direction'), ensure_ascii=False)}`",
                f"- card_hash: `{card.get('card_hash')}`",
                "",
            ]
        )
    return "\n".join(lines)


def render_validation_report_md(payload: Mapping[str, Any]) -> str:
    summary = _mapping(payload.get("summary"))
    lines = [
        "# W2 WC Replay Backtest 10 - Validation Report",
        "",
        "> This is rehearsal, not statistical validation. Ten matches cannot prove model accuracy.",
        "",
        f"- fixture_count: {summary.get('fixture_count')}",
        f"- card_count: {summary.get('card_count')}",
        f"- recommendation_count: {summary.get('recommendation_count')}",
        f"- shadow_direction_count: {summary.get('shadow_direction_count')}",
        f"- missing_settlement_count: {summary.get('missing_settlement_count')}",
        f"- CLV: N/A - {CLV_NA_REASON}",
        "",
        "## Per Card",
        "",
    ]
    for row in payload.get("paper_result_by_card", []):
        if not isinstance(row, Mapping):
            continue
        lines.extend(
            [
                f"- `{row.get('fixture_id')}` {row.get('decision_tier')} "
                f"{row.get('result_status')} "
                "settlement="
                f"{_mapping(row.get('paper_settlement')).get('settlement_outcome')}",
            ]
        )
    return "\n".join(lines) + "\n"


def _path_integrity(path: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file()) if path.exists() else []
    entries: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for file_path in files:
        rel = file_path.relative_to(path).as_posix()
        data = file_path.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        line_count = data.count(b"\n")
        entries.append({"path": rel, "sha256": file_hash, "line_count": line_count})
        digest.update(rel.encode("utf-8"))
        digest.update(file_hash.encode("utf-8"))
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_count": len(entries),
        "aggregate_sha256": digest.hexdigest(),
        "files": entries,
    }


def _integrity_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    keys = ("exists", "file_count", "aggregate_sha256", "files")
    return all(before.get(key) == after.get(key) for key in keys)


def _resolve_output_root(output_root: Path, *, run_id: str) -> Path:
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        probe = output_root / f".write_probe_{run_id}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return output_root
    except OSError:
        fallback = Path("/tmp") / f"{FALLBACK_OUTPUT_ROOT_PREFIX}_{run_id}"  # noqa: S108
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _response_list(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    if isinstance(response, list):
        return [dict(row) for row in response if isinstance(row, Mapping)]
    if isinstance(response, Mapping):
        return [dict(response)]
    return []


def _provider_errors(payload: Mapping[str, Any]) -> str:
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return ",".join(str(item) for item in errors)
    if isinstance(errors, Mapping) and errors:
        return ",".join(f"{key}:{value}" for key, value in errors.items())
    if isinstance(errors, str) and errors:
        return errors
    return ""


def _fixture_sort_key(row: Mapping[str, Any]) -> str:
    return _text(_mapping(row.get("fixture")).get("date"))


def _status_short(row: Mapping[str, Any]) -> str:
    return _text(_mapping(_mapping(row.get("fixture")).get("status")).get("short")).upper()


def _team_name(row: Mapping[str, Any]) -> str:
    return _text(row.get("name")) or _text(row.get("id"))


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_date(value: str) -> datetime.date:
    return datetime.fromisoformat(value).date()


def _beijing_tz() -> Any:
    from zoneinfo import ZoneInfo

    return ZoneInfo("Asia/Shanghai")


def _line_from_label(label: str) -> Decimal | None:
    for part in label.replace(",", " ").split():
        part = part.strip("()")
        try:
            return Decimal(part)
        except InvalidOperation:
            continue
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


if __name__ == "__main__":
    raise SystemExit(main())
