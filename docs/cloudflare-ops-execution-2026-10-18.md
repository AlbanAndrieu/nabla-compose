# Cloudflare DNS / Tunnel private ops — IaC execution handoff

Created in PR #263: [Cloudflare module](../terraform/cloudflare-ops/README.md).
This is **source-only**, not a Cloudflare activation or a proven Access configuration.

Execution order: **P0 sanitize public site → G1 FastAPI origin JWT → G2 read-only
inventory and provider import/plan → G3 Access owner/MFA proven → G4 dedicated
Tunnel TLS ingress → G5 proxied DNS and negative/positive smoke**.

`infrastructure/cloudflare-ops/terragrunt.hcl` inherits the existing Garage
state, but remains all-false to guarantee no changes when evaluated in
read-only preparation. Remote state must remain private, encrypted and
serialized (Garage lacks native lockfile semantics).

DefectDojo is deliberately **excluded** from the operator public hostname.
Its only approved API route is private TrueNAS LAN,
`http://172.17.0.24:31085/api/v2/`, with the existing import guard.
No third-party hosted CI runner should upload to this private endpoint.

Security acceptance: owner exact-match, verified MFA and independent JWT
validation; no public `*.int`, origin admin/metrics, bypass NAT, Access login
loop misread as healthy or Terraform unmanaged shared Tunnel overwrite.
