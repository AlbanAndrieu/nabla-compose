# Vercel WAF — Bababou (owner: nabla-compose)

**CODED / NOT APPLIED** (21 November 2026). This unit owns the Vercel firewall of the existing `nabla-site-bababou` project. The Next.js application, tests and deployments remain in `nabla-site-bababou`. Production has NOT been modified by this PR.

## Live configuration observed before this PR

- Vercel project: `prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0`; team: `team_3vukFMXCzaUZEyGAqLAGmXaf`.
- WAF enabled; `bot_protection=challenge`; `gen/rce/xss/sqli=log`, not blocked.
- No existing custom rule, IP rule or rate limit.
- Attack status query returned no current anomalies (NOT a WAF false-positive analysis).
- Verified public custom domains: `bababou.com` (redirects to www), `www.bababou.com`, `bababou.albandrieu.com`.
- `*.vercel.app` deployments are protected separately and NOT included in the custom rate-limit rule.

## Desired policy (pending import / plan / apply)

| Control | Desired behavior | Note |
| --- | --- | --- |
| Managed SQLi | `deny`, active | Change from `log` |
| Managed XSS | `deny`, active | Change from `log` |
| Managed RCE | `deny`, active | Change from `log` |
| Generic `gen` | `log`, active | Preserve baseline, false positives first |
| Bot Protection | `challenge`, active | Preserve existing behavior |
| Public rate limiting | **One rule**, `300 requests / 60 s / IP` (fixed-window), `deny` for **1 minute** | Only the three verified public custom domains, not Preview |
| WAF | `enabled = true` | Cannot destroy the resource unintentionally |

The single-rule limit also fits Vercel Hobby. Do not add a second rate limit for `/api` while on Hobby. The existing Bababou ZAP jobs throttle to **1 request/second**; the rate limit is intentionally higher, but simultaneous runners and shared NATs can still receive 429.

**Plan/entitlement gate:** Vercel's documentation describes managed OWASP rulesets as Enterprise-only even though the API currently reports active rules in `log` for this project. Do not assume enabling `deny` is licensed or free. Verify the Vercel team plan and an actual provider plan/apply response; stop rather than upgrading the account automatically.

## Source of truth and state

- Config: [`main.tf`](main.tf), Vercel provider [`versions.tf`](versions.tf).
- Shared Garage S3 state: [`infrastructure/vercel-waf/terragrunt.hcl`](../../infrastructure/vercel-waf/terragrunt.hcl) → `root.hcl`; state key **`vercel-waf/tfstate.json`**.
- Use **only** `scripts/infra/terragrunt-safe.sh` from one LAN workstation. Garage lacks native distributed S3 locking; that script uses a host-local `flock` and makes state backups before apply. No simultaneous CI or second-workstation writer.
- Secrets: `VERCEL_API_TOKEN` from a secrets manager, plus `GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID` and `GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY`. Do not commit tokens, state files, plan files, request logs or private URLs. Ensure token has read/write WAF project rights.

## Adoption and rollout — import first, never create a second WAF

1. Inventory current WAF via the Vercel UI/API, recording a **redacted** summary of all existing rules, actions and environments. If any new human-made rule exists, reconcile the HCL before proceeding.
2. From a single operator workstation with Garage access, verify `terraform`/`tofu`, `terragrunt`, credentials, and state ownership. Execute:

   ```bash
   python3 -m unittest tests.test_vercel_waf_contract -v
   tofu -chdir=terraform/vercel-waf fmt -check
   tofu -chdir=terraform/vercel-waf init -backend=false -input=false
   tofu -chdir=terraform/vercel-waf validate

   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf init -reconfigure
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf import \
     vercel_firewall_config.bababou \
     team_3vukFMXCzaUZEyGAqLAGmXaf/prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf plan -no-color
   ```

   `tofu init -backend=false` is **offline configuration validation only**: it is not equivalent to Garage initialization. An import updates state; never run it independently from two workstations or if the resource is already imported.

3. Examine the complete plan. Allowed changes: SQLi/XSS/RCE `log → deny`, insert **one** rate-limit rule scoped to exactly the three intended domains, and explicit `enabled=true`. **STOP** if bot protection is disabled, generic detection changes, other managed classes are activated, a domain/route or unrelated rule is removed, the provider attempts a resource replacement, or a plan/entitlement requirement is unsupported.
4. Apply only with the exact reviewed state on the designated workstation and the operator's approval, through:

   ```bash
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf apply
   ```

   The wrapper backs up Garage state before apply. Never use `Vercel PUT` (whole WAF overwrite) or manual dashboard edits while Terragrunt is authoritative. If the provider requests a paid feature, stop; do not upgrade billing automatically.

## Validation after deployment

1. Re-read Vercel WAF active config: `sqli/xss/rce=deny`, `gen=log`, `bot_protection=challenge`, `firewallEnabled=true`, exactly one rate rule with `300/60/ip/fixed_window/deny`; capture the version and timestamp.
2. Smoke-test public homepage (`/fr`, `/en`), NRE, documents, PDF print and apex → www. Check preview deployment accessibility (preview auth unaffected), legal content visibility and no unexpected 403/429.
3. Observe real firewall **events**, false positives, requests behind NAT, rate-limit `429` and platform costs. Run low-rate authorized CI/ZAP; a WAF checkpoint is coverage blocked, **not** a passing scan. No high-volume or destructive production validation.
4. Rollback: revert the HCL policy only after reviewing current WAF/state drift, then use a new plan + `terragrunt-safe.sh ... apply`, or use Vercel's WAF audit restore **only as emergency break-glass**, recording drift and reconciling Terraform immediately.
5. Keep the PR draft until the exact-SHA `fmt/validate`, contract tests, imported state, plan and production acceptance are evidenced. No assertion of DEPLOYED based only on code or a healthy Preview.

Reference documentation:
- https://registry.terraform.io/providers/vercel/vercel/3.15.3/docs/resources/firewall_config
- https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
- https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing
- https://vercel.com/docs/vercel-firewall/vercel-waf
- https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/security-zap-waf-remediation.md
