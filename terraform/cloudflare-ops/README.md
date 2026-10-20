# Cloudflare ops — safe OpenTofu DNS + Tunnel skeleton

**State: prepared only. No DNS record, Tunnel, Access app, or public route is
created by this PR.** The default plan has no managed resources. The provider
is pinned to `cloudflare/cloudflare = 5.28.0` (v5 HCL); generate and commit the
provider lock via a reviewed `tofu init -backend=false` before acceptance.

## Ownership and sequence

```text
albanandrieu.com (public sanitized site on Vercel)
ops.albandrieu.com (protected operator-only host)
    -> Cloudflare Access [deny non-owner + verified MFA]
    -> dedicated Cloudflare Tunnel (NOT shared tunnel)
    -> TLS-verified private TrueNAS FastAPI vhost
    -> application-side Access JWT validation + operator identity allowlist
```

- This module **does not manage Access policy yet**. It requires the application
  and policy to be inspected, imported and tested before either ingress or DNS
  can be enabled. Do not set a `*_verified` flag based on a document alone.
- No token in versioned files: use `CLOUDFLARE_API_TOKEN` from root-protected
  secret materialization. Separate IaC write credentials from Access Service Tokens.
- Existing TrueNAS `cloudflared` routes remain untouched. The provider owns the
  **entire** Cloudflare remote tunnel ingress, so NEVER point this configuration
  at the shared homelab tunnel.
- Origin URL must be HTTPS with valid TLS and **must not** expose metrics, Docker,
  TrueNAS admin or pfSense API. Current FastAPI `:8091` HTTP is *not* an
  acceptable verified TLS origin for publication.
- DNS is a proxied CNAME to `<dedicated-id>.cfargotunnel.com`. `prevent_destroy`
  blocks accidental deletion; explicit review is required even for planned updates.
  Creating DNS with `publish_ops_dns=true` while preconditions are false fails.
- Trust checks must cover anonymous 401/403, other identity 403, owner 200,
  origin-direct 401/403, expired/wrong-audience JWT, Access/Tunnel failure and
  cached public exports. Keep rollback as remove/disable the dedicated route,
  **not** weakening FastAPI authorization.

## Import-first and plan-only

1. Read-only inventory: zone, account, existing Access applications/policies,
   tunnel IDs, public DNS, pfSense NAT, HAProxy, TrueNAS ingress. Establish whether
   `nabla-ops` already exists as a **dedicated** tunnel. Verify Cloudflare's
   resource import syntax using provider v5.28.0 documentation.
2. On a trusted operator workstation with encrypted Garage remote state and
   external serialization, set only *identifiers* via approved environment
   variables and keep `CLOUDFLARE_API_TOKEN` in the private process boundary.
3. With the dedicated tunnel already created and `manage_dedicated_tunnel=true`,
   import `cloudflare_zero_trust_tunnel_cloudflared.ops[0]` using
   `<account_id>/<tunnel_id>` **before** planning. Never import a shared tunnel.
4. If an ops ingress config or DNS record already exists, import its exact
   resource ID before enabling its corresponding management flag; do not create
   competing ownership. Compare the existing ingress array to the two rules in
   `main.tofu` and require **zero unrelated routes**.
5. Generate an encrypted private plan, redact it for review; never run `apply`
   from GitHub-hosted CI. Review provider schema, origin certificate, SecretRef,
   read-only service tokens, state access and operational rollback.
6. First accept Access/JWT, then enable dedicated ingress, then DNS. Rerun
   anonymous/other/owner/downtime cases and never claim a service is healthy from
   an Access login redirect.

CI validation (no credentials, network to private services or backend):
`tofu fmt -check -diff -recursive terraform/cloudflare-ops`,
`tofu init -backend=false -input=false`, `tofu validate`.

Official references:
- https://developers.cloudflare.com/tunnel/guides/terraform/
- https://registry.terraform.io/providers/cloudflare/cloudflare/5.28.0/docs/resources/dns_record
- https://registry.terraform.io/providers/cloudflare/cloudflare/5.28.0/docs/resources/zero_trust_tunnel_cloudflared
- https://registry.terraform.io/providers/cloudflare/cloudflare/5.28.0/docs/resources/zero_trust_tunnel_cloudflared_config
- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/
