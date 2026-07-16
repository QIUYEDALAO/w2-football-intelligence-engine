from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CACHE_MAX_ENTRIES = 64
_CACHE_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class FrozenCaptureLookup:
    fixture_id: str
    requested_capture_hash: str
    capture: Mapping[str, Any] | None
    fixture_records: tuple[Mapping[str, Any], ...]
    source_status: str
    corruption_count: int
    matched_file: str | None
    scanned_file_count: int
    scanned_record_count: int
    reason: str | None


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    value: FrozenCaptureLookup


_cache_lock = threading.Lock()
_cache: OrderedDict[tuple[object, ...], _CacheEntry] = OrderedDict()
_inflight: dict[tuple[object, ...], threading.Event] = {}


def clear_frozen_capture_cache() -> None:
    with _cache_lock:
        _cache.clear()
        _inflight.clear()


def frozen_ledger_fingerprint(runtime_root: Path) -> str:
    """Return a content-change fingerprint without reading ledger payloads."""
    return _ledger_fingerprint(_ledger_files(runtime_root.resolve()))


def find_frozen_capture(
    runtime_root: Path,
    *,
    fixture_id: str,
    capture_hash: str,
    estimate_id: str | None = None,
    max_fixture_records: int = 512,
    max_line_bytes: int = 4 * 1024 * 1024,
) -> FrozenCaptureLookup:
    root = runtime_root.resolve()
    files = _ledger_files(root)
    fingerprint = _ledger_fingerprint(files)
    key: tuple[object, ...] = (
        str(root),
        str(fixture_id),
        str(capture_hash),
        str(estimate_id or ""),
        fingerprint,
        max_fixture_records,
        max_line_bytes,
    )
    owner = False
    while not owner:
        now = time.monotonic()
        with _cache_lock:
            entry = _cache.get(key)
            if entry is not None and entry.expires_at > now:
                _cache.move_to_end(key)
                return entry.value
            if entry is not None:
                _cache.pop(key, None)
            event = _inflight.get(key)
            if event is None:
                event = threading.Event()
                _inflight[key] = event
                owner = True
        if not owner:
            event.wait()

    try:
        result = _scan_frozen_capture(
            files,
            fixture_id=str(fixture_id),
            capture_hash=str(capture_hash),
            estimate_id=str(estimate_id) if estimate_id else None,
            max_fixture_records=max_fixture_records,
            max_line_bytes=max_line_bytes,
        )
        with _cache_lock:
            _cache[key] = _CacheEntry(
                expires_at=time.monotonic() + _CACHE_TTL_SECONDS,
                value=result,
            )
            _cache.move_to_end(key)
            while len(_cache) > _CACHE_MAX_ENTRIES:
                _cache.popitem(last=False)
        return result
    finally:
        with _cache_lock:
            completed = _inflight.pop(key, None)
            if completed is not None:
                completed.set()


def _ledger_files(root: Path) -> tuple[Path, ...]:
    ledger = root / "forward_outcome_ledger"
    directory = ledger if ledger.is_dir() else root
    return tuple(sorted(directory.glob("*.jsonl")))


def _ledger_fingerprint(files: tuple[Path, ...]) -> str:
    rows: list[tuple[str, int, int]] = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            rows.append((path.name, -1, -1))
        else:
            rows.append((path.name, stat.st_size, stat.st_mtime_ns))
    encoded = json.dumps(rows, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _scan_frozen_capture(
    files: tuple[Path, ...],
    *,
    fixture_id: str,
    capture_hash: str,
    estimate_id: str | None,
    max_fixture_records: int,
    max_line_bytes: int,
) -> FrozenCaptureLookup:
    if not files:
        return _result(
            fixture_id,
            capture_hash,
            source_status="MISSING",
            reason="LEDGER_NOT_FOUND",
        )
    target: list[tuple[dict[str, Any], str]] = []
    exact_mode = False
    corruption_count = 0
    scanned_records = 0
    try:
        for path in files:
            with path.open("rb") as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    if len(raw_line) > max_line_bytes:
                        return _result(
                            fixture_id,
                            capture_hash,
                            source_status="BLOCKED",
                            reason="LEDGER_LINE_LIMIT_EXCEEDED",
                            corruption_count=corruption_count,
                            scanned_file_count=len(files),
                            scanned_record_count=scanned_records,
                        )
                    scanned_records += 1
                    try:
                        value = json.loads(raw_line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        corruption_count += 1
                        continue
                    if not isinstance(value, dict):
                        corruption_count += 1
                        continue
                    if str(value.get("fixture_id") or "") != fixture_id:
                        continue
                    if not exact_mode:
                        target.append((value, path.name))
                    elif _relevant_to_exact_capture(value, capture_hash):
                        target.append((value, path.name))
                    if len(target) > max_fixture_records:
                        exact_mode = True
                        target = [
                            item
                            for item in target
                            if _relevant_to_exact_capture(item[0], capture_hash)
                        ]
                        if len(target) > max_fixture_records:
                            return _result(
                                fixture_id,
                                capture_hash,
                                source_status="BLOCKED",
                                reason="FIXTURE_RECORD_LIMIT_EXCEEDED",
                                corruption_count=corruption_count,
                                scanned_file_count=len(files),
                                scanned_record_count=scanned_records,
                            )
    except OSError:
        return _result(
            fixture_id,
            capture_hash,
            source_status="ERROR",
            reason="LEDGER_READ_FAILED",
            corruption_count=corruption_count,
            scanned_file_count=len(files),
            scanned_record_count=scanned_records,
        )

    records = tuple(row for row, _ in target)
    captures = [
        (row, name)
        for row, name in target
        if str(row.get("record_type") or "capture") == "capture"
    ]
    selected: tuple[dict[str, Any], str] | None = None
    for field in ("capture_hash", "evidence_hash", "card_hash"):
        matches = [item for item in captures if str(item[0].get(field) or "") == capture_hash]
        if not matches:
            continue
        if len(matches) > 1:
            reason = (
                "AMBIGUOUS_LEGACY_CAPTURE" if field == "card_hash" else "AMBIGUOUS_CAPTURE"
            )
            return _result(
                fixture_id,
                capture_hash,
                fixture_records=records,
                source_status="BLOCKED",
                reason=reason,
                corruption_count=corruption_count,
                scanned_file_count=len(files),
                scanned_record_count=scanned_records,
            )
        selected = matches[0]
        break

    if corruption_count:
        return _result(
            fixture_id,
            capture_hash,
            capture=selected[0] if selected else None,
            fixture_records=records,
            source_status="DEGRADED",
            reason="LEDGER_CORRUPTION",
            corruption_count=corruption_count,
            matched_file=selected[1] if selected else None,
            scanned_file_count=len(files),
            scanned_record_count=scanned_records,
        )
    if selected is None:
        return _result(
            fixture_id,
            capture_hash,
            fixture_records=records,
            source_status="MISSING",
            reason="CAPTURE_NOT_FOUND",
            scanned_file_count=len(files),
            scanned_record_count=scanned_records,
        )
    if estimate_id and estimate_id not in _estimate_ids(selected[0]):
        return _result(
            fixture_id,
            capture_hash,
            fixture_records=records,
            source_status="BLOCKED",
            reason="ESTIMATE_IDENTITY_MISMATCH",
            matched_file=selected[1],
            scanned_file_count=len(files),
            scanned_record_count=scanned_records,
        )
    return _result(
        fixture_id,
        capture_hash,
        capture=selected[0],
        fixture_records=records,
        source_status="PASS",
        matched_file=selected[1],
        scanned_file_count=len(files),
        scanned_record_count=scanned_records,
    )


def _relevant_to_exact_capture(record: Mapping[str, Any], capture_hash: str) -> bool:
    if str(record.get("record_type") or "capture") != "capture":
        # Old outcomes may not carry a source hash. Retaining bounded non-capture
        # records preserves historical audit visibility without keeping unrelated
        # capture history for the same fixture.
        source_hash = str(record.get("source_capture_hash") or "")
        return not source_hash or source_hash == capture_hash or any(
            str(record.get(field) or "") == capture_hash
            for field in ("capture_hash", "evidence_hash", "card_hash")
        )
    return any(
        str(record.get(field) or "") == capture_hash
        for field in ("capture_hash", "evidence_hash", "card_hash")
    )


def _estimate_ids(capture: Mapping[str, Any]) -> set[str]:
    values = {
        str(value)
        for value in capture.get("fair_market_estimate_ids") or ()
        if value
    }
    for snapshot in capture.get("fair_market_estimate_snapshots") or ():
        if isinstance(snapshot, Mapping) and snapshot.get("estimate_id"):
            values.add(str(snapshot["estimate_id"]))
    for key in ("estimate_id",):
        if capture.get(key):
            values.add(str(capture[key]))
    pick = capture.get("pick")
    if isinstance(pick, Mapping) and pick.get("estimate_id"):
        values.add(str(pick["estimate_id"]))
    return values


def _result(
    fixture_id: str,
    capture_hash: str,
    *,
    capture: Mapping[str, Any] | None = None,
    fixture_records: tuple[Mapping[str, Any], ...] = (),
    source_status: str,
    corruption_count: int = 0,
    matched_file: str | None = None,
    scanned_file_count: int = 0,
    scanned_record_count: int = 0,
    reason: str | None = None,
) -> FrozenCaptureLookup:
    return FrozenCaptureLookup(
        fixture_id=fixture_id,
        requested_capture_hash=capture_hash,
        capture=capture,
        fixture_records=fixture_records,
        source_status=source_status,
        corruption_count=corruption_count,
        matched_file=matched_file,
        scanned_file_count=scanned_file_count,
        scanned_record_count=scanned_record_count,
        reason=reason,
    )
