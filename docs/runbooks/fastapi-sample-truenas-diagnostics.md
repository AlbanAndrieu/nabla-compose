# FastAPI Sample · TrueNAS staging deployment and bounded diagnostics

Scope: operator-run procedures for `sample` on TrueNAS. Does not change
FastAPI Cloud or Cloudflare policies. The stage endpoint is
`http://127.0.0.1:8091` from TrueNAS.

## What the 2026-10-17 results show

- The unqualified command `sudo bash scripts/truenas/update-fastapi-sample.sh`
  deployed **`master` `8c4492d131c3ec6e0c0e4cdc18f261c0b9af40d4`**,
  not unmerged fastapi-sample PR #342 `748497d62881f7631801c8f8cd11bbf4c04633e8`.
- Staging reports `healthy`, `v0+1.22.1`, TrueNAS observer access
  3/3 and pfSense least-privilege 7/7. Gatus was up with 78 synthetic series.
- The parent Git repository pins submodule `f8ecc776...`; its working
  checkout is now `8c4492d1...`. The resulting `M fastapi-sample` in
  the parent is expected Gitlink drift, **not proof of modified Python code**.
  Do not automatically stage or commit that Gitlink during a staged test.
- For public HTTP endpoints, TrueNAS-host requests completed in
  0.09/0.10/0.54 seconds; container requests in 0.45/0.44/0.64 seconds.
  Container DNS: 0.04–0.19 seconds. These samples do **not** show a sustained
  DNS/egress outage. They also do not prove the 12 concurrent public probes
  fit in the existing 4-second fan-out budget. Keep that budget unchanged
  until repeated service-specific timings identify the bottleneck.
- Garage HTTP 302 is an Access/edge response, not proof of anonymous
  Garage origin access or application health.

## Compact deployment output

The updater now groups steps into six stages and summarizes:
- requested ref and checkout SHA; **default `master` is explicit**;
- Docker build mode, service health and application version;
- observer network, TrueNAS allowlist, Gatus and pfSense RBAC;
- expected Gitlink mismatch, plus `build_revision=null` evidence limitation.

Routine Git fetch/submodule chatter, network JSON, full health payload and
authenticated pfSense smoke stdout are suppressed on success. A failed
operation retains a bounded diagnostic excerpt. For intentionally verbose
build output only, set `FASTAPI_SAMPLE_VERBOSE_LOGS=true`. Do not publish
unredacted verbose logs.

**Safety:** `update-fastapi-sample.sh` is NOT read-only. It builds images,
may reconcile observer allowlists, replaces the staging container and runs
TrueNAS app.update/redeploy. Confirm reviewed ref and rollback state first.

## Non-destructive diagnostic

After updating the `nabla-compose` PR branch, run:

```bash
cd /mnt/cpool/compose/nabla-compose
bash scripts/truenas/diagnose-fastapi-sample.sh --cycles 3
```

Option `--cycles 1` is a quick check; `--cycles 3` samples cached
`/api/health-board` at 31-second intervals (two waits). Option
`--interval 30..120` changes only that sampling interval. Each external
request uses no redirect following and a 12-second maximum; the
health-board is bounded to 30 seconds/cycle.

The diagnostic collects:
1. parent/submodule SHAs, TrueNAS app and Docker state, runtime `/v2/version`;
2. the same three public HTTP timing probes from TrueNAS and inside Docker;
3. sanitized Docker resolver metadata (no environment dump);
4. internal/public health-board summary plus Garage member evidence;
5. Prometheus `/-/ready` and bounded Gatus synthetic series counts;
6. one Docker stats snapshot.

Nothing is restarted, no secrets or response headers are emitted, no
Cloudflare Access login URL is followed. Redact environment-specific hostnames
and service details before publishing outside the operational team.

### Testing the specific FastAPI PR (requires explicit operator approval)

Use explicit `sudo env` so the requested ref is passed to the root-run helper without inheriting unrelated shell environment variables:

```bash
sudo env FASTAPI_SAMPLE_DEPLOY_MODE=build \
  FASTAPI_SAMPLE_REF=748497d62881f7631801c8f8cd11bbf4c04633e8 \
  bash scripts/truenas/update-fastapi-sample.sh
```

**Do not run this command just for diagnostic collection**; it changes the
staging runtime. Confirm no tracked edits inside `fastapi-sample`, staged
runtime secrets, and an accepted rollback SHA/image. After deployment, rerun
`diagnose-fastapi-sample.sh --cycles 3` and verify Garage internal probes,
`priority_source`, public completed/timed_out and any Cloudflare tunnel
warning. If the health board still reports `timed_out=12` but individual
HTTP requests remain fast, investigate scheduling/concurrency, other
endpoints and cold-vs-warm cache rather than adjusting DNS or inflating
timeouts without evidence.

Note: `/v2/version.build_revision=null` cannot attest running image SHA.
The updater's Git checkout SHA is provenance for the local *build context*,
not cryptographic attestation of the deployed image. An OCI revision label or
immutable image digest attestation is a separate follow-up.

## Follow-up acceptance

- [ ] Current fastapi-sample PR revision deployed intentionally on staging.
- [ ] Three health-board cycles show all Garage components with fresh LAN
      evidence and correct `external`/exposure intent.
- [ ] Public timeout rate and endpoint timings correlated with resource use.
- [ ] Authoritative `nabla-compose` catalog fixes LanguageTool duplicate;
      FastAPI successfully consumes canonical priority metadata.
- [ ] Full repo quality gate and deployment script validation at exact HEAD;
      no unnecessary GitHub Actions dispatch. Never merge automatically.
