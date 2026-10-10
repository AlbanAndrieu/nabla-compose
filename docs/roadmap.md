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

## CURRENT AUTHORITATIVE EXECUTION ORDER — operator-approved (2026-10-10)

**Use this section rather than superseded chronological entries below.**
Compact new-chat handoff with complete decisions, dependencies and proofs:
[`roadmap-execution-handoff-2026-10-10.md`](./roadmap-execution-handoff-2026-10-10.md).
Historic PR #251 notes and the older `Current execution order` remain
as evidence/context only; if they disagree, **this section wins**.

**Decisions approved:** (1) stability/Gatus/pfSense before new features;
(2) secret migration **one service at a time**, bundled with its Backstage
descriptor; (3) prepare catalog v2 gradually but perform a **coordinated
three-repository cutover**, no permanent dual schema; (4) Cyberbro before
Docling when choosing between equal-priority feature work, while read-only
Docling diagnostics may run earlier; (5) finalize already operational
DSOMM/Sentry/Scrutiny/Pi-hole statuses and acceptance evidence instead
of redeploying them.

### Execution checkpoint — 2026-10-10, operator evidence on PR #253

- [x] **Git recovered (observed):** main index `albandrieu:apps 0600`,
  `git ls-files` succeeded; root-owned index scan clear after scoped repair.
  The unprivileged ownership diagnostic is working.
- [ ] **Git recurrence prevention:** eliminate remaining root-context Git
  operations in other TrueNAS scripts. A successful repair is not proof that
  all root Git writers have disappeared. Cron ID 6 runs as albandrieu;
  root cron ID 8 remains to be audited by command/child process, without
  printing secret-bearing arguments.
- [x] **Gatus runtime accepted:** TrueNAS `app.update` plus explicit
  `app.redeploy` recreated the container with `GroupAdd=["568"]`;
  `RUNNING`, exit 0, restarts 0, HTTP /health OK, zero recent
  config/permission/database/fatal errors. Existing SQLite inode
  `139:2` preserved; file size 2260992 bytes at acceptance.
- [ ] **Gatus long-term acceptance:** verify stored monitoring history
  via application/API and recovery after a later planned reboot.
  Do not modify or recreate `/mnt/cpool/gatus/gatus.db`.
- [x] **DSOMM/Sentry/Scrutiny runtime checks:** DSOMM HTTP 200,
  22 assessment activities/evidence records; Sentry 14 diagnostics OK;
  Scrutiny web/InfluxDB/collector healthy, four SMART devices accessible.
  Remaining: DSOMM reboot, Sentry fresh end-to-end event,
  Scrutiny `/dev/sde` EPERM classification, Pi-hole reboot.
- [x] **Cyberbro transport baseline:** HTTP 5100 ready; MCP endpoint
  responds HTTP 400 (transport reachable, *not* MCP authentication/tool
  acceptance).
- [ ] **CrowdSec pfSense cutover:** engine and LAPI healthy, Loki
  hits=9124, no active decisions (not a failure); canonical bouncer
  secret absent/empty, `PFSENSE_FIREWALL last_pull=<none>`.
  Render existing key directly from approved Vaultwarden source and
  validate on TrueNAS before workstation-only pfSense cutover;
  do not generate/rotate credentials implicitly.
- [x] **Catalog generators:** operator confirmed declared catalog and
  topology synchronized after Git-index recovery. The separately invoked
  consumer `--check` did not print an acceptance result; recheck in a
  consolidated gate before marking its validation complete.
- [ ] **Quality gate:** full exact-HEAD L3 remains unproven. No bypass
  and no automatic merge.

### P0 — Git index ownership: evidence of root Git access, not proven cron (2026-10-10)

- [x] **Scoped Git-index repair implemented and operator-proven:** the main
  `.git/index` was observed as `root:apps 0600`; targeted ownership repair
  restored access without recursive checkout mutation. The helper
  `scripts/truenas/diagnose-git-index-ownership.sh --repair` now repairs every
  root-owned `index` file under the canonical `.git` tree only, preserves each
  existing mode, reuses the `.git` group, and is protected by a contract test.
- [ ] **Git index recurrence remains open:** journal timestamps correlate one
  recurrence with the Gatus apply window, but that is not yet proof of cause.
  Current `deploy-gatus.sh` already runs Git provenance/diff through `runuser`
  as `albandrieu` when invoked as root. Continue correlating exact index mtime
  with cron/timers/sudo/appliance operations; never use `sudo git`.
- [ ] **Vaultwarden residual resolver drift:** pfSense/Unbound now returns
  Cloudflare IPv4, `/etc/hosts` has no matching override and NSS order is
  `hosts: files dns`. TrueNAS remains internally inconsistent: `getent hosts`
  returns Cloudflare IPv6 and Python `socket.getaddrinfo(AF_INET)` returns
  Cloudflare IPv4, while `getent ahostsv4` and curl still use `172.17.0.24`.
  `nscd` is running and is now the primary suspected stale-cache layer.
  `configure-bitwarden-cli-local.sh --flush-host-cache` invalidates only the
  `hosts` cache through `nscd -i hosts`, then reruns the HTTPS/DNS checks.
  Do not change pfSense again unless post-flush evidence points back to it.

- [x] Source investigation: `docs/truenas-deployment-automation.md`
  records TrueNAS cron **ID 6**, hourly at minute 0, user
  `albandrieu`, running `scripts/cron.sh`.
  The script checks the current branch and only fetches/
  fast-forwards the configured `master` checkout; on PR
  branches it is a no-op. This documented cron is **not**
  evidence of root-origin Git metadata writes.
- [x] Earlier incident
  `docs/incidents/2026-10-10-post-reboot-git-dsomm-gatus-vaultwarden.md`
  explicitly records `sudo git status` followed by a new
  `.git/index` owned by `root:apps 0600` at 12:16.
  Git `status` can refresh and rewrite the index.
  Therefore **root Git invocation is an evidenced cause**
  of the recurring symptom, but attribution of every later
  occurrence to a specific cron/service is still unproven.
- [ ] Verify **actual** TrueNAS cron schedule, root/user
  crontabs, systemd timers and `sudo` journal entries
  around the affected index timestamps. Avoid dumping
  secret-bearing command lines or changing cron jobs
  without evidence. Do not run `sudo git`, repository
  generators or quality gates as root. TrueNAS middleware
  or dataset-specific commands may still need sudo.
- [x] Operator explicitly elected to **discard** staged
  modifications to `scripts/quality/check-compose-config.sh`
  and `scripts/workstation/openclaw-auth-presence.py`.
  Recommended exact restore is `git restore --source=HEAD
  --staged --worktree -- <both paths>`; no stash,
  no repository reset/clean, no submodule overwrite.
- [x] Gatus `repair-gatus-config-access.sh --check`
  rejected the running container because it lacks
  `HostConfig.GroupAdd` GID 568. This is **runtime
  TrueNAS Custom App Compose drift**. Correct/redeploy
  the Custom App definition before the isolated config
  permission `--apply`; do not widen YAML readability
  or mutate SQLite as a substitute.

### P0 A2 — Gatus root cause confirmed, follow-up branch (2026-10-10)

- [x] **Definitive failure evidence:** Gatus container `restarting`,
  exit 2, 564 restarts, no HTTP :8085. Log panic is
  `open config/config.yml: permission denied`. This is a
  generated **configuration read** failure, not a proven SQLite
  problem. File `apps/gatus/config/config.yml` is
  `albandrieu:apps 0640`; Gatus dataset/database are
  `root:root 0770` and remain untouched.
- [x] Added `scripts/truenas/repair-gatus-config-access.sh`
  with `--check` (metadata/read-only) and opt-in
  `--apply` that adjusts only generated `config` directory
  group/mode (apps/0750) and `config.yml` (apps/0640).
  It rejects unsafe paths, incorrect host GID and absent
  Docker `HostConfig.GroupAdd`; no broad chmod, new
  privileges, container restart, SQLite change or data reset.
  Added an offline contract test for these safety constraints.
- [ ] **Appliance-only acceptance:** inspect
  `stat apps/gatus/config`, `docker inspect gatus`
  for `HostConfig.GroupAdd` and actual bind-mount destinations;
  run `--check` and *only if scoped preconditions are met*
  `--apply`. Docker restart policy may retry naturally.
  Validate HTTP 8085, a steady healthy process, SQLite
  history and an eventual reboot. If no supplemental apps
  group is effective, repair the TrueNAS Custom App definition,
  not the dataset permissions.
- [ ] **Parallel work:** preserve P0 pfSense/CrowdSec stability;
  continue value-blind `config/secrets/manifest.json`
  coverage and Backstage v2 service parity. Do not
  materialize new credentials, mutate private state or
  switch the multi-repository catalog without rollback proof.
- [ ] **Validation:** targeted agent tests where tools exist;
  required full L3 remains a before-merge gate rather than a
  demand for repeated user-side ShellCheck/pytest invocations.
  Historical #251 was merged; the recovery is on a follow-up PR.

### P0 A1/A2 evidence — 2026-10-10, PR #251

- [x] Added `scripts/truenas/diagnose-gatus.sh`: bounded **read-only** container status, UID/GID and mount destination metadata, SQLite/config path metadata, and **aggregate log error categories only**. No raw log text, environment, secret value, chmod/chown, restart or database mutation.
- [x] Added `tests/test_gatus_diagnostic_contract.py`; isolated agent fixture: **2 passed** (Bash parse and fake Docker log with canary secret). These are **targeted** tests, not full-HEAD L3 proof.
- [ ] **Runtime root cause remains unknown:** the previous Gatus `exit 2`, missing HTTP 8085 and root-owned 770 dataset are observations, not proof of an ACL defect. Classify the bounded evidence before any UID/permission correction. Check the container's effective user and actual log failure without publishing raw logs.
- [ ] Full local `just pre-push`, pre-commit, Compose config, BetterLeaks, SAST and generated topology on exact PR HEAD: **UNAVAILABLE/NOT RUN in this isolated agent environment** (GitHub archive DNS blocked, no complete repository checkout). Mandatory pre-merge gate unchanged. No automatic merge or runtime change.
- [ ] After verified root cause, implement the smallest Gatus config/identity fix, preserve `/mnt/cpool/gatus/gatus.db`, then separately accept HTTP :8085, persistence/history and reboot recovery.

### Validation policy — agent local first, operator only for runtime acceptance

- [ ] **Agent responsibility:** run and correct `shellcheck`,
  `bash -n`, targeted/full `pytest`, YAML validation, Ruff,
  pre-commit, Compose config, generators, BetterLeaks, SAST and
  Playwright/ZAP **in the agent's own environment wherever feasible**.
  Retrieve exact HEAD source if clone/DNS is blocked, use hermetic
  fixtures for relevant isolated tests, and state precisely what
  ran and what did not. Never claim the full gate is green based on
  partial checks.
- [ ] **Avoid operator-test ping-pong:** do **not** repeatedly require
  `just pre-push`, ShellCheck, pytest or all quality gates on
  workstation/TrueNAS between each small roadmap change. Batch
  operator-only appliance evidence or final acceptance in a single
  bounded checkpoint. An unrelated, known failing gate may remain
  explicit debt while safe independent work continues; agent fixes
  introduced regressions and prioritizes the root blocking issue.
- [ ] **Never bypass safety/quality controls:** do not disable,
  silently skip or weaken pytest, ShellCheck, Ruff, pre-commit,
  BetterLeaks, SAST, Playwright, ZAP, deployment/security contracts
  or mandatory PR checks to accelerate progress. Required full
  quality-gate acceptance remains a **before-merge** requirement,
  distinct from the targeted **before-next-step** gate.
- [ ] **No auto-merge.** No silent TrueNAS app mutations, data
  migrations, public endpoints, secret rotation or Bababou ingestion.
  Preserve rollback, version pinning and authoritative runtime evidence.

### Critical path — close started work first

| Gate | Priority | Work | Exit condition |
| --- | --- | --- | --- |
| A1 | P0 | Stabilize pre-commit YAML/executable hooks and autonomous local-first validation | Targeted agent checks executed; final L3 state tracked |
| A2 | P0 | Diagnose and repair Gatus STOPPED/restart exit 2 without SQLite loss | Correct root cause; HTTP 8085, persistence and history accepted |
| A3 | P0 | Confirm pfSense/CrowdSec DNS/memory stability; close runtime-vs-reboot acceptance on DSOMM, Sentry, Scrutiny, Pi-hole | Critical risk isolated; status declarations reconcile with proof |
| B1 | P1 | Complete `/mnt/cpool/secrets/runtime/<app>/` migration and Vaultwarden recovery per active service | Manifest/path, identity, consumer, restart/rollback proof |
| B2 | P1 | Backstage descriptors, catalog v2 parity/ownership/exposure, prepare FastAPI/Site consumers | Semantic parity and no duplicated authority |
| B3 | P1 | Coordinated `nabla-compose` → `fastapi-sample` → `nabla-site-alban` cutover | Cross-repo contract, runtime/health and reboot proof before legacy deletion |
| C1 | P2 | Cyberbro HTTP, IoC and MCP/LiteLLM least-privilege acceptance | Bounded functional and auth smoke |
| C2 | P2 | Shared Docling for OpenRAG + Open WebUI; version-verified OpenRAG search API/MCP | PDF/table/OCR extraction, known route and ACL |
| C3 | P2 | Private Bababou dataset POC via reviewed read-only subset | Measured retrieval/citation quality and no data leakage |

**Explicitly defer** Karmada/multi-cluster federation, broad image
upgrades, Trivy Operator, new observability daemons, Garage/MinIO/AIStor
consolidation and destructive legacy cleanup until the path above is
sufficiently accepted. Keep outage-driven urgent security fixes eligible
for reprioritization.

**Current proof:** DSOMM 12 tests/22 subtests + HTTP 200 + Docker
capability; Sentry diagnostic 14 OK; Scrutiny healthy web/InfluxDB and
four SMART devices; Pi-hole DNS sync healthy. Gatus was STOPPED with
restart exit 2 and HTTP 8085 unavailable. The canonical source for
the private Bababou dataset has not been located or mounted for indexing.
**Full local pre-push green has not been demonstrated in the provided
evidence.**

## PR #251 — Shared Docling, OpenRAG API/MCP, Open WebUI and Bababou POC (2026-10-10)

Implementation and security gates: [`docs/runbooks/rag-bababou-poc-architecture.md`](./runbooks/rag-bababou-poc-architecture.md).
This is a **planned** architecture, not evidence of runtime deployment or ingestion.

- [x] **Architecture decision** : keep Open WebUI for chat and per-user
  Knowledge; use OpenRAG + shared Langflow + OpenSearch as the
  independently callable RAG service. LiteLLM is the LLM/embedding
  gateway, **not** the RAG retrieval service.
- [x] **Existing declared integration** : `apps/docling/compose.yml`
  already defines a reusable Docling Serve at `docling:5001` /
  `172.17.0.24:5001`, and OpenRAG already sets
  `DOCLING_SERVE_URL=http://docling:5001`. Open WebUI currently has
  no Docling extraction config and no explicit `intranet` network;
  **shared Docling is not yet fully integrated or runtime-proven**.
- [ ] **P0 — common Docling acceptance** : verify actual TrueNAS
  App/image/health, OpenRAG extraction; connect Open WebUI to
  the same Docling endpoint using version-supported settings
  (`CONTENT_EXTRACTION_ENGINE=docling`, `DOCLING_SERVER_URL`),
  network, trust boundary and PDF/table/OCR smoke. One Docling
  runtime; independent document stores and ACL.
- [ ] **P1 — OpenRAG connector** : on the running pinned OpenRAG
  `0.7.1`, inspect supported API and whether MCP `/mcp` exists;
  do **not** assume documentation from `main` applies to 0.7.1.
  Prefer least-privilege MCP for Open WebUI when supported,
  otherwise REST/OpenAPI adapter. Restrict tools to read/search
  and scope by authorized corpus.
- [ ] **P1 — fastapi-sample integration** : consume the same
  restricted OpenRAG search API with separate service identity;
  keep inference/embeddings behind TrueNAS LiteLLM with explicit
  GPU workstation `172.17.0.57:4000/v1` proxy routing.
  Do not expose OpenSearch/Docling/Langflow or a raw MCP endpoint
  publicly. An external `fastapi-sample.fastapicloud.dev` caller
  requires a reviewed Cloudflare Access/service-token boundary,
  permission tests, rate limits and redacted telemetry.
- [ ] **P2 — Bababou RAG POC** : locate and confirm the actual
  `/mnt/cpool` dataset containing the previous Google Drive
  Bababou extraction (exact path not yet verified); inventory
  metadata first, use a **read-only** and authorized subset of
  10–20 documents in separate `bababou-poc` index. Keep PII,
  legal correspondence and private evidence away from Git,
  public endpoints, default traces and externally hosted models.
- [ ] **P2 — evaluation** : with identical documents, embeddings
  and LLMs, compare Open WebUI Knowledge vs OpenRAG on
  recall@5, MRR@10, citation page accuracy, faithfulness,
  latency p95, indexing duration and CPU/RAM/GPU. Include
  access-control, prompt-injection and deletion/erasure tests.
  Store only redacted metrics and synthetic evaluation examples
  in Git; do not commit corpus, chunks or derived private index.
- [ ] **P3** : promote one RAG integration based on benchmark
  evidence, wire Open WebUI plus fastapi-sample, monitor via
  existing Langfuse/Prometheus with private prompts/chunks
  excluded, then rehearse recovery and rollback.
  
## PR #251 — Gatus crash, Sentry/Scrutiny accepted and secret/catalog cutover (2026-10-10)

- [x] **Sentry** : TrueNAS `diagnose-sentry.sh --check`
  returned **exit 0 / 14 OK / 0 failures / 0 warnings** on
  2026-10-10. This validates its diagnostic contract now,
  but an end-to-end persisted event and reboot recovery remain
  separate acceptance gates.
- [x] **Scrutiny** : TrueNAS app RUNNING (web + collector);
  web healthy with zero restarts and HTTP `/api/health` 200,
  InfluxDB v2.9.1 reachable, collector sees
  `/dev/sda` through `/dev/sdd`. Canonical runtime secret exists
  at `/mnt/cpool/secrets/runtime/scrutiny/.env.secrets` (mode
  600, v2 token scope); **/dev/sde permission denied** is
  a bounded hardware/permission debt. Avoid widening privileges
  until the device's expected SMART support is known.
- [ ] **Gatus P1 incident** : TrueNAS app STOPPED; Docker
  `gatus` restarting with exit **2**, host port 8085 refused.
  Dataset `/mnt/cpool/gatus` and `gatus.db` are
  `root:root 770`; possible denial to a non-root container
  (not yet demonstrated). First inspect bounded restart logs,
  effective UID/GID and config mount permissions. Preserve
  SQLite DB; do not `chmod 777`, delete it or blindly restart.
- [x] **Pre-commit YAML regression** : operator L3 stopped before
  tests at `.pre-commit-config.yaml` line 470, invalid YAML.
  Converted the long inline Compose hook to a named Bash script
  `scripts/quality/check-compose-config.sh`; added a YAML/syntax
  regression test. Isolated local Bash smoke passes both success
  and failing Compose cases. Full L3 on TrueNAS remains pending.
- [ ] **Secret migration** : `config/secrets/manifest.json`
  contains a DSOMM manual baseline `GH_TOKEN` mapping
  and Scrutiny InfluxDB v2 token mappings; **no Gatus or
  Sentry manifest entries currently identified**.
  Sentry Compose already uses canonical
  `/mnt/cpool/secrets/runtime/sentry/{.env.secrets,
  .env.migrator.secrets}` paths but this alone does not prove
  Vaultwarden source materialization. Audit non-secret key names,
  manifest coverage, and bootstrap recovery; do not import values
  or rotate keys automatically.
- [ ] **Canonical catalog** : `catalog/services.json` is generated
  from declarative Compose. DSOMM is still declared
  `status: planned` despite successful runtime check; Gatus
  has no explicit status despite STOPPED. Reconcile intent,
  rollout phase and observed state independently. Update
  `x-nabla` only following approved runtime acceptance, then
  regenerate topology and downstream service consumers; never
  hand-edit `catalog/services.json`.
- [ ] **Execution order** : L3 YAML validation -> Gatus
  read-only crash triage -> Gatus permission/config fix (if
  proven) -> secrets manifest gap analysis -> Backstage/Compose
  canonical entity status reconciliation -> fresh runtime
  acceptance for Sentry/Scrutiny -> reboot test when planned.

## PR #251 — DSOMM runtime accepted, index Git ownership, next Gatus/Sentry/Scrutiny (2026-10-10)

- [x] **DSOMM runtime acceptance (operator)** : `pytest -q
  tests/test_dsomm_contract.py` **12 passed, 22 subtests** ;
  `deploy-dsomm.sh --check` confirms seed DSOMM 5.0.2
  (22 activities, 22 evidences), image 4.4.1, Compose, catalog,
  dataset, effective `NET_BIND_SERVICE` and HTTP readiness ;
  independent `curl` reports **HTTP 200** on
  `http://172.17.0.24:31088/`. **Runtime accepted**;
  reboot/persistence acceptance is **not** yet established.
  No app restart or `--apply` needed.
- [x] **Git permission root cause** : TrueNAS operator is
  `uid=1000(albandrieu)`; `.git` is `albandrieu:apps 755`,
  but `.git/index` is `root:apps 644`. Correct only that index's
  ownership back to `albandrieu:apps` (preserve mode 644);
  do not run Git as root or recursively chown the checkout.
- [ ] **P0 L3** : verify shebang of the exact executable indexed
  `scripts/workstation/openclaw-ops.sh`, update the local branch
  safely and run `just pre-push` on clean committed HEAD. No bypass.
- [ ] **P1 Gatus** : read-only TrueNAS App state/containers,
  HTTP `172.17.0.24:8085`, dataset `/mnt/cpool/gatus`,
  database presence, configuration group permissions. Determine
  migration status before deploying.
- [ ] **P1 Sentry** : execute
  `sudo bash scripts/truenas/diagnose-sentry.sh --check`,
  inspect edge/Relay/Kafka/Snuba with no secret values;
  do not redeploy while inspecting.
- [ ] **P1 Scrutiny** : execute
  `sudo bash scripts/truenas/diagnose-scrutiny.sh --check`,
  inspect collector, InfluxDB and canonical secret metadata;
  avoid `--capture-startup` and state changes.
- [ ] **DSOMM evidence in Git** : the reviewed seeds are already
  versioned. If runtime assessments must be committed, prepare
  a reviewed/redacted export; never copy raw
  `/mnt/cpool/dsomm/state` into a public repository automatically.

## PR #251 — DSOMM CAP_ normalized, Git index permissions and evidence versioning (2026-10-10)

- [x] **DSOMM effective runtime** : operator `docker inspect` reported
  `state=running`, `project=ix-dsomm`,
  `service=dsomm`, `CapAdd=["CAP_NET_BIND_SERVICE"]`,
  `CapDrop=["ALL"]`, new container created 2026-10-10.
  The deployer incorrectly accepted only `NET_BIND_SERVICE`;
  its runtime check now accepts Docker's normalized
  `CAP_NET_BIND_SERVICE` as well. HTTP readiness and uptime
  remain to be confirmed via `--check` (no new `--apply`).
- [x] **Git state source separation** : version-controlled DSOMM
  `config/team-progress.seed.yaml`,
  `config/team-evidence.seed.yaml`,
  `config/seed-activities.yaml` and
  `config/model-activity-index.json` are reviewed templates,
  whereas `/mnt/cpool/dsomm/state/{model,team-progress,team-evidence}.yaml`
  are outside the repository and may include live assessment
  evidence. Import only a reviewed and scrubbed snapshot if
  versioning it is required; preserve separate writable runtime data.
- [ ] **Git permission incident** : `git ls-files` and
  `git status` report `.git/index: Permission denied` on
  TrueNAS; diagnose index ownership and parent directory access,
  correct *only* incorrect ownership/permissions and avoid
  `sudo git`, blanket recursive chmod or disabling pre-commit.
  Reconfirm the executable shebang from the synced HEAD.
- [ ] **Service acceptance** : DSOMM `--check`, port 31088,
  Gatus runtime, Sentry E2E and Scrutiny read-only checks in order.

## PR #251 — pre-push shebang et DSOMM après app.update (2026-10-10)

- [x] **Hook shebang** : `openclaw-ops.sh` possède désormais
  `#!/usr/bin/env bash` au HEAD distant, mais l'opérateur a constaté
  `check-executables-have-shebangs` en échec au HEAD
  `f5b67697ea4d`. Le journal compact ne donne pas le chemin exact ;
  ne pas affirmer que l'échec porte sur ce script sans la liste des
  fichiers incriminés. Contrôler le journal privé `/tmp/tmp.1UY6kFZI9X`
  et les modes Git indexés, puis relancer L3 après `git pull`.
- [x] **DSOMM --apply exécuté sur TrueNAS** : seed, image,
  Compose, catalogue, stockage, modèle existant préservé et direct
  smoke Docker ont réussi ; `app.update` et `app.start` ont répondu
  succès. **L'acceptation a échoué** : conteneur réel sans
  `NET_BIND_SERVICE`, malgré un Compose rendu valide. L'App n'est
  donc pas considérée réparée.
- [x] **Diagnostic durci** : le déployeur relève maintenant, en cas
  de divergence de capacité, l'identité et la date de création Docker,
  le projet/service Compose, l'exit code, les redémarrages et les
  capacités appliquées, sans afficher l'environnement des secrets.
  Ce diagnostic différencie une Custom App non réconciliée et un
  conteneur ancien/orphelin ; il ne change pas l'état du système.
- [ ] **DSOMM action prioritaire** : confirmer la provenance du
  conteneur et la définition persistée TrueNAS, en ne révélant pas
  les valeurs `Config.Env`, `custom_compose_config` ou secrets.
  Comparer `Created`, `com.docker.compose.project`,
  `com.docker.compose.service`, `HostConfig.CapAdd` et
  `app.query`. Ne pas répéter `--apply` aveuglément.
- [x] **Pourquoi préserver un état DSOMM** : Git versionne les
  fichiers seed/config du dépôt, pas les trois fichiers runtime
  `/mnt/cpool/dsomm/state/` (modèle externe pinné et preuves
  utilisateur pouvant évoluer). Sauvegarder cet état avant les
  mutations TrueNAS évite la perte de travaux d'évaluation.
- [ ] **Gatus/Sentry/Scrutiny** : poursuivre les diagnostics en
  lecture seule dans le runbook, sans démarrer de services depuis
  la boucle de correction du pre-push.

## PR #251 — OpenClaw ShellCheck et préparation DSOMM/Gatus/Sentry/Scrutiny (2026-10-10)

- [x] **P0** : l'opérateur a confirmé `15 passed / 22 subtests`
  sur OpenClaw backup + DSOMM. Le `just pre-push` a ensuite convergé
  sur les droits exécutables de `openclaw-ops.sh`, mais ShellCheck
  SC2250 bloquait les références `$mode`, `$id`, `$ROOT`,
  `$value`. Les variables régulières ont été mises en forme
  `${...}` dans le script. Le strict ShellCheck reste actif.
- [ ] **P0** : sur le HEAD commité, exécuter
  `shellcheck -x -P SCRIPTDIR scripts/workstation/openclaw-ops.sh`,
  les tests ciblés OpenClaw/DSOMM puis `just pre-push`. Sans
  exécution locale du vrai ShellCheck dans le conteneur agent,
  ne pas déclarer L3 vert avant preuve opérateur.
- [x] **DSOMM correctif prêt** : le déployeur fait le direct smoke
  avec `--cap-drop ALL --cap-add NET_BIND_SERVICE`, refuse un
  Compose rendu dépourvu de la capacité et contrôle le `HostConfig`
  effectif. Désormais, un `--apply` réutilise le `model.yaml`
  existant si sa version et ses UUID sont valides ; il ne le remplace
  plus systématiquement. Les fichiers team-progress/evidence existants
  restent inchangés. Contrat ajouté, validation runtime à effectuer.
- [ ] **DSOMM intervention** : sauvegarder et vérifier empreintes
  de `model.yaml`, `team-progress.yaml` et `team-evidence.yaml`,
  inspecter l'App existante, puis exécuter explicitement
  `sudo bash scripts/truenas/deploy-dsomm.sh --apply` lorsque
  la gate et les préconditions sont vertes. L'outil peut appeler
  `app.update` puis `app.start` : il s'agit d'une mutation.
  Vérifier ensuite `NET_BIND_SERVICE`, `RUNNING`, HTTP 31088
  et SHA256 des trois fichiers ; ne pas utiliser `docker restart`.
- [x] **Pi-hole DNS Sync** : accepté `healthy`, sessions 16 ;
  pas de réparation à faire au vu des preuves actuelles.
- [ ] **Gatus**, puis **Sentry**, puis **Scrutiny** :
  diagnostics runtime et acceptation en lecture seule via
  [le runbook](./runbooks/2026-10-10-platform-services-acceptance.md) ;
  redémarrer seulement les App pour lesquelles un incident est
  établi et un rollback existe.

## PR #251 — DNS Pi-hole accepté, DSOMM pas encore redémarrable (2026-10-10)

- [x] **Pi-hole DNS Sync** : `sudo bash scripts/truenas/verify-pihole-dns-sync.sh`
  a répondu `OK: Pi-hole DNS sync healthy`. Résolution du
  `docker-socket-proxy` fonctionnelle (adresse IPv6 Docker
  `fdd0:0:0:30::2`), synchronisation initiale achevée, sessions
  API = **16**. `restart_count=1` reste un warning historique à
  surveiller, non un défaut actuel. Pas de redémarrage requis.
- [x] **Quality P0** : `tests/test_homelab_external_services_contract.py`
  **4 passed** ; `just pre-push` a appliqué les droits exécutable
  de `scripts/workstation/openclaw-cron-runs-summary.py`, convergé
  en deux passes, puis buté sur
  `test_openclaw_backup_contract.py::test_rejects_backup_when_gateway_active`
  (**1 failed / 333 passed / 1 skipped / 154 subtests**).
  Le test a été rendu hermétique vis-à-vis des variables d'environnement
  exportées, `BASH_ENV` et des hooks utilisateur, en conservant
  le refus strict de sauvegarde lorsque Gateway est actif.
  **L'assertion exacte de cet échec reste non fournie** ; confirmer le
  test ciblé sur TrueNAS avant de conclure à la cause.
- [x] **DSOMM garde-fou applicatif** : le Compose versionné inclut
  `cap_add: NET_BIND_SERVICE`, mais le conteneur actuel en est dépourvu ;
  les logs montrent `exec /usr/bin/caddy: operation not permitted`.
  Le déployeur vérifie maintenant la présence de cette capacité dans
  le Compose rendu *avant* réconciliation et dans
  `docker inspect` *après* attente d'un App RUNNING ; refuse de
  déclarer le runtime sain sans capacité. Test de régression ajouté.
- [ ] **DSOMM intervention distincte** : ne pas se limiter à
  `docker restart dsomm` ou `app.start` (l'ancien HostConfig resterait
  inchangé). Avant `deploy-dsomm.sh --apply`, vérifier la définition
  Custom App TrueNAS, documenter un rollback, sauvegarder le modèle et
  les deux fichiers d'évidence sans les divulguer, et contrôler l'effet
  de `--apply` sur `model.yaml` (script actuellement susceptible de
  le réinstaller). Réconciliation explicite seulement après ces vérifications.
- [ ] **P0 L3** : tests OpenClaw et DSOMM ciblés puis `just pre-push`
  à l'issue du pull sur HEAD propre. La validation locale de chaque
  sous-contrat ne vaut pas acceptation L3 complète.
- [ ] **P1 suivant** : Gatus, Sentry, Scrutiny après stabilisation
  et qualification DSOMM.

## PR #251 — parallèle qualité / DSOMM / Pi-hole (2026-10-10)

- [x] **P0 catalogue** : `test_active_operator_truenas_services_are_projected`
  s'arrêtait après **204 tests réussis**. Cause : `Plumber` et
  `Vaultwarden` existaient dans `homelab-services.json` mais sans
  `id` canonique alors que `catalog/services.json` les déclare
  `truenas-app`, `presentationRole: service`. Les IDs ont été
  ajoutés et un test protège unicité et noms. Aucun endpoint n'a
  été changé.
- [ ] **Plumber inventaire** : la ligne historique pointe vers
  `172.17.0.57:3001` tandis que la nouvelle déclaration Compose
  annonce `172.17.0.24:31070`. Ne pas modifier la cible
  opérationnelle par hypothèse ; confirmer la migration/runtime et
  ajuster le catalogue seulement après preuve.
- [ ] **P0 validation** : `pytest -q
  tests/test_homelab_external_services_contract.py`, puis
  `just pre-push` sur le HEAD propre. Ne considérer la gate L3
  réussie que lorsque toutes les étapes passent.
- [ ] **P1 DSOMM parallèle (diagnostic en lecture seule)** :
  le Compose versionné contient `NET_BIND_SERVICE`, mais le
  conteneur existant a `CapAdd=null`, `CapDrop=["ALL"]`,
  `no-new-privileges:true`, exit 255 et `exec /usr/bin/caddy:
  operation not permitted`. Relever seulement `HostConfig.CapAdd`
  / `HostConfig.CapDrop`, état Docker et configuration déclarée
  TrueNAS **sans les secrets**. Proposer ensuite une réconciliation
  limitée de la Custom App (pas `privileged:true`), avec sauvegarde
  métadonnées, contrôle des fichiers d'état, smoke et rollback ;
  **aucun apply automatique**.
- [ ] **P1 Pi-hole DNS parallèle (diagnostic en lecture seule)** :
  `verify-pihole-dns-sync.sh` vérifie le DNS du proxy Docker,
  la stabilité du synchroniseur, `Initial sync done`,
  `api_seats_exceeded`, la limite d'API 16 et son ENV.
  Vérifier l'état réel via ce script et le réseau `intranet` ;
  ne pas augmenter arbitrairement la limite de sessions, ne pas
  donner le socket Docker brut au synchroniseur, ne pas redémarrer
  Docker. Si le réseau ou la résolution est défaillant, rétablir
  uniquement la connectivité proxy ↔ intranet avant une reprise
  contrôlée du service.
- [ ] **P1 ensuite** : Gatus, Sentry et Scrutiny un service à la fois,
  en continuant les validations P0 indépendamment.

## PR #251 — Pi-hole DNS sync et contrôles délégués (2026-10-10)

- [x] Échec L3 identifié : `test_pihole_dns_sync_acceptance_contract`,
  après **191 tests réussis, 1 ignoré et 91 sous-tests réussis**.
  Le test demandait la chaîne `getent hosts` dans
  `verify-pihole-dns-sync.sh`, alors que le script appelle
  `probe_container_dns_success` et `probe_container_dns_records`.
  L'implémentation `docker exec ... getent hosts` appartient au
  helper partagé `scripts/lib/probe.sh`.
- [x] Test modifié pour vérifier la source du helper, ses deux appels
  avec les paramètres bornés et l'instruction `getent hosts` dans le
  helper réel. Aucun contournement du DNS, des erreurs Pi-hole
  `api_seats_exceeded` ou du contrôle `webserver.api.max_sessions`.
- [x] Reproduction locale isolée de l'ancienne assertion : **1 échec** ;
  même fixture après correction : **1 succès**. Le test du checkout
  complet exact-HEAD n'a pas été exécuté localement.
- [ ] P0 : relancer le test de contrat puis `just pre-push` sur TrueNAS,
  traiter le prochain échec sans ignorer de hook. P1 service :
  DSOMM `STOPPED` et Caddy `execve EPERM` sur une configuration
  runtime dépourvue de `NET_BIND_SERVICE` ; diagnostiquer sa
  définition TrueNAS avant toute réconciliation.

## PR #251 — Smoke FastAPI/Pyroscope et dérive runtime DSOMM (2026-10-10)

- [x] **P0 test de contrat FastAPI** : `just pre-push` a dépassé les
  contrats Docling (**2 passed** après pull), puis a bloqué au premier
  échec de la suite globale :
  `test_fastapi_observability_smoke_covers_error_trace_and_profile`
  (**1 failed, 187 passed, 1 skipped, 91 subtests**).
  L'assertion `"Pyroscope readiness"` était un libellé de log obsolète.
  Le script réel vérifie `probe_http_success` sur la racine, l'exposition
  `/metrics` puis `/querier.v1.QuerierService/Series` et refuse les
  profils absents. Le test a été aligné sur ces **contrôles fonctionnels**
  sans contourner l'exigence de profils.
- [ ] **Validation P0** : relancer le test ciblé FastAPI, puis
  `just pre-push` depuis un checkout propre. Le prochain échec éventuel
  doit être corrigé avant les modifications de services.
- [x] **DSOMM état/runtime** : `docker inspect` reproduit
  `CapAdd=null`, `CapDrop=["ALL"]`, `no-new-privileges:true`,
  avec **1121 redémarrages** ; le dépôt exige
  `cap_add: NET_BIND_SERVICE`. Logs précédents :
  `exec /usr/bin/caddy: operation not permitted`.
  La configuration effective du conteneur est donc différente de la
  configuration canonique. L'état des fichiers d'évidence doit rester
  préservé.
- [ ] **DSOMM action suivante** : inspecter la configuration persistée
  TrueNAS sans divulguer de secrets, puis planifier une réconciliation
  bornée de la Custom App seulement après P0 vert. Mesurer
  `CapAdd` et santé HTTP `172.17.0.24:31088` après correction.
  Ne pas utiliser `privileged:true` ni assouplir les ACL de l'état.
- [ ] **Ordre P1** : DSOMM → Gatus → Sentry → Scrutiny ; P2 Scanopy,
  Joplin, AutoKuma ; P3 Docling/OpenRAG/LiteLLM.

## PR #251 — Docling contract et DSOMM Caddy EPERM (2026-10-10)

- [x] **P0 Docling** : le service déclare un port Compose sous forme
  structurée `{name: web, target: 5001, published: "5001",
  host_ip: "172.17.0.24", protocol: tcp, app_protocol: http}`. Le
  test attendait l'ancienne chaîne `172.17.0.24:5001:5001`, d'où
  `1 failed, 154 passed, 1 skipped, 64 subtests`. Contrat actualisé
  sans toucher au service ni à son exposition réseau.
- [ ] **L3** : rejouer `python3 -m pytest -q
  tests/test_docling_joplin_contract.py --tb=short`, puis
  `just pre-push` sur le HEAD actuel. L'agent a exécuté une
  reproduction isolée de l'assertion de ports : 1 passed ; cela
  ne remplace pas le test du dépôt complet.
- [x] **DSOMM — cause runtime corroborée** : conteneur actuel
  `dsomm` `restarting`, `ExitCode=255`, `OOMKilled=false`,
  `RestartCount=1109`, `CapDrop=["ALL"]`, `CapAdd=null`,
  `SecurityOpt=["no-new-privileges:true"]`. Logs :
  `exec /usr/bin/caddy: operation not permitted`. Le Compose
  canonique *déclare* `cap_add: NET_BIND_SERVICE` ; le conteneur
  inspecté ne l'a pas. C'est une divergence de posture **déclarée
  versus appliquée**, pas un problème démontré de permissions sur
  les datasets (`700` et `600 root:root`).
- [ ] **DSOMM — prochaine étape explicite** : confronter
  `docker compose -f apps/dsomm/compose.yml config --format json`
  et les métadonnées sans secrets de `docker inspect dsomm`, puis
  revoir la définition Custom App persistée dans TrueNAS. Contrôler
  la conservation du jeu de données avant de réconcilier le runtime
  via une opération `--apply` **distincte, planifiée et surveillée**.
  Ne pas ouvrir `privileged`, retirer `no-new-privileges` ou
  réinitialiser les états pour masquer le problème.
- [ ] **Suite P1** : Gatus puis Sentry puis Scrutiny, un par un
  après résolution du P0 et revue explicite DSOMM.

## PR #251 — quality gate L3 et DSOMM restart 255 (2026-10-10)

- [x] `tests/test_truenas_deploy_output_contract.py` : **8 passed** sur
  TrueNAS. Le gate a également confirmé les contrats pfSense/CrowdSec,
  les primitives runtime et les projections Homarr/Gatus/AutoKuma.
- [x] Échec L3 suivant : `test_agent_error_excerpt_limits_remain_configurable`
  dans `tests/test_agent_offline_check.py`, **1 failed, 6 passed,
  1 skipped** (journal privé : `/tmp/tmp.CFWSNgh4sq`). Cause établie :
  attentes obsolètes `QUALITY_LOG_TAIL:-32` et
  `QUALITY_SUMMARY_LINES:-12`, valeurs réelles `12` et `10`.
  Le test suit maintenant les valeurs publiées sans désactiver le
  contrôle de bornage ni supprimer les diagnostics privés.
- [ ] **P0 L3** : confirmer le contrat ciblé puis `just pre-push`
  sur le dernier HEAD. Ne déclarer L3 vert qu'après un passage complet.
- [x] **DSOMM runtime** : `app.query` indique `STOPPED`,
  `active_workloads.containers=0`, tandis que `docker ps -a`
  montre un conteneur `dsomm Restarting (255)`. État de fichiers :
  dossier `/mnt/cpool/dsomm/state` `700 root:root`, `model.yaml`,
  `team-progress.yaml` et `team-evidence.yaml` en
  `600 root:root`. Cela établit l'existence des données, pas la santé
  de l'application ni l'origine de l'exit code 255.
- [ ] **DSOMM analyse ciblée et lecture seule** : obtenir
  `docker inspect` avec `State.Error`, `ExitCode`, `OOMKilled`,
  `RestartCount`, `Config.User`, `SecurityOpt`, `CapAdd`,
  `CapDrop`, `HostConfig.Privileged` et les dernières lignes de logs,
  sans valeurs d'environnement ni secrets. Vérifier les mounts en
  mode metadata uniquement. Une défaillance Caddy/file-capability
  `execve EPERM` a déjà été observée dans l'incident précédent :
  **hypothèse prioritaire à revérifier**, sans conclure qu'elle cause
  cette occurrence. Ne pas lancer `docker restart`, `app.start`,
  `--apply` ni changer les ACL avant le diagnostic.
- [ ] **P1 services** : ne reprendre Gatus puis Sentry et Scrutiny
  qu'après traitement P0 et une décision explicite sur DSOMM.

## PR #251 — preuve opérateur DSOMM et provenance Git (2026-10-10)

- [x] Vérifications TrueNAS : `pytest -q tests/test_opencre_contract.py`
  **5 tests réussis**. `just pre-push` a convergé en une passe et validé
  la régénération des projections, puis s'est arrêté au contrat
  `test_checkout_provenance_is_local_and_non_blocking` :
  **1 échec, 33 tests réussis** dans le groupe pfSense/CrowdSec.
  Journal privé : `/tmp/tmp.srBqJeenIk`.
- [x] Renforcer le test de provenance du checkout : inspecter uniquement
  `truenas_repo_provenance()`, refuser les opérations Git réseau/mutantes
  (`fetch/pull/push/checkout/switch/reset`), expliciter les contrats
  manquants. La fonction de production n'a pas été modifiée.
  **L'assertion exacte de l'échec d'origine n'a pas été fournie** ;
  ne pas attribuer rétroactivement une cause non démontrée.
- [x] `sudo bash scripts/truenas/deploy-dsomm.sh --check` a établi :
  seed DSOMM 5.0.2 cohérente (22 activités et 22 preuves),
  image `wurstbrot/dsomm:4.4.1` présente,
  Compose et projections synchronisés, dataset `cpool/dsomm`
  présent et non vide ; provenance `HEAD=f1773f969679`,
  `tree=clean`, upstream synchronisé.
- [ ] **DSOMM App STOPPED** : le `--check` a correctement refusé de
  démarrer l'application. Ce n'est ni une erreur de seed ni une preuve
  de disponibilité HTTP. Diagnostiquer `app.query`, workloads, jobs
  et persistance avant une opération explicite `--apply`.
  Ne pas supprimer, écraser ou réinitialiser `/mnt/cpool/dsomm`.
- [ ] **P0** : exécuter le test de provenance ciblé puis
  `just pre-push` sur la branche à jour. Ne pas entamer d'autres
  changements fonctionnels tant que L3 est rouge.
- [ ] **P1** : une fois L3 validé, ordre d'acceptation :
  DSOMM STOPPED → Gatus → Sentry → Scrutiny
  (voir [runbook](./runbooks/2026-10-10-platform-services-acceptance.md)).

## PR #251 — OpenCRE gate + acceptation séquentielle des services (2026-10-10)

- [x] Corriger le test `opencre-contract` : le déployeur exécutable a
  légitimement le shebang `#!/usr/bin/env bash` ; confirmer
  `bash -n` plutôt qu'imposer `not text.startswith("#!")`.
  Le contrôle du mode exécutable et la politique de refus des images
  mutables restent actifs.
- [x] Publier le runbook de vérification **lecture seule** :
  [DSOMM → Gatus → Sentry → Scrutiny](./runbooks/2026-10-10-platform-services-acceptance.md).
- [ ] P0 : sur TrueNAS, vérifier `pytest -q tests/test_opencre_contract.py`
  puis `just pre-push` sur le HEAD commité ; les 9 tests DSOMM, les
  5 tests des audits Cloudflare et `just loop` ont été rapportés verts
  par l'opérateur, mais **pas** le contrôle L3 complet.
- [ ] P1, **une App à la fois** : DSOMM `--check` → preuve de
  persistance/HTTP ; Gatus → historique SQLite et endpoints ; Sentry →
  diagnostic edge/Relay/Kafka/Snuba ; Scrutiny → diagnostic Web,
  collector, InfluxDB et provenance des secrets. Ne pas exécuter de
  `--apply`, `--capture-startup` ou redéploiement sans preuve.
- [ ] P2 : Scanopy/Joplin/AutoKuma puis Docling/OpenRAG/LiteLLM après
  les acceptations de priorité P1.

## PR #251 — Node.js absent du PATH TrueNAS (2026-10-10)

- [x] Diagnostiquer le faux échec de validation Cloudflare : le test
  `test_all_committed_audit_json_passes_vendored_cloudflare_validators`
  échoue avant de lire les audits lorsque `shutil.which("node") is None`.
  **Ce constat ne démontre aucune corruption du JSON d'audit.**
- [x] Étendre `scripts/truenas/bootstrap-dev-tools.sh` : installer
  `node@24.18.1` via `mise --no-config` sous le HOME opérateur et publier
  l'exécutable dans `~/.cache/nabla-compose/dev-venv/bin/node`. Le gate
  réutilise ce venv en tête de `PATH`. Aucun `apt` ni privilège Docker.
- [x] Contrat de régression : `tests/test_agent_quality_gate_contract.py`
  atteste la version pin et le lien vers le binaire utilisateur.
- [ ] **Operator local-first L1/L3** : exécuter
  `bash scripts/truenas/bootstrap-dev-tools.sh` uniquement si Node n'est
  pas déjà accessible ; vérifier `command -v node` et `node --version`
  dans le venv et relancer `pytest -q tests/test_security_audit_skill_contract.py`.
  Poursuivre `just loop` puis `just pre-push` seulement après
  convergence sur un HEAD commité, sans `SKIP` ou `--no-verify`.
- [ ] La roadmap services (DSOMM, Gatus, Sentry, Scrutiny, Scanopy et
  Docling/OpenRAG) reprend seulement quand le P0 L3 passe.

## PR #251 — DSOMM gate recovery and service acceptance (2026-10-10)

- [x] Repair stale **DSOMM test contracts** without weakening deployment security:
  `DSOMM_BASELINE_SUMMARY_OUTPUT` is a configurable Compose expression whose
  default is `/reports/dsomm-baseline.md`; the DSOMM model path is constructed
  from `state_root` and `model_file`, not embedded as one literal string.
  Pinned model/image, manual baseline profile, secret-backed configuration and
  fail-closed custom-app deployment remain unchanged.
- [ ] **P0 quality gate** — run exact `python3 -m pytest -q
  tests/test_dsomm_contract.py --tb=short`; then `just loop` and
  `just pre-push` on a clean, committed HEAD, resolving each reported hook
  before proceeding. The agent's isolated source-contract reproduction is
  partial L1 evidence only, **not** the full suite or L3.
- [ ] **P1 DSOMM service** — first run the read-only
  `sudo bash scripts/truenas/deploy-dsomm.sh --check`. Before any
  `--apply`, inspect storage prerequisites, immutable assessment seeds,
  supported TrueNAS Custom App configuration and image availability. Runtime
  `RUNNING`, HTTP 31088 and persisted evidence are required before claiming
  acceptance or changing `x-nabla.status: planned`.
- [ ] **P1 platform recovery** — triage Gatus and canonical Sentry/Scrutiny
  secrets read-only; do not infer successful migration from passing contracts.
  Confirm live service/secret provenance one service at a time, with rollback.
- [ ] **P2 subsequent services** — resume the planned Scanopy/Joplin/AutoKuma
  first-wave runtime-env migration, then bounded Docling health/conversion and
  OpenRAG/LiteLLM GPU integration. Do not deploy or restart these as a side
  effect of fixing the CI.

## Local-first quality gate compact diagnostics — 2026-10-10

- [x] Keep complete security/lint/test coverage, but print only failed
  pre-commit hook identifiers and pytest failure summaries by default.
  Preserve complete private `mktemp` logs (mode 0600) on failure; successful
  logs are removed. The fallback tail is used only if no structured failure
  lines are found. `QUALITY_LOG_TAIL` and `QUALITY_SUMMARY_LINES` remain
  operator overrides.
- [x] Fix stale agent contract tests: native ShellCheck no longer uses
  docker.sock; aggregate hooks across both `repo: local` sections; align
  the gate's changed-file message and canonical pre-push policy assertions.
- [x] Restore syntactically valid CrowdSec scripts: remove duplicated tail
  and repair the truncated secret check; restore Loki `curl` line
  continuations. Validate with `bash -n` and the existing
  `test_agent_quality_gate_contract.py` syntax preflight.
- [ ] Operator: pull the branch after safely committing any indexed local
  work, run `python -m pytest -q tests/test_agent_quality_gate_contract.py`,
  and rerun pre-commit plus the strict local gate. Do not bypass pre-push
  and do not stage the unrelated `fastapi-sample` gitlink.

## TrueNAS local ShellCheck pre-commit incident — 2026-10-10

- [x] Root cause: official `shellcheck-precommit` hook invokes Docker;
  non-privileged TrueNAS operator cannot access
  `unix:///var/run/docker.sock`, so the commit fails *before* shell
  linting. **Do not add operator to `docker` group, run hooks with
  `sudo`, disable ShellCheck, or bypass pre-push**.
- [x] Replace Docker-based hook with `repo: local`, `language: system`,
  `entry: shellcheck`, preserving `-x -P SCRIPTDIR` and exclusions.
  Existing `bootstrap-dev-tools.sh` installs pinned ShellCheck 0.11.0
  under the operator's home via `mise`/venv. Contract test added.
- [ ] Operator: `command -v shellcheck && shellcheck --version`;
  install in home using the documented TrueNAS tool bootstrap only
  if absent. Re-run `pre-commit run shellcheck --files` for the
  four executable scripts before retrying the permission commit.
- [ ] Re-run bounded local gate, resolve actual ShellCheck diagnostics,
  reconcile remote HEAD with `git fetch`, then push without
  `--no-verify`, `sudo git` or `--force`.

## Consumer hook and stash hygiene — 2026-10-10

- [x] Repair `scripts/quality/check-service-consumers.sh`: prior
  `git ... || cd ... && pwd` executed `pwd` even when Git succeeded,
  yielding two newline-separated roots and breaking `cd` at pre-commit.
  An explicit `if/else` now selects exactly one path; isolated
  checkout/archive test added.
- [ ] Operator: after pulling this fix, rerun staged pre-commit and
  complete the generated-only commit; never stage the unrelated
  `fastapi-sample` gitlink.
- [ ] Keep a **stash-free active workflow** after acceptance. First
  inspect `git stash list`; then drop only the two recent
  generated-catalog stashes by message, preferably by stash object ID
  after verifying them. The older stashes (other branches) may contain
  unrelated unrecovered work and must not be cleared automatically.
- [ ] Confirm the five generated assets pass both generator `--check`
  commands and the consumer quality hook on the same checkout/HEAD.

## Operator follow-up: Git-generated files and DSOMM check (2026-10-10)

- [x] Operator repaired Git index ownership in the superproject and nested
  submodules; ordinary `git status` now works without `sudo`. Preserve
  unrelated `fastapi-sample` submodule HEAD drift.
- [x] Both catalog generators and `--check` commands passed on TrueNAS.
  Generated topology, services, Gatus, Homarr and AutoKuma changes are
  **uncommitted**; preserve them while updating the source branch.
- [ ] To integrate upstream changes without losing local artifacts:
  `git stash push -m "pre-pull generated catalogs" --` for **only**
  the five generated paths, followed by
  `git -c pull.rebase=false pull --ff-only origin
  fix/agent-compose-gate-offline-followup`; regenerate and re-check.
  Keep the stash for rollback, do not pop stale generated outputs on
  top of newer inputs. Inspect/commit the regenerated diff separately.
- [x] DSOMM direct Docker smoke now uses the same minimal
  `NET_BIND_SERVICE` exception as Compose; `--check` fails fast when
  the TrueNAS App is STOPPED instead of waiting the entire timeout.
- [ ] Validate DSOMM `--apply` only after reviewing the fresh generated
  catalog diff, then accept actual health and stable restart count.
- [ ] Gatus config mode fix (`0640` and group ID) is in PR but the
  observed `0600` regeneration was from older local HEAD. Confirm
  TrueNAS `apps` group GID and active file ownership, update generator
  and Compose, reconcile Gatus only after checking runtime group access.

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

## Restart context — 2026-10-10

État de reprise canonique pour un nouveau chat/agent :

- PR active : `#251`, branche `fix/agent-compose-gate-offline-followup`; ne jamais merger automatiquement.
- Local-first obligatoire : corriger le premier échec déterministe avant toute nouvelle amélioration, puis rejouer `bash scripts/agent-pre-push.sh`.
- OpenClaw : le test backup `Gateway active` est désormais compatible TrueNAS `/tmp noexec`; `openclaw-ops.sh` doit rester `100755` avec shebang Bash explicite.
- Vaultwarden : RCA confirmée. Un Host Override pfSense
  `vaultwarden.albandrieu.com -> 172.17.0.24` génère
  `/var/unbound/host_entries.conf`. Le supprimer côté pfSense et conserver, si nécessaire, un nom privé séparé `vaultwarden.int.albandrieu.com`.
- pfSense syslog : émission RFC5424 réelle prouvée
  `172.17.0.1:514 -> 172.17.0.24:1514`; Alloy/Loki valident deux runs consécutifs `exit=0 ok=10`.
- CrowdSec central TrueNAS : `crowdsecurity/crowdsec:v1.8.1`, healthy, LAPI `:8084`, metrics `:6060`, scénario `firewallservices/pf-scan-multi_ports` désactivé.
- CrowdSec Loki acquisition : événements pfSense réels visibles ; `cs_lokisource_hits_total` confirmé et croissant (174 → 180 → 287). Étapes pfSense→Alloy→Loki→CrowdSec terminées.
- Bouncer pfSense : encore sur LAPI local `http://172.17.0.1:8089`; ne pas basculer vers `172.17.0.24:8084` tant que credential/registration/last_pull ne sont pas validés.
- Syslog legacy : `172.17.0.57:1514` est une ancienne cible workstation à retirer ; la cible canonique doit rester `172.17.0.24:1514`.
- Bitwarden/secrets : explicitement différés jusqu'après stabilisation du bouncer. Ne pas bloquer la chaîne observabilité dessus.
- Quality gate actuelle : le dernier blocage observé est le contrat shebang/executable OpenClaw ; corriger sans `--no-verify`, puis relancer la gate complète.
- Git local : préserver tout commit local non poussé ; si la branche distante avance, inspecter `HEAD...@{upstream}` et merger/rebaser sans reset destructif.

Prochain ordre de travail :

1. obtenir une gate locale L3 verte sur le HEAD courant ;
2. supprimer l'Host Override public Vaultwarden et valider public Cloudflare + privé `.int` ;
3. nettoyer la cible syslog workstation `.57` ;
4. préparer/valider le credential et la registration du bouncer central ;
5. basculer le bouncer pfSense vers `172.17.0.24:8084` ;
6. exiger `last_pull` non vide et décisions visibles avant acceptation ;
7. seulement ensuite reprendre Bitwarden/secrets.

### P0 evidence update — skill review and LiteLLM (2026-10-10, PR #253)

- [x] Classify failed OpenClaw cron runs without printing virtual-key prefixes or content: `scripts/workstation/openclaw-cron-runs-summary.py`.
- [x] Add a CLI-only read-only entry point for the failing main skill review: `bash scripts/workstation/openclaw-ops.sh --skill-review`.
- [ ] Resolve actual `openclaw-main` key-budget exhaustion (10.046146 / 10.0): inspect LiteLLM usage/reset period and reduce job usage, do not override budget or treat shared-key model fallback as recovery.
- [ ] Verify main `skill-collection-review` actually succeeds after budget resets; one retained run failed after 272541 ms, five consecutive failures reported by the job status.
- [ ] Separately resolve embedding provider 401 and paused main/cron vector indexes, preserving backup and secret isolation.

See [the OpenClaw remediation runbook](./runbooks/2026-10-10-openclaw-workstation-remediation.md) for source evidence, commands, acceptance and rollback.

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
- [ ] **P0 recovery gate:** run `bash scripts/workstation/backup-openclaw.sh --check`.
  Stop/quiesce the user Gateway **manually** during maintenance; create an
  offline archive via `--create` (refuses a running service), then separately
  run `--verify ARCHIVE` and `--restore-test ARCHIVE`. Only then restart the
  Gateway manually. Backup is private (0600), its directory 0700, and is not
  uploaded to Git. The restore-test checks archive safety and readability,
  **not** full application-level restoration or session compatibility.
  Backup omits symlinks/sockets; inventory those separately if used.
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
  - [ ] Complete the pfSense Small cutover in two independent gates:
    first reconcile CrowdSec 1.8.1 centrally on TrueNAS with
    `deploy-crowdsec.sh --check` then explicit `--apply`; require
    `diagnose-crowdsec-cutover.sh --runtime` to prove image, LAPI/listeners,
    Loki acquisition and removal of `firewallservices/pf-scan-multi_ports`.
    A missing bouncer credential does not block this central-runtime repair.
    Only after the canonical credential is materialized, require
    `diagnose-crowdsec-cutover.sh --check` before the pfSense change and
    `--accept` afterwards. The central engine must reuse the existing
    Alloy/Loki pfSense stream `{job="pfsense",device="pfsense"}`; do not add a
    second syslog receiver or depend on nonexistent `/mnt/cpool/logs/pfsense`
    files. Keep the local pfSense Security Engine stopped; do not restart it
    merely to collect metrics.
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

### CrowdSec / pfSense cutover evidence — 2026-10-10 21:17 CEST

- [x] TrueNAS central runtime remains healthy: CrowdSec `v1.8.1`, LAPI
  `172.17.0.24:8084`, metrics `:6060`, problematic
  `firewallservices/pf-scan-multi_ports` absent.
- [x] Canonical pfSense Loki acquisition is live; operator observed
  `cs_lokisource_hits_total=8563`.
- [ ] Canonical runtime secret is still absent:
  `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets`.
- [ ] CrowdSec secret rendering is currently blocked by the known Vaultwarden
  public split-DNS: TrueNAS resolves `vaultwarden.albandrieu.com` to
  `172.17.0.24` through the historical pfSense/Unbound Host Override and
  therefore receives local HTTPS `404` instead of traversing Cloudflare.
  Correct the Host Override first; do not bypass by copying secrets between
  hosts.
- [ ] Central bouncer `PFSENSE_FIREWALL` exists but `last_pull=<none>`;
  therefore the remote LAPI cutover has **not** happened.
- [x] Workstation-side pfSense proof: local Security Engine absent, firewall
  bouncer running, PF tables exist with 31,513 IPv4 + 586 IPv6 entries.
- [x] Workstation preflight is now accepted: pfSense reaches central LAPI TCP
  `172.17.0.24:8084`, local Security Engine is absent, firewall bouncer is
  running, and PF tables contain 32,099 entries.
- [ ] pfSense bouncer still points to legacy local LAPI
  `http://172.17.0.1:8089`; strict `--accept` correctly fails until the
  bouncer is reconfigured to `http://172.17.0.24:8084`.
- [ ] Operator TrueNAS checkout used for this evidence was
  `ffdf66e43ad8`, dirty and behind 25 commits. Runtime observations remain
  useful, but code-level acceptance must be repeated after synchronizing PR
  #253 without discarding local work.
- [ ] Next transaction: render the existing CrowdSec bouncer key directly from
  Vaultwarden into the canonical TrueNAS runtime file; run workstation
  `verify-crowdsec-pfsense.sh --preflight`; only then change pfSense CrowdSec
  package settings through the workstation/operator path and require both
  TrueNAS `--accept` + workstation `--accept`.
- [x] Trust boundary stays explicit: TrueNAS never SSHes/API-calls pfSense and
  no runtime secret is copied from TrueNAS to the workstation.

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
