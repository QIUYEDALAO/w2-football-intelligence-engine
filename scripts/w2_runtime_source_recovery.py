"""Capture a runtime source anomaly and admit only that frozen recovery input.

No schema, source, container or credentials are changed by this utility. The
release still stops all old outlets before migration and never restarts them.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

FINGERPRINT = """import hashlib,pathlib
base=pathlib.Path("/app")
files=sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts and p.is_file())
h=hashlib.sha256()
for p in files:
    h.update(p.relative_to(base).as_posix().encode()); h.update(b"\\0")
    h.update(p.read_bytes()); h.update(b"\\0")
print(h.hexdigest())"""
ARCHIVE = """import pathlib,tarfile,sys
base=pathlib.Path("/app")
with tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz") as t:
    for p in sorted(base.rglob("*.py")):
        if "__pycache__" not in p.parts and p.is_file():
            t.add(p,arcname=p.relative_to(base).as_posix(),recursive=False)
"""


def command(*args: str) -> str:
    return subprocess.check_output(args).decode().strip()


def capture(target: str, output: Path, project: str = "w2-staging") -> Path:
    assert re.fullmatch(r"[0-9a-f]{40}", target), "RECOVERY_TARGET_INVALID"
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "w2.runtime_source_recovery.v1",
        "target_sha": target,
        "captured_at": datetime.now(UTC).isoformat(),
        "database_revision": command(
            "docker",
            "exec",
            f"{project}-postgres-1",
            "psql",
            "-XAt",
            "-U",
            "w2_user",
            "-d",
            "w2",
            "-c",
            "SELECT version_num FROM alembic_version",
        ),
        "services": {},
    }
    for name in ("api", "worker", "worker-heavy", "scheduler"):
        container = f"{project}-{name}-1"
        image = command("docker", "inspect", container, "--format", "{{.Image}}")
        image_head = command(
            "docker", "run", "--rm", "--entrypoint", "alembic", image, "heads"
        ).split()[0]
        container_head = command("docker", "exec", container, "alembic", "heads").split()[0]
        image_hash = command(
            "docker", "run", "--rm", "--entrypoint", "python", image, "-c", FINGERPRINT
        )
        container_hash = command("docker", "exec", container, "python", "-c", FINGERPRINT)
        archive = subprocess.check_output(["docker", "exec", container, "python", "-c", ARCHIVE])
        archive_name = name + "-" + hashlib.sha256(archive).hexdigest() + ".tar.gz"
        path = output / archive_name
        with path.open("xb") as stream:
            stream.write(archive)
        path.chmod(0o400)
        manifest["services"][name] = {
            "image": image,
            "image_head": image_head,
            "container_head": container_head,
            "image_hash": image_hash,
            "container_hash": container_hash,
            "archive": archive_name,
            "archive_sha256": hashlib.sha256(archive).hexdigest(),
        }
    path = output / f"source-drift-recovery-{target}.json"
    with path.open("x") as stream:
        stream.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    path.chmod(0o400)
    print(
        json.dumps(
            {
                "manifest": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "schema": manifest["database_revision"],
                "services": manifest["services"],
            }
        )
    )
    return path


def verify(
    path: Path, expected_sha: str, target: str, service: str, schema: str, values: list[str]
) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", expected_sha), "RECOVERY_MANIFEST_DIGEST_INVALID"
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == expected_sha, "RECOVERY_MANIFEST_HASH_MISMATCH"
    manifest = json.loads(data)
    assert manifest["schema_version"] == "w2.runtime_source_recovery.v1", "RECOVERY_SCHEMA_INVALID"
    assert manifest["target_sha"] == target, "RECOVERY_TARGET_MISMATCH"
    assert manifest["database_revision"] == schema, "RECOVERY_DATABASE_REVISION_MISMATCH"
    captured = datetime.fromisoformat(manifest["captured_at"])
    assert captured.tzinfo is not None, "RECOVERY_TIME_INVALID"
    assert timedelta(0) <= datetime.now(UTC) - captured <= timedelta(hours=1), "RECOVERY_EXPIRED"
    entry = manifest["services"][service]
    keys = ("image", "image_head", "container_head", "image_hash", "container_hash")
    assert [entry[k] for k in keys] == values, "RECOVERY_CURRENT_SOURCE_CONFLICT"
    assert Path(entry["archive"]).name == entry["archive"], "RECOVERY_ARCHIVE_PATH_INVALID"
    archive = (path.parent / entry["archive"]).read_bytes()
    assert hashlib.sha256(archive).hexdigest() == entry["archive_sha256"], (
        "RECOVERY_ARCHIVE_HASH_MISMATCH"
    )
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        files = {
            member.name: tar.extractfile(member).read()
            for member in tar.getmembers()
            if member.isfile()
        }
    assert files and all(name.endswith(".py") for name in files), "RECOVERY_ARCHIVE_INVALID"
    digest = hashlib.sha256()
    # pathlib sorts by path components. Sorting the slash-joined names differs
    # for example/a.py versus example.py and would reject a genuine archive.
    for name in sorted(files, key=lambda value: PurePosixPath(value).parts):
        contents = files[name]
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(contents)
        digest.update(b"\0")
    assert digest.hexdigest() == entry["container_hash"], "RECOVERY_ARCHIVE_SOURCE_MISMATCH"
    print("SOURCE_RECOVERY_VERIFIED:" + service)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    record = sub.add_parser("capture")
    record.add_argument("--target", required=True)
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--project", default="w2-staging")
    check = sub.add_parser("verify")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--sha256", required=True)
    check.add_argument("--target", required=True)
    check.add_argument("--service", required=True)
    check.add_argument("--database-revision", required=True)
    check.add_argument("values", nargs=5)
    args = parser.parse_args()
    if args.action == "capture":
        capture(args.target, args.output, args.project)
    else:
        verify(
            args.manifest,
            args.sha256,
            args.target,
            args.service,
            args.database_revision,
            args.values,
        )


if __name__ == "__main__":
    main()
