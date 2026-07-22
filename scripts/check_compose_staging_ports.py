#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

COMPOSE = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else Path("infra/compose/compose.staging.yml")
)
FORBIDDEN_PUBLIC = {
    "::",
}
ALLOWED_PUBLIC_BINDINGS: set[tuple[str, str]] = set()
FORBIDDEN_SHORT = {
    "8000:8000",
    "8080:8080",
    "5432:5432",
    "6379:6379",
    "9000:9000",
}


def fail(message: str) -> None:
    print(f"compose_staging_ports FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_port(port: object) -> str:
    if isinstance(port, str):
        return port
    if isinstance(port, dict):
        host_ip = str(port.get("host_ip", ""))
        published = str(port.get("published", ""))
        target = str(port.get("target", ""))
        return f"{host_ip}:{published}:{target}"
    fail(f"unsupported port syntax {port!r}")
    raise AssertionError("unreachable")


def service_ports(compose: dict[str, Any], service: str) -> list[str]:
    services = compose.get("services", {})
    definition = services.get(service, {})
    return [normalize_port(port) for port in definition.get("ports", [])]


def assert_no_public_ports(ports: list[str], service: str) -> None:
    for port in ports:
        if (service, port) in ALLOWED_PUBLIC_BINDINGS:
            continue
        if port.startswith("0.0.0.0:"):  # noqa: S104 - forbidden unless allowlisted above.
            fail(f"{service} exposes public host binding")
        if any(port.startswith(f"{host}:") for host in FORBIDDEN_PUBLIC):
            fail(f"{service} exposes public host binding")
        if port in FORBIDDEN_SHORT:
            fail(f"{service} exposes forbidden short binding {port}")


def main() -> int:
    if not COMPOSE.is_file():
        fail(f"compose file not found: {COMPOSE}")
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services = compose.get("services", {})
    api_ports = service_ports(compose, "api")
    web_ports = service_ports(compose, "web")
    if api_ports != ["127.0.0.1:18000:8000"]:
        fail("api must bind exactly 127.0.0.1:18000:8000")
    if web_ports != ["127.0.0.1:18080:8080"]:
        fail("web must bind exactly 127.0.0.1:18080:8080")
    for service, definition in services.items():
        ports = [normalize_port(port) for port in definition.get("ports", [])]
        assert_no_public_ports(ports, service)
        if service in {"postgres", "redis"} and ports:
            fail(f"{service} must not publish ports")
        status = "PASS" if ports or service in {"postgres", "redis"} else "PASS"
        policy = ports if ports else ["no_published_ports"]
        print(f"{service} port_bind_policy={policy} {status}")
    print("compose_staging_ports PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
