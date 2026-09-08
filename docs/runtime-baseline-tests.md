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
