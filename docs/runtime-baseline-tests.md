# Runtime baseline tests

`scripts/testing/runtime-baseline.py` provides **non-destructive, bounded**
production checks. It is intentionally smaller than a DAST suite.

## Modes

### Integration

Validates the application health/version contract:

```bash
python scripts/testing/runtime-baseline.py integration \
  --url https://fastapi-sample.fastapicloud.dev
```

Expected evidence:

- `/health` returns HTTP 200 and JSON;
- `/v2/version` returns HTTP 200 and JSON.

### HTTP security baseline

Runs read-only transport/header checks:

```bash
python scripts/testing/runtime-baseline.py pentest \
  --url https://fastapi-sample.fastapicloud.dev
```

It checks HTTPS policy, TRACE, frame protection, HSTS,
`X-Content-Type-Options`, dangerous credentialed wildcard CORS and cookie
flags. Known response-header debt is explicitly ratcheted in
`config/security/production-http-baseline.json`; new failures still fail the
workflow.

This mode is **not OWASP ZAP** and is intentionally low-cost.

### Performance smoke

Runs a small bounded health-endpoint load:

```bash
python scripts/testing/runtime-baseline.py performance \
  --url https://fastapi-sample.fastapicloud.dev \
  --requests 20 \
  --concurrency 4 \
  --max-p95-ms 1500 \
  --max-error-rate 0.05
```

This is a smoke test, not a load/performance benchmark.

## GitHub Actions ownership

`.github/workflows/production-security.yml` runs the integration and HTTP
security checks on relevant pull requests. Master/scheduled/manual runs also
execute the bounded performance smoke.

The workflow is path-scoped so documentation-only or Renovate-only changes do
not consume this runtime-security job.

## OWASP ZAP / DAST

**ZAP is disabled in `nabla-compose` for now.**

Application DAST belongs to `fastapi-sample`, where findings can be correlated
with the application code, routes and releases that expose the HTTP surface.
Do not add a second FastAPI ZAP baseline here.

The historical `.zap/` rules and `scripts/security/prepare-zap-openapi.py`
remain dormant reference material for now; they are not invoked by the active
`nabla-compose` workflow. They can be removed later once the
`fastapi-sample` DAST ownership is fully accepted.

## Diagnostic order

When the runtime workflow fails:

1. run the failing baseline mode locally against the same URL;
2. distinguish transport failure from an application HTTP failure;
3. for header debt, compare the emitted `failures` array with
   `config/security/production-http-baseline.json`;
4. for `/api/homelab/status` or `/api/runtime/topology`, inspect the endpoint
   response independently before changing probes;
5. do not weaken a security check merely to make CI green.

If a ZAP finding is involved, diagnose it in `fastapi-sample`, not here.
