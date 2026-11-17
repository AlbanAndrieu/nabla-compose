# Entra ID Free lab — HCP Free remote state (local OpenTofu execution)

Source of truth: [H16 security runbook](../../docs/security/entra-id-homelab-lab.md).

- `backend "remote"` in [backend.tofu](backend.tofu), with the HCP workspace
  explicitly configured for **Local** execution. No Azure Blob/Garage state.
- GitHub Actions `validate|plan|apply` with hardware SSHSIG confirmation:
  [workflow](../../.github/workflows/entra-id-lab.yml).
- Signed challenge script: [approval.py](../../scripts/entra/approval.py).
- Default CI disables Entra group and user writes to minimize Graph permissions.
- `.terraform.lock.hcl` is committed and must not be relaxed in CI.

Run `tofu init -backend-config=/path/outside/repo/entra.hcp.tfbackend`
on the workstation only after setting up an HCP token and verifying that
the workspace is Local. Then run `tofu validate` and `tofu plan`.
Never run `tofu apply` locally without an explicit reviewed plan: the CI
hardware authorization only protects the **CI workflow**, not users who hold
independent Graph and HCP state write permissions. No secrets in Git.

The previous `infrastructure/entra-id-lab/terragrunt.hcl` Garage path was
removed. HCP workspace creation and state migration are NOT_APPLIED.
