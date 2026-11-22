# Entra Nabla — HCP Free remote state (local OpenTofu execution)

Source of truth: [H16 security runbook](../../docs/security/entra-id-homelab-lab.md).

- `backend "remote"` in [backend.tofu](backend.tofu), with a **dedicated HCP Free organization containing only this disposable workspace**, with the HCP workspace
  explicitly configured for **Local** execution. No Azure Blob/Garage state.
- GitHub Actions `validate|plan|apply` with hardware SSHSIG confirmation:
  [workflow](../../.github/workflows/entra.yml).
- Signed challenge script: [approval.py](../../scripts/entra/approval.py).
- Default CI disables Entra group and user writes to minimize Graph permissions.
- `.terraform.lock.hcl` is committed and must not be relaxed in CI.

Run `tofu init -backend-config=/path/outside/repo/entra-nabla.hcp.tfbackend`
on the workstation only after setting up an HCP token and verifying that
the workspace is Local. Then run `tofu validate` and `tofu plan`.
Never run `tofu apply` locally without an explicit reviewed plan: the CI
hardware authorization only protects the **CI workflow**, not users who hold
independent Graph and HCP state write permissions. No secrets in Git.

The previous `infrastructure/entra/terragrunt.hcl` Garage path was
removed. HCP workspace creation and state migration are NOT_APPLIED.

**Security caveat:** HCP Terraform Free has no custom team RBAC: the HCP token
used by the plan job is NOT guaranteed read-only and can hold organization-owner
privileges. This is a disposable pilot only. For strong production read/write
separation choose Azure Blob + Entra OIDC or a paid HCP tier.

**Domaine initial** : le propriétaire déclare
`albanandrieuhotmail.onmicrosoft.com`. Le test
`tests/test_user.tftest.hcl` reproduit ce domaine comme **mock**
offline ; dans `users.tofu`, la source `data.azuread_domains.initial`
récupère le domaine réel du tenant actif lors d'une exécution autorisée.
Aucun domaine n'est écrit en dur dans les ressources de production.

**Nomenclature décidée le 22/11** : CI environments
`entra-nabla-plan` et `entra-nabla-apply`, applications
Graph/OIDC de mêmes noms ; HCP Free workspace proposé
`entra-nabla-state`. L'opérateur déclare avoir créé le tenant
et ajouté deux YubiKeys pour l'accès interactif. Aucune connexion
Microsoft ni création d'application n'a été vérifiée ici.
Ne jamais inclure le courriel administrateur ni la clé privée dans
un fichier d'environnement public.

## Initial CI identities — one-time Terraform bootstrap (NOT_APPLIED)

The **operator** confirmed the personal Entra tenant using Azure CLI on
22 November 2026; that verifies the tenant selection, not successful
authorization of the two GitHub applications. The new
[bootstrap.tofu](bootstrap.tofu) declares, **without applying**:

- Two **single-tenant** app registrations: `entra-nabla-plan` and
  `entra-nabla-apply`, each with its enterprise service principal.
- A **different GitHub environment-bound OIDC credential for each app**.
  Exact issuer: `https://token.actions.githubusercontent.com`; audience:
  `api://AzureADTokenExchange`; subjects:
  `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-plan` and
  `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-apply`.
- Graph application permissions **requested but NOT consented**:
  `Application.Read.All` for the plan job (tenant-wide application metadata
  read); `Application.ReadWrite.OwnedBy` for apply (can create application
  registrations and manage apps/service principals it owns). This is
  security-sensitive even in a personal tenant. Never use
  `Application.ReadWrite.All`, `Directory.ReadWrite.All`,
  subscription `Contributor`, app passwords or certificates in CI.
- A stable personal **operator object ID** as owner. Resource
  `prevent_destroy=true` guards protect app registrations, principals
  and credentials. The `use_existing=true` principal reconciliation is
  scoped only to these new app registrations.

**One HCP Free organization + one workspace** `entra-nabla-state` in
**Local** execution mode is the single backend for both bootstrap and
the future pilot. Do not create a second local/unlocked state, put
bootstrap resources in Garage, or run two independent roots against
the same HCP state. Terraform code uses `enable_ci_identity_bootstrap`
and `enable_workload_pilot` independently; default both are `false`.
The GitHub workflow keeps CI identity bootstrap enabled for **state
refresh only**; its plan policy blocks *any* bootstrap create, update
or delete. Its workload pilot remains disabled.

Bootstrap procedure, exact CLI and release gates:
[Entra Nabla runbook](../../docs/runbooks/entra-tenant-and-test-user.md).
The GitHub static tests do **not** authenticate or create cloud objects.
