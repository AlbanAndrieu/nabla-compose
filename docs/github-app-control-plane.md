# GitHub control plane App: fastapi-sample

Separate from the artifact-only nabla-github-app and release/Renovate Apps.
The pilot is private, actions:read, installed only on fastapi-sample and
nabla-compose. No write permissions, rule bypass or auto-apply. The webhook
is disabled during bootstrap and activation is explicit.

```bash
mkdir -m 700 "$HOME/fastapi-control-app-bootstrap"
python3 scripts/security/bootstrap-github-app-manifest.py --profile control-plane --check
python3 scripts/security/bootstrap-github-app-manifest.py --profile control-plane --serve \
  --output-dir "$HOME/fastapi-control-app-bootstrap"
```

Open http://127.0.0.1:8765/ and confirm on GitHub. Install Selected repositories.
Store the PEM, metadata and distinct generated webhook secret in the private
Vaultwarden item nabla/prod/fastapi-sample-github-app. The secret file is
generated locally; configure the SAME value on GitHub when enabling webhooks.
No PEM in FastAPI web runtime; only webhook secret and verified installation
ID (not App ID) in its environment. Materialization and verification for this
new profile remain operator tasks. Do not reuse the collector's credentials.

## Edge activation (not performed)

Use existing Tunnel host fastapi-sample.albandrieu.com, POST /webhooks/github.
Cloudflare Access cannot interactively authenticate GitHub; the prepared
path-specific bypass is OFF by default. Before opt-in, review the current
zone WAF rules and add a blocking rule limited to this host/path: block
non-POST or source not in GitHub's current `hooks` CIDRs from
https://api.github.com/meta (refresh and handle drift); add rate limiting
within plan capabilities. Never replace the existing zone ruleset or trust
CF-Connecting-IP supplied by a direct LAN client. Reject trailing paths,
query strings as appropriate, verify alternate alias not bypassed. Origin
HMAC is mandatory, independent of the WAF. Configure FastAPI's
GITHUB_WEBHOOK_ENABLED, GITHUB_WEBHOOK_INSTALLATION_ID and
GITHUB_WEBHOOK_SECRET from private runtime material, test LAN first, then
review Cloudflare plan with fastapi_github_webhook_edge_ready=true;
verify negative requests and GitHub signed ping. Enable the GitHub webhook,
URL above and workflow_run event in registration. Test redelivery, Redis
bounded telemetry and owner API. Rollback: disable hook, disable receiver
and revert path bypass; rotate secret if needed. Do not open a WAN port.

## Sensitive operations

Existing .github/workflows/entra.yml verifies an OpenSSH FIDO2 signature over
a plan challenge before privileged apply; it checks master SHA, actor owner,
environment and OIDC identity. A GitHub App actor is not the owner and must
not be substituted without redesign and independent acceptance. FastAPI's
webhook projection is telemetry only, never approval or execution. Future
isolated dispatch worker may mint a repository-scoped actions:write token
for exact allowlisted workflows, after verifying hardware-signed challenge,
nonce, expiry, plan digest, tenant and target. No generic dispatch proxy,
arbitrary shell or Terraform invocation, admin/write permissions or
automatic apply from webhook. Start with validate/plan and preserve manual
apply via the existing owner workflow. Durable audit and one-time approval
consumption are future requirements; Redis projection is not that ledger.

CODED: manifest, bootstrap profile, opt-in path exception. WAF rule,
Vaultwarden runtime profile, App registration/install, live tests, Terraform
plan/apply, dispatcher and approval ledger NOT_RUN or NOT_CODED.
