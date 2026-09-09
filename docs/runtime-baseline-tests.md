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
- `master` pushes, the daily schedule and manual dispatch run the same smoke,
  a bounded performance pass and two bounded ZAP checks: the filtered FastAPI
  OpenAPI surface and the public TrueNAS API transport when the runner is permitted;
- the FastAPI OpenAPI scan runs in ZAP safe mode (`-S`) against a generated
  read-only specification; the TrueNAS checks use passive
  zero-spider-budget baselines; active/mutating attack scanning is excluded;
- PRs do not rerun ZAP. Instead `DAST master baseline gate` requires the latest
  completed `master` DAST to be successful and no older than 36 hours;
- the PR introducing the workflow has a one-time bootstrap exception because
  no `master` run can exist until that workflow is merged.

The ZAP actions are pinned by commit SHA, do not create GitHub issues, and
publish separate scan artifacts. `fail_action: true` makes high-signal
findings a failed master security baseline. The only current
exceptions are the three production response-header findings already observed
on 2026-09-09 (anti-framing, `X-Content-Type-Options`, HSTS), recorded in
`config/security/production-http-baseline.json` and `.zap/rules.tsv`. Remove
those exceptions as the FastAPI production headers are fixed; do not add a new
exception merely to turn CI green.

CodeQL remains the Python SAST implementation and now runs on non-draft pull
requests as well as its scheduled scan. Checkov in MegaLinter continues to
cover repository IaC/configuration concerns that CodeQL does not model.

## Production gate hardening

The integration/performance target remains
`https://fastapi-sample.fastapicloud.dev`. DAST intentionally also validates
the public TrueNAS API transport at
`https://truenas.albandrieu.com:7000/api/versions`. These checks are bounded and
read-only; they must not be expanded to the pfSense management API. The TrueNAS
scan is skipped when the generic GitHub runner is denied or source-filtered.

The pre/post-deploy smoke also verifies the production
`/api/homelab/status` and `/api/runtime/topology` contracts so a green
`/health` cannot hide a broken runtime/topology API.

### ZAP result policy

The initial master ZAP run on 2026-09-09 found zero configured FAIL findings and
nine passive WARN categories. WARN findings remain visible in the ZAP artifact
but do not fail the workflow by themselves. The policy promotes high-signal
rules (vulnerable JS, insecure cookies, debug/sensitive disclosure, directory
browsing, mixed content, cross-domain misconfiguration, weak authentication and
application error disclosure) to `FAIL`.

Only the FastAPI API policy carries the three already-known response-header
debts as `IGNORE`: rules 10020, 10021 and 10035. The TrueNAS
policies carry no IGNORE entries. Do not expand an IGNORE list merely to make CI
green.

The PR DAST evidence gate queries the **latest** relevant master run, including
an in-progress or failed run. It therefore cannot pass on an older completed
success while a newer master DAST is still running or has regressed.

### Required GitHub checks

Workflows alone do not make a pull request unmergeable. Configure repository
rules/branch protection for `master` to require at least:

- `SAST / CodeQL (Python)`;
- `Production pre/post-deploy smoke`;
- `DAST master baseline gate`;
- the repository pre-commit/agent quality gate.

The repository currently exposes no GitHub Ruleset through the available API,
and the connected GitHub App does not have repository Administration permission
to change classic branch protection. This enforcement therefore remains an
explicit repository-admin action.

## API-aware DAST targets

The master-only DAST now has three bounded layers:

1. a **safe-mode ZAP API Scan** driven by the FastAPI production OpenAPI
   document after repository-side filtering;
2. a passive TrueNAS API transport scan against
   `https://truenas.albandrieu.com:7000/api/versions`;
3. a passive web baseline against `https://sample.albandrieu.com` with a
   zero-minute spider budget, so it validates the web entry point without
   crawling into the API surface.

The FastAPI filter keeps only `GET`/`HEAD`/`OPTIONS` operations and
explicitly removes pfSense/Snort/pfBlocker plus aggregate health routes that can
fan out into the pfSense API.

The FastAPI OpenAPI API scan runs with ZAP `-S` safe mode, so it skips active
scanning and cannot exercise mutating OpenAPI operations. The filtered spec is
generated by `scripts/security/prepare-zap-openapi.py` and fails closed if
every operation is removed.

TrueNAS 26 no longer exposes the legacy REST API. Its real management API is
versioned JSON-RPC 2.0 over WebSocket at `/api/current`; `/api/versions`
proves the HTTPS API surface but not authenticated WebSocket access. Functional
`/api/current` authentication/RBAC therefore remains covered by the dedicated
read-only TrueNAS observer acceptance checks rather than by an active ZAP scan.

The **pfSense API on TCP/10443 is deliberately excluded from ZAP, OpenAPI DAST
and performance/load tests** because that appliance API is sensitive to request
fan-out. pfSense stays covered by low-frequency posture/observer checks only.
