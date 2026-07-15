from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, kw_only=True)
class JsonlReadResult:
    records: list[dict[str, Any]]
    status: str
    corruption_count: int


def read_jsonl(path: Path) -> JsonlReadResult:
    if not path.exists():
        return JsonlReadResult(records=[], status="MISSING", corruption_count=0)
    records: list[dict[str, Any]] = []
    corrupt = 0
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    corrupt += 1
                    continue
                if isinstance(value, dict):
                    records.append(value)
                else:
                    corrupt += 1
    except OSError:
        return JsonlReadResult(records=records, status="ERROR", corruption_count=corrupt + 1)
    return JsonlReadResult(
        records=records,
        status="DEGRADED" if corrupt else "PASS",
        corruption_count=corrupt,
    )


def append_jsonl_once(
    path: Path,
    record: Mapping[str, Any],
    *,
    key: str,
    key_fn: Callable[[Mapping[str, Any]], str],
) -> tuple[bool, JsonlReadResult]:
    """Lock read/dedupe/append as one durable cross-process transaction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        existing = read_jsonl(path)
        if any(key_fn(item) == key for item in existing.records):
            return False, existing
        needs_newline = path.exists() and path.stat().st_size > 0
        if needs_newline:
            with path.open("rb") as source:
                source.seek(-1, os.SEEK_END)
                needs_newline = source.read(1) != b"\n"
        with path.open("a", encoding="utf-8") as handle:
            if needs_newline:
                handle.write("\n")
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return True, existing


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write old-or-new complete JSON and durably replace it in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
