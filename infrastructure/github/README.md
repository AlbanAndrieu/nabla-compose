# GitHub governance with OpenTofu

This live Terragrunt stack prepares GitHub repository governance as code for
repositories owned by `AlbanAndrieu`.

**It is intentionally inert.** The committed configuration keeps every mutation
switch disabled:

- `github_governance_enabled = false`;
- `manage_rulesets = false`;
- `manage_actions_permissions = false`;
- `manage_workflow_permissions = false`;
- `ruleset_enforcement = "disabled"`.

A normal checkout, CI run, `tofu validate`, or Terragrunt plan must therefore
not create or modify repository rules, Actions permissions, or workflow-token
permissions.

## What the module prepares

`terraform/github` can manage, per explicitly allow-listed repository:

- a default-branch repository ruleset;
- pull-request-only changes to the default branch;
- deletion and non-fast-forward protection;
- required checks chosen per repository profile;
- `strict_required_status_checks_policy = false`, matching
  **Require branches to be up to date before merging = OFF**;
- GitHub Actions SHA pinning;
- read-only default `GITHUB_TOKEN` permissions;
- prohibition of GitHub Actions approving pull requests;
- an optional dedicated release GitHub App bypass for semantic-release.

CodeQL, FOSSA, Docker, website, and repository-specific checks are not
automatically made required. Required checks are an explicit per-repository
allow-list so a missing/path-filtered workflow cannot leave a PR permanently
waiting for a check that will never report.

## Authentication

The GitHub provider uses the standard provider authentication chain. For the
initial workstation pilot, export a short-lived `GITHUB_TOKEN` with only the
permissions required to read/plan the selected repositories.

Do not commit tokens, private keys, or GitHub App credentials. The target state
is a dedicated governance GitHub App / short-lived credential path documented in
`docs/github-governance-roadmap.md`.

## Safe validation

Format and statically validate the module without contacting the Garage backend:

```bash
mise exec -- tofu -chdir=terraform/github fmt -check
mise exec -- tofu -chdir=terraform/github init -backend=false
mise exec -- tofu -chdir=terraform/github validate
```

For the repository-standard Terragrunt path, keep all mutation switches false
and use the serialized infrastructure wrapper:

```bash
scripts/infra/terragrunt-safe.sh infrastructure/github init -reconfigure
scripts/infra/terragrunt-safe.sh infrastructure/github validate
scripts/infra/terragrunt-safe.sh infrastructure/github plan
```

Do **not** run `apply` as part of this preparation.

## Activation sequence

Activation must be a separate reviewed change:

1. inventory current classic branch protection, rulesets, required checks, and
   Actions settings;
2. enable read-only inventory only;
3. add repositories to the explicit allow-list;
4. enable `github_governance_enabled` plus `manage_rulesets` with
   `ruleset_enforcement = "disabled"` and inspect the plan;
5. create the disabled pilot ruleset on one repository;
6. verify required-check names actually report on every applicable PR;
7. remove/reconcile overlapping classic branch protection so GitHub does not
   apply a stricter legacy policy in parallel;
8. activate the pilot ruleset;
9. separately enable Actions SHA-pinning and workflow-token controls;
10. add the dedicated release GitHub App bypass only after semantic-release
    behavior is proven;
11. expand repository-by-repository with drift detection.

The detailed rollout and acceptance criteria live in
`docs/github-governance-roadmap.md`.
