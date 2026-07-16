# W2 Public Edge Observer Evidence Fix Design

Date: 2026-07-16  
Status: Approved for specification  
Scope: Observer evidence collection only

## Problem

The public-edge observer currently discards response bodies and reads
`x-request-id` from a response header that staging nginx does not emit. Staging
does inject nginx `$request_id` into the upstream request, and the DayView JSON
body returns that value as `request_id`, but the generated evidence therefore
contains an empty `request_id`. Samples also omit their timestamp and API
`Server-Timing`. The resulting artifacts cannot satisfy
`W2_PUBLIC_EDGE_ACCEPTANCE_V1`, regardless of their latency result.

## Constraints

- Do not change the Dashboard hot path, FME, denominator, pagination, Frozen L2,
  recommendation gates, thresholds, or the 12-second timeout.
- Preserve one curl process for a reused keep-alive sample batch so connection
  reuse remains real and measurable.
- Preserve one curl process per fresh sample so every fresh observation remains
  an independent connection.
- Do not log response bodies, query strings, credentials, headers, or secrets in
  the retained report.
- Keep all evidence separated by observer, IP protocol, connection mode,
  endpoint, and concurrency.

## Considered Approaches

1. **Retain one temporary response body per request and parse its request ID.**
   This preserves the existing network behavior, requires no staging deployment,
   and uses the request ID already returned by the API. This is the selected
   approach.
2. **Add `X-Request-ID` to nginx responses.** This is small, but it requires a
   staging deployment before the predeployment public gate and therefore creates
   a circular dependency. It also does not solve the missing timestamp by itself.
3. **Infer correlation from nginx log timestamps and request order.** This is not
   exact under concurrency and fails the frozen request-ID alignment requirement.

## Design

`collect_samples` will create a temporary directory for each curl process. Its
curl command will assign a distinct output file to every repeated URL while
retaining all URLs in the same process for `REUSED` mode. After curl exits, the
collector will pair write-out records and response files by deterministic index.
It will parse only the top-level JSON `request_id`, then delete the temporary
directory automatically.

The curl write-out record will additionally capture the response
`Server-Timing` value. Each normalized sample will record a UTC ISO-8601
timestamp at collection time, `no_proxy`, IP protocol, the existing DNS/TCP/TLS/
pretransfer/TTFB/total metrics, response bytes, HTTP status, connection reuse,
request ID, and Server-Timing. Observer-level fields already held in the report
remain unchanged.

The collector will fail closed when a response body is missing, is not JSON, has
an empty request ID, or cannot be paired one-to-one with a write-out record. No
partial report will be accepted. Temporary bodies will never be copied into the
report or repository.

## Data Flow

1. Build the existing no-proxy curl command and allocate indexed temporary
   response paths.
2. Execute one curl process per reuse group or per fresh request, unchanged from
   the current connection model.
3. Parse each curl write-out line.
4. Parse the corresponding response body and extract only `request_id`.
5. Add the UTC timestamp, no-proxy assertion, IP protocol, and Server-Timing.
6. Validate remote IP, request ID, sample count, and one-to-one pairing.
7. Emit the sanitized report and remove all temporary response files.

## Error Handling

- Curl failures retain the existing subprocess failure behavior.
- Missing or malformed bodies raise a descriptive `ValueError`.
- Empty request IDs raise a descriptive `ValueError`.
- Mismatched body/write-out counts raise `SAMPLE_COUNT_MISMATCH` or a dedicated
  pairing error.
- Temporary data is cleaned on success and failure through a managed temporary
  directory.

## Verification

Unit tests will prove:

- reused batches still use one curl process and mark requests after the first as
  reused;
- fresh concurrency still creates one connection per sample;
- every sample receives the exact body request ID, UTC timestamp, no-proxy flag,
  IP protocol, and Server-Timing;
- missing, malformed, or empty-ID bodies fail closed;
- response bodies are absent from the final evidence;
- existing threshold and adjudication tests remain unchanged and pass.

After local checks and the repository's three required CI jobs pass, the fix PR
may merge automatically. Both public observers must then rerun the entire matrix;
no evidence collected before this fix counts as a formal blocking PASS.

## Out of Scope

- Staging or production deployment.
- Infrastructure changes.
- Latency tuning or threshold changes.
- Product, model, recommendation, lock, OFFICIAL, or denominator behavior.
