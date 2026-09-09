# Operator script refactor plan

## Why this refactor exists

The repository currently contains 67 files under `scripts/`, including 21
TrueNAS-specific operator scripts. The service diagnostics have converged on a
useful pattern, especially `scripts/truenas/diagnose-scrutiny.sh`:

1. collect platform state without mutating it;
2. inspect the service/container state and health history;
3. prove dependency reachability from the same runtime namespace;
4. validate mounts, secrets and filesystem permissions without printing
   secret values;
5. collect bounded logs and lifecycle evidence;
6. support a guarded startup-capture mode when the platform cleans failed
   containers too quickly;
7. return a meaningful non-zero status so the global TrueNAS audit can use the
   diagnostic as an acceptance gate.

The goal is to preserve this behavior while removing duplicated shell
implementation.

## Design principles

- Keep current CLI paths working during migration. Existing scripts become
  compatibility wrappers where necessary.
- Separate **read-only diagnosis**, **bootstrap**, **deploy/reconcile** and
  **recovery**. A diagnostic must never restart/redeploy a service.
- Make common probes deterministic and bounded: explicit connect/max timeouts,
  finite retries and bounded log tails.
- Never print secret values. Generic helpers may validate key presence, owner,
  mode and file size only.
- Prefer service contracts/data for declarative checks and thin service
  adapters only for genuinely special logic.
- Keep the global TrueNAS audit as the orchestrator; it should call diagnostics,
  not reimplement them.

## Reusable components identified

### 1. Shell/runtime primitives — `scripts/lib/common.sh`

Reusable across almost every shell script:

- `die` / `warn` / `info` / `ok`;
- `require_command`;
- `require_root` and operator-mode checks;
- repository-root discovery;
- temporary-file/directory creation;
- cleanup registration / `trap EXIT`;
- mode parsing (`--check`, `--apply`, `--capture-startup`);
- compact/full diagnostic output switches.

### 2. Diagnostic result/reporting — `scripts/lib/diagnostic.sh`

The Sentry diagnostic already has richer reporting concepts that can become
generic:

- ok / failed / warning / skipped counters;
- bounded detailed report file;
- concise key findings;
- stable exit-code contract;
- section headings;
- redacted command output;
- optional JSON output later for FastAPI/topology consumers.

### 3. TrueNAS middleware primitives — `scripts/lib/truenas.sh`

Repeated across audit/deploy/diagnose scripts:

- `truenas_app_query <app>`;
- `truenas_app_state <app>`;
- active workload/container extraction;
- recent `app.*` jobs;
- create/update custom app using include or rendered compose;
- canonical checkout/worktree drift detection;
- recent `/var/log/app_lifecycle.log` evidence;
- wait for aggregate app state with a bounded timeout.

Mutation helpers must live here but must only be imported by deploy/bootstrap
scripts, never by read-only diagnostics.

### 4. Docker/runtime inspection — `scripts/lib/docker.sh`

Repeated in Scrutiny, Sentry, Wazuh and InfluxDB diagnostics:

- container existence;
- state / health / restart count / exit code;
- healthcheck history;
- mounts and network membership;
- process/resource context (`docker top`, `docker stats --no-stream`);
- bounded recent logs;
- environment extraction with explicit allow-list/redaction;
- wait for stable health across more than one healthcheck cycle;
- targeted container restart for explicit recovery helpers.

### 5. Network and application probes — `scripts/lib/probe.sh`

Common forms:

- HTTP/HTTPS probe with accepted status-code set;
- JSON health assertion;
- TCP probe;
- container-to-container HTTP/TCP probe;
- DNS/getent resolution proof;
- retry/backoff / wait-until-ready;
- optional service-token headers without logging them.

This should replace hand-written `curl` loops in individual service scripts.

### 6. Secret/file contracts — `scripts/lib/secrets.sh`

Common checks:

- regular file exists and is non-empty;
- owner UID/GID;
- mode (`0600`, `0400`, etc.);
- required environment key exists and has a non-empty value;
- public certificate vs private-key policy;
- no secret value is emitted to stdout/stderr.

Wazuh TLS ownership and Scrutiny token validation are concrete examples.

### 7. Guarded startup capture — `scripts/lib/startup-capture.sh`

The Scrutiny incident showed a generally useful pattern for TrueNAS Custom
Apps: failed `app.create` operations can remove temporary containers before
an operator can read their logs.

The reusable helper should provide:

- refuse capture while the TrueNAS app or target container already exists;
- `docker compose up -d --no-deps <service>`;
- configurable capture/stability duration;
- capture inspect/health/log/mount/network/env evidence;
- optional dependency probes from inside the container;
- guaranteed cleanup on EXIT;
- no collector/worker/side-effect service unless explicitly selected.

Candidates that can benefit later include Wazuh Indexer/Dashboard, Sentry
one-shot migrations/consumers, OpenRAG and other multi-container apps.

### 8. Service contracts — `scripts/contracts/truenas/*.yaml`

Most services should not require a bespoke 200-400 line diagnostic. A
declarative contract can describe:

- TrueNAS app id;
- required/optional containers;
- expected steady state;
- HTTP/TCP endpoints and accepted status codes;
- dependency endpoints;
- required mounts/networks;
- secret/file contracts;
- health stabilization window;
- allowed one-shot exited containers;
- log patterns that are warnings vs failures.

A future generic driver:

```bash
scripts/truenas/diagnose-service.sh scrutiny
scripts/truenas/diagnose-service.sh influxdb
```

can execute the common contract.

### 9. Thin specialized adapters

Some services genuinely require custom logic and should keep small adapters:

- **Sentry:** Kafka topics/groups, heartbeat files, one-shot migrations and
  targeted consumer recovery;
- **Scrutiny:** SMART device visibility, workstation collector, InfluxDB
  bucket/task/migration contract;
- **Wazuh:** Indexer/Dashboard TLS ownership and `vm.max_map_count`;
- **InfluxDB:** scraper inventory and Influx-specific API/token checks;
- **Talos/Kubernetes:** `talosctl`/Kubernetes resource semantics.

The adapter should call common primitives instead of duplicating them.

## Target layout

```text
scripts/
├── lib/
│   ├── common.sh
│   ├── diagnostic.sh
│   ├── docker.sh
│   ├── probe.sh
│   ├── secrets.sh
│   ├── startup-capture.sh
│   └── truenas.sh
├── contracts/
│   └── truenas/
│       ├── influxdb.yaml
│       ├── scrutiny.yaml
│       ├── sentry.yaml
│       └── wazuh.yaml
├── truenas/
│   ├── diagnose/
│   ├── bootstrap/
│   ├── deploy/
│   ├── recover/
│   └── audit-app-lifecycle.sh
└── ...
```

The existing paths such as
`scripts/truenas/diagnose-scrutiny.sh` remain compatibility entrypoints until
all callers, documentation and CI have migrated.

## Migration sequence

### Phase A — extract without behavior change

1. add `common.sh`, `probe.sh`, `docker.sh`, `truenas.sh` and
   `diagnostic.sh`;
2. add unit/contract tests for each primitive;
3. migrate the smallest diagnostic first: InfluxDB;
4. compare old/new output and exit codes.

### Phase B — migrate existing specialist diagnostics

Order:

1. InfluxDB;
2. Wazuh;
3. Scrutiny;
4. Sentry last because its Kafka logic is the most specialized.

Keep current CLI names as wrappers.

### Phase C — data-driven diagnostics

Introduce service contracts and `diagnose-service.sh`. Move generic service
checks out of bespoke shell code. Keep only specialized adapters.

### Phase D — directory reorganization

Move implementation files into `diagnose/`, `bootstrap/`, `deploy/` and
`recover/`; keep compatibility wrappers for at least one release cycle.

### Phase E — quality gate

Add a repository guard that:

- rejects new executable scripts placed directly in an already-organized
  namespace when a matching subdirectory exists;
- enforces executable mode for shebang scripts;
- runs `bash -n`/ShellCheck where applicable;
- detects obvious duplicated operator primitives so new service scripts use the
  common library instead.

## Current Scrutiny lesson feeding the design

The standalone startup capture proved that network connectivity, SQLite access
and the InfluxDB health endpoint can all be green while application startup
still fails later during a privileged migration. Scrutiny v0.9.3 attempts to
create temporary `<bucket>_new` buckets during its WWN→UUID migration, so the
runtime token must have the minimum organization-scoped bucket permissions
required for create/delete/rename during that migration. This is a
service-specific authorization contract and belongs in the Scrutiny adapter,
while the token/file mechanics belong in the shared secrets/probe libraries.
