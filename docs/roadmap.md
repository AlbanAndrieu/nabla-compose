# Homelab roadmap

Last updated: 2026-10-10.

This file is the **concise execution index and conversation restart point**.
Detailed procedures, rollback instructions and historical evidence stay in their
canonical runbooks/incidents; see [`docs/README.md`](./README.md).

Primary references:

- reboot/recovery: [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md);
- runtime/storage layout: [`truenas-runtime-layout.md`](./truenas-runtime-layout.md);
- secret migration: [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md);
- platform migration: [`homelab-platform-migration-roadmap.md`](./homelab-platform-migration-roadmap.md);
- security tooling: [`security-inventory-tooling-roadmap.md`](./security-inventory-tooling-roadmap.md);
- AI stack upgrades, integrations and consolidation:
  [`ai-stack-upgrade-consolidation-plan.md`](./ai-stack-upgrade-consolidation-plan.md);
- service catalog v2: [`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md);
- incidents/evidence: [`incidents/`](./incidents/).

## Roadmap contract

- **declared / repository-ready** means code/config exists; it does not imply
  deployment or runtime acceptance;
- **runtime accepted** requires functional health/evidence appropriate to the
  service;
- **reboot accepted** additionally proves recovery from canonical persisted state;
- migrations are one service at a time and remain rollback-safe until acceptance;
- warning/unknown external dependencies stay distinguishable from application DOWN;
- roadmap = status/order/next action; runbook = procedure; incident = evidence.

## Post-reboot LIGHT profile and runtime acceptance (2026-10-10)

- [x] Define explicit optional app set in
  `config/truenas/restore-optional-apps.txt` (Graylog, Zabbix,
  Transmission and the *arr family). Default restore behavior excludes
  this final optional wave even if an older restore list requests it.
- [x] Add `restore-optional-apps.sh --check|--stop|--start`.
  It uses exact TrueNAS App IDs, refuses protected foundation services
  and refuses interruption of in-flight `DEPLOYING` Apps.
- [x] Add bounded read-only `triage-post-reboot-apps.sh` for
  non-RUNNING Apps and problematic containers.
- [ ] On TrueNAS, verify the actual App IDs and update optional list;
  check that no required service depends on an optional workload.
- [ ] Run read-only triage first; distinguish intentionally STOPPED
  optional Apps from `DEPLOYING`/`CRASHED` core applications.
- [ ] **DSOMM:** validate seeds, runtime image and canonical storage with
  `deploy-dsomm.sh --check`; apply only after an exact failing
  precondition is understood, then prove healthy HTTP and saved state.
- [ ] **Cyberbro:** verify two Compose services, diagnostics and canonical
  env materialization with `diagnose-cyberbro.sh` and
  `bootstrap-cyberbro-env.sh --check`. Only reconcile/redeploy after
  identifying failed dependency, permission, secret contract or readiness.
- [ ] **Secrets:** take a global read-only
  `bootstrap-repository-env-files.sh --check` inventory, then stage and
  finalize each App separately using the canonical Vaultwarden manifest.
  Never overwrite existing nonempty `.env.secrets`, never print values,
  preserve rollback and never finalize a failing runtime.
- [ ] Reboot acceptance: foundation RUNNING, no core App stuck
  DEPLOYING/STARTING, no unauthorized optional auto-start, and all
  previously accepted secrets/loadable integrations unchanged.

Commands and safety boundary:

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/triage-post-reboot-apps.sh
sudo bash scripts/truenas/restore-optional-apps.sh --check
sudo bash scripts/truenas/restore-app-set.sh --check --apps-file config/truenas/restore-foundation-apps.txt
sudo bash scripts/truenas/deploy-dsomm.sh --check
sudo bash scripts/truenas/diagnose-cyberbro.sh
sudo bash scripts/truenas/bootstrap-cyberbro-env.sh --check
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check
```

Stop optional apps only by explicit operator action:
`sudo bash scripts/truenas/restore-optional-apps.sh --stop`.
Later opt in to the final optional wave by
`sudo bash scripts/truenas/restore-optional-apps.sh --start`.
A `restore-app-set.sh --apply` defaults to LIGHT unless
`--include-optional` is passed. Do not treat STOPPED optional Apps
as a platform recovery failure.

## Targeted post-reboot incident follow-up (2026-10-10)

Runbook: [Git/DSOMM/Gatus/Vaultwarden/Scrutiny incident](./incidents/2026-10-10-post-reboot-git-dsomm-gatus-vaultwarden.md).

- [x] Identify `dsomm` exit 255 as Caddy `execve EPERM`,
  consistent with the upstream file-capability versus `cap_drop: ALL`
  issue; source fix adds only `NET_BIND_SERVICE` back to the bounding
  set. **Runtime validation pending**, not yet a confirmed repair.
- [ ] Correct Gatus read access to `apps/gatus/config/config.yml`
  using the **actual** container UID and TrueNAS path ACL. Do not
  loosen all dataset permissions or modify application data.
- [ ] Correct `bitwarden-api`'s persisted `http://vaultwarden`
  Bitwarden CLI server URL; tracked Compose already specifies HTTPS.
  Check old Doco-CD adapter consumers, back up only the affected
  CLI config and verify TLS before its isolated restart.
- [ ] Repair the TrueNAS operator's `.git/index` ownership/access
  without `sudo git` or reset/clean on the nested
  `fastapi-sample` submodule.
- [ ] Reconcile Scrutiny after operator removed its repository-local
  legacy file and commented a possible old InfluxDB token in the
  canonical file. Do not uncomment unverified credentials, restage,
  finalize or rotate as a batch. Missing `dotenv` under system Python
  requires the existing **user-space venv**.
- [ ] Confirm DSOMM/Gatus/Vaultwarden acceptance via runtime health and
  exact-HEAD generator/quality gate checks before closing the incident.

## Runtime evidence — 2026-10-10, post-reboot (user-provided)

- [x] LIGHT review: `emby`, `graylog`, `lidarr`,
  `transmission`, `zabbix` are STOPPED; the remaining optional
  `*arr` names in the configured list are ABSENT. This is **expected**,
  not a recovery failure. Do not bulk start them.
- [x] Cyberbro: TrueNAS App `RUNNING`, two Compose containers running,
  web healthy, MCP HTTP 400 reachable (not a standalone TrueNAS App),
  zero restarts and canonical Cyberbro `.env`/`.env.secrets` contract
  accepted. No Cyberbro redeploy required.
- [ ] DSOMM: TrueNAS `STOPPED`, Docker `dsomm` restarting exit 255.
  Seed check passed (22 activities/22 evidence), pinned image exists and
  Compose validation passed. Fix catalog generator defect first (orphan
  `openwebui-pipelines` icon + missing `subprocess` import; source fixes
  in this PR), regenerate the catalog/consumers, then capture **bounded
  DSOMM logs** and TrueNAS app job errors. Do **not** assume a catalog
  error caused the Docker restart loop. Do not blindly redeploy.
- [ ] Gatus: TrueNAS `STOPPED` but container `Restarting (2)`.
  Diagnose its startup/config and regenerate Pipelines-derived monitors
  before a controlled restart; do not classify as intentional LIGHT.
- [ ] `bitwarden-api`: Docker restart exit 1; inspect owning project,
  active consumers and its logs separately. Avoid rotating Vaultwarden
  or upstream tokens without evidence.
- [ ] Docling: `ABSENT` (not `DEPLOYING`); schedule explicit install
  only once prior state and resources are verified.
- [ ] Scrutiny secrets: **hard conflict** between
  `/mnt/cpool/scrutiny/.env.secrets`, repository-local
  `apps/scrutiny/.env.secrets`, and canonical
  `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`.
  Compare **key names and semantic equality without printing values**,
  preserve historical InfluxDB token and do not issue `--restage` or
  `--finalize` until source authority is reconciled.
- [ ] `.env.secrets` global inventory: 8 declared missing-source apps,
  empty placeholders including AutoKuma, CrowdSec, Joplin, PostgreSQL and
  Scanopy, plus numerous staged/finalize-pending apps. Treat
  intentionally disabled/not-installed services separately; no empty
  secret placeholders accepted as production credentials. Finalize
  individually after the runtime consumer passes.

Safe next TrueNAS commands (bounded output, no raw secret values):

```bash
cd /mnt/cpool/compose/nabla-compose
sudo bash scripts/truenas/triage-post-reboot-apps.sh
sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check scrutiny
sudo python3 scripts/secrets/compare_dotenv_sources.py --app scrutiny \
  --left /mnt/cpool/scrutiny/.env.secrets \
  --right /mnt/cpool/compose/nabla-compose/apps/scrutiny/.env.secrets
sudo docker logs --tail 50 dsomm 2>&1 | tail -50
sudo docker logs --tail 40 gatus 2>&1 | tail -40
sudo docker logs --tail 40 bitwarden-api 2>&1 | tail -40
```

**Quality gate distinction:** generator source defects fixed in PR; output
catalog, topology, Gatus, Homarr and AutoKuma projections still require
canonical regeneration and L3 exact-HEAD validation. No runtime changes
have been made by the agent.

## Restart context — 2026-10-07

PR #240 (`fix: stabiliser DSOMM, Sentry et les migrations runtime TrueNAS`) is
**merged**. Its repository contracts are available on `master`, but the
post-merge TrueNAS operator transactions were **not run as part of that merge**.
A new discussion must therefore **not** treat DSOMM/Sentry/Scrutiny/Code runtime
migration as complete.

Conversation bootstrap:

```text
Repository: AlbanAndrieu/nabla-compose
Base: master after merged PR #240
Validation policy: local-first; GitHub Actions are not the edit loop
Never merge automatically
Do not assume the TrueNAS commands below were already executed
Start with read-only checks and current runtime evidence
Apply/finalize exactly one service transaction at a time
Preserve legacy files/datasets until runtime + restart/reboot acceptance
```

### Immediate TrueNAS acceptance queue

Execute from the canonical TrueNAS checkout. Start with the read-only global
inventory:

```bash
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check
sudo bash scripts/truenas/audit-app-lifecycle.sh
```

Then progress in bounded transactions:

1. [ ] **DSOMM** — repository seed/deployer is ready; perform the first runtime
   acceptance without overwriting existing assessment state:

   ```bash
   sudo bash scripts/truenas/deploy-dsomm.sh --check
   sudo bash scripts/truenas/deploy-dsomm.sh --apply
   ```

   Require TrueNAS App `RUNNING`, HTTP health and protected persisted seed/state
   before changing DSOMM from `planned` to `active`.

2. [ ] **Sentry canonical secret finalization** — existing Sentry E2E ingestion
   history remains valid evidence, but the merged recovery/restage/finalize
   transaction still needs current TrueNAS evidence. Run `--check` first,
   use `--apply` only when the current diagnostic requires reconciliation, and
   use `--finalize` only after a fresh diagnostic + E2E ingestion smoke.
   Never reset Kafka offsets/topics/databases as part of this transaction.

3. [ ] **Scrutiny runtime-env acceptance** — preserve the existing v2 InfluxDB
   token, scope-version marker and authorization ID as one set. Compare sources
   value-blind, import the accepted historical values to Vaultwarden, materialize
   `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets`, then run:

   ```bash
   sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh --check
   sudo bash scripts/truenas/deploy-scrutiny.sh --check
   ```

   Do not run the bootstrap `--apply` merely because the canonical file is
   missing. Rotate only as an explicit operator decision. Acceptance also
   requires Web/API health, TrueNAS SMART visibility and the pinned workstation
   collector submission.

4. [ ] **Code Server runtime-env cutover** — preserve the historical
   `CODE_PASSWORD` value while mapping it to runtime `PASSWORD`. Import and
   materialize through the canonical secret tooling, validate
   `http://172.17.0.24:8443/healthz`, then finalize only when the generic
   runtime-env check is clean:

   ```bash
   sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check code
   sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize code
   ```

5. [ ] **First-wave runtime envs** — accept Scanopy, Joplin and AutoKuma one
   service at a time with
   `accept-runtime-env-first-wave.sh --check/--stage/--accept`. AutoKuma stays
   blocked until repository-owned Uptime Kuma is present and RUNNING. Scanopy
   requires reviewed immutable server/daemon digests.

6. [ ] **Sample** — finish canonical runtime-env/reboot acceptance and normalize
   PostgreSQL ownership to a dedicated `sample` database/role. Keep
   `fastapi_observer` read-only and prove `VM_READ` for the three Talos VMs.

The exact import/materialization/finalization commands and rollback rules remain
owned by [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md) and
the service README/runbook. Never bulk-finalize env files or recreate non-empty
datasets just to change presets.

## OpenClaw personal assistant — workstation stabilization

**Scope:** OpenClaw manages personal Gmail/WhatsApp triage and proposed replies
(read-only by default); Hermes manages development/cloud/cybersecurity. Their
secrets, memory, tokens and tools must remain isolated. No private message
contents or tokens may enter Git, logs or CI artifacts.

- [ ] **P0 read-only audit:** from the repo on the workstation run
  `bash scripts/workstation/diagnose-openclaw.sh`. Codes 0=clean,
  2=warnings (including preserved foreign `/usr` destination), 1=failure.
  This intentionally does not invoke `openclaw doctor`, which has been
  observed installing a plugin even with `--non-interactive`.
- [ ] **P0 recovery gate:** create/verify a private versioned OpenClaw backup
  and test isolated restore before package, service or migration changes.
- [ ] **P0 Node divergence:** run
  `bash scripts/workstation/prepare-openclaw-systemd.sh` to **print only**
  an override for the observed systemd unit using `/usr/bin/node`, while
  the CLI uses mise Node 24.18.1. It refuses unfamiliar service flags; it
  neither installs the override nor restarts the Gateway. Preserve any
  separately owned `/usr/lib/node_modules/openclaw` package.
- [ ] **P1 application:** after validated rollback, align systemd runtime
  and npm prefix, then run update dry-run and controlled update; repair
  Slack state migration, inspect SQLite sessions (29 warnings), reconcile
  WhatsApp plugin version/reconnect, review cron errors and migrate
  cleartext tokens to SecretRefs. Reverify channels, sessions and Gateway
  after restart and reboot; do not declare 2026.9.9 installed based on dry-run.
- [ ] **P2 personal workflows:** test Gmail and WhatsApp with synthetic data
  in read-only mode; require explicit approval for any sending, deletion,
  archiving or labeling, including cron-triggered actions.
- [ ] **P3 TrueNAS:** only after workstation acceptance, stage isolated,
  pinned Compose/ZFS/secret-backed deployment; prove restore with all
  personal connectors disabled; coordinate single-owner cutover and failback.
- [ ] **Quality gate:** run
  `python -m pytest -q tests/test_openclaw_workstation_contract.py`
  and `bash -n scripts/workstation/*openclaw*.sh` locally, no GitHub Actions.

Observed workstation baseline (2026-10-09): OpenClaw 2026.9.5,
CLI mise Node 24.18.1, Gateway service /usr/bin/node, target 2026.9.9
**dry-run only**. No direct access to workstation from this repository
change; acceptance requires its actual runtime evidence.

## Current execution order

1. **P0 runtime closure:** stabilize the pfSense edge-memory/DNS regression,
   then complete the TrueNAS acceptance queue above.
2. **P0 agent engineering:** improve the local-first agent loop, evaluate Dagger
   as portable execution and add Context7 for current version-specific external
   documentation.
3. **P1 dependency automation:** finish hosted Mend Renovate acceptance without
   depending on GitHub Actions runners for routine updates.
4. **P2 catalog/security:** advance Backstage/catalog v2 and accept already
   declared security/inventory tools before adding more always-on services.
5. **P3 observability/runtime:** migrate Grafana before
   Mimir / Loki / Tempo / Alloy, then reconcile Prometheus and cross-signal
   observability.
6. **P4 Kubernetes/federation:** finish the single-cluster storage/security/
   ingress baseline before Karmada/workstation/cloud GPU federation.
7. **P5 cleanup/identity:** only after the runtime foundation above is stable.

## Accepted platform baseline

Keep detailed proof in incidents/runbooks. Current accepted foundations are:

- Talos `v1.13.9` / Kubernetes `v1.36.3` is 3/3 Ready after controlled
  recovery; Docker/IPAM and VM autostart are proven;
- `materialize-reboot-bundle.sh` and the controlled reboot transaction are
  accepted; the historical CSI orphan was **successfully removed** after
  **complete quiesce**;
- TrueNAS CSI dynamic provisioning, cross-worker RWX and fresh reclaim
  postconditions are accepted;
- Sentry end-to-end ingestion and Suricata `br0` capture/EVE are established
  baseline evidence;
- canonical storage/config/runtime-secret separation and value-blind migration
  tooling are implemented;
- local-first agent gates, Betterleaks, Just/Mise, shared Compose discovery,
  JSON Schema secret validation and shared TrueNAS/Docker/probe primitives are
  repository-owned.

## P0 — runtime/storage/secrets closure

### P0.1 — TrueNAS lifecycle and DNS

- [ ] Continue reducing `no topology mapping`; declare `runtime.appId` only
  when ownership is genuinely ambiguous.
- [ ] Move service-specific readiness into declarative lifecycle metadata where
  it removes duplicated policy.
- [ ] Keep current + previous known-good reboot bundles until another normal
  reboot cycle passes.
- [ ] **pfSense edge-memory / DNS resilience regression:** repeated FreeBSD
  reclaim/OOM kills on 2026-10-08 removed Unbound at 02:10 and 11:03 and killed
  `php_pfb` at 19:00. Current evidence points to combined edge-capacity pressure
  rather than native Unbound caches alone: Unbound Python DNSBL, Snort, the
  generated PHP-FPM pool and a broken CrowdSec event path can overlap on the
  memory-constrained Netgate 1100.
  - [x] Set pfBlockerNG `ASN Reporting=disabled` while `asn.mmdb`/`asn.csv`
    are absent and no IPinfo token is configured; verify the repeated IPinfo
    download attempts stop.
  - [x] Stop the CrowdSec engine after `firewallservices/pf-scan-multi_ports`
    accumulated millions of failed event-send attempts; keep the firewall
    bouncer independent while the engine is isolated.
  - [x] Diagnose CrowdSec event backpressure without restarting the engine.
    Workstation evidence on 2026-10-10 shows 19,213 stuck lines,
    `max_failed_sent=19,899,999`, `max_attempts=19,900,000` and
    `max_sigclosed=0`: a live `pf-scan-multi_ports` leaky bucket is spinning
    internally while the independent firewall bouncer remains healthy. Treat
    this as a major CPU/memory-pressure contributor, not sole-cause proof for
    every OOM.
  - [ ] Complete the pfSense Small cutover: run CrowdSec 1.8.1 centrally on
    TrueNAS, remove only `firewallservices/pf-scan-multi_ports` through
    `DISABLE_SCENARIOS`, render the bouncer secret, then require
    `diagnose-crowdsec-cutover.sh --check` before the pfSense change and
    `--accept` afterwards. Keep the local pfSense Security Engine stopped;
    do not restart it merely to collect metrics.
  - [ ] Correlate the Snort 02:09 rule-update job with the 02:10 OOM before
    changing its schedule; keep optional restart/reload churn bounded meanwhile.
  - [ ] Measure the generated PHP-FPM `pm.max_children=8` pool under normal
    traffic before any supported persistent tuning; do not hand-edit generated
    runtime config. Keep detailed tuning in
    [`pfsense-php-fpm-hardening.md`](./pfsense-php-fpm-hardening.md).
  - [x] Reduce untrusted WebConfigurator/API ingress: WAN TCP/10443 now uses
    `PFSENSE_ADMIN_WAN` (one reviewed public source) followed immediately by
    an explicit `any -> WAN address:10443` block. The block matched untrusted
    traffic immediately and sampled public `root`/`admin` PHP-FPM
    authentication failures stopped afterwards.
  - [x] Remove the malformed legacy `ExternalOffice` alias after resolving its
    rule references. It contained one office address plus all 256 LAN /24
    addresses expanded individually; the replacement admin alias resolves only
    to `80.15.4.233`.
  - [x] Repair the rejected pfSense exporter credential: create dedicated
    `pfsense_exporter`, rotate the stale key, prove HTTP 200 for
    `status/system`, `status/gateways` and `status/services`, then restore
    the exporter and obtain real pfSense metrics. Keep the identity lifecycle
    repository-managed and separate from FastAPI/admin identities.
  - [x] Observe multiple normal 300-second Prometheus cycles after rotation:
    the last `172.17.0.24` authentication failure was observed at
    `2026-10-09 20:41:24`, with no recurrence across the following 20:xx/21:xx
    checks. Exporter credential regression is closed.
  - [ ] Revalidate TrueNAS/HAProxy TCP/7000 source policy separately after the
    legacy alias removal; do not use the FastAPI Cloud public hostname as a
    source identity because ingress DNS does not prove stable cloud egress.
  - [ ] Keep Unbound out of Service Watchdog during OOM remediation; reassess
    guarded recovery only after the memory policy is stable, rather than hiding
    a kill/restart loop.
  - [ ] Exit gate: sustained observation with no new allocation/reclaim kills,
    stable Unbound/Kea DNS/DHCP, no ASN retry spam, and bounded
    Unbound/Snort/PHP-FPM/CrowdSec RSS plus free-memory headroom under normal
    WebGUI/API traffic. Incident evidence:
    [`2026-10-08-pfsense-unbound-oom-wan-exposure.md`](./incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md).
- [ ] DNS maintenance acceptance: only after the edge-memory exit gate, stop
  Pi-hole during a controlled window, rerun pfSense posture + Talos
  ResolverStatus/DNSUpstream checks and prove public registry resolution through
  pfSense/Unbound.
- [ ] Keep the TrueNAS LXC GitHub Actions runner dormant until a concrete need
  justifies operating it.

### P0.2 — CSI

- [x] Dynamic provisioning, publishContext, RWX and reclaim postconditions.
- [x] Restricted-style smoke Pod hardening and appliance-side reclaim proof.
- [ ] Replace deprecated `auth.login_with_api_key` before TrueNAS 27; a
  TrueNAS CSI version bump alone does not close this authentication debt.

### P0.3 — TrueNAS storage + runtime secret normalization

Target runtime path remains:

```text
/mnt/cpool/secrets/runtime/<service>/
```

Vaultwarden bootstrap remains independently recoverable under:

```text
/mnt/cpool/secrets/bootstrap/vaultwarden/
```

Open work:

- [ ] close the immediate DSOMM/Sentry/Scrutiny/Code queue above;
- [ ] after DSOMM runtime acceptance, pilot importing one existing Custom App
  into `truenas_app.custom_compose` with the existing OpenTofu/Terragrunt
  stack. Require an empty post-import plan plus a no-op apply before replacing
  repository deploy scripts; keep those scripts as recovery tooling until
  reboot/rollback acceptance. Evaluate provider v3.x separately from the
  currently pinned `PjSalty/truenas ~> 2.4.1` so a major provider upgrade is
  not mixed with the first App-state migration.
- [ ] accept Scanopy/Joplin/AutoKuma and Sample one service at a time;
- [ ] convert remaining explicit legacy `env_file` declarations to canonical
  runtime paths, keeping compatibility paths until restart/reboot acceptance;
- [ ] classify repository-local ignored `.env*`: secrets → Vaultwarden,
  non-secret config → tracked config, obsolete → remove only after consumer proof;
- [ ] review Apps-preset drift without recreating non-empty datasets;
- [ ] continue Vaultwarden waves only for `active` services by default:
  foundation/state → platform/network/observability → AI/RAG;
- [ ] preserve migration-critical values during path cutover; rotate only after
  runtime + reboot acceptance;
- [ ] reconcile live Doco-CD against canonical Compose and retire the inactive
  1Password bootstrap dependency only after its remaining consumers are mapped.

## P0.4 — AI agent and local-first engineering

Accepted local loop:

```text
just context
  -> just preflight
  -> targeted contract
  -> just loop
  -> commit logical batch
  -> just pre-push
  -> one push
  -> inspect existing remote checks
```

Evidence levels remain L0 static, L1 targeted, L2 changed-file convergence and
L3 full local publication. Only L3 means the complete local gate is green.

- [x] Prevent offline source checks from passing on a failed Git comparison;
  parse Python sources in one interpreter, retain an opt-in scope limit and
  keep error excerpts bounded without truncating forensic logs.
- [x] Define exact-HEAD GitHub-connector/source-snapshot recovery in the
  `local-first-quality` skill; use already-existing artifacts only and never
  treat source-only verification as a full Git publication proof.
- [x] Keep bounded agent context operational when a cached Git base exists
  but has unrelated history; never fetch merely to print changed-path context.
- [ ] Demonstrate L3 on the PR's exact checkout with cached dependencies;
  report first actionable failure only, and preserve security/formatter checks.

### Dagger — portable local/CI execution

Dagger remains a **beta parity PoC**, not a second source of quality policy.
The canonical publication evidence remains `agent-pre-push`.

- [x] Add a bounded `dagger.toml` workspace with
  `defaults_from_dotenv=false`, generated checks disabled for the PoC and
  sensitive/heavy source trees excluded.
- [x] Start with native concerns already owned by the repository:
  **ShellCheck + Biome**; module sources are commit-pinned.
- [x] Pin Dagger `0.21.10` in Mise/mise.lock and centralize the
  workspace/check surface in one non-secret Mise value,
  `DAGGER_WORKSPACE_RELEASE=v1.0.0-beta.15`; task commands reference only
  that value.
- [x] Make Biome reproducible before benchmarking:
  `@biomejs/biome=2.4.12` is exact in package.json/package-lock; the Dagger
  module is pinned to official commit
  `03db7bbf81087918657205c1eace20dfff7e29b3`, uses a digest-pinned Node
  image, forces npm and installs with `--ignore-scripts`.
- [x] Replace the legacy `detailyang/pre-commit-shell` wrapper with the
  official `koalaman/shellcheck-precommit@v0.11.0`; the native reference no
  longer depends on an unpinned system ShellCheck binary.
- [x] Align the relevant ShellCheck exclusion set with the native Pre-commit
  contract, including `biscuitcutter.sh`.
- [x] Make native Biome parity non-mutating: use the exact local
  `node_modules/.bin/biome check` after `npm ci --ignore-scripts`, not the Pre-commit
  `biome-check` hook because that hook runs with `--write`.
- [x] Keep the PoC credential-free:
  `defaults_from_dotenv=false`; Mise-loaded operator `.env*` values are not
  Dagger module settings/defaults. Any future credential must use an explicit
  Dagger `Secret` input and receive a separate security review.
- [x] Fail closed: `dagger-list`, `dagger-poc` and `dagger-bench` refuse
  execution until a reviewed `dagger.lock` exists.
- [x] Add mature OSS benchmark tooling instead of custom timing code:
  Hyperfine `2.0.0` is pinned through Mise; `just dagger-bench` compares
  the two stable recipes `just dagger-native-parity` and `just dagger-poc`
  using one warmup + three runs.
- [ ] Run `just dagger-sync` on a supported container runtime, review/commit
  the generated `dagger.lock`, and verify that the official ShellCheck
  module's internal `koalaman/shellcheck-alpine` lookup is resolved
  immutably. If not, stop promotion rather than adding a local wrapper.
- [ ] Run `just dagger-list`, then `just dagger-native-parity` and
  `just dagger-poc` on the same exact HEAD. Compare findings, scope and
  failure readability; parity must be understood before performance matters.
- [ ] Run `just dagger-bench` for warm-cache comparison. Record cold-start
  behavior only from a naturally cold/fresh environment; never clear shared
  Docker/Dagger caches just to generate a benchmark.
- [ ] Decide whether measured cache reuse and failure readability remove enough
  CI glue to justify promotion. If not, keep Dagger experimental or remove it.
- [ ] **Pytest deferred:** do not invent root project metadata solely for
  Dagger. Add Pytest only after a clean root Python project marker and native
  Python project metadata are intentionally normalized, or a durable module
  measurably reduces orchestration code.
- [x] Native Ruff configuration is standalone; keep Ruff outside Dagger unless
  an official module or broader reusable module removes measurable code.
- [ ] Keep GitHub Actions unchanged during the PoC. Only after reproducibility,
  parity and performance acceptance may a later PR make Actions a thin
  `dagger check` trigger.
- [ ] Promote Dagger out of the experimental skill section only after those
  runtime criteria pass.

References: <https://docs.dagger.io/reference/config-files/dagger-toml/>,
<https://docs.dagger.io/cli/checking/>,
<https://docs.dagger.io/reference/modules/shellcheck/> and
<https://docs.dagger.io/reference/modules/js/biome/>.

### Context7 — current documentation for coding agents

Context7 is documentation-only: it improves version/API accuracy for external
libraries but never replaces repository/runtime evidence.

- [x] Register the hosted Context7 MCP endpoint without credentials/headers in
  `.mcp.json`, `.cursor/mcp.json` and OpenCode V2
  `opencode.json -> mcp.servers.context7`. OpenCode keeps
  `codemode=true` so the server stays grouped rather than expanding every MCP
  tool directly into the native tool list.
- [x] Add `context7-docs` as an on-demand skill with an anonymous CLI fallback
  (`ctx7 library` → versioned library ID → `ctx7 docs`) and telemetry disabled
  in the documented CLI path.
- [x] Route external/version-specific library questions through Context7 from
  `AGENTS.md` and `local-first-quality`, while keeping repository files,
  lockfiles and runtime diagnostics authoritative.
- [x] Add a Pre-commit contract that rejects a required
  `CONTEXT7_API_KEY` in the project MCP configuration and verifies the
  free-first/on-demand boundaries.
- [ ] Runtime-smoke the anonymous endpoint from the primary OpenCode client
  (`opencode mcp list` + one version-specific lookup). If the anonymous quota
  is insufficient, prefer OpenCode OAuth/free login before any paid tier.
- [ ] Keep `CONTEXT7_API_KEY` optional and outside Git; reserve it for
  non-interactive automation or higher free-plan limits only.
- [x] Route every `dagger.toml` change through both `local-first-quality`
  and `context7-docs`, so future Dagger edits automatically request current
  external API documentation. Runtime Context7 lookup remains acceptance-gated
  by the OpenCode smoke above.
- [x] Keep an official-doc/web fallback for environments where Context7 is not
  connected, lacks the required library/version or is rate-limited. The current
  API-only agent used that fallback to validate the Dagger/OpenCode contracts
  without pretending the Context7 runtime smoke had passed.

Reference: <https://context7.com/docs/overview> and
<https://context7.com/docs/clients/cli>.

### Code/debt reduction policy

- [ ] Continue replacing repeated policy with canonical metadata/schema or mature
  OSS libraries only when maintenance surface measurably shrinks.
- [ ] Continue centralizing bounded TrueNAS middleware/readiness helpers in
  `scripts/lib/` and generic Python behavior in `scripts/nabla_ops/`.
- [x] Compose discovery is shared through `nabla_ops.compose_paths`.
- [x] Dotenv parsing delegates to `python-dotenv`; secret manifest structure
  uses Draft 2020-12 JSON Schema + `jsonschema`/`check-jsonschema`.
- [ ] Evaluate Typer only for genuinely complex/repetitive operator CLIs; keep
  `argparse` for small appliance-safe scripts where a dependency adds no value.
- [ ] Move code-server startup-time packages/extensions into a derived immutable,
  versioned, digest-pinned image before removing current runtime provisioning.
- [x] Anti-duplication gates protect migrated runtime primitives.
- [x] `planned`/`disabled` services stay catalog-visible without generating
  false Gatus/AutoKuma runtime expectations.

## P1 — dependency automation and infrastructure secrets

### Renovate / Mend

- [ ] Install hosted Mend Renovate for `nabla-compose` and `fastapi-sample`.
- [ ] Grant read access to Dependabot alerts and prove one real vulnerability
  remediation path.
- [ ] Disable Dependabot Security Updates only after Renovate is proven as the
  single security-fix PR producer; keep Dependabot Alerts enabled.
- [ ] Remove the self-hosted Renovate Actions workflow after hosted acceptance.
- [ ] Keep routine concurrency bounded and no automerge without authoritative
  green required checks.

### Infrastructure secrets

- [ ] OpenTofu/Terragrunt + Garage backend credentials.
- [ ] Dedicated TrueNAS infrastructure automation identity; never reuse the
  FastAPI observer.
- [ ] Nexus automation credentials.
- [ ] Talos/Kubernetes/CSI machine credentials.
- [ ] Keep root-owned `0600` runtime materializations and encrypted recovery.
- [ ] Move long-lived machine secrets to Vault/OpenBao only after persistence,
  rollback and recovery are proven.

## P2 — service catalog and security platform

Catalog-v2 detail remains in
[`service-catalog-v2-normalization.md`](./service-catalog-v2-normalization.md).

- [ ] preparation/parity: deterministic identities, schemas and no duplicate
  ownership;
- [ ] pilot representative services and provider-outage behavior;
- [ ] bulk service descriptor/BIA/PRA migration, coupled with touched secret
  migrations;
- [ ] prepare FastAPI/site/operational consumers;
- [ ] coordinated v1 → Backstage cutover;
- [ ] remove legacy compatibility only after runtime/reboot/consumer acceptance.

Security-tooling acceptance:

- [ ] accept Plumber, NetBox, OCS Inventory, Dependency-Track, DefectDojo and
  Neo4j before treating declarations as deployed;
- [ ] add Dependency-Check as reproducible SCA evidence feeding DefectDojo;
- [ ] evaluate ArcherySec/Faraday only as bounded complements, not competing
  systems of record;
- [ ] keep Cartography/OpenSSF Scorecard as explicit/manual jobs where intended;
- [ ] OpenCRE: create/verify storage, pin immutable image, prove health,
  useful correlation and reboot persistence;
- [ ] DSOMM: after runtime deployment, publish/merge repository-assessment
  producers for `nabla-compose`, `fastapi-sample`, `nabla-site-alban` and
  `nabla-site-bababou`, then require complete-source aggregation before using
  it as portfolio review evidence;
- [ ] complete manual DSOMM Security Champions/IAM/Agentic AI/Identity/process
  review and close/accept GitHub branch-protection gaps;
- [ ] keep source-first security audit validation local and close the Scanopy
  daemon-bootstrap lead with passive runtime evidence.

## P3 — runtime and observability

### Grafana native → Compose migration

Do this before enabling/reconciling Mimir / Loki / Tempo / Alloy.

- [ ] run `sudo bash scripts/truenas/diagnose-grafana-migration.sh --check`;
- [ ] inventory `grafana.db` read-only and snapshot the actual backing ZFS
  dataset;
- [ ] preserve `/mnt/cpool/grafana/data` and plugin state;
- [ ] remove only the native App wrapper, never its preserved data;
- [ ] start repository Grafana on `:30037`, verify `/api/health` and compare
  representative dashboard/datasource identities;
- [ ] keep rollback snapshot/material until acceptance;
- [ ] only then reconcile Mimir / Loki / Tempo / Alloy.

### Remaining observability/runtime

- [ ] Prometheus DOWN-target reconciliation: canonical database telemetry is
  **PostgreSQL, Redis, ClickHouse, InfluxDB and OpenSearch**; **Sybase is
  excluded**.
- [ ] finish FastAPI Sentry transaction/span persistence acceptance.
- [ ] correlate FastAPI Sentry + Prometheus/Grafana + Loki/Tempo + Pyroscope with
  stable service/environment/release/route/trace/span identities.
- [ ] prove Suricata `eve.json` downstream consumption.
- [ ] restore pfSense NetFlow → Cloudflare Network Analytics.
- [ ] restore repository-owned Uptime Kuma, then enable/reconcile AutoKuma.
- [ ] finish Scrutiny SMART + workstation collector acceptance.
- [ ] deploy/accept Joplin and its dedicated shared-PostgreSQL role/database.
- [ ] make Homarr first-run initialization idempotent/secret-backed.
- [ ] keep native PostgreSQL and AdGuard Home until explicit migration
  backup/rollback/consumer plans exist.
- [ ] defer NPM/OpenArchiver/Paperless migration until inventory/rollback
  contracts are ready.
- [ ] Akvorado ingestion/query acceptance and later ntopng reconciliation.
- [ ] Pi-hole post-reboot DNS/UI/API/sync/exporter acceptance.
- [ ] Docling API/health + one bounded conversion, then OpenRAG ↔ workstation
  LiteLLM/GPU ingest/retrieve acceptance.
- [ ] Cyberbro free-engine baseline, then provider onboarding in bounded
  least-privilege batches; resolve Vaultwarden token-refresh/icon TLS debt.

### Local-first follow-up after merged PR #250 (2026-10-10)

- [x] Trigger topology and Homarr/Gatus/AutoKuma generator checks for
  nested `apps/*/compose.yml` edits, not only files directly under `apps/`.
- [x] Fail closed when local quality-gate Git path collection errors;
  never interpret a broken `git diff` as zero changed files.
- [ ] Regenerate and validate any stale Pipelines catalog, topology,
  Gatus, Homarr or AutoKuma projections from the merged source change
  using the canonical generators; preserve deterministic diffs.
- [ ] Run exact-HEAD L3 after obtaining a full verified checkout/cache.
  Offline L1 and source-level assertions remain limited evidence; do not
  rerun GitHub Actions merely to discover the next error.

## P3.1 — AI stack upgrades and service consolidation (planning only)

Execution plan: [AI stack upgrade and consolidation](./ai-stack-upgrade-consolidation-plan.md).
**No runtime upgrade, redeploy, migration, deletion or secret rotation is
authorized by this entry.** Declared Compose versions are not runtime proof.

- [x] Inventory the declared OpenRAG, Open WebUI, Langflow, Docling,
  LiteLLM, Langfuse, OpenSearch and storage dependencies; record available
  upstream releases and identify candidate integration/duplication areas.
- [x] Define bounded upgrade waves, stop conditions, compatibility
  evidence, rollback/restore gates and conditional service additions.
- [ ] Capture TrueNAS exact image digests, Docker networks, bucket/index
  owners, and recent backups in a **read-only** runtime audit.
- [x] Remove unused Open WebUI Pipelines service from Compose and its
  Backstage component (operator confirmed). Runtime retirement and generated
  catalog/Gatus/Homarr/AutoKuma reconciliation still require acceptance.
- [x] Prepare the existing `hello.int.albandrieu.com` Traefik router:
  explicitly pin Docker network `traefik_network` and backend port `80`,
  and add regression contract (source-only; **not runtime cutover**).
- [ ] Run the read-only hello ingress preflight and accept actual TrueNAS
  routing, pfSense HAProxy, DNS/TLS, headers and expected response before
  retiring the NPM test; see [hello cutover](./hello-traefik-migration.md).
- [ ] Canary `hello.int.albandrieu.com` with CrowdSec LAPI bouncer,
  real-client-IP trust and optional staged AppSec WAF;
  avoid migrating pfSense HAProxy or Cloudflare routes implicitly.
- [ ] Confirm NPMplus has **no active proxy hosts or callers**, then
  disable the TrueNAS app and only subsequently delete app + data if
  unused. NPM is a test too: migrate any other configured routes
  explicitly and remove NPM only after consumer-free evidence.
- [ ] Confirm AIStor has no buckets, consumers or data, stop the app,
  observe Langfuse/MinIO health, then delete AIStor after backup review.
- [ ] Add Trivy Operator as a scoped Talos/Kubernetes **planned service**,
  then export its reports using DefectDojo's `Trivy Operator Scan`
  parser and its reimport-scan API, avoiding duplicate findings.
- [ ] Compare Databasus (PostgreSQL PITR, MongoDB/MySQL backups) against
  Restic (general files/ZFS exports): choose complementary roles or one
  minimal stack, then pilot offsite encrypted backup and restore.
- [ ] Reconcile NPM/NPMplus trial ingress ownership after the canary;
  do not delete their data before reviewing host/cert/port consumers.
- [ ] Evaluate reuse of Docling by Open WebUI and Langfuse/Alloy tracing,
  then retire Pipelines only after equivalent Function/MCP coverage.
- [ ] Qualify Open WebUI 0.11.4 independently before upgrading the
  coordinated OpenRAG 0.8.0 / Langflow / OpenSearch bundle.
- [ ] Preserve isolated security data, S3 buckets, RAG indices, DNS
  authority and ingress ownership until an explicit migration is accepted.
- [ ] Add a new service only after documenting a missing capability and
  verifying reuse of the existing stack is insufficient.

## P4 — Kubernetes and multi-cluster

- [ ] Vault/OpenBao after single-cluster storage/recovery acceptance.
- [ ] Falco after infrastructure baseline stabilizes.
- [ ] Kubara + Traefik ingress with explicit bare-metal exposure.
- [ ] FastAPI Kubernetes immutable-image smoke through
  `test.int.albandrieu.com`.

Karmada remains outside the bootstrap critical path:

- [ ] define cluster identity/labels, GPU/power/cost/workload classes;
- [ ] build an always-on small Karmada management cluster/VM on TrueNAS;
- [ ] register `nabla-talos` first and prove one bounded stateless propagation;
- [ ] build/register intermittent `workstation-gpu`, with offline state treated
  as expected capacity loss rather than home-platform failure;
- [ ] select cloud GPU capacity only after SKU/network/storage/startup/
  scale-to-zero/cost comparison;
- [ ] keep mandatory state/quorum off intermittent nodes and do not assume
  transparent cross-cluster networking or TrueNAS NFS reachability;
- [ ] final smoke: home stateless workload, workstation GPU workload when online,
  workstation shutdown without mandatory-service degradation, then cloud GPU.

## P5 — identity, policy and bounded cleanup

- [ ] Keycloak/GitHub SSO after network/storage stability.
- [ ] Vault/OpenBao human authentication after infrastructure secrets.
- [ ] Continue NIST CSF 2.0 mapping and Restricted Pod Security migration with
  explicit infrastructure exceptions.
- [ ] archive accepted reboot evidence and retain current + previous known-good
  bundles.
- [ ] remove only owner-reviewed zero-endpoint Docker networks; never blanket
  `docker network prune` / `docker system prune`.
- [ ] keep weekly bounded dangling-image cleanup separate from Git sync; accept
  the documented TrueNAS cron and record the next cold-start convergence.
- [ ] review old unmanaged/exited containers/build cache only after the bounded
  cleanup policy is established.

## Ordering rule

```text
MERGED PR #240, runtime still pending
  -> DSOMM / Sentry / Scrutiny / Code checks + one-service acceptance
  -> Scanopy / Joplin / AutoKuma / Sample runtime-env closure
  -> local-first agent improvements (Dagger PoC + Context7 PoC)
  -> hosted Renovate acceptance
  -> service intent / catalog-v2 preparation and security-tool runtime acceptance
  -> Vaultwarden waves for active services only
  -> Grafana native -> Compose
  -> Prometheus canonical target reconciliation
  -> Mimir / Loki / Tempo / Alloy
  -> FastAPI cross-signal observability
  -> Suricata downstream + pfSense NetFlow
  -> Uptime Kuma / AutoKuma
  -> Docling / OpenRAG-LiteLLM
  -> Kubernetes ingress + smoke
  -> Karmada/workstation/cloud GPU federation
  -> infrastructure secrets / Vault / Falco
  -> bounded cleanup + remaining deferred services
```

When restarting a ChatGPT/agent discussion, begin from **Restart context** and
the first unchecked item in **Immediate TrueNAS acceptance queue**. Do not
reconstruct completed history from chat memory when the repository runbook or
current runtime evidence can answer it.
