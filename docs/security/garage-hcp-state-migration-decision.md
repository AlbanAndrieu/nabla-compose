# HCP Terraform Free vs Garage — state migration decision

Date: 2026-11-17. Status: **RECOMMENDATION, NOT_APPLIED**.
Do not migrate existing Garage states as part of H16.

## Non-negotiable safeguards

1. Inventory each `infrastructure/*` unit, state key, provider/tool version,
   consumers of remote outputs, resource count and embedded sensitive values.
   Use metadata-only queries: **never publish a raw state or a plan file**.
2. Before any migration: encrypted independent backup, SHA-256 verification,
   a tested offline restore and an exclusive writer window across workstation,
   agents and CI. Local `flock` from `scripts/infra/terragrunt-safe.sh`
   is **NOT distributed locking**.
3. Evaluate HCP Free **500 managed resource limit per organization** and
   the absence of custom teams/workspace RBAC (only owners). Do not rely on
   owner-scoped HCP API tokens as read-only or least-privilege CI credentials.
4. Separate by trust boundary: high-sensitivity LAN/TrueNAS/Talos,
   public cloud/SaaS, disposable experimental identities. Do not mix all
   states in the one free organization merely to obtain a lock.
5. A backend migration is NOT a resource migration: prohibit destructive
   changes and check `plan` is no-op after switching state backends.
   Keep the original state immutable until verified and documented rollback.

## Initial classification (requires state inspection, not proven)

| Module family | Initial decision | Reason |
| --- | --- | --- |
| `terraform/entra` | HCP Free PILOT | Disposable objects, tiny state, isolated org |
| GitHub governance | DEFER | Security-critical GitHub write authority; RBAC too broad on HCP Free |
| Cloudflare tunnels / Access | DEFER | External exposure, sensitive policy and routing metadata |
| TrueNAS / Garage / Talos | KEEP Garage for now | Private topology, state locality, dependent services |
| Mixed storage/credentials | INVESTIGATE | Secrets and outputs may be serialized despite sensitive markers |

## Next architecture decision

For Garage-backed modules, evaluate a distributed locking coordinator
supported by the chosen backend (or switch to a compatible lock-capable
backend such as PostgreSQL/Consul after testing restore, HA and failure
semantics). Do not add an untested DynamoDB emulation or rely on S3 native
lockfiles where Garage lacks required conditional writes. The existing
single-writer workstation lock remains required until an accepted replacement.

Where security demands **separate read/write CI identity and secretless OIDC
to the state**, an appropriately secured **Azure Blob** container with
Entra OIDC is preferable to HCP Free's owners-only permission model, despite
possible storage costs. Evaluate cost/budget alerts first.

**New P1 evaluation, not a migration:** the [private PostgreSQL `pg` locking POC](opentofu-postgresql-private-locking-poc.md) tests native advisory locks on local loopback / SSH tunnel only. Unlike an external lock service, the `pg` backend would also store the state in PostgreSQL. Do not expose PostgreSQL or change any Garage state as part of this POC.

## Migration acceptance gates

- Evidence: state count, resource counts and backend target documented
- Rollback: immutable encrypted backup and verified restore (same state serial)
- Preflight: no concurrent writer, exact workspace/backend key, no state copying
  to CI artifacts or Git comments
- Migration: a single reviewed `tofu init -migrate-state`/Terragrunt path
  with current provider lock; never `-force-copy` blindly
- Post: `tofu state list` counts and `plan` no-op on exact code SHA, lock
  collision tests, documented credentials and recovery
- Deprecate old writers only after the new state is accepted

Sources:
https://developer.hashicorp.com/terraform/cloud-docs/architectural-details/security-model
https://developer.hashicorp.com/terraform/cloud-docs/overview
https://developer.hashicorp.com/terraform/tutorials/cloud/migrate-remote-s3-backend-hcp-terraform
https://opentofu.org/docs/language/settings/backends/remote/
