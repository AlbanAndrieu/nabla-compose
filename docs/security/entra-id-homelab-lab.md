# H16 — Entra Free / Talos / ZITADEL / SPIRE lab

2026-11-14. Owner: nabla-compose. P0 CODED; TESTED NOT_RUN;
DEPLOYED NOT_APPLIED; ACCEPTED(runtime) NOT_VERIFIED.

## Decisions
- Use a PERSONAL Entra ID Free tenant, never the company tenant.
- Use OpenTofu/Terragrunt + the existing private Garage backend and
  scripts/infra/terragrunt-safe.sh host-local lock. Single writer only.
- Do not create Azure subscriptions/resources, service-principal passwords,
  Graph permissions, privileged groups, directory roles or public routes.
- Two security groups: readers, operators. Two Service Principals: reader
  enabled, denied disabled. Neither is granted Azure RBAC/Graph API access.
- Existing test-only user accounts may be joined to groups via workstation
  UPN variables; do not create azuread_user.password in Terraform state.
- app_role_assignment_required alone is NOT a universal prohibition on
  client-credentials tokens; tests must check resource-side authorization.

## P0 read-only procedure
1. In a personal tenant, verify your application/group administrator rights.
   Create two test users manually if user-group testing is needed.
2. On workstation: az login --tenant "$ENTRA_LAB_TENANT_ID" --allow-no-subscriptions.
   Set ENTRA_LAB_TENANT_ID, ENTRA_LAB_CONFIRMED=true and
   AGENT_EXECUTION_MODE=workstation; optionally ENTRA_LAB_READER_UPN and
   ENTRA_LAB_OPERATOR_UPN. Never commit these values.
3. Run bash scripts/entra/entra-lab-preflight.sh. Mismatched or missing
   tenant must fail with exit 2; no OpenTofu command runs.
4. Run scripts/infra/terragrunt-safe.sh infrastructure/entra-id-lab init
   then plan. Review tenant, add/change/destroy summary and output
   privacy before authorizing a separate apply.
5. Accept only two groups, two applications, two Service Principals and
   optional test group memberships, with no Azure RBAC or Graph grants.
   The disabled negative-control principal must remain disabled.

## Next phases (NOT deployed)
- P1 Talos: after H01 CSI checks, dedicate a namespace, ServiceAccount and
  workload identity. Prove Kubernetes OIDC discovery/JWKS access by Entra
  with TLS and JWKS rotation, without making the API server or private
  services public. Add federated identity credential with exact
  issuer/subject/audience and negative tests for forged JWT/scope.
- P1 ZITADEL: standalone internal OIDC/M2M sandbox, own database, encrypted
  backup, user flows, PKCE and least-privilege client tests. ZITADEL is
  not a Microsoft Graph or Azure RBAC emulator. No Keycloak dependency.
- P2 SPIRE: install after cluster security acceptance; attested workloads,
  SPIFFE IDs, short-lived X.509/JWT SVIDs and failure/revocation tests.
- P3 Azure Arc pilot (optional): a real Managed Identity requires an Azure
  resource or Arc-enabled machine; check licensing and charges independently.

## Acceptance and rollback
- L1: bash -n scripts/entra/entra-lab-preflight.sh; python -m unittest
  tests/test_entra_id_lab_contract.py; tofu fmt -check, then validate with
  a locally initialized provider.
- L2/L3: workstation quality gates at the committed HEAD; cloud and
  LAN checks NOT_RUN until connected and authorized.
- Reject any unintended change to existing tenant resources. Back up
  Garage state and keep a recovery admin. Remove only lab-owned resources
  during controlled rollback. Do not print tokens or credentials.

Dependencies: [Talos CSI](../kubernetes-csi-preflight.md),
[H16 PKI/OAuth](postgresql-fips-tls13-vault-oauth-20261110.md),
[workflow](../agent-execution-playbook.md).
External references: https://registry.terraform.io/providers/hashicorp/azuread/latest/docs ;
https://learn.microsoft.com/entra/workload-id/workload-identity-federation ;
https://spiffe.io/ ; https://zitadel.com/docs/guides/manage/terraform-provider .
