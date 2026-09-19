# Security tooling inventory and control architecture

_Last reviewed: 2026-09-17._

This document inventories security tooling evidenced across `nabla-compose`,
`nabla-site-alban` and `fastapi-sample`, then classifies it using a consistent
control model. It complements `docs/security-inventory-tooling-roadmap.md` and
the Notion **Nabla — Système opérationnel DevSecOps sur 90 jours** roadmap.

The objective is not to maximize the number of scanners. It is to make every
control attributable to an owner, a risk-reduction objective, an SDLC/runtime
stage, an evidence source and an explicit lifecycle decision.

## Classification model

No single framework answers all of the questions needed by the tooling
inventory. Use the following dimensions together:

1. **IIA Three Lines Model — responsibility, not scan order.**
   - **Line 1 — Engineering / Platform / Operations:** owns services and risks,
     runs preventive/detective controls in delivery and runtime, fixes findings.
   - **Line 2 — Security / AppSec / SecOps / Risk:** defines standards, provides
     shared security capabilities, challenges and monitors Line 1, aggregates
     evidence and risk.
   - **Line 3 — Internal Audit / independent assurance:** independently assesses
     governance and control effectiveness. A scanner does not become a Line 3
     control merely because it is independent from the application team.
2. **NIST CSF 2.0 — control outcome:** Govern, Identify, Protect, Detect,
   Respond, Recover. The functions are concurrent and mutually reinforcing.
3. **OWASP SAMM + NIST SSDF — software lifecycle:** Governance, Design,
   Implementation, Verification, Operations; secure practices are integrated
   throughout the SDLC rather than added as a final gate.
4. **Technical control class:** inventory, SAST, SCA/SBOM, secrets, IaC,
   container/image, CI/CD, DAST/API, infrastructure vulnerability, cloud/K8s
   posture, runtime detection, SIEM/log analytics, identity/secrets, CTI,
   vulnerability-management and attack-graph analysis.
5. **Priority:** based on dependency and Tier 0/1 risk reduction, not product
   popularity.

### Priority convention

| Priority | Meaning | Typical decision |
| --- | --- | --- |
| **P0 — foundation** | Required to know the assets, identities and software being protected, or to stop high-confidence defects before deployment. | Standardize now; Tier 0/1 coverage first. |
| **P1 — exposure/runtime** | Validates deployed attack surface, posture and runtime behavior; enables actionable vulnerability/detection workflows. | Industrialize after P0 identity/inventory is reliable. |
| **P2 — enrichment** | Improves context, graph analysis, hunting or depth after basic coverage is stable. | PoC with measurable use cases. |
| **P3 — alternative/reference** | Duplicate, commercial candidate, research/reference-only or intentionally disabled channel. | Do not deploy without a demonstrated gap. |

### Status convention

| Status | Meaning |
| --- | --- |
| **USED** | Direct repository evidence shows the tool/control is executed or is a repository-managed runtime capability. |
| **AVAILABLE** | Configuration/Compose/scripts exist, but current runtime or recurring execution is not proven by repository evidence alone. |
| **PLANNED** | Roadmap/manifests/current PR prepare the capability; acceptance or cutover is incomplete. |
| **REFERENCE** | Documented resource or comparison candidate; presence is not deployment evidence. |
| **DISABLED(channel)** | Explicitly disabled in the named integration, which does not imply global exclusion if another execution path exists. |
| **EXCLUDED/REPLACED** | Current architecture intentionally prefers another control; re-introduction requires a documented coverage gap. |

## Control architecture at a glance

```text
                       GOVERN / IDENTIFY
             inventory · ownership · tier · evidence
                 x-nabla · Scanopy · NetBox
                          |
        +-----------------+-----------------+
        |                                   |
   LINE 1 / SHIFT LEFT                LINE 1 / RUNTIME
   code -> build -> test              deploy -> operate
   SAST / SCA / secrets               DAST / posture / IDS
   IaC / image / workflow             Wazuh / Suricata / Falco
        |                                   |
        +-----------------+-----------------+
                          |
                   LINE 2 / SECURITY
      standards · correlation · challenge · risk workflow
       Dependency-Track · DefectDojo · SIEM · Cyberbro
                          |
                   LINE 3 / ASSURANCE
       independent audit / pentest / control effectiveness
```

Line 2 tooling can also be operated by Platform/SecOps; the diagram expresses
accountability intent, not a mandatory organization chart.

## Detailed inventory

### 1. Inventory, ownership, software composition and finding workflow

| Tool / capability | Class | Priority | Three Lines | NIST | Status | Evidence / decision |
| --- | --- | --- | --- | --- | --- | --- |
| `x-nabla` + generated service catalog/topology | Asset/service inventory | P0 | L1 owns, L2 consumes/challenges | Govern, Identify | **USED** | `nabla-compose` canonical declared application/service identity and dependency source. Do not replace with a CMDB. |
| Scanopy | Network discovery/topology | P0 | L1 | Identify, Detect | **AVAILABLE/USED design** | `apps/scanopy/compose.yml`, deploy/bootstrap scripts and generated catalog exist. Reconcile observations with canonical identities. |
| NetBox | IPAM/DCIM/infrastructure source of truth | P0 | L1 with L2 consumption | Identify | **PLANNED — PR #207** | `apps/netbox/compose.yml` in #207. Own network/infrastructure intent, not application identity. |
| CycloneDX / `cyclonedx-bom` | SBOM format/generator | P0 | L1 | Identify, Protect | **AVAILABLE** | `fastapi-sample` carries `cyclonedx-bom`; `run-trivy.sh` can emit CycloneDX. |
| OWASP Dependency-Track | SCA/SBOM risk inventory | P0 | L1 supplies SBOM, L2 monitors | Identify, Protect, Detect | **PLANNED — PR #207** | `apps/dependency-track/compose.yml`; consume CycloneDX rather than becoming service inventory. |
| OWASP DefectDojo | Finding aggregation/dedup/remediation | P1 | L2 shared capability; L1 remediates | Govern, Identify, Respond | **PLANNED — PR #207** | `apps/defectdojo/compose.yml`; normalize findings across scanners. |
| Plumber | CI/security scan orchestration/reporting | P1 | L1/L2 | Govern, Identify, Protect, Detect | **MIGRATING — PR #207** | `apps/plumber/compose.yml` replaces the legacy root submodule only after runtime acceptance. |
| OpenSSF Scorecard | Repository/supply-chain posture | P1 | L1/L2 | Identify, Protect | **PLANNED — PR #207** | `apps/scorecard/compose.yml`, intentionally one-shot/manual rather than daemon. |
| Cartography + Neo4j | Security relationship / attack graph | P2 | L2 | Identify, Detect | **PLANNED — PR #207** | `apps/cartography/compose.yml` + `apps/neo4j/compose.yml`; analytical graph only, never source of deployment truth. |

### 2. SAST and code-level security

| Tool | Priority | Three Lines | Status | Repository evidence / decision |
| --- | --- | --- | --- | --- |
| CodeQL | P0 | L1 gate, L2 policy | **USED** | Dedicated CodeQL workflows exist in `nabla-compose` and `fastapi-sample`; security resources also reference it in `nabla-site-alban`. |
| Semgrep CE | P0 | L1 gate, L2 rules | **USED / repo-dependent** | Makefile/security evidence exists across the three repos; `nabla-site-alban` documents Semgrep CE as an active validation control. FastAPI's old CodeClimate Semgrep plugin is disabled, so that channel must not be counted as coverage. |
| Bandit | P0 | L1 | **USED** | `fastapi-sample` pre-commit/tox/scripts execute Bandit and high-confidence/high-severity findings are documented as blocking. `nabla-site-alban` MegaLinter config keeps Bandit non-blocking. |
| DevSkim | P3 | L1/L2 | **DISABLED(MegaLinter)** | Explicitly disabled in the reviewed MegaLinter configurations; do not count it as current coverage. |
| TheAuditor | P3 | L2 evaluation | **REFERENCE** | Curated in `nabla-site-alban` security resources; no deployment evidence found. |

### 3. SCA, SBOM, dependency and supply-chain controls

| Tool | Priority | Three Lines | Status | Repository evidence / decision |
| --- | --- | --- | --- | --- |
| Trivy | P0 | L1 | **USED** | Makefile/scripts and CI evidence across repos. `fastapi-sample` MegaLinter runs vuln/misconfig/secret/license scanning but currently marks repository Trivy findings non-blocking. |
| CycloneDX | P0 | L1 | **AVAILABLE** | FastAPI can emit CycloneDX SBOM; make this the interchange contract for Dependency-Track/DefectDojo. |
| Grype | P1 | L1 | **AVAILABLE, DISABLED(MegaLinter)** | `.grype.yaml` exists in `nabla-compose` and `fastapi-sample`; MegaLinter channels reviewed here disable Grype. Re-enable only if it adds material coverage beyond Trivy. |
| Syft | P1 | L1 | **PLANNED/REFERENCE, DISABLED(MegaLinter)** | Mentioned as SBOM option, but disabled in current MegaLinter channels. Prefer one normalized CycloneDX pipeline. |
| Renovate | P0 remediation support | L1 | **USED** | Renovate workflows/configuration exist in `nabla-compose` and `fastapi-sample`; complements SCA by producing upgrade actions rather than vulnerability detection itself. |
| Dependency-Track | P0 | L1/L2 | **PLANNED** | See inventory section; target component-risk system. |
| OpenSSF Scorecard | P1 | L1/L2 | **PLANNED** | Repository/upstream posture evidence, not a replacement for SCA. |
| Dustilock | P3 | L1 | **DISABLED(MegaLinter)** | Explicitly disabled in current `nabla-compose`/FastAPI MegaLinter; no reason to count it as coverage. |

### 4. Secrets and credential leakage

| Tool | Priority | Three Lines | Status | Repository evidence / decision |
| --- | --- | --- | --- | --- |
| Gitleaks | P0 | L1 | **USED** | `.gitleaks.toml` exists in all three repos; FastAPI roadmap records native pre-commit execution and `nabla-site-alban` MegaLinter fails on Gitleaks findings. |
| BetterLeaks | P0 | L1 | **USED (FastAPI)** | FastAPI MegaLinter uses `.gitleaks.toml`, redacts findings and fails the job on detections. |
| Secretlint | P0 | L1 | **USED (FastAPI/site)** | Enabled/blocking in FastAPI and site MegaLinter; disabled in `nabla-compose` MegaLinter where canonical local/pre-commit controls should remain authoritative. |
| TruffleHog | P3 | L1/L2 | **REFERENCE / DISABLED(MegaLinter)** | Present in security resources but disabled in current Compose/FastAPI MegaLinter. Prefer the standardized Gitleaks/BetterLeaks path unless a coverage gap is demonstrated. |
| GitGuardian | P3/external | L2 | **EXTERNAL / evidence integration** | FastAPI release documentation references GitGuardian; `nabla-site-alban` catalogs it. Treat as external capability, not repo-hosted tooling. |

### 5. IaC, container and CI/CD configuration security

| Tool | Class | Priority | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| Checkov | IaC/misconfiguration | P0 | **USED** | Enabled in `nabla-compose` and FastAPI MegaLinter; explicitly disabled in site MegaLinter, so coverage is repo-specific. |
| Zizmor | GitHub Actions security | P0 | **USED** | Enabled in Compose and FastAPI MegaLinter. |
| Hadolint | Dockerfile hardening | P1 | **USED/supporting** | Active/configured in FastAPI and site lint pipelines; supporting secure build hygiene, not a vulnerability scanner. |
| KICS | IaC | P3 | **DISABLED/REFERENCE** | Explicitly disabled in reviewed Compose/site channels; reference only unless selected after comparison. |
| Terrascan | IaC | P3 | **DISABLED/REFERENCE** | Site configuration contains Terrascan settings but current linter is disabled. |
| TFLint | Terraform quality/posture support | P3 | **DISABLED(site MegaLinter)** | Not current security coverage. |
| `pre-commit-terraform` | IaC workflow | P3 | **REFERENCE** | Cataloged in the site security resource page; no cross-repo standardization evidence. |
| Trivy misconfiguration/image scanning | IaC/container/image | P0 | **USED** | Prefer as the common image/filesystem/misconfiguration baseline where it already exists. |

### 6. DAST, API and externally observable attack surface

| Tool | Priority | Three Lines | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| OWASP ZAP | P1 | L1 executes, L2 defines policy | **USED** | `nabla-compose` has bounded OpenAPI preparation and ZAP rule sets; `nabla-site-alban` has preview/production DAST workflows; FastAPI has `security-zap.yml` and DAST roadmap evidence. |
| Nuclei | P2 | L1/L2 | **PLANNED/Notion baseline** | Included in the 90-day control architecture but no recurring execution evidence was found in the three repos reviewed. |
| Pentest-Tools.com | P3 external assurance | L2/L3 depending engagement | **REFERENCE/EXTERNAL** | Curated by `nabla-site-alban`; external service, not repo-run control. |
| Burp Suite / Enterprise | P3 | L2/L3 | **REFERENCE/COMMERCIAL** | Comparison candidate from Notion; use for authenticated/manual/deep testing gaps, not as duplicate baseline by default. |

### 7. Network, infrastructure and host vulnerability discovery

| Tool | Priority | Three Lines | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| Greenbone / OpenVAS | P1 | L1/L2 | **AVAILABLE — legacy stack** | `openvas/docker-compose-openvas.yml` and startup instructions exist; the root aggregate Compose reference is commented, so do not describe it as currently managed/running without runtime evidence. |
| Scanopy | P0 inventory | L1 | **AVAILABLE/USED design** | Repository-managed Compose, deploy/bootstrap scripts and generated monitoring/catalog evidence. |
| Nmap | P1 discovery/validation | L1/L2 | **REFERENCE** | Curated in `nabla-site-alban`; no recurring repo-managed scan evidence found. |
| Masscan | P2 discovery | L2 | **REFERENCE** | Curated in site resources; use only for explicitly authorized high-speed discovery. |
| Wireshark | P2 packet analysis | L1/L2 | **REFERENCE** | Analyst tool, not automated vulnerability coverage. |
| `ssh-audit` / `ssh_scan` | P1 SSH posture | L1/L2 | **REFERENCE** | Curated in site hardening resources; candidate for bounded host/edge checks. |
| OpenSCAP | P1 host compliance | L1/L2 | **REFERENCE** | Site hardening catalog; no standardized execution across the three repos found. |
| Lynis | P1 host hardening audit | L1/L2 | **REFERENCE** | Site hardening catalog; candidate for host baseline. |
| dev-sec Ansible hardening | P1 remediation | L1 | **REFERENCE** | Curated remediation framework; not a scanner and not current cross-repo coverage. |

### 8. Kubernetes, cloud-native posture and runtime detection

| Tool / control | Class | Priority | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| Falco | Runtime threat detection | P1 | **PLANNED/PREPARED** | `kubernetes/platform-tools/falco-values.yaml`, installer/readiness scripts and version pinning exist. Repository preparation does not by itself prove accepted runtime deployment. |
| Kubescape | K8s posture | P1 | **PLANNED/Notion baseline** | Named in Notion target architecture; no standardized active path found in reviewed repo evidence. |
| kube-bench | CIS K8s benchmark | P1 | **PLANNED/Notion baseline** | Same: target baseline, not yet counted as current coverage. |
| Kyverno | Admission/policy | P2 | **REFERENCE** | `nabla-site-alban` Kubernetes security resources; no active canonical deployment evidence found. |
| OPA Gatekeeper | Admission/policy | P2 | **REFERENCE** | Site security catalog; evaluate against Kyverno rather than deploying both by default. |
| Cilium policy | Network policy | P1 | **REFERENCE/architecture candidate** | Site resources; not equivalent to Falco runtime detection. |
| Hubble | Network observability | P2 | **REFERENCE** | Site resources; useful evidence source if Cilium is adopted. |
| Tetragon | eBPF runtime security | P2 | **REFERENCE** | Site resources; compare to Falco after defining detection use cases. |
| Prowler | Cloud security posture | P2 | **REFERENCE** | Site cloud-security resources; activate only when AWS/Azure/GCP scope justifies it. |

### 9. Runtime security, SIEM, IDS/IPS and malware detection

| Tool | Class | Priority | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| Wazuh | SIEM/XDR/HIDS/security platform | P1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/wazuh/compose.yml` defines the logical platform and workloads. Runtime health is separate evidence and must not be inferred solely from Compose presence. |
| Suricata | NIDS | P1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/suricata/compose.yml`; detection capability and CrowdSec integration evidence exist. |
| CrowdSec | behavioral detection/response | P1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/crowdsec/compose.yml` declares Detect/Respond functions. |
| ClamAV | malware scanning | P1 | **DECLARED/INTEGRATION** | Referenced by the service catalog/site Wazuh integration material; distinguish a logical/native service from a repository-owned Compose runtime. |
| OpenSearch Security | security analytics/search | P1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/opensearch/compose.yml`; can support security analytics but is not by itself a complete SIEM operating model. |
| Elastic Security | SIEM | P3 | **REFERENCE/Notion baseline option** | Comparison/baseline option in Notion; not selected merely because Elastic/OpenSearch components exist elsewhere. |

### 10. Identity, secrets and preventive platform controls

| Tool | Priority | Three Lines | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| HashiCorp Vault | P0 | L1 platform + L2 policy | **PLANNED/PREPARED for K8s** | Kubernetes platform tooling prepares Vault; Notion target says reuse Vault for dynamic/short-lived credentials. |
| Vaultwarden | P0 supporting secrets/passwords | L1 | **USED/REPOSITORY-MANAGED** | `apps/vaultwarden/compose.yml`; high-criticality password-management service and current secret-rendering foundation. Do not conflate Vaultwarden with HashiCorp Vault capabilities. |
| 1Password Connect | P1 secrets API | L1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/opconnect/compose.yml`; high-criticality secrets API/sync capability. |
| Keycloak | P0 IAM | L1/L2 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/keycloak/compose.yml`, critical core OIDC/SAML identity provider. |
| 2FAuth | P1 MFA support | L1 | **AVAILABLE/REPOSITORY-MANAGED** | `apps/2fauth/compose.yml`; Protect function. |
| SOPS | P2 secrets-as-code pattern | L1 | **REFERENCE** | Site DevSecOps resources reference SOPS/Vault integration; no need to make it a second runtime secret authority by default. |
| Docker Socket Proxy | P0 privilege boundary | L1 | **USED/REPOSITORY-MANAGED** | Root Compose declares the restricted Docker API security proxy; preventive architectural control, not a scanner. |

### 11. Threat intelligence and detection engineering

| Tool / source | Priority | Three Lines | Status | Evidence / decision |
| --- | --- | --- | --- | --- |
| Cyberbro | CTI/IOC analysis workbench | P1 | L2/SecOps | **AVAILABLE/REPOSITORY-MANAGED** | `apps/cyberbro/compose.yml`; IOC enrichment and external-provider integrations. |
| OpenCTI | CTI platform | P2 | L2 | **PLANNED/PENDING integration** | Cyberbro onboarding/env/secret contracts contain OpenCTI endpoint/API-key placeholders, but current repo evidence marks onboarding pending. |
| MISP | CTI sharing | P2 | L2 | **PLANNED/PENDING connector** | Cyberbro provider surface includes MISP; treat as connector target until an accepted runtime exists. |
| OpenCVE / NVD / CISA KEV | vulnerability intelligence | P1 | L2 | **REFERENCE/EXTERNAL FEEDS** | Site resources include OpenCVE/NVD/CVE/CISA KEV. Use as enrichment/prioritization sources, not substitutes for asset/SBOM inventory. |
| MITRE ATT&CK Detection Strategies | detection methodology | P1 | L2 | **REFERENCE STANDARD** | Structure detection use cases around threat model -> technique -> telemetry -> detection strategy/analytics -> test -> coverage. |
| MITRE D3FEND | defensive technique vocabulary | P2 | L2 | **REFERENCE STANDARD** | Useful to normalize what a defensive capability does; D3FEND explicitly does not prioritize controls or assert effectiveness. |

## Commercial / external comparison candidates

These are target-market comparisons from the Notion roadmap or security-resource
catalog, not proof of current deployment. They stay **P3 until a measured gap
justifies a PoC**.

| Domain | Candidates |
| --- | --- |
| SAST / ASPM | SonarQube/SonarCloud, GitHub Advanced Security, Checkmarx, Veracode, Snyk, Datadog Code Security |
| SCA | Sonatype Lifecycle, Snyk, Mend, Wiz, Datadog |
| Secrets | GitGuardian, GitHub Advanced Security, Wiz, Datadog |
| DAST/API | Burp Suite Enterprise, Invicti, Bright, StackHawk |
| Infrastructure vulnerability | Tenable, Qualys, Rapid7, Wiz |
| CNAPP/Kubernetes | Wiz, Prisma Cloud, Aqua, Sysdig |
| SIEM | Splunk, Microsoft Sentinel, Google SecOps, Datadog Security |
| EDR/XDR | CrowdStrike, Microsoft Defender, SentinelOne |
| Secrets platform | HCP Vault only if the operational model requires managed Vault |

## What is intentionally not counted as security coverage

- A tool listed on `nabla-site-alban`'s security-resource page is **REFERENCE**
  until repository/runtime evidence demonstrates execution.
- A disabled MegaLinter linter is not active coverage merely because its config
  remains in the repository.
- A Compose definition is deployment intent; it does not prove runtime health.
- A generated SBOM is inventory evidence, not vulnerability remediation.
- Prometheus/Grafana/observability data can be security evidence but is not a
  functional security dependency of the service being observed.
- Linters such as Ruff/ESLint/ShellCheck improve engineering quality; they are
  listed here only when they directly support a security control boundary.

## Recommended control-line priorities

### P0 — establish the control substrate

1. Keep `x-nabla` canonical for services and reconcile Scanopy/NetBox observations
   instead of creating competing identities.
2. Standardize code/security gates by repository: CodeQL/Semgrep/Bandit where
   relevant, Gitleaks/BetterLeaks/Secretlint, Checkov/Zizmor and Trivy.
3. Emit a normalized CycloneDX SBOM for Tier 0/1 software and ingest it into
   Dependency-Track.
4. Attach findings to an owner, service ID and tier; avoid scanner-only metrics.
5. Complete identity/secrets foundations (Keycloak/Vault strategy/short-lived
   credentials) for critical services.

### P1 — validate exposure and runtime

1. Make ZAP/API testing recurrent for authorized Internet-facing Tier 0/1 targets.
2. Normalize infrastructure scanning with Greenbone/OpenVAS or a selected
   alternative, and reconcile discovered assets with the inventory.
3. Activate Kubernetes posture/runtime controls based on the Talos threat model:
   posture/benchmark plus Falco runtime detection, not Falco as a NetworkPolicy
   substitute.
4. Feed actionable findings into DefectDojo and runtime/detection evidence into
   the selected SIEM workflow.
5. Measure coverage and evidence freshness, not only finding counts.

### P2 — enrich once P0/P1 evidence is stable

1. Connect CTI use cases through Cyberbro/OpenCTI/MISP only where detections or
   vulnerability prioritization consume the intelligence.
2. Prove Cartography/Neo4j attack-path queries with stable IDs/provenance.
3. Compare Tetragon/Cilium/Hubble, Prowler or additional scanners only against a
   documented coverage gap.

### P3 — comparison / de-duplication

Commercial PoCs and duplicate OSS scanners are justified only when the baseline
shows an unserved requirement, a materially better signal-to-noise ratio, a
coverage/compliance gap or lower operating cost.

## Evidence and measurement contract

For each selected control, record at minimum:

```yaml
control:
  id: sast-codeql
  class: sast
  owner: platform-security
  threeLines: line-1-with-line-2-oversight
  nistCsf: protect
  stage: verification
  priority: P0
  status: used
  scope: tier-0-1
  evidence:
    source: github-actions
    freshnessSla: 7d
  findingDestination: defectdojo
```

Recommended J0-30 metrics:

- percentage of services/repositories with owner + Tier + authoritative ID;
- percentage of Tier 0/1 services reconciled declared vs observed;
- percentage of Tier 0/1 software with fresh CycloneDX SBOM;
- SAST/SCA/secrets/IaC/container/DAST/runtime coverage by Tier;
- percentage of controls with evidence fresher than their SLA;
- orphan/unmanaged assets and observed-only dependencies;
- Critical/High findings by owner, age and SLA state;
- EOL/unsupported components;
- duplicate scanners without differentiated coverage.

## Methodology references

- IIA, **Three Lines Model** — governance/risk/assurance responsibilities:
  <https://www.theiia.org/en/standards/documents/>.
- NIST, **Cybersecurity Framework 2.0** — Govern, Identify, Protect, Detect,
  Respond, Recover: <https://www.nist.gov/cyberframework>.
- NIST SP 800-218, **Secure Software Development Framework (SSDF) v1.1**:
  <https://csrc.nist.gov/pubs/sp/800/218/final>.
- OWASP, **Software Assurance Maturity Model (SAMM)**:
  <https://owaspsamm.org/model/>.
- CIS, **Critical Security Controls v8.1** and Implementation Groups:
  <https://www.cisecurity.org/controls/v8-1>.
- MITRE ATT&CK, **Detection Strategies**:
  <https://attack.mitre.org/detectionstrategies/>.
- MITRE **D3FEND** defensive countermeasure knowledge graph:
  <https://d3fend.mitre.org/>.

## Repository evidence reviewed

### `nabla-compose`

- `catalog/README.md`, `catalog/services.json`, `catalog/service-topology.json`
- `.mega-linter.yml`, `.gitleaks.toml`, `.grype.yaml`, `Makefile`
- `.github/workflows/{codeql,pre-commit,production-security,...}.yml`
- `.zap/*`, `scripts/security/prepare-zap-openapi.py`
- `apps/{wazuh,suricata,crowdsec,cyberbro,keycloak,2fauth,opconnect,vaultwarden,opensearch,scanopy}/`
- `openvas/docker-compose-openvas.yml`
- `kubernetes/platform-tools/falco-values.yaml`, platform-tool scripts/docs
- PR #207: `apps/{netbox,dependency-track,defectdojo,scorecard,neo4j,cartography,plumber}/compose.yml`

### `nabla-site-alban`

- `SECURITY.md`
- `.mega-linter.yml`, `.gitleaks.toml`, `Makefile`
- `.github/workflows/{ci,mega-linter,production-dast,zap-preview,...}.yml`
- `app/[locale]/security/securityResources.ts`

### `fastapi-sample`

- `.mega-linter.yml`, `.gitleaks.toml`, `.grype.yaml`, `.semgrepignore`
- `.pre-commit-config.yaml`, `tox.ini`, `pyproject.toml`
- `scripts/{run-bandit,run-trivy}.sh`
- `.github/workflows/{codeql,mega-linter,security-zap,docker-build,...}.yml`
- `sonar-project.properties`, release/engineering security documentation

When repository evidence conflicts with an older resource/catalog entry, prefer
the current executable workflow/configuration and record the stale entry as
reference or technical debt instead of claiming active coverage.
