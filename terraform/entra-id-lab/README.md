# Entra ID Free — isolated lab, Azure Blob state

Source of truth: [H16 security runbook](../../docs/security/entra-id-homelab-lab.md).

- Tenant: PERSONAL Entra Free, never employer Entra.
- Backend: one Azure Blob state with native leases; NOT Garage.
- CI: GitHub-hosted OIDC, Graph identity separate from state-storage identity,
  explicit GitHub environment approval and a creation-only plan allowlist.
- Workstation: interactive Azure CLI session authenticated with a registered
  YubiKey FIDO2 passkey; use the *same* blob key as CI.
- Default CI scope: only two application registrations and their Service
  Principals (reader enabled, denied disabled). Groups and memberships remain
  disabled by default to avoid tenant-wide Group.ReadWrite.All permissions.
- No app secrets, Azure RBAC assignments, privileged roles or Graph grants
  are provisioned by this module. Terraform state remains sensitive.

Bootstrap requires an Azure subscription and a **separate secured Blob storage
container** (potential charges). Turn OFF shared account key authentication and
anonymous access, turn ON encryption, versioning and soft delete; grant the
CI storage principal Blob Data Contributor on the container, not subscription.
No state or credential values are checked into this public repository.

Workstation preparation only:

~~~bash
export AGENT_EXECUTION_MODE=workstation
export ENTRA_LAB_TENANT_ID="<PERSONAL-TENANT-GUID>"
export ENTRA_LAB_CONFIRMED=true
az login --tenant "$ENTRA_LAB_TENANT_ID" --allow-no-subscriptions
bash scripts/entra/entra-lab-preflight.sh
cd terraform/entra-id-lab
tofu init -backend-config="storage_account_name=<PRIVATE_STORAGE_ACCOUNT>" \
          -backend-config="container_name=<PRIVATE_CONTAINER>"
tofu fmt -check
tofu validate
tofu plan
# No apply until the reviewed plan, backend permissions and state recovery are proven.
~~~

After `tofu init -backend=false`, review and COMMIT the provider lock
`.terraform.lock.hcl` for reproducible CI `-lockfile=readonly`. It has not
been generated in the disconnected execution environment.

GitHub workflow: [entra-id-lab.yml](../../.github/workflows/entra-id-lab.yml).
Remote plan/apply requires environment variables and identities to be
bootstrapped by the operator first. No GitHub hosted job reaches the homelab.
Static source inspection is not a cloud verification.
