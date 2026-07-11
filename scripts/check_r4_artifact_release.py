from __future__ import annotations

import argparse
import json
from pathlib import Path

from w2.models.r4_1_artifacts import load_r4_1_artifacts


def validate_artifact_release(
    artifact_dir: Path, *, approved_versions: set[str]
) -> dict[str, object]:
    result = load_r4_1_artifacts(artifact_dir)
    failures = [
        f"INVALID_ARTIFACT:{competition}:{reason}"
        for competition, reason in sorted(result.invalid_reasons.items())
    ]
    for competition, artifact in sorted(result.artifacts.items()):
        if artifact.artifact_version not in approved_versions:
            failures.append(
                f"UNAPPROVED_ARTIFACT_VERSION:{competition}:{artifact.artifact_version}"
            )
    if not result.artifacts:
        failures.append("NO_VALID_ARTIFACTS")
    return {
        "status": "PASS" if not failures else "BLOCKED",
        "artifact_count": len(result.artifacts),
        "artifact_versions": sorted(
            {artifact.artifact_version for artifact in result.artifacts.values()}
        ),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate approved staging R4 artifacts")
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--approved-version", action="append", required=True)
    args = parser.parse_args()
    report = validate_artifact_release(
        args.artifact_dir, approved_versions=set(args.approved_version)
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
