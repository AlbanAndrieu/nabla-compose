# DSOMM initial evidence review

_Last reviewed: 2026-10-04._

This is a **pre-fill aid**, not an OWASP DSOMM maturity score. It records
repository evidence that can be reviewed and attached to the matching activity
in DSOMM 5.0. The pinned `tweag/dsomm-baseline` remains the automated scanner
of record for its supported checks; this document covers evidence that is
directly visible from the current GitHub repository structure.

## Evidence rules

- **Detected** means a concrete file/workflow exists on the repository default
  branch.
- **Candidate evidence** still requires a human to map it to the exact DSOMM
  activity UUID and judge scope/effectiveness.
- **Not observed** means the inspected root/workflow inventory did not expose
  evidence; it does not prove the control is absent.
- **Manual** covers organization/process/interview controls and the DSOMM 5.0
  Agentic AI / Identity dimensions not covered by the pinned Tweag baseline.

Do not convert the rows below directly to `Fully implemented`.

## Seeded assessment status

The reviewed evidence below has already been converted into the conservative
DSOMM 5.0.2 seed under `config/team-progress.seed.yaml` and
`config/team-evidence.seed.yaml`; this document remains the **source inventory
and manual-review aid**, not a second status tracker.

Key acceptance constraints are canonical in [`README.md`](./README.md): only
`Version control` is seeded Fully implemented, GitHub branch/ruleset
enforcement is not demonstrated, and the TrueNAS continuity evidence remains
partial because the PT1H RTO was breached and PT1H RPO was not exercised.

## Nabla Platform

### Repository: AlbanAndrieu/nabla-compose

#### Detected candidate evidence

- [ ] **Automated dependency updates** — `renovate.json` and
  `.github/workflows/renovate.yml`.
- [ ] **SAST / code scanning** — `.github/workflows/codeql.yml`.
- [ ] **Secret scanning in repository quality controls** — `.gitleaks.toml`.
- [ ] **Dependency/container/IaC security configuration** — `.grype.yaml`,
  `.checkov.yml`, `.trivyignore.yaml`, `.semgrepignore`.
- [ ] **Repeatable local quality controls** — `.pre-commit-config.yaml` plus
  repository quality-gate scripts.
- [ ] **Versioning/release process** — `CHANGELOG.md`,
  `.releaserc.yaml`, and `.github/workflows/release.yml`.
- [ ] **Production/runtime security checks** —
  `.github/workflows/production-security.yml` and
  `.github/workflows/runtime-baseline.yml`.
- [ ] **Infrastructure-as-code validation** —
  `.github/workflows/terragrunt-ci.yaml`.

#### Manual / verify

- [ ] Map the above evidence to the exact DSOMM 5.0 activities.
- [ ] Confirm GitHub repository/ruleset enforcement rather than inferring it
  from workflow/config presence.
- [ ] Review DSOMM 5.0 Agentic AI and Identity activities manually.
- [ ] Confirm security training, threat modelling, risk acceptance,
  incident-response and organizational process evidence separately.

## Nabla Applications

### Repository: AlbanAndrieu/fastapi-sample

#### Detected candidate evidence

- [ ] **Automated dependency updates** — `renovate.json` and
  `.github/workflows/renovate.yml`.
- [ ] **SAST / code scanning** — `.github/workflows/codeql.yml`,
  `.bandit.yml`, and `.semgrepignore`.
- [ ] **Secret scanning** — `.gitleaks.toml` and Secretlint configuration.
- [ ] **SCA/container evidence** — `.grype.yaml`, `.trivyignore.yaml`,
  plus checked-in `trivy-sbom.json` as an SBOM evidence candidate.
- [ ] **DAST** — `.github/workflows/security-zap.yml` and repository
  `.zap/` configuration.
- [ ] **Security policy** — `SECURITY.md`.
- [ ] **Release/versioning** — `CHANGELOG.md`,
  `.github/workflows/release.yml`,
  `.github/workflows/semantic-release.yml`.
- [ ] **Repeatable test/build gates** — dedicated test, Docker build and
  production smoke workflows.

#### Manual / verify

- [ ] Confirm freshness/provenance of `trivy-sbom.json` before treating it as
  a current SBOM control.
- [ ] Confirm branch/ruleset enforcement and required checks.
- [ ] Map DAST execution/authorization/evidence retention to the exact DSOMM
  activity rather than counting workflow presence alone.
- [ ] Review DSOMM 5.0 Agentic AI and Identity activities manually.

### Repository: AlbanAndrieu/nabla-site-alban

#### Detected candidate evidence

- [ ] **Automated dependency updates** — `renovate.json`.
- [ ] **Secret scanning** — `.gitleaks.toml`.
- [ ] **Repository quality controls** — `.pre-commit-config.yaml`,
  `.mega-linter.yml`, Biome/ESLint configuration and CI workflows.
- [ ] **DAST** — `.github/workflows/production-dast.yml` and
  `.github/workflows/zap-preview.yml`, with repository `.zap/`.
- [ ] **Security policy** — `SECURITY.md`.
- [ ] **Release/versioning** — `CHANGELOG.md`,
  `.releaserc.json` / `.releaserc.yaml`, and
  `.github/workflows/release.yml`.
- [ ] **Browser/end-to-end testing** — Playwright workflow and configuration.

#### Not observed / verify

- [ ] No dedicated `codeql.yml` was observed in the workflow directory
  inventory; verify whether SAST is provided through another workflow/service
  before marking the corresponding DSOMM activity.
- [ ] No checked-in SBOM artifact was observed at repository root; verify the
  build/release pipeline before marking SBOM coverage.
- [ ] Review DSOMM 5.0 Agentic AI and Identity activities manually.

### Repository: AlbanAndrieu/nabla-site-bababou

#### Detected candidate evidence

- [ ] **Automated dependency updates** — `renovate.json`.
- [ ] **Secret scanning** — `.gitleaks.toml`.
- [ ] **Repository quality controls** — `.pre-commit-config.yaml`,
  `.mega-linter.yml`, Biome/ESLint configuration and CI workflows.
- [ ] **DAST** — `.github/workflows/production-dast.yml` and
  `.github/workflows/zap-preview.yml`, with repository `.zap/`.
- [ ] **Security policy** — `SECURITY.md`.
- [ ] **Release/versioning** — `CHANGELOG.md`, `.releaserc.yaml`, and
  `.github/workflows/release.yml`.
- [ ] **Browser/end-to-end testing** — Playwright workflow and configuration.

#### Not observed / verify

- [ ] No dedicated `codeql.yml` was observed in the workflow directory
  inventory; verify alternative SAST coverage before marking the activity.
- [ ] No checked-in SBOM artifact was observed at repository root.
- [ ] Review DSOMM 5.0 Agentic AI and Identity activities manually.

## Suggested first DSOMM review order

1. Run the pinned Tweag baseline and open
   `/mnt/cpool/dsomm/reports/dsomm-baseline.md`.
2. For each detected item, open the corresponding DSOMM 5.0 activity and attach
   concrete evidence only after confirming scope and freshness.
3. Start with Level 1 and Level 2 activities before interpreting higher-level
   automated detections.
4. Review repository/ruleset enforcement, security ownership, training,
   threat-model/risk and incident-management activities manually.
5. Review the DSOMM 5.0 Agentic AI and Identity dimensions independently of the
   Tweag score.
6. Export reviewed `team-progress.yaml` and `team-evidence.yaml` from DSOMM
   and place them only in the protected TrueNAS runtime state, not in Git.

## Runtime report locations

```text
/mnt/cpool/dsomm/reports/dsomm-baseline.csv
/mnt/cpool/dsomm/reports/dsomm-baseline.md
/mnt/cpool/dsomm/state/team-progress.yaml
/mnt/cpool/dsomm/state/team-evidence.yaml
```
