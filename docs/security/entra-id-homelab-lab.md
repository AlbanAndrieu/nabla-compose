# Entra ID Free : HCP Terraform Free + YubiKey + Falco

Date: 2026-11-17. **CODED only — no cloud apply, no runtime evidence.**

## Decisions and threat model

- Use a **personal Entra ID tenant**, never the employer tenant.
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
  organization containing only this disposable Entra lab workspace**; NEVER
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
  login uses a separate personal Entra user via browser+YubiKey FIDO2.
- Entra Graph application permission `Application.ReadWrite.OwnedBy` is
  sensitive: never make the CI service principal owner of privileged company
  apps. Tenant-wide group writes remain disabled in CI.
- PRs run only offline validation: `zizmor`, OpenTofu formatting, negative
  Python tests. Apply is **manual and signature-gated** from `master` only.
  No self-hosted runner linked to TrueNAS. No plan/state binaries in artifacts.

## Bootstrap checklist (not done by this PR)

1. Create a **dedicated HCP Terraform Free organization containing exactly
   one disposable Entra-lab workspace** in **Local** execution mode.
   HCP Free does not support custom team/workspace RBAC. Configure the
   HCP owner-scoped token in GitHub environment secret `HCP_TF_TOKEN`
   only for this isolated organization; any separate plan/apply tokens are
   still equally privileged in HCP. Rotate them and keep no other states
   in this organization.
2. In Entra personal tenant create plan and apply Graph Service Principals
   with correct owner/Graph permissions, admin consent, and federated
   GitHub OIDC identities for
   `repo:AlbanAndrieu/nabla-compose:environment:entra-lab-plan` and
   `repo:AlbanAndrieu/nabla-compose:environment:entra-lab-apply`.
   No client secrets and no company tenant permission.
3. GitHub environment variables for both:
   `ENTRA_LAB_TENANT_ID`, `ENTRA_GRAPH_CLIENT_ID`,
   `HCP_TF_ORGANIZATION`, `HCP_TF_WORKSPACE`.
   Set the apply environment variable `ENTRA_LAB_APPLY_ENABLED=true`
   only after security acceptance. In that environment register
   `ENTRA_APPROVAL_ALLOWED_SIGNER` as one single-line OpenSSH
   allowed-signers entry: `entra-operator sk-ssh-ed25519@openssh.com AAAA...`
   with the **actual PUBLIC key** from the user's YubiKey SSH-FIDO2 key.
   The private key must never leave the workstation/YubiKey.
4. Restrict GitHub environments to `master`, configure reviewers (where
   available), protect the workflow and authorization policy, disable admin
   bypass. **No assertion of configured protections without UI evidence**.
5. Configure the same HCP workspace on workstation via a locally created
   `.tfbackend` file (outside Git) with `organization` and
   `workspaces { name = "..." }`, and authenticate HCP CLI using an
   independent personal HCP token. No HCP token in dotfiles.
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

Only the disposable Entra lab state is selected for HCP Free.
[Risk-based migration decision](garage-hcp-state-migration-decision.md)
documents why Garage states must NOT be bulk-migrated before inventory,
state-secret review, cost/resource-count evaluation, verified backups
and backend locking remediation.
