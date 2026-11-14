# Documentation map

The active documentation is organized by **purpose**, with one canonical owner
for each kind of information. Prefer links over duplicated procedures.
Completed migrations, dated handoffs and session logs are not kept here: their
procedure lives in the canonical runbook, their root cause in `incidents/`, and
the rest in git history.

## Start here

| Need | Canonical document |
| --- | --- |
| **Ordre G1 de #369 : H02 → H01 → H05** | [`roadmap-portfolio.md`](./roadmap-portfolio.md) |
| Index général allégé | [`roadmap.md`](./roadmap.md) ; [archive du 13/11](./archive/2026-11-13-roadmap-before-compaction.md) |
| Audit des fichiers source les plus volumineux (H11/F03/F11) | [`code-hotspots.md`](./code-hotspots.md) ; `just code-hotspots` |
| Documentation ownership / navigation | this file |
| Agent and repository policy | [`../AGENTS.md`](../AGENTS.md), [`agent-skills-architecture.md`](./agent-skills-architecture.md), [`architecture-governance.md`](./architecture-governance.md) |
| Controlled TrueNAS reboot | [`homelab-reboot-runbook.md`](./homelab-reboot-runbook.md) |
| Secrets migration (blocked workstream) | [`secrets-migration-roadmap.md`](./secrets-migration-roadmap.md) |

## Canonical backlogs in related repositories

- [FastAPI Sample engineering](https://github.com/AlbanAndrieu/fastapi-sample/blob/master/docs/engineering-roadmap.md) — API, Cloud runtime, probe evidence; its historical details are archived, not an infrastructure to-do list.
- [Site Alban quality](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/quality-roadmap.md) and [homelab UI](https://github.com/AlbanAndrieu/nabla-site-alban/blob/master/docs/homelab-roadmap.md) — Next.js and Vercel.
- [Site Bababou](https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/roadmap.md) — content and legal-document publication.
- [OpenClaw](https://github.com/AlbanAndrieu/nabla-openclaw/blob/master/docs/roadmap.md) — Gateway, heartbeat, FinOps Vercel; Compose owns only its infrastructure.

The [OpenClaw/YubiKey separation record](roadmap-openclaw-yubikey-extraction-20261030.md) is a **dated handoff**; completed migrations stay closed. Outstanding compatibility cleanup belongs to the Compose roadmap, not a parallel migration plan.

## Decisions (ADR)

- [Frontières des dépôts et diagnostics / proposition ADR](adr/0003-repository-ownership-and-diagnostics.md)
- [Audit des duplications FastAPI / Gatus / Prometheus](diagnostics-duplication-audit.md)
- [Inventaire technique H11 : scripts opérateur, OpenClaw et pfSense](runbooks/operator-script-ownership-inventory.md) — annexe de l'ADR existante, pas une seconde ADR-0003.


- [APISIX API gateway PoC and gateway selection](./adr/0001-apisix-api-gateway-poc.md)
- [Workstation option A](./adr/adr-workstation-option-a.md)
- [Home Assistant installation type (proposed)](./adr/0002-home-assistant-installation-type.md)
- [Hermes Secure by Design](./security/hermes-secure-by-design.md)
- [Hermes on Talos (broker/sandbox migration)](./security/hermes-talos-migration.md) — gateway details in [`../apps/hermes/README.md`](../apps/hermes/README.md)

## Architecture

- [Network topology and IPAM](./homelab-network-topology.md)
- [DNS and ingress ownership](./dns-ingress-ownership.md)
- [Private homelab access](./private-homelab-access-architecture.md)
- [Bibliothèque média *arr, VPN et DNS](./arr-media-library-roadmap.md)
- [Analyse complémentaire CrowdSec, Traefik, Dozzle et sécurité](./arr-security-integration-roadmap.md)
- [Health and observability, exporters](./homelab-health-observability.md)
- [TrueNAS runtime layout](./truenas-runtime-layout.md)
- [Security tooling control architecture](./security-tooling-control-architecture.md)
- [Watchtower service units](./watchtower-service-units.md)
- Service catalog: [v2 normalization](./service-catalog-v2-normalization.md),
  [security graph](./service-catalog-security-graph.md),
  [security standards](./catalog-security-standards.md),
  [consumers](./service-catalog-consumers.md)

## TrueNAS operations

- [Application lifecycle](./truenas-app-lifecycle.md)
- [Migration operator](./runbooks/truenas-migration-operator.md)
- [Catalog v2 two-wave restart](./runbooks/catalog-v2-truenas-two-wave-restart.md)
- [Talos and TrueNAS batch upgrade](./runbooks/2026-10-23-fast-batch-migration.md)
- [pfSense Plus 26.07 sur le Netgate 1100 : environnements de boot et upgrade](./runbooks/pfsense-26.07-upgrade.md)
- [Operator tools and TrueNAS upgrade coupling](./truenas-operator-tools.md)
- [Deployment automation](./truenas-deployment-automation.md)
- [Prompt de déploiement pour une session Claude sur TrueNAS](runbooks/claude-remote-truenas-rollout-prompt.md) : ordre complet, ProtonVPN en dernière étape.
- [G1 PostgreSQL : rotation et restauration isolée](runbooks/postgres-g1-restore-and-secret-rotation.md)
- [Opérations de production des Apps TrueNAS](runbooks/production-app-operations.md) : `app-ops.sh` (état, stockage, secrets, déploiement, redémarrage, diagnostic, supervision, sauvegarde) et [matrice générée](master-readiness.md).
- [Service resource inventory](./runbooks/2026-10-26-homelab-service-resource-inventory.md)
- [CSI orphan datasets](./truenas-csi-orphan-datasets.md)
- [ZFS snapshot policy](./truenas-zfs-snapshot-policy.md)
- [OpenWebUI backup / PRA](./openwebui-backup-pra.md)
- [OpenWebUI / Home Assistant canonical rename](./runbooks/openwebui-homeassistant-canonical-rename.md)
- [Workstation Compose](./workstation-compose.md)

## Talos and Kubernetes

- [Infrastructure bootstrap](./infrastructure-bootstrap.md)
- [Talos on TrueNAS: bootstrap, image factory, machine config](./truenas-talos-bootstrap.md)
- [Kubernetes CSI preflight and pod security](./kubernetes-csi-preflight.md)
- [Home Assistant studies: EnOcean and Somfy](./roadmap-homeassistant-integrations.md)
- [Kubernetes FastAPI smoke](./kubernetes-fastapi-smoke.md)
- [Kubernetes platform tools](./kubernetes-platform-tools.md)

## Network edge: pfSense, DNS, Cloudflare

- [pfSense Plus 26.03.1 → 26.07 upgrade (Netgate arm64)](./pfsense-upgrade-26-07.md)

- [pfSense diagnosis/recovery and WebConfigurator 502](./pfsense-diagnose-recover.md)
- [pfSense flow observability and memory](./pfsense-flow-observability-memory.md)
- [pfSense PHP-FPM hardening](./pfsense-php-fpm-hardening.md)
- [pfSense ingress exposure policy](./runbooks/pfsense-ingress-exposure-policy.md)
- [CrowdSec decision provenance on pfSense](./runbooks/crowdsec-pfsense-decision-provenance.md)
- [Cloudflare Tunnel/Access and self-hosted Sentry platform diagnostics](./cloudflare-sentry-platform-diagnostics.md)
- [Cloudflare Tunnel/DNS/Access as OpenTofu](../terraform/cloudflare/README.md)
- [Nexus private DNS ingress](./runbooks/nexus-private-dns-ingress.md)
- [Workstation split-DNS recovery](./runbooks/workstation-split-dns-recovery.md)

## Diagnostics and acceptance

- [Probe and TrueNAS App remediations still open](./runbooks/2026-11-04-probe-remediation.md)
- [Runtime acceptance](./runbooks/homelab-runtime-acceptance.md)
- [Operator diagnostics (read-only entry point)](./runbooks/2026-10-25-homelab-operator-diagnostics.md)
- [Observability triage: Prometheus, Pyroscope, Akvorado, exporters, FastAPI](./runbooks/2026-10-25-observability-triage.md)
- [End-to-end diagnostics](./runbooks/homelab-e2e-diagnostics.md)
- [Gatus catalog reconciliation](./runbooks/gatus-catalog-reconciliation.md)
- [FastAPI consolidated diagnostics](./runbooks/fastapi-consolidated-diagnostics-20261030.md)
- [FastAPI Sample on TrueNAS](./runbooks/fastapi-sample-truenas-diagnostics.md)
- [Diagnostic output contract](./diagnostic-output.md)
- [Runtime baseline tests](./runtime-baseline-tests.md)

## Secrets and identities

- [Runtime secret initialization](./secrets-runtime-initialization.md)
- [Vaultwarden account for TrueNAS doco-cd](./vaultwarden-truenas-dococd-account.md)
- [Vaultwarden CLI compatibility](./vaultwarden-cli-compatibility.md)
- [GitHub App for DefectDojo](./github-app-defectdojo.md)
- MCP client variables: [`mcp-environment.example`](./mcp-environment.example)

## Security tooling

- [DefectDojo private scan ingestion](./defectdojo-private-scan-ingestion.md)
- [DefectDojo admin access recovery](./runbooks/defectdojo-admin-access-recovery.md)
- [FreshRSS security feeds](./freshrss-security-runbook.md)
- [Security audits](./security-audits/README.md) — source-first audit runs, ledgers, findings and explicit validation gaps.

## AI and RAG

- [FastAPI Sample and LiteLLM](./runbooks/fastapi-sample-litellm.md)
- [LiteLLM UI admin hardening](./runbooks/litellm-ui-admin-hardening.md)
- [OpenRAG / Bababou ingestion diagnostics](./runbooks/openrag-babou-ingestion-diagnostics.md)
- OpenClaw is owned by [nabla-openclaw docs](https://github.com/AlbanAndrieu/nabla-openclaw/tree/master/docs);
  cross-repo split plan: [OpenClaw / workstation / YubiKey](./roadmap-openclaw-yubikey-extraction-20261030.md)

## Quality and CI

- [GitHub required checks](./github-required-checks.md)
- [Node 22 local fast tests](./runbooks/node22-local-fast-tests.md)
- [Refactoring risk register](./runbooks/homelab-refactoring-risk-register.md)

## Incidents and historical evidence

All date-specific incidents belong under [`incidents/`](./incidents/).

- [2026-09-07 · ClickHouse / Langfuse failure modes](./incidents/2026-09-07-clickhouse-langfuse-failure-modes.md)
- [2026-09-08/10 · pfSense WebConfigurator/API 502](./incidents/2026-09-08-pfsense-webconfigurator-http-502.md)
- [2026-09-11 · Sentry Taskbroker / project-config](./incidents/2026-09-11-sentry-taskbroker-project-config.md)
- [2026-09-11 · TrueNAS CSI VolumeAttachment / publishContext](./incidents/2026-09-11-truenas-csi-publishcontext-rbac.md)
- [2026-09-11 · TrueNAS controlled reboot](./incidents/2026-09-11-truenas-reboot.md)
- [2026-09-27 · pfSense/Talos DNS dependency after TrueNAS reboot](./incidents/2026-09-27-pfsense-dns-truenas-dependency.md)
- [2026-10-08 · pfSense Unbound OOM and WAN WebConfigurator exposure](./incidents/2026-10-08-pfsense-unbound-oom-wan-exposure.md)
- [2026-10-10 · post-reboot Git checkout, DSOMM, Gatus, Bitwarden adapter](./incidents/2026-10-10-post-reboot-git-dsomm-gatus-vaultwarden.md)
- [2026-10-10 · Vaultwarden public split-DNS](./incidents/2026-10-10-vaultwarden-public-split-dns.md)
- [2026-10-23 · Sample / Chrome ECH Pi-hole override](./incidents/2026-10-23-sample-pihole-ech-split-dns.md)
- [2026-10-24 · pfSense Unbound restarts, 02:10 OOM, DNSBL cycle](./incidents/2026-10-24-pfsense-unbound-restarts.md)
- [2026-10-24 · TrueNAS Prometheus, Pyroscope and exporters recovery](./incidents/2026-10-24-truenas-observability-recovery.md)
- [2026-10-25 · workstation `hide-location.service` DNS rewrite](./incidents/2026-10-25-workstation-dns-hide-location.md)
- [2026-10-27 · FastAPI TrueNAS build, Docker Hub 429](./incidents/2026-10-27-fastapi-truenas-build-dockerhub-429.md)
- [2026-11-04 · TrueNAS `app.query` blocked by a stuck container lock](./incidents/2026-11-04-truenas-app-query-stuck-container-lock.md)
- [2026-11-06 · migration lessons: STOPPED App binding, WAF, OOM, OpenClaw, secrets, pre-commit](./incidents/2026-11-06-migrations-retour-experience.md)
- [2026-11-13 · pfSense Unbound OOM during Snort rules rebuild, then boot environment rollback](./incidents/2026-11-13-pfsense-unbound-oom-snort-crowdsec.md)

Incident documents retain evidence needed for diagnosis: symptoms, commands,
observations, root cause, recovery boundary and acceptance. They are not the
place for current priorities.

## Archive

- [Roadmap and operator evidence through 2026-10-24](./archive/roadmap-through-2026-10-24.md) (frozen)
- [GitHub Actions runner in a TrueNAS LXC](./archive/github-actions-runner-lxc.md) (not deployed)

## Debt-control rules

1. `roadmap.md` is an index, not a runbook: keep status, ordering and next actions.
2. Completed roadmap work is compacted into accepted milestones; detailed proof
   remains in tests, commits, runbooks or incident documents.
3. Runbooks own supported procedures; incident documents own historical evidence.
4. Architecture documents own target state and trade-offs.
5. Prefer links over copied command blocks.
6. Keep a diagnostic only when it helps answer at least one of: **what failed,
   how to prove it, how to recover, how to validate recovery**.
7. Remove superseded planning documents once their still-relevant actions are
   represented in the canonical roadmap/design document.
8. Delete dated acceptance, handoff and "next commands" documents once their
   work is merged: the procedure goes to the canonical runbook, the root cause
   to `incidents/`.
