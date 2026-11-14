# Operator scripts

`scripts/` contains executable operator workflows. Keep entry points stable and
move reusable implementation details into `scripts/lib/` instead of copying
helpers between platform directories.

## Local-first task entry points

`justfile` is a lightweight interface alongside the unchanged legacy `Makefile`.
Install pinned tools using `mise install` (Just 1.58.0; Betterleaks 1.9.0),
then use:

```bash
just --list
just quality
just fix
just pre-push
just tooling-test
just secrets
```

`just quality` delegates to `mise run agent-quality`, while `just fix` uses
the existing deterministic autofix gate. `just pre-push` performs the strict
publication checks without pushing or merging. `just secrets` scans the current
worktree with Betterleaks, `just secrets-staged` scans staged diffs and
`just secrets-history` is an explicit, potentially expensive full-history scan.
Outputs are redacted; no online credential validation is requested.

Betterleaks v2.0.0-rc.5 is the sole active Pre-commit secret scanner; the existing
`.gitleaks.toml` is intentionally retained as its compatibility policy during
migration. Historical `gitleaks:allow` comments are still understood by
Betterleaks. The old MegaLinter Gitleaks linter remains disabled.

The `Makefile` is retained for legacy targets. Avoid its default `make`
build/cleanup cycle when only validation is intended.

## Ownership

- `scripts/truenas/`: TrueNAS lifecycle, diagnostics, deployment and recovery.
- `scripts/talos/`: Talos/Kubernetes installation, validation and smoke tests.
- `scripts/pfsense/`: pfSense posture, diagnosis and recovery.
- `scripts/pfsense/prepare-upgrade.sh --ssh <alias>`: read-only version, arm64,
  memory/storage and package inventory before upgrade; see
  [`docs/pfsense-upgrade-26-07.md`](../docs/pfsense-upgrade-26-07.md) for backup,
  upgrade and REST API reinstall steps.
- `scripts/secrets/`: metadata-driven secret rendering and validation.
- `scripts/observability/`: monitoring/telemetry helpers.
- `scripts/lib/`: small side-effect-free shell primitives shared by operator
  entry points.

## Consolidated TrueNAS entry points (2026-11-08)

- `scripts/truenas/bootstrap-app-postgres.sh [--check|--apply|--describe] <app>`
  provisions one application's role/database on the shared PostgreSQL App
  from its canonical runtime secret (`homeassistant`, `joplin`, `scanopy`,
  `plumber`, `netbox`, `dependency-track`, `defectdojo`, `keycloak`).
  `bootstrap-joplin-postgres.sh`, `bootstrap-scanopy-postgres.sh`,
  `bootstrap-homeassistant-postgres.sh` and
  `bootstrap-security-tooling-postgres.sh` are thin compatibility wrappers.
  `scripts/lib/postgres.sh` owns container resolution, idempotent SQL and the
  login proof; passwords only travel through `docker exec -e`.
- `scripts/lib/app-deploy.sh` is the shared `--check`/`--apply` contract of the
  single-App deployers (`deploy-joplin.sh`, `deploy-scanopy.sh`): canonical
  checkout gate, Compose validation, `<app>_mutations=0` preflight report and
  middleware reconciliation gated by `NABLA_RUNTIME_CHANGE_APPROVED=yes`.
- `scripts/truenas/diagnose-homeassistant.sh`, `diagnose-homeassistant-usb.sh`
  and `diagnose-homeassistant-overkiz.sh --host <ip>` are read-only Home
  Assistant checks (runtime owner, integrations, HACS, USB dongle hand-off,
  Overkiz io gateway local API). `scripts/lib/homeassistant.sh` owns container
  resolution and the optional API token (`HA_TOKEN`, root:root 600, sent only
  through `secrets_curl_headers`).
- `scripts/truenas/rollout-pending-apps.sh [--plan|--check|--apply] [app]`
  is the single operator entry point for the Apps declared but not deployed
  yet: `--plan` prints the ordered steps without root, `--check` runs every
  read-only gate and reports READY/BLOCKED per App, `--apply <app>` deploys
  one App through its owning deployer and re-applies the backup role.

## Documentation and cross-repository script ownership

The [Compose roadmap](../docs/roadmap.md) owns the remaining infrastructure and script-acceptance decisions. The [FastAPI engineering roadmap](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) owns Python API/UI test runners and probes; [OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md) owns Gateway/heartbeat. Do not copy launchers between repositories. Retain a compatibility wrapper only while a live recipe, test or rollback procedure calls it; track that consumer before removal. No removal of historical OpenClaw or YubiKey entry points without their contract tests.

## Approved execution and offline portfolio check

The approved priority, recorded in merged PR #369, is **H02/G1 (PostgreSQL) → H01 (CSI) → H05 (Gatus / Prometheus)**. See [portfolio](../docs/roadmap-portfolio.md).

- `python3 scripts/quality/check-roadmap-portfolio.py --check` validates the declared order, IDs, state vocabulary and local references offline.
- `python3 scripts/quality/check-roadmap-portfolio.py --json` exports the dated decision, without claiming live status.
- `python3 scripts/quality/check-roadmap-portfolio.py --worklist` prints only the H02/H01/H05 order of PR #369 (read-only).
- For H01 use the dedicated `scripts/talos/validate-csi-prereqs.sh` and `smoke-truenas-csi-nfs.sh`. For H02 use the existing `postgresbackup` restoration process. For H05 use `scripts/truenas/verify-service-observability.py`. These scripts have different privileges: do not fuse them into a mutating all-in-one operation.

## G1 — Backup verification and secret rotation

- `scripts/truenas/verify-postgresbackup-restore.py`: verify checksum, then optionally restore in a disposable Docker container with `--network none` and `--pull never`.
- [G1 operator runbook](../docs/runbooks/postgres-g1-restore-and-secret-rotation.md): rotate the exposed exporter secret privately and accept a dated independent restoration.
- The cron remains disabled; code and `pg_restore --list` alone do not close H02.

## Refactor rules

1. Preserve existing operator entry-point paths while extracting shared code.
2. Keep generic primitives in `scripts/lib/`; keep platform behavior in the
   owning platform directory.
3. Do not create a library for a helper used by only one script.
4. Shared libraries must not mutate infrastructure when sourced.
5. Immutable bundles must explicitly include and checksum every sourced file.
6. New shell code must pass `bash -n`, shfmt and ShellCheck; Bashate is a
   complementary style check, not a second semantic linter.

The long-term target is fewer entry points with explicit modes, thin wrappers
for compatibility, and domain libraries only where duplication is proven.

## Agent execution mode (workstation vs disconnected)

`AGENT_EXECUTION_MODE=offline` is the default for API-only/Codex sessions;
`bash scripts/agent-diagnostics.sh --static` runs the existing offline L1
syntax gate. Live verification is explicitly blocked with `NOT_RUN` in that mode.
On a connected Claude Code workstation choose `AGENT_EXECUTION_MODE=workstation`
and `bash scripts/agent-diagnostics.sh --runtime <service>` for a bounded,
read-only direct/Gatus/Prometheus triad (1–3 named services). This does not
replace full local quality or a TrueNAS authenticated acceptance run.
See [agent execution playbook](../docs/agent-execution-playbook.md).
