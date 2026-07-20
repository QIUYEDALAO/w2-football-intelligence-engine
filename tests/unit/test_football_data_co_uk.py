from __future__ import annotations

import subprocess
import zipfile
from html import escape
from pathlib import Path

from w2.historical.football_data_co_uk import (
    PHASE_CLOSE,
    PHASE_PRE,
    build_football_data_audits,
    cover_bucket,
    discover_football_data_files,
    football_data_row,
    settle_home_ah,
    write_football_data_ingest_artifacts,
)

HEADER = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,"
    "B365H,B365D,B365A,B365CH,B365CD,B365CA,"
    "B365>2.5,B365<2.5,B365C>2.5,B365C<2.5,"
    "AHh,AHCh,B365AHH,B365AHA,B365CAHH,B365CAHA\n"
)


def test_header_detection_and_phase_semantics(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        HEADER
        + "E0,01/08/2020,15:00,Home One,Away One,2,1,H,"
        "2.1,3.2,3.4,2.0,3.1,3.6,1.9,1.9,1.8,2.0,-0.25,-0.5,1.9,1.9,2.0,1.8\n",
        encoding="utf-8",
    )

    files = discover_football_data_files(tmp_path)

    assert len(files) == 1
    assert files[0]["row_count"] == 1
    assert files[0]["odds_capability"]["phase_ready_rows"] == 1


def test_zip_member_detection(tmp_path: Path) -> None:
    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("nested/member.csv", HEADER + _row("E0", "1", "0", "-0.25", "-0.5"))

    files = discover_football_data_files(tmp_path)

    assert files[0]["archive_member"] == "nested/member.csv"
    assert files[0]["div_coverage"] == {"E0": 1}


def test_xlsx_sheet_detection(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_minimal_xlsx(
        path,
        HEADER.strip().split(","),
        _row("E0", "1", "0", "-0.25", "-0.5").strip().split(","),
    )

    files = discover_football_data_files(tmp_path)

    assert len(files) == 1
    assert files[0]["columns"][:6] == ["Div", "Date", "Time", "HomeTeam", "AwayTeam", "FTHG"]


def test_ahh_ahch_cohort_isolation_and_no_captured_at(tmp_path: Path) -> None:
    season = tmp_path / "2021"
    season.mkdir()
    path = season / "sample.csv"
    path.write_text(HEADER + _row("E0", "1", "0", "-0.25", "-0.5"), encoding="utf-8")

    audits = build_football_data_audits(tmp_path)
    f5 = audits["FOOTBALL_DATA_F5_AUDIT"]
    market = audits["FOOTBALL_DATA_MARKET_EVIDENCE_AUDIT"]

    assert f5["closing_canonical_facts"] == 1
    assert f5["pre_closing_canonical_facts"] == 1
    assert f5["captured_at"] is None
    assert market["evidence_status"] == "PHASE_BASED_MARKET_EVIDENCE"
    assert market["captured_at"] is None


def test_date_time_and_mtime_are_not_used_as_captured_at(tmp_path: Path) -> None:
    row = {
        "Div": "E0",
        "Date": "01/08/2020",
        "Time": "15:00",
        "HomeTeam": "Home One",
        "AwayTeam": "Away One",
        "FTHG": "1",
        "FTAG": "1",
        "FTR": "D",
    }

    adapted = football_data_row(
        row,
        source_sha="a" * 64,
        file_name="sample.csv",
        row_number=2,
        phase=PHASE_PRE,
    )

    assert adapted.capture_time_precision == "SOURCE_PHASE_ONLY"
    assert adapted.source_phase == PHASE_PRE
    assert adapted.date == "01/08/2020"


def test_quarter_line_settlement_and_push_denominator(tmp_path: Path) -> None:
    assert settle_home_ah(line_decimal("-0.25"), 1, 0) == "WIN"
    assert settle_home_ah(line_decimal("-0.75"), 1, 1) == "LOSS"
    assert settle_home_ah(line_decimal("0"), 1, 1) == "PUSH"
    assert cover_bucket("PUSH") is None

    path = tmp_path / "sample.csv"
    path.write_text(HEADER + _row("E0", "1", "1", "0", "0"), encoding="utf-8")

    f5 = build_football_data_audits(tmp_path)["FOOTBALL_DATA_F5_AUDIT"]

    assert f5["push_excluded_count"] == 2
    assert f5["f5_denominator_count"] == 0


def test_missing_ah_and_allsvenskan_separate_coverage(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text(
        HEADER.replace("AHh,AHCh,B365AHH,B365AHA,B365CAHH,B365CAHA", "")
        + "SWE,01/08/2020,15:00,Home One,Away One,1,0,H,"
        "2.1,3.2,3.4,2.0,3.1,3.6,1.9,1.9,1.8,2.0,\n",
        encoding="utf-8",
    )

    inventory = build_football_data_audits(tmp_path)["FOOTBALL_DATA_LOCAL_INVENTORY"]

    assert inventory["coverage_by_div"]["SWE"]["matches"] == 1
    assert "AH_NOT_AVAILABLE" in inventory["files"][0]["capabilities"]


def test_allsvenskan_alternate_schema_is_unsupported_not_f5(tmp_path: Path) -> None:
    path = tmp_path / "SWE.csv"
    path.write_text(
        "Country,League,Season,Date,Time,Home,Away,HG,AG,Res,B365CH,B365CD,B365CA\n"
        "SE,SW,2024,2024-04-01,18:00,Home One,Away One,1,0,H,2.0,3.2,3.5\n",
        encoding="utf-8",
    )

    audits = build_football_data_audits(tmp_path)
    inventory = audits["FOOTBALL_DATA_LOCAL_INVENTORY"]
    f5 = audits["FOOTBALL_DATA_F5_AUDIT"]

    assert inventory["unsupported_file_count"] == 1
    assert inventory["unsupported_files"][0]["has_ahh"] is False
    assert inventory["unsupported_files"][0]["has_ahch"] is False
    assert f5["total_matches"] == 0


def test_fixture_natural_identity_deterministic() -> None:
    row = {
        "Div": "E0",
        "Date": "01/08/2020",
        "Time": "15:00",
        "HomeTeam": "Home One",
        "AwayTeam": "Away One",
        "FTHG": "1",
        "FTAG": "0",
        "FTR": "H",
    }
    first = football_data_row(
        row,
        source_sha="a" * 64,
        file_name="sample.csv",
        row_number=2,
        phase=PHASE_CLOSE,
    )
    second = football_data_row(
        row,
        source_sha="a" * 64,
        file_name="sample.csv",
        row_number=2,
        phase=PHASE_CLOSE,
    )

    assert first.fixture_natural_identity == second.fixture_natural_identity


def test_raw_private_data_not_tracked() -> None:
    root = Path(__file__).resolve().parents[2]
    tracked = subprocess.check_output(["git", "ls-files"], cwd=root, text=True).splitlines()
    raw_suffixes = (".csv", ".csv.gz", ".zip", ".xlsx", ".xls")
    offenders = [
        path
        for path in tracked
        if "football-data" in path.lower() and path.lower().endswith(raw_suffixes)
    ]

    assert offenders == []


def test_ingest_artifacts_build_canonical_outputs(tmp_path: Path) -> None:
    season = tmp_path / "2021"
    season.mkdir()
    path = season / "sample.csv"
    path.write_text(HEADER + _row("E0", "1", "0", "-0.25", "-0.5"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    result = write_football_data_ingest_artifacts(tmp_path, artifact_root)
    manifest = result["manifest"]
    coverage = result["f5_coverage"]
    baseline = result["market_baseline_candidate"]

    assert manifest["source_snapshot_count"] == 2
    assert manifest["closing_ah_fact_count"] == 1
    assert manifest["pre_closing_ah_fact_count"] == 1
    assert manifest["phase_market_evidence_count"] == 1
    assert manifest["f5_ready_count"] == 2
    assert coverage["query_contract"] == {"team": True, "before_kickoff": True, "limit": True}
    assert baseline["status"] == "READY_CANDIDATE"
    assert baseline["exact_captured_at"] is False
    assert (artifact_root / "FOOTBALL_DATA_CLOSING_AH_FACTS.jsonl").is_file()


def test_ingest_rejects_duplicate_fixture_per_phase(tmp_path: Path) -> None:
    season = tmp_path / "2021"
    season.mkdir()
    row = _row("E0", "1", "0", "-0.25", "-0.5")
    (season / "sample.csv").write_text(HEADER + row + row, encoding="utf-8")

    manifest = write_football_data_ingest_artifacts(tmp_path, tmp_path / "artifacts")[
        "manifest"
    ]

    assert manifest["closing_ah_fact_count"] == 1
    assert manifest["pre_closing_ah_fact_count"] == 1


def _row(div: str, home_goals: str, away_goals: str, ahh: str, ahch: str) -> str:
    return (
        f"{div},01/08/2020,15:00,Home One,Away One,{home_goals},{away_goals},H,"
        f"2.1,3.2,3.4,2.0,3.1,3.6,1.9,1.9,1.8,2.0,"
        f"{ahh},{ahch},1.9,1.9,2.0,1.8\n"
    )


def line_decimal(value: str):
    from decimal import Decimal

    return Decimal(value)


def _write_minimal_xlsx(path: Path, header: list[str], row: list[str]) -> None:
    strings = header + row
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(f"<si><t>{escape(item)}</t></si>" for item in strings)
        + "</sst>"
    )
    cells = []
    idx = 0
    for row_num, values in enumerate((header, row), start=1):
        cols = []
        for col_num, _value in enumerate(values):
            cols.append(f'<c r="{chr(65 + col_num)}{row_num}" t="s"><v>{idx}</v></c>')
            idx += 1
        cells.append(f'<row r="{row_num}">{"".join(cols)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(cells)}</sheetData></worksheet>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
