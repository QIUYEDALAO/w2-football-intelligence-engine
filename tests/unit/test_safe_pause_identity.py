"""An unreachable public API only admits a verified paused collector set."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "attack,reason",
    [
        ("noop", None),
        ("api", "SAFE_PAUSE_PUBLIC_SERVICE_RUNNING:api"),
        ("web", "SAFE_PAUSE_PUBLIC_SERVICE_RUNNING:web"),
        ("paused", "SAFE_PAUSE_COLLECTOR_NOT_PAUSED:worker"),
        ("stopped", "SAFE_PAUSE_COLLECTOR_NOT_PAUSED:worker"),
        ("identity", "SAFE_PAUSE_RELEASE_IDENTITY_CONFLICT:worker"),
        ("mixed", "SAFE_PAUSE_COLLECTOR_SET_CONFLICT"),
        ("drift", "SAFE_PAUSE_SOURCE_DRIFT:worker"),
        ("schema", "SAFE_PAUSE_SCHEMA_UNSUPPORTED"),
    ],
)
def test_safe_pause_identity_refuses_one_field_conflicts(monkeypatch, attack, reason):
    path = Path(__file__).resolve().parents[2] / "scripts/w2_safe_pause_identity.py"
    spec = importlib.util.spec_from_file_location("safe_pause_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sha, image = "a" * 40, "sha256:" + "b" * 64
    payload = {
        name: {
            "State": {"Running": name not in {"api", "web"}},
            "Image": image,
            "Config": {
                "Env": [
                    "W2_GIT_SHA=" + sha,
                    "W2_RELEASE_ID=" + sha,
                    "W2_CURRENT_RECOMMENDATIONS_PAUSED=true",
                ]
            },
        }
        for name in ("api", "web", "worker", "worker-heavy", "scheduler")
    }
    original = deepcopy(payload)
    fault = False

    def invoke(command):
        if command[1] == "inspect":
            if command[2].startswith("sha256:"):
                return json.dumps(
                    [
                        {
                            "Config": {
                                "Labels": {
                                    "org.opencontainers.image.revision": sha,
                                }
                            }
                        }
                    ]
                )
            name = command[2].removeprefix("w2-staging-").removesuffix("-1")
            return json.dumps([payload[name]])
        if "psql" in command:
            return "0076_forward_review_evidence"
        if fault and attack == "drift" and command[1:3] == ["exec", "w2-staging-worker-1"]:
            return "d" * 64
        if fault and attack == "schema" and "SAFE_PAUSE_SCHEMA_UNSUPPORTED" in command[-2]:
            raise RuntimeError("SAFE_PAUSE_SCHEMA_UNSUPPORTED")
        return "c" * 64

    monkeypatch.setattr(module, "run", invoke)
    # Same inspection/read channel first, unchanged payload.
    control = module.read_identity()
    assert control["release_id"] == sha and control["public_services_stopped"]
    assert payload == original
    if attack == "noop":
        assert module.read_identity() == control
        return
    fault = True
    if attack in {"api", "web"}:
        payload[attack]["State"]["Running"] = True
    elif attack == "paused":
        payload["worker"]["Config"]["Env"][-1] = "W2_CURRENT_RECOMMENDATIONS_PAUSED=false"
    elif attack == "stopped":
        payload["worker"]["State"]["Running"] = False
    elif attack == "identity":
        payload["worker"]["Config"]["Env"][0] = "W2_GIT_SHA=" + "e" * 40
    elif attack == "mixed":
        payload["worker-heavy"]["Image"] = "sha256:" + "e" * 64
    with pytest.raises(RuntimeError, match=reason):
        module.read_identity()
