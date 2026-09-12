# GitHub governance as code roadmap

Last updated: 2026-09-13.

## Goal

Manage the GitHub repositories owned by `AlbanAndrieu` through reviewed,
versioned OpenTofu/Terragrunt policy instead of one-off repository UI changes.

The first implementation is deliberately **prepared but inactive** under
`infrastructure/github` and `terraform/github`.

## Safety contract

- [x] Keep `github_governance_enabled = false` in the committed live config.
- [x] Keep ruleset, Actions-permission, and workflow-permission management
  individually disabled.
- [x] Keep `ruleset_enforcement = "disabled"` for the first pilot.
- [x] Use an explicit repository allow-list; read-only discovery must never
  auto-enrol repositories.
- [x] Keep `strict_required_status_checks_policy = false` so required checks do
  not imply **Require branches to be up to date before merging**.
- [x] Do not add CodeQL/FOSSA or any other advisory check to required checks by
  default.
- [x] Do not add a broad user/admin bypass.
- [ ] Never run `apply` from generic PR CI; mutation requires a separately
  reviewed operator/release path.

## P0 — inventory and policy model

- [ ] Inventory every owned, non-archived, non-fork repository.
- [ ] Record existing classic branch protections, repository rulesets, default
  branch, merge methods, required checks, Actions policies, workflow-token
  permissions, and release automation.
- [ ] Classify repositories into policy profiles such as baseline, Docker,
  Python/API, website, and infrastructure.
- [ ] For each profile, prove that every proposed required check is
  always-reporting. Path-filtered workflows must not become globally required
  until they emit a deterministic success/skip result for irrelevant changes.
- [ ] Keep repository-specific exceptions explicit in code rather than hidden in
  the GitHub UI.

## P1 — disabled pilot

Pilot on `AlbanAndrieu/ansible-jenkins-slave-docker`.

- [ ] Enable read-only inventory and compare OpenTofu discovery with the manual
  repository inventory.
- [ ] Enable only `manage_rulesets` while keeping
  `ruleset_enforcement = "disabled"`.
- [ ] Review the plan and create one disabled `nabla-default-branch` ruleset.
- [ ] Confirm the pilot required checks are exactly:
  `Agent preflight`, `Build Docker`, and `Mega Linter`.
- [ ] Keep CodeQL and FOSSA visible/advisory unless policy is intentionally
  changed later.
- [ ] Verify `strict_required_status_checks_policy = false`.
- [ ] Reconcile/remove overlapping classic branch protection before activating
  the ruleset; GitHub evaluates overlapping protections together and the
  stricter rule can still block merges.

## P2 — activate default-branch governance

- [ ] Activate the pilot ruleset only after the disabled definition is reviewed.
- [ ] Require pull requests for the default branch.
- [ ] Block deletion and non-fast-forward/force-push updates.
- [ ] Keep approving-review count at `0` for solo-owner repositories unless an
  explicit repository profile requires reviewers.
- [ ] Require review-thread resolution where the repository uses review
  conversations.
- [ ] Keep branch freshness non-strict (`strict_required_status_checks_policy =
  false`) unless a repository explicitly opts into strict freshness.
- [ ] Validate merge UX on a real PR before expanding to another repository.

## P3 — Actions and workflow-token hardening

Activate independently from rulesets.

- [ ] Set default `GITHUB_TOKEN` permissions to read-only.
- [ ] Keep `can_approve_pull_request_reviews = false`.
- [ ] Require full-SHA pinning for Actions/reusable workflows where repository
  workflows have already converged to immutable pins.
- [ ] Inventory exceptions before enabling SHA pinning globally.
- [ ] Keep validation workflows secret-free where possible; move registry or
  publication credentials to dedicated release workflows.

## P4 — release identity and bypass

- [ ] Create/use a dedicated GitHub App for semantic-release and other controlled
  release writes.
- [ ] Grant only the minimal repository permissions required for release
  commit/tag/GitHub Release operations.
- [ ] Record the verified GitHub App ID in secret-free configuration.
- [ ] Add only that `Integration` actor as a ruleset bypass.
- [ ] Prove that normal users and generic GitHub Actions cannot bypass the
  default-branch policy.
- [ ] Reconcile semantic-release behavior across `nabla-compose`,
  `fastapi-sample`, sites, and other repositories before broad rollout.

## P5 — expand and detect drift

- [ ] Add repositories to the explicit OpenTofu allow-list in small reviewed
  batches.
- [ ] Generate/review plans on a schedule or on governance changes.
- [ ] Detect UI drift and fail/report when a managed setting diverges from code.
- [ ] Keep state in the existing Garage-backed Terragrunt architecture while
  respecting the repository's single-writer state-safety contract.
- [ ] Document import/migration steps for existing rulesets/settings before
  treating OpenTofu as authoritative.
- [ ] If repositories move to a GitHub organization later, evaluate replacing
  repeated repository rulesets with organization rulesets while preserving
  repository-specific required-check profiles.

## Acceptance criteria

GitHub governance is considered managed by OpenTofu only when:

1. the repository inventory is complete;
2. every managed repository is explicitly allow-listed;
3. classic protection overlap has been reconciled;
4. required checks are known to report deterministically;
5. rulesets and Actions/workflow permissions are represented in code;
6. release bypass uses only the dedicated release GitHub App;
7. a plan shows no unexplained drift;
8. rollback to the previous policy is documented and tested on the pilot.
