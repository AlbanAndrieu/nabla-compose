# Security inventory, supply-chain and attack-graph roadmap

_Last reviewed: 2026-10-01._

This document expands the concise `docs/roadmap.md` P2.1 workstream. The canonical application/service identity and declared dependency model remain `x-nabla` plus the generated `catalog/services.json` and `catalog/service-topology.json`. Specialized tools must enrich that model without becoming competing sources of truth.

The cross-repository tooling inventory, scan taxonomy, Three Lines responsibilities, NIST CSF/SAMM mapping, priorities and lifecycle decisions are maintained in [`docs/security-tooling-control-architecture.md`](./security-tooling-control-architecture.md).

## Target capability split

- **NetBox** — network/infrastructure intent: IPAM, prefixes, VLANs, devices/VMs, interfaces and infrastructure ownership.
- **OCS Inventory NG** — observed endpoint hardware/software inventory. Use agents on supported general-purpose endpoints and bounded network/SNMP discovery where useful; do not make OCS authoritative for application identity, IPAM or desired topology.
- **OWASP Dependency-Track** — CycloneDX SBOM/component inventory and software-supply-chain vulnerability/risk tracking. Reference: <https://blog.stephane-robert.info/docs/securiser/analyser-code/dependency-track/>.
- **OWASP Dependency-Check** — local/CI Software Composition Analysis producer for known vulnerable third-party dependencies; export machine-readable results and feed the central findings workflow rather than creating a second source of truth.
- **OWASP DefectDojo** — normalized security findings, deduplication, triage and remediation workflow across SAST/SCA/secrets/IaC/container/DAST/infrastructure scanners; default findings system of record while complementary PoCs are evaluated.
- **ArcherySec** — evaluate as a bounded vulnerability-assessment/scanner-orchestration layer, especially where active scanning and CI/CD-triggered assessment add value beyond DefectDojo. Keep it non-authoritative during the PoC.
- **Faraday Community** — evaluate as a collaborative pentest/vulnerability workspace for scanner imports, manual findings and reporting. Keep it non-authoritative during the PoC and avoid duplicating DefectDojo ownership of remediation state.
- **OpenSSF Scorecard** — repository and upstream dependency security-posture evidence.
- **Cartography + Neo4j** — relationship graph for attack-path, privilege-chain, internet-exposure and blast-radius analysis after stable asset identities and provenance exist.


## Endpoint inventory — OCS Inventory NG

OCS Inventory NG is the default candidate for the missing **endpoint/host
inventory** layer. It complements NetBox and `x-nabla` instead of replacing
either one:

- `x-nabla` remains authoritative for declared application/service identity,
  ownership, dependencies and lifecycle intent;
- NetBox remains authoritative for network/DCIM/IPAM and infrastructure intent;
- OCS owns **observed** endpoint hardware, operating-system and installed
  software facts;
- Scanopy remains useful for network discovery/topology observations;
- reconciliation must expose drift and identity mismatches before any automated
  write-back is considered.

Current release constraint (reviewed 2026-10-01): OCS 3.0 is still a release
candidate and must remain test-only; use a maintained stable 2.x release for a
production-like pilot or defer production cutover until a 3.x GA is available.
Re-check this decision immediately before deployment.

Implementation gates:

1. [ ] Define the first inventory scope: workstation and supported
   Linux/Windows/macOS endpoints. Do **not** install an OCS agent on the TrueNAS
   appliance or Talos nodes merely for inventory; use existing APIs/Kubernetes
   evidence and network/SNMP discovery where appropriate.
2. [ ] Create repository-owned `apps/ocs-inventory/compose.yml` (or a
   deliberately documented equivalent name) with explicit `x-nabla` metadata,
   internal-only administration exposure, health/readiness checks and persistent
   storage.
3. [ ] Use the database officially supported by the selected OCS generation;
   do not force it onto the shared PostgreSQL service if that release expects a
   different datastore. Document backup/restore and rollback before enrollment.
4. [ ] Materialize server/admin/agent credentials through the canonical secrets
   workflow; no credentials, registration tokens or inventory payloads belong
   in Git.
5. [ ] Enroll the workstation first and prove stable host identity, hardware
   facts, OS/version and installed-software inventory without leaking sensitive
   values into logs.
6. [ ] Add at least one bounded network/SNMP discovery test for devices that
   cannot or should not run an agent, while keeping discovery findings
   distinguishable from authenticated agent inventory.
7. [ ] Define reconciliation keys between OCS host IDs, NetBox device/VM IDs and
   Nabla asset/service identifiers. Start read-only: report drift/duplicates
   instead of automatically rewriting NetBox or `x-nabla`.
8. [ ] Acceptance: inventory survives restart/reboot, a backup can restore the
   server state, stale/decommissioned endpoints have an explicit lifecycle, and
   the data flow has one authoritative owner per field/class of data.

## Dependency-Check + ArcherySec + Faraday evaluation

The objective is to complement DefectDojo, not to multiply authoritative vulnerability databases.

1. [ ] Add **OWASP Dependency-Check** to the local/CI security path for supported application repositories, producing a machine-readable artifact suitable for retention and DefectDojo import. Keep the scan reproducible and cache vulnerability-data downloads where appropriate.
2. [ ] Define one controlled import path into **DefectDojo** and prove idempotent re-import/deduplication on a representative dependency finding set.
3. [ ] Prepare **ArcherySec** and **Faraday Community** as manual/evaluation profiles only. Before any TrueNAS Custom App registration, review image provenance, supported database/storage model, secrets, health endpoints, backup/rollback and network exposure.
4. [ ] Exercise the same bounded finding corpus through DefectDojo, ArcherySec and Faraday: Dependency-Check/SCA, Trivy/container, application DAST evidence imported from `fastapi-sample`, and a small Nmap or pentest sample where supported.
5. [ ] Compare only concrete capabilities: scanner orchestration, import coverage, deduplication, vulnerability lifecycle, manual/pentest workflow, API automation, RBAC, reporting, ticketing hooks, resource footprint and operational complexity.
6. [ ] Record an explicit **keep / complement / drop** decision. DefectDojo remains the authoritative remediation/finding store unless another tool is assigned a narrowly separated responsibility (for example active scanner orchestration or collaborative pentest workspace).
7. [ ] If ArcherySec or Faraday is retained, model it in Backstage/Compose with explicit relations to DefectDojo and scanners, mark its lifecycle criticality deliberately, and prevent bidirectional synchronization loops or duplicated remediation ownership.

Acceptance requires a documented data-flow showing one authoritative owner for finding state and evidence that repeated imports do not create uncontrolled duplicates.

## Cartography + Neo4j

1. [ ] Run a bounded PoC with Cartography backed by Neo4j using only data sources that exist in the homelab, starting with GitHub and Kubernetes.
2. [ ] Define stable identifiers that map graph nodes back to canonical Nabla service IDs and preserve the origin/provenance of every imported or inferred relationship.
3. [ ] Import or enrich selected `x-nabla` ownership and topology relations without allowing the graph to rewrite `x-nabla`, lifecycle ordering or runtime intent.
4. [ ] Prove read-only Cypher queries for at least four cases: internet-exposed paths, identity/privilege escalation paths, paths from a compromised repository/runner to runtime assets, and blast radius from a compromised Tier 0/1 dependency.
5. [ ] If the PoC is useful, deploy repository-managed `apps/neo4j/compose.yml` and `apps/cartography/compose.yml` (or a documented equivalent execution model when Cartography is better operated as a scheduled job), with persistent storage, secrets, health checks, least privilege and explicit backup/rollback.
6. [ ] Keep Neo4j as an analysis store, not a CMDB. Rebuildable imported graph data should remain reproducible from authoritative sources.

## Plumber normalization

Repository evidence shows Plumber still uses the legacy root-level `plumber-platform` submodule (`https://github.com/AlbanAndrieu/platform.git`) and `docker-compose-albandrieu.yml` still contains a commented reference to `plumber-platform/compose.local.yml`. The service is also represented in the generated homelab catalog and has an existing external/tunnel identity, so migration must preserve service identity and exposure contracts.

1. [ ] Inventory the effective `plumber-platform/compose.local.yml`: images/build contexts, ports, networks, volumes, secrets/env files, databases and other functional dependencies.
2. [ ] Create repository-owned `apps/plumber/compose.yml` following current `x-nabla`, runtime-layout, secrets and shared-service conventions.
3. [ ] Preserve the canonical Plumber service ID/name, internal endpoint and `plumber-albandrieu.albandrieu.com` exposure policy; reconcile generated catalog/topology artifacts instead of hand-editing them.
4. [ ] Migrate required configuration/data out of the root submodule model without copying live secrets into Git. Prefer shared canonical data services when compatible; document any justified dedicated stateful dependency.
5. [ ] Add bounded deploy/diagnostic/smoke validation for HTTP/API readiness and any critical downstream dependency.
6. [ ] Remove the stale root `docker-compose-albandrieu.yml` include/reference only after `apps/plumber` acceptance and rollback are proven.
7. [ ] Remove the `plumber-platform` submodule and related linter/pre-commit exclusions only after no build, runtime, documentation or rollback dependency remains.

## Acceptance

- [ ] Every deployed tool has canonical `x-nabla` metadata, explicit runtime ownership, health/readiness checks and a documented persistence/secrets model.
- [ ] Stable IDs reconcile data across `x-nabla`, NetBox, OCS Inventory, Dependency-Track, DefectDojo, Scorecard and Cartography/Neo4j.
- [ ] No tool silently becomes a second source of truth for service identity or declared service dependencies.
- [ ] Attack-graph queries are read-only analytical evidence; inferred graph edges never alter deployment/lifecycle decisions automatically.
