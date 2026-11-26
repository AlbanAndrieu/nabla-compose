# Vercel WAF — Bababou (owner: nabla-compose)

**CODED / IMPORT REPORTED, NOT APPLIED** (26 November 2026). This unit declares the Vercel firewall of the existing `nabla-site-bababou` project. The Next.js application, tests and deployments remain in `nabla-site-bababou`. Production has NOT been modified by this PR.

**Incident du 22/11 :** la roadmap [H04](../../docs/roadmap.md) confirme que l'import du WAF a été effectué dans l'état Terraform et que l'apply initial a retourné `payment_required` (règles OWASP managées hors forfait). **Ne pas recommencer l'import** : l'import est attesté par la roadmap, mais l'état Garage n'a pas été consulté dans cette session. Vérifier avec `state list` avant toute modification. Le connecteur Vercel confirme le 26/11 que le WAF de production est inchangé (SQLi/XSS/RCE toujours en `log`, aucune règle de rate limiting).

## Live configuration observed before this PR

- Vercel project: `prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0`; team: `team_3vukFMXCzaUZEyGAqLAGmXaf`.
- WAF enabled; `bot_protection=challenge`; `gen/rce/xss/sqli=log`, not blocked.
- No existing custom rule, IP rule or rate limit.
- Attack status query returned no current anomalies (NOT a WAF false-positive analysis).
- Verified public custom domains: `bababou.com` (redirects to www), `www.bababou.com`, `bababou.albandrieu.com`.
- `*.vercel.app` deployments are protected separately and NOT included in the custom rate-limit rule.

## Desired policy (Hobby-safe default, Enterprise opt-in)

| Control | Desired behavior | Note |
| --- | --- | --- |
| Managed SQLi | `log` by default; `deny` if `enable_owasp_blocking=true` | `deny` requires Enterprise |
| Managed XSS | `log` by default; `deny` if `enable_owasp_blocking=true` | `deny` requires Enterprise |
| Managed RCE | `log` by default; `deny` if `enable_owasp_blocking=true` | `deny` requires Enterprise |
| Generic `gen` | `log`, active | Preserve baseline, false positives first |
| Bot Protection | `challenge`, active | Preserve existing behavior |
| Public rate limiting | **One rule**, `300 requests / 60 s / IP` (fixed-window), `deny` on excess, **without persistent action** | Hobby-compatible in principle; verify provider API/plan |
| WAF | `enabled = true` | Cannot destroy the resource unintentionally |

The single-rule limit also fits Vercel Hobby. Do not add a second rate limit for `/api` while on Hobby. The existing Bababou ZAP jobs throttle to **1 request/second**; the rate limit is intentionally higher, but simultaneous runners and shared NATs can still receive 429.

**Plan/entitlement gate:** the 22/11 `payment_required` already demonstrated OWASP `deny` is not available to this project. `enable_owasp_blocking=false` is intentional and must remain the default. The rate-limit-only plan should leave all OWASP actions unchanged; if Vercel still refuses a full-config update, **STOP** rather than bypass Terraform or modifying billing. OWASP `deny` is NOT claimed as achieved.

## Source of truth and state

- Config: [`main.tf`](main.tf), Vercel provider [`versions.tf`](versions.tf).
- Shared Garage S3 state: [`infrastructure/vercel-waf/terragrunt.hcl`](../../infrastructure/vercel-waf/terragrunt.hcl) → `root.hcl`; state key **`vercel-waf/tfstate.json`**.
- Use **only** `scripts/infra/terragrunt-safe.sh` from one LAN workstation. Garage lacks native distributed S3 locking; that script uses a host-local `flock` and makes state backups before apply. No simultaneous CI or second-workstation writer.
- Secrets: `VERCEL_API_TOKEN` from a secrets manager, plus `GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID` and `GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY`. Do not commit tokens, state files, plan files, request logs or private URLs. Ensure token has read/write WAF project rights.

## Read-only drift guard (new, 26 November 2026)

The Python checker makes only a GET of Vercel's active WAF when given `--live`. It prints a short PASS/FAIL code, never the raw WAF JSON, credentials or request data. It requires `VERCEL_API_TOKEN` as an environment variable (not as a command-line parameter). You may alternatively validate a private redacted JSON snapshot with `--file` or `--stdin`.

```bash
python3 -m unittest discover -s tests -p 'test_vercel_waf_preflight.py' -v
python3 scripts/security/check_vercel_waf.py --phase baseline --live
```

The `baseline` phase proves **no new custom rule**, OWASP `log`, bot `challenge` and the exact project/team. If unexpected rules have appeared, reconcile code/state first. After an independently reviewed and successful *rate-only* apply:

```bash
python3 scripts/security/check_vercel_waf.py --phase rate-only --live
```

The `enforced` phase applies only after Enterprise entitlement and `enable_owasp_blocking=true` have been reviewed and applied:

```bash
python3 scripts/security/check_vercel_waf.py --phase enforced --live
```

All phases are **read-only** and fail closed on policy drift. An `enforced` PASS is not a replacement for testing actual WAF response behavior.

## GitHub Actions static validation (no secrets)

The dedicated `vercel-waf-ci.yml` workflow validates `tofu fmt`, the pinned
Vercel provider schema (`tofu init -backend=false`, `tofu validate`) and the
Python policy and plan-rejection contracts on pull requests. It deliberately does **not** access
Garage, obtain a Vercel API token, import state, create a plan against live
infrastructure or call `apply`. A green workflow is necessary but not
sufficient for production acceptance.

Before any operator apply, compare the imported state, existing WAF rule IDs,
provider output and the exact reviewed plan. A full-config Vercel WAF resource
may re-submit unchanged managed-ruleset fields; if Vercel returns
`payment_required` even for the rate-only change, stop and preserve production
rather than forcing a paid capability or replacing the whole WAF via API.

## Adoption and rollout — already imported on 22/11; do not import again

1. Run the read-only `baseline` guard, inventory the live WAF and verify the operator state belongs to this exact project. If any new human-made rule exists, reconcile the HCL before proceeding.
2. From a single operator workstation with Garage access, verify `terraform`/`tofu`, `terragrunt`, credentials, and state ownership. Execute:

   ```bash
   python3 -m unittest tests.test_vercel_waf_contract -v
   python3 -m unittest discover -s tests -p 'test_vercel_waf_preflight.py' -v
   tofu -chdir=terraform/vercel-waf fmt -check
   tofu -chdir=terraform/vercel-waf init -backend=false -input=false
   tofu -chdir=terraform/vercel-waf validate

   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf init -reconfigure
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf state list
   # Expected: vercel_firewall_config.bababou (already imported on 22/11)
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf plan -no-color
   ```

   `tofu init -backend=false` is **configuration validation only**, not Garage initialization. **Do not run `import` again** when `state list` already shows the firewall resource. State writes must never run on two workstations.

3. Examine the complete plan. With default `enable_owasp_blocking=false`, the ONLY intended change is insertion of **one** non-persistent rate-limit rule on the three custom domains; SQLi/XSS/RCE must remain `log`. With Enterprise approval and `enable_owasp_blocking=true`, a separate future plan may additionally change SQLi/XSS/RCE `log → deny`. **STOP** if bot protection is disabled, generic detection changes, other managed classes are activated, a domain/route or unrelated rule is removed, the provider attempts a resource replacement, or a plan/entitlement requirement is unsupported.
4. **Automated local plan gate (rate-only):** generate a private plan against the
   already-imported Garage state. The checker accepts only an in-place update
   that introduces the **one** approved 300/min/IP rule, while leaving OWASP,
   Bot Protection and every other property unchanged.

   ```bash
   umask 077
   review_dir="$(mktemp -d)"
   trap 'rm -rf -- "$review_dir"' EXIT
   review_plan="$review_dir/bababou-waf.tfplan"

   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf plan \
     -input=false -out="$review_plan"
   (cd infrastructure/vercel-waf && terragrunt show -json "$review_plan") |
     python3 scripts/security/check_vercel_waf_plan.py
   ```

   **STOP** unless the checker returns `WAF_PLAN_ALLOWED`. Its contract is
   intentionally narrow: it does not approve an Enterprise OWASP rollout or
   a provider reconciliation that changes unrelated attributes. `tofu show
   -json` includes sensitive state metadata: **never** publish its output,
   redirect it to Actions logs, or commit the plan. Review the exact
   human-readable plan separately before any apply.

5. Apply **the exact approved saved plan** only after the local gate and human review, from the **same operator shell** (before its `EXIT` cleanup trap runs), with the operator's approval:

   ```bash
   scripts/infra/terragrunt-safe.sh infrastructure/vercel-waf apply "$review_plan"
   ```

   The wrapper backs up Garage state before apply. Never use `Vercel PUT` (whole WAF overwrite) or manual dashboard edits while Terragrunt is authoritative. If the provider requests a paid feature, stop; do not upgrade billing automatically.

## Validation after deployment

1. Run `check_vercel_waf.py --phase rate-only --live` (or `--phase enforced` only on Enterprise after explicit approval). Confirm bot challenge, generic log, firewall enabled and exactly one rate rule `300/60/ip/fixed_window/deny`; capture a redacted version/timestamp.
2. Smoke-test public homepage (`/fr`, `/en`), NRE, documents, PDF print and apex → www. Check preview deployment accessibility (preview auth unaffected), legal content visibility and no unexpected 403/429.
3. Observe real firewall **events**, false positives, requests behind NAT, rate-limit `429` and platform costs. Run low-rate authorized CI/ZAP; a WAF checkpoint is coverage blocked, **not** a passing scan. No high-volume or destructive production validation.
4. Rollback: revert the HCL policy only after reviewing current WAF/state drift, then use a new plan + `terragrunt-safe.sh ... apply`, or use Vercel's WAF audit restore **only as emergency break-glass**, recording drift and reconciling Terraform immediately.
5. Keep the PR draft until exact-SHA `fmt/validate`, contract tests, Garage state inspection, a clean plan and real acceptance are evidenced. `payment_required` is a hard stop, not success. No assertion of DEPLOYED based only on code or a healthy Preview.

Reference documentation:
- https://registry.terraform.io/providers/vercel/vercel/3.15.3/docs/resources/firewall_config
- https://vercel.com/docs/vercel-firewall/vercel-waf/rate-limiting
- https://vercel.com/docs/vercel-firewall/vercel-waf/usage-and-pricing
- https://vercel.com/docs/vercel-firewall/vercel-waf
- https://github.com/AlbanAndrieu/nabla-site-bababou/blob/master/docs/security-zap-waf-remediation.md
