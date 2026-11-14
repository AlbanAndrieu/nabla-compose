# H16 — Entra ID Free, Terraform, Talos, ZITADEL, SPIRE

Date: 2026-11-14. Owner: nabla-compose. **CODED / remote apply NOT_RUN /
Azure resources NOT_APPLIED / runtime NOT_VERIFIED**.

## Threat model and decisions

- Repository is public; **no self-hosted GitHub runner** connected to TrueNAS,
  Talos or private Garage. Untrusted PRs get only static checks.
- A YubiKey protects a HUMAN interactive sign-in (registered FIDO2 passkey)
  on the workstation, not an automatic GitHub job. No PIV private key, FIDO
  credential, CLI token cache or PAT is exported into GitHub.
- CI authenticates via short-lived GitHub OIDC workload federation, not
  long-lived Azure client secrets or certificates. Microsoft Graph and Blob
  storage require separate Service Principals. Distinguish read-only plan
  identities from write-capable apply identities.
- Single H16 state location: Azure Blob backend with distributed native blob
  lease, encryption, versioning and recovery. No concurrent Garage state.
  The original Terragrunt unit was removed before any cloud apply.
- Azure Blob requires a subscription and may have charges, unlike Entra Free.
  A strict zero-cost alternative is HCP Terraform Free remote execution/state;
  in that model GitHub triggers HCP runs, not direct GitHub `tofu apply`.
- CI initially manages only two disposable apps + Service Principals.
  `enable_group_management=false` avoids Group.ReadWrite.All:
  groups/user membership need a separately reviewed human/bootstrap flow.
  The negative-control Service Principal remains disabled.

## GitHub to Entra federation

Bootstrap separate app identities for Graph **plan** and **apply** and a
separate blob-state identity per environment. For each identity, register
a federated credential with:

- Issuer: `https://token.actions.githubusercontent.com`
- Audience: `api://AzureADTokenExchange`
- Subject for plan: `repo:AlbanAndrieu/nabla-compose:environment:entra-lab-plan`
- Subject for apply: `repo:AlbanAndrieu/nabla-compose:environment:entra-lab-apply`

The apply Graph principal should have no higher privileges than
`Application.ReadWrite.OwnedBy`, and it must own **only disposable lab apps**.
This role permits editing credentials of owned applications; do not assign it
ownership of any privileged application. Do not grant Group.ReadWrite.All,
Directory.ReadWrite.All, Application.ReadWrite.All or Azure Owner/Contributor.
The plan identity gets read-only Graph permissions appropriate for the test.
Admin consent and app ownership bootstrap are **manual tenant-admin actions**.

The Blob storage principal requires `Storage Blob Data Contributor` at
the **state container** scope. Require `use_azuread_auth=true` and OIDC.
Do not use shared-key, SAS or storage account access keys. Configure encryption
at rest, private containers, soft-delete, state versioning and restore tests.
A GitHub-hosted runner needs a reachable Azure Blob endpoint; do not expose
Garage S3 through a new WAN tunnel.

## GitHub environment controls (not automatically configured)

Create `entra-lab-plan` and `entra-lab-apply`. Restrict deployment branches
to `master`. Require approval on apply, disable admin bypass, protect workflow
and source changes using repository rules, and keep `ENTRA_LAB_APPLY_ENABLED`
unset until checks are complete. **A self-approval on a solo account is not
independent control.** GitHub Environment rules could not be read through the
current integration; they are NOT_VERIFIED.

For each environment set non-secret environment variables:

| Variable | Purpose |
| --- | --- |
| `ENTRA_LAB_TENANT_ID` | Personal Entra tenant GUID |
| `ENTRA_STATE_CLIENT_ID` | State-only OIDC principal client ID |
| `ENTRA_GRAPH_CLIENT_ID` | Environment-specific Graph principal |
| `ENTRA_STATE_SUBSCRIPTION_ID` | Subscription containing Blob storage |
| `ENTRA_STATE_ACCOUNT` | Private Blob storage account name |
| `ENTRA_STATE_CONTAINER` | Isolated state container name |
| `ENTRA_LAB_APPLY_ENABLED` | Must be `true` only after approval (apply environment) |

The workflow [entra-id-lab.yml](../../.github/workflows/entra-id-lab.yml)
offers manual `validate`, `plan`, `apply`. For plan/apply require the exact
40-character `master` commit SHA; apply also requires typing
`APPLY_ENTRA_LAB`. The GitHub-hosted job has `id-token:write`, no
write-capable repository token, no static Azure secrets, and refuses unintended
deletions, updates, app grants or group writes. The plan is generated and
applied within the same ephemeral job; no raw state/plan file in artifacts,
PR comments, GitHub cache or logs. Commit `.terraform.lock.hcl` after
workstation provider initialization (read-only provider download) before CI
plan/apply can execute.

## Workstation + YubiKey

Authenticate through browser-based `az login --tenant <PERSONAL_TENANT>`.
Register the YubiKey FIDO2 passkey on the account and verify the method used;
merely inserting a YubiKey does not make an Azure CLI session hardware-bound.
Avoid device-code login if a normal browser sign-in is available, since device
codes are susceptible to phishing. Restrict `~/.azure` access; log out after
work; don't copy CLI tokens into environment, CI logs or Vaultwarden.
The workstation uses interactive user permissions and **the same Azure Blob
backend/key** as CI. Azure Blob leases coordinate concurrent writers, unlike
the previous host-local `flock`.

## Negative acceptance checks

1. Incorrect GitHub branch, actor, expected SHA, confirmation, missing
   identities or missing environment flag: deny before obtaining cloud tokens.
2. Reject `destroy`, `replace`, any `update`, any group/user creation,
   externally named apps, any API grant, and an enabled `denied` principal.
3. Verify least-privilege app ownership and Blob scope, native lease under
   concurrent CI/workstation plans, backup, version history and recovery.
4. Test signed-in admin, reader and denied identities; verify no elevated
   Graph/ARM authorization. A disabled SP's denial is not by itself sufficient
   to prove reader least privilege.
5. Workstation must run `bash scripts/entra/entra-lab-preflight.sh` then
   `tofu init/validate/plan`; CI static checks run without cloud credentials.
6. Before activating apply, independently verify GitHub environment protection,
   real WIF audience/subject, tenant scope, provider lock and backup recovery.

**Unfinished security enhancement:** require a hardware-signed approval
manifest for each plan (YubiKey SSH/FIDO2 signature verified by CI). This
closes the gap between GitHub account approval and physical hardware approval;
it is not yet implemented and must not be claimed as a current control.

## Follow-up P1/P2

- P1 Talos federation: after H01 CSI acceptance, private Kubernetes
  ServiceAccount + publicly reachable OIDC discovery/JWKS with no public API
  server; exact issuer/subject/audience, key rotation, negative JWT tests.
- P1 ZITADEL: isolated internal OIDC/M2M sandbox, private DB, backup, PKCE,
  service identity scopes, no dependency on Keycloak.
- P2 SPIRE: SPIFFE IDs, workload attestation, short-lived JWT/X.509 SVIDs,
  trust domain and revocation tests.
- P3 optional Azure Arc Managed Identity pilot with separate cost review.

Links: [H01 CSI](../kubernetes-csi-preflight.md),
[existing PKI/OAuth plan](postgresql-fips-tls13-vault-oauth-20261110.md),
[AzureAD provider](https://registry.terraform.io/providers/hashicorp/azuread/latest/docs),
[OpenTofu Azure Blob backend](https://opentofu.org/docs/language/settings/backends/azurerm/),
[GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use),
[SPIRE](https://spiffe.io/).
