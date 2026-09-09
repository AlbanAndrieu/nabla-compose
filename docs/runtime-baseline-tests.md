# Runtime baseline tests

These checks provide a small, bounded validation layer for FastAPI Sample and
other HTTP services. They deliberately avoid destructive scanning, brute force,
large load generation or mutation.

## Integration smoke

Validate the application-level health and version contracts:

```bash
python scripts/testing/runtime-baseline.py integration \
  --url http://127.0.0.1:8091
```

The gate requires HTTP 200 and valid JSON from `/health` and `/v2/version`.

## Non-destructive HTTP pentest baseline

Run the baseline against the HTTPS ingress:

```bash
python scripts/testing/runtime-baseline.py pentest \
  --url https://sample.albandrieu.com
```

The check verifies:

- HTTPS unless `--allow-http` is explicitly selected for a trusted LAN target;
- `TRACE` is not accepted with a 2xx response;
- `X-Content-Type-Options: nosniff`;
- frame protection through `X-Frame-Options` or CSP `frame-ancestors`;
- HSTS on HTTPS;
- no wildcard CORS combined with credentialed requests;
- `HttpOnly` and, on HTTPS, `Secure` on cookies when cookies are returned;
- obvious version disclosure in the `Server` header as a warning.

For a Cloudflare Access protected endpoint, the runner automatically uses
`CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` when both are present.

For the direct TrueNAS-local HTTP endpoint, explicitly acknowledge the trusted
cleartext path:

```bash
python scripts/testing/runtime-baseline.py pentest \
  --url http://127.0.0.1:8091 \
  --allow-http
```

## Basic performance smoke

Use a deliberately small load to catch gross latency/error regressions without
turning CI into a load test:

```bash
python scripts/testing/runtime-baseline.py performance \
  --url http://127.0.0.1:8091 \
  --requests 25 \
  --concurrency 5 \
  --max-p95-ms 1000 \
  --max-error-rate 0.02
```

The report includes request count, concurrency, error rate, p50, p95 and maximum
latency. Production capacity testing remains a separate activity; this smoke is
only a regression guard.

## CI

`.github/workflows/runtime-baseline.yml` runs all three modes against a local,
deterministic fixture on relevant pull requests. This keeps PR validation
independent from TrueNAS, Cloudflare and secrets.

The same workflow can be started manually with `target_url` to validate an
explicit live endpoint. The live performance pass remains bounded to 20
requests at concurrency 4.

## Production security gate

`.github/workflows/production-security.yml` separates cheap PR checks from the
heavier DAST scan:

- every non-draft PR targeting `master` runs the live integration and HTTP
  security baseline against `https://fastapi-sample.fastapicloud.dev`;
- `master` pushes, the daily schedule and manual dispatch run the same smoke, a
  bounded performance pass and an OWASP ZAP Baseline scan;
- ZAP is passive/non-destructive here: it spiders for at most two minutes and
  performs passive analysis; active attack scanning is intentionally excluded;
- PRs do not rerun ZAP. Instead `DAST master baseline gate` requires the latest
  completed `master` DAST to be successful and no older than 36 hours;
- the PR introducing the workflow has a one-time bootstrap exception because
  no `master` run can exist until that workflow is merged.

The ZAP action is pinned by commit SHA, does not create GitHub issues, and
publishes its scan report as a workflow artifact. `fail_action: true` makes
new ZAP alerts visible as a failed master security baseline; review and
explicitly baseline a confirmed false positive rather than weakening the PR
freshness gate.

CodeQL remains the Python SAST implementation and now runs on non-draft pull
requests as well as its scheduled scan. Checkov in MegaLinter continues to
cover repository IaC/configuration concerns that CodeQL does not model.
