#!/usr/bin/env python3
from __future__ import annotations

import argparse
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreflightResult:
    passed: bool
    reason: str
    path: Path
    uid: int
    gid: int
    owner_uid: int | None = None
    owner_gid: int | None = None
    mode: int | None = None

    def status_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        details = [
            f"path={self.path}",
            f"target={self.uid}:{self.gid}",
            f"reason={self.reason}",
        ]
        if self.owner_uid is not None and self.owner_gid is not None:
            details.append(f"owner={self.owner_uid}:{self.owner_gid}")
        if self.mode is not None:
            details.append(f"mode={self.mode:04o}")
        return f"{status} " + " ".join(details)


def parse_uid_gid(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("target must be formatted as uid:gid")
    try:
        uid = int(parts[0])
        gid = int(parts[1])
    except ValueError as exc:
        raise argparse.ArgumentTypeError("uid and gid must be integers") from exc
    if uid < 0 or gid < 0:
        raise argparse.ArgumentTypeError("uid and gid must be non-negative")
    return uid, gid


def mode_allows_directory_write(
    mode: int,
    *,
    uid: int,
    gid: int,
    owner_uid: int,
    owner_gid: int,
) -> bool:
    required_owner = stat.S_IWUSR | stat.S_IXUSR
    required_group = stat.S_IWGRP | stat.S_IXGRP
    required_other = stat.S_IWOTH | stat.S_IXOTH
    if uid == owner_uid:
        return mode & required_owner == required_owner
    if gid == owner_gid:
        return mode & required_group == required_group
    return mode & required_other == required_other


def check_runtime_writable(path: Path, *, uid: int, gid: int) -> PreflightResult:
    try:
        info = path.stat()
    except FileNotFoundError:
        return PreflightResult(False, "MISSING", path, uid, gid)
    except OSError as exc:
        return PreflightResult(False, f"STAT_FAILED:{exc.__class__.__name__}", path, uid, gid)
    mode = stat.S_IMODE(info.st_mode)
    if not stat.S_ISDIR(info.st_mode):
        return PreflightResult(
            False,
            "NOT_DIRECTORY",
            path,
            uid,
            gid,
            info.st_uid,
            info.st_gid,
            mode,
        )
    if mode_allows_directory_write(
        mode,
        uid=uid,
        gid=gid,
        owner_uid=info.st_uid,
        owner_gid=info.st_gid,
    ):
        return PreflightResult(
            True,
            "TARGET_UID_GID_CAN_WRITE",
            path,
            uid,
            gid,
            info.st_uid,
            info.st_gid,
            mode,
        )
    return PreflightResult(
        False,
        "TARGET_UID_GID_CANNOT_WRITE",
        path,
        uid,
        gid,
        info.st_uid,
        info.st_gid,
        mode,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for a runtime directory and target uid:gid."
    )
    parser.add_argument("runtime_path", type=Path)
    parser.add_argument(
        "target",
        type=parse_uid_gid,
        help="Target runtime identity, formatted uid:gid.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    uid, gid = args.target
    result = check_runtime_writable(args.runtime_path, uid=uid, gid=gid)
    print(result.status_line())
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
