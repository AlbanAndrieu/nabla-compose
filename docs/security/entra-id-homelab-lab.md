# Entra Nabla : Entra ID Free, HCP Terraform Free, YubiKey and Harden-Runner

Date: 2026-11-17. **CODED only — no cloud apply, no runtime evidence.**

## Decisions and threat model

- Use the **operator-created personal Entra ID tenant** (account and two YubiKeys reported by the operator on 2026-11-22, not independently verified). Never use an employer tenant or a Microsoft personal-account token for tenant administration.
- **HCP Terraform Free** is the new name of Terraform Cloud. A Free workspace
  supports up to 500 managed resources (confirm your current plan), but this
  lab uses HCP for **remote state ONLY** and sets workspace execution mode
  to **Local**: OpenTofu 1.12.5 runs on GitHub-hosted runner and on the
  workstation, not inside HCP. No Azure Blob or Garage backend for this lab.
- The HCP workspace manages state locking and versioning. Both CI and
  workstation MUST use the same HCP organization/workspace; do not create a
  second state.
- **Free security limitation:** regular HCP Terraform Free organizations have
  ONLY the owners team, no custom teams or fine-grained workspace RBAC. The
  CI HCP token is therefore **organization-owner-equivalent** even in the plan
  workflow: it is NOT genuinely read-only. Provision a **dedicated HCP Free
  organization containing only this disposable Entra Nabla workspace**; NEVER
  put TrueNAS, Cloudflare, GitHub governance or other sensitive states there.
  Rotate/revoke tokens; treat GitHub plan/apply environment protection as an
  application safeguard, NOT an HCP permission boundary.
- If the security requirement is **true read-only plan vs write-only apply**
  state access without permanent HCP tokens, prefer a minimal Azure Blob
  account with **Entra OIDC + container-scoped RBAC**, accepting a small
  nonzero potential bill, or a paid HCP tier with custom RBAC. The free
  alternative explicitly trades away this isolation.
- CI uses **GitHub OIDC → Entra** for provider authentication, with distinct
  plan/apply application identities scoped to lab-owned objects. Workstation
  login is interactive in a trusted browser using a registered YubiKey FIDO2 passkey (the primary key preferred, the second independently tested for recovery). The Entra passkey is distinct from the YubiKey SSH-FIDO2 signing credential for Terraform approval.
- Entra Graph application permission `Application.ReadWrite.OwnedBy` is
  sensitive: never make the CI service principal owner of privileged company
  apps. Tenant-wide group writes remain disabled in CI.
- PRs run only offline validation: `zizmor`, OpenTofu formatting, negative
  Python tests. Apply is **manual and signature-gated** from `master` only.
  No self-hosted runner linked to TrueNAS. No plan/state binaries in artifacts.

## Existing Nabla account : two YubiKeys and authentication boundaries

The operator reports an existing personal Microsoft/Azure account, a
personal Entra tenant and **two enrolled YubiKeys** (2026-11-22).
This is **operator-supplied information, not an observed Microsoft session**.
The tenant ID and initial domain are used as **private configuration inputs**
on the workstation and as protected GitHub environment variables, not committed
to this public repository. The personal email address, access tokens, passkey
metadata, private keys, PIN/PUK, recovery codes and YubiKey serials must never
be published.

**Interactive access**: use the tenant-specific browser sign-in flow
`az login --tenant "$ENTRA_NABLA_TENANT_ID" --allow-no-subscriptions`,
then explicitly select the physical FIDO2 security key. Test both YubiKeys,
one at a time, in the *actual Entra directory administrator identity*.
Passkeys enrolled in the underlying **personal Microsoft account** do not
automatically prove registration under the Entra workforce identity:
check [Security info](https://mysignins.microsoft.com/security-info) within
the intended tenant before claiming acceptance. Keep Security Defaults
enabled. Requiring a strictly phishing-resistant FIDO2 authentication strength
through Conditional Access needs Entra ID **P1**; do not claim this enforcement
in Entra Free.

**Unattended CI** cannot touch a physical YubiKey. It uses two distinct
GitHub OIDC-federated applications, `entra-nabla-plan` and
`entra-nabla-apply`, without static client secrets. Their GitHub environment
names MUST match these strings exactly. The `apply` additionally requires
a separate SSH-FIDO2 YubiKey signature of a sanitized plan manifest;
this is a human approval, **not** an Entra passkey sign-in.

External sources:
- https://learn.microsoft.com/en-us/entra/identity/authentication/how-to-register-passkey-with-security-key
- https://learn.microsoft.com/en-us/entra/fundamentals/security-defaults
- https://learn.microsoft.com/en-us/entra/identity/authentication/concept-authentication-strength-advanced-options
- https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively

## Manual Azure Free → personal Entra tenant onboarding (22 Nov 2026)

**Operator-only; this IaC PR does not create Microsoft accounts or tenants.**

1. **Already completed as reported**: [Microsoft Azure Free signup](https://azure.microsoft.com/free/)
   with a **personal** Microsoft identity (never the employer tenant).
   Complete identity/payment verification required by Microsoft. Do not
   provision paid Azure resources just to test Microsoft Graph.
2. The **Azure Free trial** and **Entra ID Free directory edition** are
   different: Azure trial credit lasts up to 30 days, and Azure may
   disable services afterward unless the account is converted to pay-as-you-go.
   Such conversion can create bills; explicitly assess it before agreeing.
   Entra ID Free does **not** grant Conditional Access P1/P2 features.
3. In [Entra admin center](https://entra.microsoft.com/), select the
   personal **Workforce** directory, never an External ID trial, and record
   only the non-secret **Directory (tenant) ID** and initial
   `*.onmicrosoft.com` domain. Protect the Global Administrator with
   phishing-resistant MFA and separate recovery.
4. Microsoft now restricts **additional** workforce-tenant creation for
   free/trial customers: if the Create tenant option is blocked, do not
   assume this is an application/IaC bug or try to create a tenant inside
   an employer's paid subscription. The original Azure Free onboarding
   supplies the directory for this lab.
5. On a trusted workstation only, read-only inventory:
   ```bash
   export ENTRA_NABLA_TENANT_ID="<personal-tenant-guid>"
   az login --tenant "$ENTRA_NABLA_TENANT_ID" --allow-no-subscriptions
   az account tenant list --output table
   ```
   Verify the selected directory before invoking any Graph or OpenTofu
   write. No passwords, access tokens, card details or recovery keys in
   issues, pull requests or conversation logs.
6. Only after verifying the tenant, create **separate app registrations**
   for the GitHub plan and apply jobs, respectively, with federation
   subjects:
   `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-plan`
   and
   `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-apply`.
   Use issuer `https://token.actions.githubusercontent.com`, audience
   `api://AzureADTokenExchange`; **no client secret**. Review Graph
   least-privilege permissions and lab object ownership before admin
   consent; no group/user management via CI by default.
7. Independently create a dedicated HCP Terraform Free organization with
   **exactly one workspace in Local execution mode**, for this disposable
   Entra pilot only. The owner-equivalent HCP token must not be confused
   with a read-only credential. Keep `ENTRA_NABLA_APPLY_ENABLED` unset
   until the negative security tests and YubiKey signature are accepted.

References:
[Microsoft account creation prerequisites](https://learn.microsoft.com/en-us/entra/fundamentals/create-new-tenant),
[Microsoft Entra licensing](https://learn.microsoft.com/en-us/entra/fundamentals/licensing),
[Azure Free trial terms](https://azure.microsoft.com/en-us/pricing/purchase-options/azure-account),
[GitHub OIDC workload identity federation](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation-create-trust).

## Bootstrap checklist (not done by this PR)

1. Create a **dedicated HCP Terraform Free organization containing exactly
   one disposable Entra Nabla workspace** in **Local** execution mode.
   HCP Free does not support custom team/workspace RBAC. Configure the
   HCP owner-scoped token in GitHub environment secret `HCP_TF_TOKEN`
   only for this isolated organization; any separate plan/apply tokens are
   still equally privileged in HCP. Rotate them and keep no other states
   in this organization.
2. In Entra personal tenant create plan and apply Graph Service Principals
   with correct owner/Graph permissions, admin consent, and federated
   GitHub OIDC identities for
   `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-plan` and
   `repo:AlbanAndrieu/nabla-compose:environment:entra-nabla-apply`.
   No client secrets and no company tenant permission.
3. GitHub environment variables for both:
   `ENTRA_NABLA_TENANT_ID`, `ENTRA_GRAPH_CLIENT_ID`,
   `HCP_TF_ORGANIZATION`, `HCP_TF_WORKSPACE`.
   Set the apply environment variable `ENTRA_NABLA_APPLY_ENABLED=true`
   only after security acceptance. Set
   `ENTRA_APPROVAL_ALLOWED_SIGNER` as a **repository-level GitHub Actions
   variable** (public data), one single-line OpenSSH allowed-signers entry:
   `entra-operator sk-ssh-ed25519@openssh.com AAAA...`, using the actual
   YubiKey SSH-FIDO2 **PUBLIC** key. This repository-level variable is
   mandatory because `approval_gate` runs **before** a protected GitHub
   environment is entered; an environment-only variable cannot be read
   there. Do not override it with a different environment value. Never
   upload the private key or a PIN.
4. Restrict GitHub environments to `master`, configure reviewers (where
   available), protect the workflow and authorization policy, disable admin
   bypass. **No assertion of configured protections without UI evidence**.
5. Configure the same HCP workspace on workstation via a locally created
   `.tfbackend` file (outside Git) with `organization` and
   `workspaces { name = "..." }`, and authenticate HCP CLI using an
   independent personal HCP token. No HCP token in dotfiles. The suggested HCP workspace name is `entra-nabla-state` (not yet provisioned).
6. Confirm `tofu init -backend-config=... -lockfile=readonly`, test state
   lock contention, HCP state history/restore, and Graph least privilege.

## Hardware signature: plan → inspect → touch → apply

1. After merge, manually run workflow **operation=plan** on `master`, with
   `expected_sha=<40-char master HEAD>`. It obtains Graph OIDC read-only and
   HCP state, computes a **create-only** plan, checks the allowlist, and
   stores only the sanitized `challenge.json` as a 1-day GitHub artifact.
   Its manifest binds: repository, SHA, tenant, HCP organization/workspace,
   unique plan run ID, nonce, 90-minute expiry, list of action addresses and
   SHA-256 of canonical `resource_changes` including before/after values.
   The raw plan and state are not uploaded.
2. On workstation, download the manifest for that plan run, inspect tenant,
   object names and SHA. Sign its exact bytes with a registered FIDO2 SSH
   YubiKey (touch/PIN as configured):
   `ssh-keygen -Y sign -n nabla-entra-apply -f ~/.ssh/id_ed25519_sk_backup challenge.json`.
   This creates `challenge.json.sig`; it does not expose the private key.
   Never sign arbitrary challenge files or display HCP tokens.
3. Trigger `operation=apply` on the exact same `master` SHA with
   `plan_run_id` and base64 of `challenge.json.sig`. The apply GitHub
   environment must approve and allow the run.
4. GitHub downloads the original immutable challenge artifact, verifies
   the earlier plan run succeeded on the SAME SHA, re-plans using HCP state
   locking, checks the strict allowlist, then checks signature
   (`ssh-keygen -Y verify`), hardware public-key type, nonce/expiry,
   tenant/workspace/run ID and **exact canonical planned resource digest**.
   Any drift, deletion, update, wrong key, wrong identity or expiry fails
   before `tofu apply`. CI applies the SAME saved binary plan verified
   in the job.
5. This is **semantic plan equality**, not a byte-identical cross-run binary
   plan; a changed value in the plan invalidates the approval. Replays may
   be possible in the 90-minute window if the exact same resources are
   recreated, so use short-lived manifest, master pinning, run-ID checks
   and HCP state auditing. There is no global one-time nonce database yet.

## Runner runtime protection — GitHub-hosted only

The workflow uses **StepSecurity Harden-Runner Community** on each job
(`static`, `approval_gate`, and `remote`), pinned to immutable SHA
`05e31511f85b41b11d1cf0ef85d0992719546e2c` (v2.21.0).
**These are ephemeral GitHub-hosted `ubuntu-24.04` runners, NOT Talos
Pods or any self-hosted Kubernetes runner.** The first job step enables
`egress-policy: audit` before checkout; review connections per step,
processes and file writes, then approve the exact destinations needed
for OpenTofu, HCP Terraform, Microsoft Graph, GitHub APIs and provider
downloads. A future PR may change the policy to `block` with a tested
`allowed-endpoints` list. No speculative allowlist is enabled.

Comparison to Falco: Harden-Runner is specialized for ephemeral GitHub Actions,
has built-in network egress auditing/blocking, process/file correlation and
Community features free for public repositories on GitHub-hosted runners.
Falco is a general Linux/eBPF runtime detection engine and is better suited
to **a separate Talos workload security initiative**. We have removed the
Falco actions from the Entra workflow to avoid redundant privileged agents
and runner overhead; **Falco is not deployed on Talos**.

StepSecurity's Community agent sends operational telemetry/metadata to
StepSecurity; evaluate privacy and logs before assigning sensitive cloud
permissions. Free Community does NOT protect self-hosted ARC/Talos runners
(Enterprise licensing would be needed). Deployment and real network evidence
remain **NOT_RUN** until CI is explicitly executed.

Sources:
- https://www.stephane-robert.info/en/docs/github-actions/security/harden-runner/
- https://github.com/step-security/harden-runner
- https://github.com/falcosecurity/falco

## Validation and rollback

No authorization to use company tenant. No cloud apply performed.
CODED != TESTED != DEPLOYED. Execute the offline tests on workstation,
verify `zizmor --offline`, and review the provider lockfile before enabling
apply. Never manually remove HCP state from a failed CI run.
Sources: https://developer.hashicorp.com/terraform/cloud-docs/overview ;
https://opentofu.org/docs/language/settings/backends/remote/ ;
https://docs.zizmor.sh/integrations/ ;
https://github.com/falcosecurity/falco-actions ;
https://man.openbsd.org/ssh-keygen.1 .

## Vault, ZITADEL and SPIRE decision (17 November)

Vault/OpenBao is the preferred secrets, PKI and dynamic PostgreSQL credential
authority. Vault can also be an **OIDC provider**, but lacks the broad end-user
IAM lifecycle, MFA and self-service coverage of ZITADEL; it is not a complete
drop-in replacement. Vault's new SPIFFE JWT-SVID **secrets engine requires
Enterprise license**; do not promise it in the free homelab. Standard
Vault/OpenBao Kubernetes/JWT auth and PKI provide useful identity flows, but
SPIRE remains the preferred independent node/workload attestation mechanism.
A SPIRE server can use Vault PKI as upstream CA without replacing SPIRE.

H16 stays independent of Keycloak. For the next experiments prioritize
Vault/OpenBao Kubernetes auth + PKI, then SPIRE/attestation, then optional
ZITADEL end-user IAM if needed. Never claim that PKI issuance alone attests
a workload's runtime identity.

## HCP migration scope

Only the disposable Entra Nabla state is selected for HCP Free.
[Risk-based migration decision](garage-hcp-state-migration-decision.md)
documents why Garage states must NOT be bulk-migrated before inventory,
state-secret review, cost/resource-count evaluation, verified backups
and backend locking remediation.
