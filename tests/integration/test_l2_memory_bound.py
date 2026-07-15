from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_known_oom_fixture_stays_bounded_in_real_fastapi_subprocess() -> None:
    repository_root = Path(__file__).parents[2]
    fixture_root = repository_root / "tests" / "fixtures" / "frozen_audit"
    script = f"""
import json
import resource
import sys
from types import SimpleNamespace

limit = 1024 * 1024 * 1024
if sys.platform != 'darwin' and hasattr(resource, 'RLIMIT_AS'):
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

from apps.api.main import app
from fastapi.testclient import TestClient
from w2.api import routers
from w2.api.repository import ReadModelService
import w2.api.repository as repository_module

class EmptyRepository:
    def matchday_cards(self): return []
    def dashboard_fixture(self, fixture_id): return None
    def fixture_payloads(self): return []

repository_module.get_settings = lambda: SimpleNamespace(
    resolved_runtime_root=__import__('pathlib').Path({str(fixture_root)!r}),
)
routers.service = ReadModelService(repository=EmptyRepository())
before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
response = TestClient(app).get(
    '/v1/fixtures/1576804/audit-detail',
    params={{'capture_hash': '0ceebd3db9a826d72cdafef626d64f54f7fdd837cca528a29188b3c1e93457bc'}},
)
after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
unit = 1 if sys.platform == 'darwin' else 1024
print(json.dumps({{
    'status': response.status_code,
    'response_bytes': len(response.content),
    'rss_delta_bytes': max(after - before, 0) * unit,
    'max_rss_bytes': after * unit,
    'memory_limit_bytes': limit,
}}))
raise SystemExit(0 if response.status_code == 200 else 1)
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    metrics = json.loads(completed.stdout.strip().splitlines()[-1])
    assert metrics["status"] == 200
    assert metrics["response_bytes"] <= 512 * 1024
    assert metrics["rss_delta_bytes"] <= 192 * 1024 * 1024
    assert metrics["max_rss_bytes"] < metrics["memory_limit_bytes"]
