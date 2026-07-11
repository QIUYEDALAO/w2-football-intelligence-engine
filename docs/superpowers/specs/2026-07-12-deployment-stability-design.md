# Deployment Stability Design

## Scope

Harden staging image startup, API/Web switching, nginx service discovery, and
release probes. This change does not deploy, alter dependencies, call a
provider, restart worker/scheduler, or modify production configuration.

## Design

- Python runtime commands execute the already-built `/app/.venv/bin` tools;
  `uv` remains a build-time dependency only.
- nginx resolves the Docker `api` service through `127.0.0.11` with a 10-second
  TTL, so an API container replacement does not leave a stale upstream address.
- staging Web retains `service_healthy` dependency on API.
- an approved staging release runs migration, switches API, requires three
  consecutive health/ready/version successes, then switches Web and requires
  three consecutive health/ready/version/meta successes.
- worker and scheduler are not recreated by the release switch. Their lifecycle
  remains a separate, explicit operation.
- predeploy E2E keeps Web running while force-recreating API, then verifies that
  Web reconnects through the dynamically resolved upstream.
