"""Read-only VPS reconciliation. No Provider, notification, migration or restart."""

import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

out: Path
expected_sha: str
expected_schema: str
commands: list[dict] = []


def ssh(command):
    argv = (
        ["bash", "-lc", command]
        if os.environ.get("W2_MONITOR_LOCAL") == "1"
        else ["ssh", "w2-hk", command]
    )
    result = subprocess.run(argv, text=True, capture_output=True)
    commands.append(
        {
            "command": command,
            "exit": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    if result.returncode:
        raise RuntimeError("READ_ONLY_SSH_FAILED")
    return result.stdout.strip()


def sql(query):
    statement = "BEGIN READ ONLY; " + query + "; COMMIT"
    result = ssh(
        "docker exec w2-staging-postgres-1 psql -XqAt -v ON_ERROR_STOP=1 -U w2_user -d w2 -c "
        + shlex.quote(statement)
    )
    return result


def rows(query):
    return json.loads(
        sql("SELECT coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) FROM (" + query + ") t")  # noqa: S608 -- queries are fixed literals below, never CLI input
    )


def http(endpoint, port=18000):
    value = ssh(
        "curl -sS --max-time 60 -w '\\n%{http_code}' "
        + shlex.quote("http://127.0.0.1:" + str(port) + endpoint)
    )
    body, code = value.rsplit("\n", 1)
    try:
        body = json.loads(body)
    except json.JSONDecodeError:
        body = body[:200]
    return {"http": int(code), "body": body}


def pipeline_issues(state: dict) -> list[str]:
    """Persisted uncertainty is a fault even when no recommendations exist."""
    issues = []
    for row in state.get("provider_stage_counts", []):
        stage, status = row["stage"], row["state"]
        if status in {"SIDE_EFFECT_UNCERTAIN", "BLOCKED"}:
            issues.append("PROVIDER_STAGE_BLOCKED:" + stage + ":" + status)
        elif status not in {"ATTEMPTING", "DONE"}:
            issues.append("PROVIDER_STAGE_STATE_UNKNOWN:" + stage + ":" + status)
    if any(row["state"] == "ATTEMPTING" for row in state.get("stale_provider_stages", [])):
        issues.append("PROVIDER_STAGE_STALE_ATTEMPTING")
    if state.get("done_without_forward"):
        issues.append("TASK_DONE_WITHOUT_REFRESH_FORWARD")
    for row in state.get("failed_task_results", []):
        issues.append("TASK_RESULT_FAILED:" + str(row["stored_status"]))
    if any(row["status"] == "FAILED" for row in state.get("checkpoint_health", [])):
        issues.append("CHECKPOINT_FAILED")
    return sorted(set(issues))


def main() -> None:
    global out, expected_sha, expected_schema
    out = Path(sys.argv[1])
    expected_sha = sys.argv[2]
    expected_schema = sys.argv[3]
    assert not out.exists()
    state = {
        "captured_at": datetime.now(UTC).isoformat(),
        "expected_sha": expected_sha,
        "ssh_alias": "w2-hk",
        "read_only": True,
        "monitor_provider_calls": 0,
        "monitor_bark_calls": 0,
    }
    state["schema"] = sql("SELECT version_num FROM alembic_version")
    state["containers"] = {}
    for name in ("api", "web", "worker", "worker-heavy", "scheduler"):
        # Inspect only safe identity fields; never emit the full environment.
        command = (
            "docker inspect w2-staging-"
            + name
            + "-1 --format "
            + shlex.quote(
                '{"image":{{json .Image}},"ref":{{json .Config.Image}},"running":{{json '
                '.State.Running}},"health":{{json .State.Health.Status}}}'
            )
        )
        state["containers"][name] = json.loads(ssh(command))
    state["http"] = {
        path: http(path)
        for path in (
            "/ready",
            "/v1/version",
            "/v1/dashboard/intelligence-workspace/list",
            "/v1/dashboard/intelligence-workspace/validation",
            "/v1/dashboard/day-view",
        )
    }
    state["web_http"] = http("/", 18080)
    state["web_meta"] = http("/meta.json", 18080)
    state["legacy"] = {}
    for table in (
        "dynamic_prematch_evaluations",
        "dynamic_prematch_opportunities",
        "validation_samples",
        "validation_samples_calibrated",
    ):
        n, digest = sql(
            (  # noqa: S608 -- table comes exclusively from the fixed tuple above
                "SELECT count(*), md5(string_agg(h, '' ORDER BY h)) FROM (SELECT "
                "md5(to_jsonb(t)::text) h FROM "
            )
            + table
            + " t) s"
        ).split("|")
        state["legacy"][table] = {"count": int(n), "sorted_row_digest": digest}
    state["archived_unproven_sources"] = {
        table: rows("SELECT * FROM " + table)  # noqa: S608 -- fixed archive table whitelist
        for table in (
            "w2_legacy_unproven_matchday_endpoint_captures_0076",
            "w2_legacy_unproven_results_0076",
        )
    }
    state["legacy_ledger"] = rows(
        "SELECT to_jsonb(d)-ARRAY['decision_contract','frozen_terms','terms_hash'] AS "
        "original, decision_contract, frozen_terms, terms_hash FROM "
        "ah_ou_decision_ledger d WHERE model_version='m1' ORDER BY decision_id"
    )
    state["decisions"] = rows(
        "SELECT d.*, to_jsonb(s) AS settlement, to_jsonb(v) AS validation_sample, "
        "to_jsonb(r) AS trusted_result, to_jsonb(f) AS fixture_identity FROM "
        "ah_ou_decision_ledger d LEFT JOIN ah_ou_v3_settlement s USING(decision_id) LEFT "
        "JOIN ah_ou_v3_validation_sample v USING(decision_id) LEFT JOIN results r ON "
        "r.fixture_id='api_football:'||replace(d.fixture_id,'api_football:','') LEFT "
        "JOIN matchday_fixture_identities f ON "
        "f.fixture_id='api_football:'||replace(d.fixture_id,'api_football:','') WHERE "
        "d.decision_contract='w2.ah_ou_decision.v3.1' ORDER BY d.created_at DESC LIMIT "
        "1000"
    )
    state["capture_recent"] = rows(
        "SELECT "
        "capture_id,fixture_id,endpoint,provider_captured_at,capture_status,status_code,r"
        "aw_payload_sha256 FROM matchday_endpoint_captures ORDER BY provider_captured_at "
        "DESC LIMIT 50"
    )
    state["capture_last_hour"] = rows(
        "SELECT endpoint,capture_status,count(*),max(provider_captured_at) AS "
        "latest_captured_at FROM matchday_endpoint_captures WHERE "
        "provider_captured_at>now()-interval '1 hour' GROUP BY endpoint,capture_status "
        "ORDER BY endpoint,capture_status"
    )
    state["checkpoint_health"] = rows(
        "SELECT checkpoint,status,count(*),min(scheduled_at) AS "
        "earliest_scheduled_at,max(claim_expires_at) AS latest_claim_expiry FROM "
        "matchday_checkpoint_plans WHERE status IN ('DUE','RUNNING','FAILED') "
        "AND window_end>now()-interval '1 hour' GROUP BY "
        "checkpoint,status ORDER BY checkpoint,status"
    )
    state["f9_proof_counts"] = rows(
        "SELECT pit_proven, count(*) FROM team_xg_rolling_snapshot GROUP BY pit_proven"
    )
    state["notification_counts"] = rows(
        "SELECT event_type,delivery_status,count(*) FROM candidate_notification_outbox "
        "GROUP BY event_type,delivery_status ORDER BY event_type,delivery_status"
    )
    state["v3_daily"] = rows(
        "SELECT "
        "notification_event_id,event_type,delivery_status,created_at,payload->>'football_"
        "day' AS day,payload->>'selected' AS selected,payload->>'settled' AS "
        "settled,payload->>'pending' AS pending,payload->>'net_units' AS net_units FROM "
        "candidate_notification_outbox WHERE event_type='AH_OU_V3_DAILY_SETTLEMENT' "
        "ORDER BY created_at DESC LIMIT 10"
    )
    state["reasons"] = rows(
        "SELECT market,selected,skip_reason,count(*) FROM ah_ou_decision_ledger WHERE "
        "decision_contract='w2.ah_ou_decision.v3.1' GROUP BY market,selected,skip_reason "
        "ORDER BY market,selected,skip_reason"
    )
    state["provider_stage_counts"] = rows(
        "SELECT stage,state,count(*) FROM provider_side_effect_fence GROUP BY "
        "stage,state ORDER BY stage,state"
    )
    state["monitoring_schema_present"] = (
        sql(
            "SELECT to_regclass('ah_ou_v3_monitoring_fact') IS NOT NULL AND "
            "to_regclass('ah_ou_v3_monitoring_report') IS NOT NULL"
        )
        == "t"
    )
    if state["monitoring_schema_present"]:
        state["monitoring_progress"] = rows(
            "SELECT market,model_version,calibration_version,count(*) AS ft_facts, "
            "count(*) FILTER (WHERE payload->>'eligible'='true') AS eligible_settled, "
            "count(*) FILTER (WHERE payload->>'selected'='true') AS selected "
            "FROM ah_ou_v3_monitoring_fact GROUP BY market,model_version,calibration_version"
        )
        state["monitoring_reports"] = rows(
            "SELECT report_id,market,model_version,calibration_version,eligible_settled_count, "
            "payload_hash,created_at FROM ah_ou_v3_monitoring_report ORDER BY created_at DESC"
        )
    state["stale_provider_stages"] = rows(
        "SELECT task_id,stage,state,created_at,updated_at FROM "
        "provider_side_effect_fence WHERE state IN "
        "('ATTEMPTING','SIDE_EFFECT_UNCERTAIN','BLOCKED') AND updated_at<now()-interval "
        "'30 minutes' ORDER BY updated_at LIMIT 100"
    )
    state["done_without_forward"] = rows(
        "SELECT task_id FROM provider_side_effect_fence t WHERE t.stage='task' AND "
        "t.state='DONE' AND NOT EXISTS (SELECT 1 FROM provider_side_effect_fence f WHERE "
        "f.task_id=t.task_id AND f.stage='refresh_forward' AND f.state='DONE')"
    )
    state["failed_task_results"] = rows(
        "SELECT task_id,stored_result->>'status' AS stored_status,"
        "stored_result->'result'->'blockers' AS blockers,updated_at FROM "
        "provider_side_effect_fence WHERE stage='task' AND state='DONE' AND "
        "(stored_result->>'status' LIKE 'BLOCKED%' OR stored_result->>'status' "
        "IN ('FAILED','PARTIAL_FAILED')) ORDER BY updated_at DESC LIMIT 100"
    )
    state["old_events_pending"] = rows(
        "SELECT event_type,count(*) FROM candidate_notification_outbox WHERE event_type "
        "IN "
        "('DAILY_CANDIDATE_LIST','VALIDATION_SAMPLE_CONFIRMED','VALIDATION_SIGNAL','DAILY"
        "_SETTLEMENT') AND delivery_status IN ('PENDING','RETRY_PENDING') GROUP BY "
        "event_type"
    )
    state["role_source_read"] = sql(
        "SET LOCAL ROLE quant_asof_reader_role; SELECT count(*) FROM ah_ou_history_capture_sources"
    )
    deny_command = (
        "docker exec w2-staging-postgres-1 psql -XqAt -v ON_ERROR_STOP=1 -U w2_user -d "
        "w2 -c 'BEGIN READ ONLY; SET LOCAL ROLE quant_asof_reader_role; SELECT count(*) "
        "FROM results; COMMIT'"
    )
    deny_argv = (
        ["bash", "-lc", deny_command]
        if os.environ.get("W2_MONITOR_LOCAL") == "1"
        else ["ssh", "w2-hk", deny_command]
    )
    denied = subprocess.run(deny_argv, text=True, capture_output=True)
    state["role_result_denied"] = {
        "exit": denied.returncode,
        "stdout": denied.stdout,
        "stderr": denied.stderr,
    }
    issues = pipeline_issues(state)
    if state["schema"] != expected_schema:
        issues.append("SCHEMA_HEAD_CONFLICT")
    if any(
        not item["running"] or item["health"] != "healthy" for item in state["containers"].values()
    ):
        issues.append("SERVICE_NOT_HEALTHY")
    if state["http"]["/ready"]["http"] != 200:
        issues.append("READY_NOT_200")
    if state["http"]["/v1/version"]["body"].get("release_id") != expected_sha:
        issues.append("RELEASE_SHA_CONFLICT")
    if (
        state["web_meta"]["http"] != 200
        or state["web_meta"]["body"].get("web_git_sha") != expected_sha
    ):
        issues.append("WEB_SHA_CONFLICT")
    if (
        any(item["http"] != 200 for item in state["http"].values())
        or state["web_http"]["http"] != 200
    ):
        issues.append("PUBLIC_READ_FAILED")
    if denied.returncode == 0 or "permission denied" not in denied.stderr:
        issues.append("ASOF_ROLE_RESULT_READ_NOT_DENIED")
    baseline = json.loads((out.parent / "PRODUCTION_BEFORE.json").read_text())
    if state["legacy"] != baseline["legacy"]:
        issues.append("LEGACY_BUSINESS_ROWS_CHANGED")
    original_ledger = json.loads(
        (out.parent / "inputs/production_legacy_ledger_rows.json").read_text()
    )
    if [r["original"] for r in state["legacy_ledger"]] != original_ledger or any(
        r["decision_contract"] or r["frozen_terms"] or r["terms_hash"]
        for r in state["legacy_ledger"]
    ):
        issues.append("LEGACY_LEDGER_CHANGED_OR_UPGRADED")
    if state["old_events_pending"]:
        issues.append("OLD_EVENTS_PENDING_AFTER_SWITCH")
    selected = [r for r in state["decisions"] if r["selected"]]
    for d in selected:
        settlement, sample, result = d["settlement"], d["validation_sample"], d["trusted_result"]
        if not result:
            if settlement or sample:
                issues.append("POSTMATCH_WITHOUT_RESULT:" + d["decision_id"])
            continue
        if not settlement or not sample:
            issues.append("FT_POSTMATCH_PAIR_INCOMPLETE:" + d["decision_id"])
            continue
        hash_fields = (
            "decision_id",
            "fixture_id",
            "market",
            "schema_version",
            "terms_hash",
            "result_id",
            "result_hash",
            "result_raw_sha256",
            "result_capture_id",
            "home_goals",
            "away_goals",
            "outcome",
            "net_units",
        )
        independent_hash = hashlib.sha256(
            json.dumps(
                {key: settlement[key] for key in hash_fields},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        if independent_hash != settlement["settlement_hash"]:
            issues.append("SETTLEMENT_HASH_CONFLICT:" + d["decision_id"])
        terms = d["frozen_terms"]
        shared = {
            "fixture_id": d["fixture_id"],
            "market": d["market"],
            "terms_hash": d["terms_hash"],
            "result_hash": result["result_hash"],
        }
        for field, expected in shared.items():
            if settlement[field] != expected or sample[field] != expected:
                issues.append("POSTMATCH_FIELD_CONFLICT:" + field + ":" + d["decision_id"])
        for field, expected in {
            "selection": terms["selection"],
            "exact_line": terms["selected_line"],
            "decimal_odds": terms["entry_odds"],
        }.items():
            if sample[field] != str(expected):
                issues.append("VALIDATION_FIELD_CONFLICT:" + field + ":" + d["decision_id"])
        line, price = Decimal(terms["selected_line"]), Decimal(terms["entry_odds"])
        q = int(line * 4)
        assert line * 4 == q
        levels = [line, line] if q % 2 == 0 else [Decimal(q - 1) / 4, Decimal(q + 1) / 4]
        margin = Decimal(result["home_goals"] - result["away_goals"])
        if terms["selection"] == "AWAY":
            margin = -margin
        if d["market"] == "TOTALS":
            values = [Decimal(result["home_goals"] + result["away_goals"]) - n for n in levels]
            if terms["selection"] == "UNDER":
                values = [-v for v in values]
        else:
            values = [margin + n for n in levels]
        signed = sum((v > 0) - (v < 0) for v in values)
        outcome = {2: "WIN", 1: "HALF_WIN", 0: "PUSH", -1: "HALF_LOSS", -2: "LOSS"}[signed]
        if result["result_status"] in {"AET", "PEN"}:
            outcome = "VOID"
        net = {
            "WIN": price - 1,
            "HALF_WIN": (price - 1) / 2,
            "PUSH": Decimal(0),
            "HALF_LOSS": Decimal("-0.5"),
            "LOSS": Decimal(-1),
            "VOID": Decimal(0),
        }[outcome]
        if settlement["outcome"] != outcome or Decimal(settlement["net_units"]) != net:
            issues.append("INDEPENDENT_SETTLEMENT_CONFLICT:" + d["decision_id"])
        if (
            sample["settlement_hash"] != settlement["settlement_hash"]
            or Decimal(sample["net_units"]) != net
        ):
            issues.append("VALIDATION_SAMPLE_CONFLICT:" + d["decision_id"])
    # Independently reconcile the persisted decision identity with actual public
    # rows. Pending results remain pending; a missing scheduled daily report is
    # recorded separately until its documented football-day reporting window.
    state["decision_reconciliation"] = []
    public_by_day = {}
    details_by_fixture = {}
    for d in selected[:100]:
        terms = d["frozen_terms"]
        kickoff = datetime.fromisoformat(
            d["fixture_identity"]["kickoff_utc"].replace("Z", "+00:00")
        )
        local = kickoff.astimezone(ZoneInfo("Asia/Shanghai"))
        day = (local.date() if local.hour >= 12 else local.date() - timedelta(days=1)).isoformat()
        if day not in public_by_day:
            public_by_day[day] = http("/v1/dashboard/intelligence-workspace/list?date=" + day)
        fid = d["fixture_id"].removeprefix("api_football:")
        if fid not in details_by_fixture:
            details_by_fixture[fid] = http("/v1/dashboard/intelligence-workspace/matches/" + fid)
        home = public_by_day[day]
        detail = details_by_fixture[fid]
        home_rows = home["body"].get("today_recommendations", []) if home["http"] == 200 else []
        detail_rows = (
            detail["body"].get("ah_ou_v3_recommendations", []) if detail["http"] == 200 else []
        )
        home_matches = [r for r in home_rows if r["decision_id"] == d["decision_id"]]
        detail_matches = [r for r in detail_rows if r["decision_id"] == d["decision_id"]]
        entry = {
            "decision_id": d["decision_id"],
            "football_day": day,
            "home_row_count": len(home_matches),
            "detail_row_count": len(detail_matches),
            "result_present": bool(d["trusted_result"]),
            "settlement_present": bool(d["settlement"]),
            "sample_present": bool(d["validation_sample"]),
        }
        if len(home_matches) != 1 or len(detail_matches) != 1:
            issues.append("PUBLIC_DECISION_ROW_CONFLICT:" + d["decision_id"])
        else:
            for row in (home_matches[0], detail_matches[0]):
                if d["settlement"] and Decimal(str(row["net_units"])) != Decimal(
                    d["settlement"]["net_units"]
                ):
                    issues.append("PUBLIC_NET_UNITS_CONFLICT:" + d["decision_id"])
                elif not d["settlement"] and (
                    row.get("net_units") is not None or row.get("status") != "pending"
                ):
                    issues.append("PUBLIC_PENDING_CONFLICT:" + d["decision_id"])
        state["decision_reconciliation"].append(entry)
    state["public_days"] = public_by_day
    state["public_details"] = details_by_fixture
    state["issues"] = issues
    state["real_event_status"] = (
        "BLOCKED_PIPELINE"
        if issues
        else "PENDING_REAL_EVENT"
        if not selected
        else "PENDING_REAL_FT"
        if any(not d["trusted_result"] for d in selected)
        else "REAL_EVENTS_REQUIRE_PAGE_DAILY_RECONCILIATION"
    )
    state["commands"] = commands
    out.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(out),
                "schema": state["schema"],
                "sha": expected_sha,
                "issues": issues,
                "real_event_status": state["real_event_status"],
                "selected_count": len(selected),
            },
            ensure_ascii=False,
        )
    )
    raise SystemExit(bool(issues))


if __name__ == "__main__":
    main()
