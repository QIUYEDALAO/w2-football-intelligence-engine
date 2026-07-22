from __future__ import annotations

import json

from scripts.check_w2_stage7h import compose_services, docker_command


def test_compose_services_reads_array_and_json_lines() -> None:
    rows = [
        {"Service": "api", "State": "running", "Health": "healthy"},
        {"Service": "web", "State": "running", "Health": "healthy"},
    ]

    assert compose_services(json.dumps(rows)) == rows
    assert compose_services("\n".join(json.dumps(row) for row in rows)) == rows


def test_docker_command_uses_noninteractive_sudo_for_unprivileged_user(monkeypatch) -> None:
    monkeypatch.setattr("scripts.check_w2_stage7h.os.geteuid", lambda: 1000)

    assert docker_command("compose", "ps") == ("sudo", "-n", "docker", "compose", "ps")
