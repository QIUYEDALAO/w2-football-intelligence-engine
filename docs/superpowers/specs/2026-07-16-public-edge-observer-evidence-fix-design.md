# W2 Public Edge Observer Evidence V2 Design

Date: 2026-07-16
Status: APPROVED_FOR_IMPLEMENTATION
Scope: Observer evidence collection, validation, and adjudication only

## Problem and invariants

The V1 collector discards response bodies and attempts to read `x-request-id`
from a response header that staging nginx does not emit. The DayView JSON body
contains nginx's request ID, but retained V1 evidence therefore has empty
correlation IDs and no per-sample timestamp. V1 evidence and evidence missing
any mandatory V2 field can never form a formal PASS.

This change must not alter the Dashboard hot path, nginx timeout, FME,
denominator, pagination, Frozen L2, thresholds, recommendation behavior, locks,
OFFICIAL data, or historical evidence.

## Evidence schema V2

The report schema is `w2.public_edge_latency.v2`. Every sample uses
`w2.public_edge_latency.sample.v2`. The collector identifies itself as
`w2.public_edge_observer.v2`.

`config/operations/public_edge_acceptance_v1.json` declares:

- `required_evidence_schema = w2.public_edge_latency.v2`
- `required_sample_schema = w2.public_edge_latency.sample.v2`
- `required_collector_version = w2.public_edge_observer.v2`

The validator rejects V1 reports and reports or samples missing any required
field from success evidence.

## Temporary response bodies and request IDs

Each curl process receives a permission-restricted `TemporaryDirectory`. Every
transfer writes to a unique file named
`process-<process-index>-transfer-<request-index>.body`. Reused transfers remain
in one curl process; fresh transfers each have their own process.

The collector parses only the top-level JSON `request_id`. A successful DayView
sample requires an existing JSON body and a non-empty request ID of at most 128
UTF-8 bytes matching the allowlist `[A-Za-z0-9._:-]+`. Request IDs must be unique
within a report; duplicates fail with `DUPLICATE_REQUEST_ID`.

Response bodies never enter the report, diagnostic exceptions, workflow
artifacts, or repository. Temporary bodies are removed after success and every
failure path. Errors identify process/request indexes but omit body content and
full temporary paths.

## Time semantics

Every sample records `collected_at_utc`, the UTC time captured after a transfer's
body and write-out metadata are paired. It is not the request start time. Each
sample also records `curl_process_started_at_utc` and
`curl_process_finished_at_utc` for its owning curl process.

All timestamps are timezone-aware ISO-8601 UTC values.

## Server-Timing

The only retained response-header evidence is `Server-Timing`. Curl writes it to
an indexed metadata file or a safely delimited write-out field. The collector
rejects values larger than 4 KiB and values containing CR, LF, tab, or other
control characters. Unvalidated raw header text never enters the final report.

The parser retains an allowlisted metric map only. Allowed metrics are `route`,
`fixture`, `capture`, `market`, `performance`, `projection`, `validation`, and
`serialization`, each with a finite, non-negative `dur` value. A successful HTTP
200 sample with missing or invalid Server-Timing fails correlation with
`EVIDENCE_CORRELATION_INVALID`.

## IP protocol and no-proxy proof

`curl_command` requires `ip_protocol`. IPv4 commands include `--ipv4`; IPv6
commands include `--ipv6`. The collector validates `remote_ip` with
`ipaddress.ip_address` and fails with `IP_PROTOCOL_MISMATCH` when the actual
address family differs from the declared family.

Every sample records `ip_protocol`, `remote_ip`, and `no_proxy`. For DIRECT
samples, `no_proxy=true` is derived from both the actual `--noproxy *` command
and the scrubbed proxy environment. Callers cannot supply or override this
value. PROXY samples record `no_proxy=false` and never enter direct-route
percentiles.

## Connection modes

FRESH uses exactly one curl process and one transfer for each sample. Its
`connection_reused` must be false.

REUSED uses one curl process for all transfers in a reuse group. For every
sample, connection reuse is derived only from curl's `num_connects == 0`.
Request position never implies reuse; a server-forced reconnect therefore
records `connection_reused=false`.

Every sample records `curl_process_index`, `request_index_within_process`,
`num_connects`, and `connection_reused`.

## Transfer failures

The collector does not use `check=True` in a way that discards failed-transfer
facts. When curl produces deterministic write-out metadata, it retains the curl
exit code, status (including 0, 502, and 504), available timings, and response
byte count.

For HTTP 502/504 or transport failure, request ID and Server-Timing may be null.
The sample records:

- `sample_valid_for_success_evidence=false`
- `sample_valid_for_failure_evidence=true`
- `correlation_status=EDGE_FAILURE_BEFORE_API`

Such a sample fails the observer but remains part of the factual report.

Collector hard errors produce no partial report. They include indeterminate
sample count, write-out/body pairing failure, corrupt metadata, unsupported curl
capability, or temporary-file boundary violation.

## Size and pairing limits

- `MAX_OBSERVER_RESPONSE_BODY_BYTES = 1 MiB`
- `MAX_SERVER_TIMING_BYTES = 4 KiB`
- `MAX_REQUEST_ID_BYTES = 128`

For successful transfers, the number of write-out records, body files, and
requested samples must be identical. Limits and pairing errors fail closed
without emitting response content or complete temporary paths.

## Required successful sample fields

Every formal HTTP 200 sample contains:

- sample schema and `collected_at_utc`
- path kind and derived `no_proxy`
- IP protocol and validated remote IP
- connection mode, process index, and request index
- `num_connects`, `connection_reused`, and `curl_exit_code`
- HTTP status/version
- DNS, TCP, TLS, pretransfer, TTFB, and total timings
- response bytes
- validated request ID
- parsed Server-Timing metric map
- `correlation_status=CORRELATED`
- `sample_valid_for_success_evidence=true`
- `sample_valid_for_failure_evidence=true`

## Report validation and adjudication

The report validator checks the report schema, collector version, sample schema,
mandatory fields, sample uniqueness, IP family, no-proxy proof, connection
invariants, counts, size limits, correlation status, and Server-Timing map before
threshold evaluation. Invalid evidence cannot form a PASS. Failure evidence is
retained and makes its observer fail.

Adjudication continues to separate observers, IP protocols, connection modes,
and direct/proxy paths. It never removes failed samples, averages observers, or
changes the frozen thresholds.

## Workflow artifacts

The GitHub workflow runs the V2 collector explicitly, validates every report,
and uploads only sanitized JSON reports. Temporary directories, bodies, raw
headers, query strings, cookies, authorization material, and environment content
are excluded from artifacts.

## Verification

Unit coverage includes schema validation, request-ID validation and uniqueness,
timestamp validation, safe Server-Timing parsing, IP-family enforcement,
derived no-proxy state, fresh/reused `num_connects` behavior, failure retention,
pairing/count failures, size limits, and V1 rejection.

`tests/integration/test_public_edge_curl_evidence.py` starts a local HTTP/1.1
keep-alive server that returns a unique JSON request ID and Server-Timing value.
It covers:

- reused one-process/multi-transfer behavior
- fresh one-transfer/one-process behavior
- exact write-out/body pairing and real connection reuse
- server-forced reconnect
- malformed JSON and empty request ID
- oversized body
- HTTP 502 with an HTML body
- timeout retention
- temporary-directory cleanup
- final-report exclusion of bodies, query strings, raw headers, cookies, access
  material, and environment content

Required verification includes targeted unit and real-curl integration tests,
full pytest, Ruff, Mypy, TypeScript, Web build, acceptance, tracked-output,
all-stage, legacy guard, sensitive-pattern scan, diff check, and the three GitHub
CI jobs.

## Frozen scope

This specification is approved and frozen. New observer requirements are not
added during implementation unless a `HARD_BLOCKER_CURRENT_SCOPE` prevents the
existing terminal condition. Ordinary improvements are deferred.
