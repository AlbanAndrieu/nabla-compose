# Nabla Compose — execution roadmap and new-chat handoff

**Date:** 2026-10-10. **PR:** [#251](https://github.com/AlbanAndrieu/nabla-compose/pull/251), branch `fix/agent-compose-gate-offline-followup`. **Status:** roadmap accepted by operator; PR must **never** be automatically merged. Use `docs/roadmap.md` for the current execution index and canonical runbooks for details. This file intentionally summarizes rather than copying historical incident output.

## Ratified decisions

1. **Stability first:** repair the local quality-gate infrastructure and Gatus; ensure pfSense/CrowdSec memory/DNS risks are isolated or resolved. Continue evidence gathering on other services in parallel; do not open a new service deployment ahead of a current critical incident.
2. **Secrets per service:** normalize each active application's paths under `/mnt/cpool/secrets/runtime/<service>/`, validate names in `config/secrets/manifest.json`, materialization, consumer acceptance and rollback; do not bulk-rotate or bulk-finalize. Bundle this with its Backstage descriptor where possible.
3. **Catalog v2:** prepare Parity/Backstage/Compose in stages but perform a **single coordinated consumer cutover** across `nabla-compose`, `fastapi-sample`, `nabla-site-alban`. No permanent dual-schema layer. Never delete legacy JSON until desired-exposure and consumer parity, safe rollback and reboot acceptance.
4. **Cyberbro before Docling as equally ranked backlog features**, after operational foundations and migration transactions. Read-only Docling probes can run in parallel. Shared Docling + OpenRAG retrieval via restricted API/MCP + LiteLLM GPU + Open WebUI are the accepted RAG architecture. Bababou POC stays private and read-only.
5. **Close accepted services:** DSOMM HTTP 200 and 12 pytest/22 subtests; Sentry diagnostic 14 OK; Scrutiny web/InfluxDB/SMART sda–sdd healthy; Pi-hole DNS sync healthy. Remaining DSOMM reboot evidence, Sentry fresh E2E, Scrutiny sde classification, Pi-hole reboot proof are explicit follow-ups, not reasons to repeat deployment.
6. **No automatic merge**. Commit cohesive improvements in the same PR; fix meaningful regressions without turning all optional/local environment checks into a blocking loop between every roadmap item.

## Local-first validation policy — strict on safety, flexible on progression

- **Agent executes and iterates validations in its own available environment by default:** `bash -n`, `shellcheck` (if installed), `python -m pytest` (targeted and broader when available), YAML/JSON parsing, Ruff/pre-commit, topology generators, Compose config, BetterLeaks, SAST and other applicable gates. Obtain exact HEAD source via GitHub connector or archive if git/network unavailable; do not misrepresent a partial fixture as full-repository verification.
- **Do not ask the operator to run the entire `just pre-push`, ShellCheck or pytest on the workstation/TrueNAS for each small change.** Record `PASS`, `FAIL`, `UNAVAILABLE` or `NOT RUN` per check with evidence, commit incremental progress and investigate failures autonomously. Group operator-only checks into a single explicit acceptance checkpoint or when real appliance evidence is indispensable.
- **Distinguish pre-existing from introduced failures.** An introduced code/security regression must be fixed before declaring that change complete. An unrelated pre-existing environmental failure may be recorded as debt while independent, safe work continues; do not mark the full quality gate green.
- **Do not disable, bypass, skip, weaken or silently suppress** ShellCheck, pytest, Ruff, SAST, BetterLeaks, Playwright, ZAP or repository contract gates to make them pass. Where tools cannot run, explain the missing capability and retain the final acceptance gate. `[skip ci]` is not a substitute for local quality validation.
- **Final PR merge/readiness gate:** complete required local validation on the exact PR HEAD, review unresolved failures, preserve security checks, obtain the necessary TrueNAS/workstation runtime acceptance, and leave merging to the operator. GitHub Actions credit or network unavailability must not cause infinite speculative re-runs.
- Treat external services, data changes, ZFS state, identity and secrets more strictly than documentation-only changes; never auto-restart/redeploy existing apps, expose a tunnel or index private data merely to complete an autonomous step.

## Critical path (dependencies and done criteria)

| Step | Task | Dependency | Closure criterion |
| --- | --- | --- | --- |
| A1 | Stabilize quality-gate tooling and malformed pre-commit YAML; local-first execution | none | YAML valid; relevant script syntax/contract checks pass in agent environment; unresolved full L3 explicitly tracked |
| A2 | Recover Gatus from STOPPED / restarting exit 2; preserve SQLite | A1 for code commits; read-only diagnostic independent | exact failure explained; Gatus healthy HTTP 8085; history preserved and functional checks |
| A3 | Close pfSense/CrowdSec critical DNS/memory regressions and already-accepted DSOMM/Sentry/Scrutiny accounting | A2 may run in parallel; firewall mutations independent approval | no active high-severity edge instability; accepted vs reboot-accepted documented; fresh E2E where required |
| B1 | Secrets runtime migration in bounded service bundles | A1 + stable consumers | canonical paths, manifest, identity, delivery, permission, recovery and no legacy active consumers per service |
| B2 | Backstage/catalog v2 parity and descriptor/consumer preparation | B1 per touched service, generator gate | deterministic refs, no duplicate relation/owner, desired exposure preserved, consumers prepared |
| B3 | Coordinated v2 consumer cutover and legacy retirement | B2 complete + tested rollback | `nabla-compose` → `fastapi-sample` → `nabla-site-alban` switch, contract/health parity; legacy deletion only after reboot proof |
| C1 | Accept Cyberbro HTTP/IOC and MCP 8013 via LiteLLM, providers minimally privileged | A1–A3 + needed secrets | bounded IOC smoke and MCP auth/tool policy, no secrets in logs |
| C2 | Accept shared Docling and integrate Open WebUI; then OpenRAG API/MCP | C1 order default, infrastructure stable | common Docling conversion PDF/OCR, independent knowledge ACL, known OpenRAG-version API and protected retrieval |
| C3 | Bababou POC on explicitly identified `cpool` copy of Google Drive | C2 + approved private subset | read-only sample, isolated index, retrieval/citation/latency evaluation, no private Git/cloud trace exposure |

**Deferrals:** Karmada/federation, broad AI upgrades, Trivy Operator, new observability daemons, S3 backend consolidation, native Grafana migration unless an active incident warrants it, and destructive cleanup of legacy services.

## Latest execution addendum — 2026-10-10 21:04 CEST

PR **#251 is already merged**. Active follow-up is the draft
[PR #253](https://github.com/AlbanAndrieu/nabla-compose/pull/253)
on `fix/gatus-config-permissions-and-runtime-closure`.
Do not reopen or push new changes to the closed #251 branch.

**Gatus root cause established:** the container logged
`panic: error reading configuration from directory config/config.yml: open config/config.yml: permission denied`;
its exit=2 and restart_count=564 are secondary effects.
Host config YAML was `albandrieu:apps 640`; SQLite dataset/db
are `root:root 770`. The confirmed fault is reading Gatus
configuration, **not a SQLite error**. PR #253 introduces
`scripts/truenas/repair-gatus-config-access.sh` (read-only
`--check`, explicit `--apply`), which first compares Docker
`/config` mount source against the repository path and verifies
`HostConfig.GroupAdd` and group `apps` GID 568. It repairs
only directory group/mode (0750) and YAML group/mode (0640),
never database data. If mount source or group differs, stop and
investigate TrueNAS Custom App config instead. Runtime
application/HTTP acceptance is still pending.

**Next execution:** check current PR head, verify scripts/contracts
locally, obtain minimal non-secret operator-only mount/group/permissions
evidence as needed; apply only a proven correction and check
HTTP 8085 without deleting historical SQLite. Continue secrets
manifest and Backstage descriptor parity in parallel, respecting
the ratified priority sequence and no merge.

### CrowdSec cutover update — 2026-10-10 21:17 CEST

Central TrueNAS CrowdSec is healthy and consuming pfSense logs through Loki
(`cs_lokisource_hits_total=8563`). The blocking state is now precise:
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` is absent,
`PFSENSE_FIREWALL last_pull=<none>`, and the pfSense firewall bouncer still
uses the legacy local LAPI `http://172.17.0.1:8089`. pfSense Small posture is
otherwise correct: local Security Engine absent, firewall bouncer running, PF
tables present with 31,513 IPv4 and 586 IPv6 entries.

PR #253 adds a workstation `--preflight` mode that treats the legacy URL as a
pre-cutover warning while proving TCP reachability from pfSense to
`172.17.0.24:8084`; `--accept` remains strict after cutover. The shared key
must be obtained directly from Vaultwarden on each operator side; never copy the
TrueNAS runtime secret to the workstation and never grant TrueNAS pfSense
administrative access. The operator's last TrueNAS checkout was dirty and
behind 25 commits, so synchronize without destructive reset before final
acceptance.

## Proven state / unresolved facts

- **DSOMM:** `deploy-dsomm.sh --check` completed; capacity `CAP_NET_BIND_SERVICE` confirmed in `ix-dsomm`; HTTP 200 on `172.17.0.24:31088`. Declared `x-nabla.status: planned` and catalog descriptor still planned (needs intentional status reconciliation); `dsomm-baseline` stays planned; runtime evidence files are outside Git and must not be blindly committed.
- **Sentry:** `diagnose-sentry.sh --check` exit 0, 14 OK; runtime-path declarations use `/mnt/cpool/secrets/runtime/sentry`. Manifest/source-of-truth parity and recent event persistence/reboot still to prove.
- **Scrutiny:** app RUNNING, web healthy, InfluxDB v2.9.1 reachable, secret runtime file mode 600; `/dev/sde` SMART access denied, other four SATA devices visible.
- **Pi-hole DNS sync:** healthy, sessions=16, one historical restart warning. No need to redeploy.
- **Gatus:** TrueNAS STOPPED, Docker restarting exit 2, HTTP 8085 absent, `/mnt/cpool/gatus` and `gatus.db` root:root 770; cause not yet proved (read crash logs/UID/config before permissions change); protect DB.
- **Git/pre-commit:** historical `.git/index` root-owned permission incident; earlier executable shebang and malformed `.pre-commit-config.yaml` errors. New standalone `scripts/quality/check-compose-config.sh` and `tests/test_precommit_compose_validator.py` are staged in PR; **full L3 has not been demonstrated green**.
- **Cyberbro:** declared main HTTP :5100, MCP streamable HTTP :8013, runtime env files already declared under `/mnt/cpool/secrets/runtime/cyberbro`; descriptor says active, but runtime acceptance remains unknown.
- **Docling/OpenRAG:** Docling declaration :5001; OpenRAG backend 0.7.1 points to `http://docling:5001` and shared Langflow :7860; Open WebUI lacks declared Docling engine and explicit intranet network. Running versions/health and available OpenRAG MCP/API routes must be verified. TrueNAS LiteLLM :4000/v1 proxies GPU workstation LiteLLM `172.17.0.57:4000/v1`; don't silently swap embedding models/dimensions.
- **Bababou:** a Google Drive export exists on `cpool` according to operator, **exact dataset path unknown**; no ingestion authorized. Use a reviewed local-only, least-privilege corpus.
- **Catalog:** declarative Compose/`x-nabla` plus Backstage descriptor vs generated legacy `catalog/services.json`; v2 cutover spans three repositories and desired exposure policy. Avoid equating `active` descriptor to healthy runtime.

## Next agent action on a new chat

1. Read **this handoff** and top/current section of `docs/roadmap.md`, fetch the **current PR #253 head** (do not assume a SHA in this document is current).
2. Perform independent local-first verification of `.pre-commit-config.yaml`, `scripts/quality/check-compose-config.sh`, `tests/test_precommit_compose_validator.py` and adjacent changed files. Fix regressions without asking the operator to re-run all gates.
3. Advance Gatus read-only diagnostics from existing evidence; implement a targeted, tested correction only once root cause is established. In parallel, generate **non-secret** coverage/debt reports for secrets and Backstage v2 from repository scripts.
4. Commit coherent changes in PR #253; maintain a short current roadmap status and don't merge.
5. Once environment-specific acceptance is indispensable, consolidate required operator commands into one bounded verification set, rather than interrupting every step.

Key references: `docs/secrets-migration-roadmap.md`, `docs/service-catalog-v2-normalization.md`, `docs/runbooks/2026-10-10-platform-services-acceptance.md`, `docs/runbooks/rag-bababou-poc-architecture.md`, `docs/ai-stack-upgrade-consolidation-plan.md`.
