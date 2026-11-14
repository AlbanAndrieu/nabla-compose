# Entra ID Free P0 — isolated personal tenant

See [security lab runbook](../../docs/security/entra-id-homelab-lab.md).
Real Entra objects, not emulation: two unprivileged groups, two application
registrations and Service Principals (reader enabled; denied disabled).
NO user passwords, API grants, secret credentials, Azure RBAC or directory
roles. Existing TEST users may be linked via workstation-only environment UPNs.

This repo is public. Never store tenant IDs, passwords, client secrets or user
emails in tracked files. State stays in the existing private Garage S3 backend,
with its host-local lock; do not run concurrent writers or public CI apply.

Operator workstation (read-only before an explicitly reviewed apply):

~~~sh
export AGENT_EXECUTION_MODE=workstation
export ENTRA_LAB_TENANT_ID="<PERSONAL-TENANT-GUID>"
export ENTRA_LAB_CONFIRMED=true
az login --tenant "$ENTRA_LAB_TENANT_ID" --allow-no-subscriptions
bash scripts/entra/entra-lab-preflight.sh
scripts/infra/terragrunt-safe.sh infrastructure/entra-id-lab init
scripts/infra/terragrunt-safe.sh infrastructure/entra-id-lab plan
# Authorized only after manual review and state backup:
# scripts/infra/terragrunt-safe.sh infrastructure/entra-id-lab apply
~~~

P0 CODED; local provider validation, plan, apply and runtime NOT_RUN.
