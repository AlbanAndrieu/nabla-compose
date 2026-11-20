# Vercel WAF — Bababou (infrastructure ownership: nabla-compose)

Scope: Vercel project `nabla-site-bababou`, not the Next.js application. This unit manages only its firewall, not the existing project or deployment.

## Observed baseline (21 November 2026)

- Project `prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0` in team `team_3vukFMXCzaUZEyGAqLAGmXaf`.
- Firewall enabled; bot protection **challenge**.
- OWASP generic, RCE, XSS and SQLi **log** (NOT block); remaining OWASP classes inactive.
- No custom rules, IP rules or rate limiting in live configuration.
- API rate limiting is staged **disabled** by default, including after a successful apply. Existing bot protection must not be lost.

## Mandatory import-first procedure

A fresh Terraform state is NOT safe to apply against an already configured WAF. Authenticate using a scoped token through `VERCEL_API_TOKEN`; use the same secure remote state procedure as the existing Compose Terraform units (Garage), without committing credentials or state.

```bash
terraform -chdir=terraform/vercel-waf fmt -check
terraform -chdir=terraform/vercel-waf init
terraform -chdir=terraform/vercel-waf import vercel_firewall_config.bababou \
  team_3vukFMXCzaUZEyGAqLAGmXaf/prj_9eUAYmWQtHFIRKIOBYsumhU3QLU0
terraform -chdir=terraform/vercel-waf plan -out=review.tfplan
terraform -chdir=terraform/vercel-waf show review.tfplan
```

**STOP** if the plan disables firewall/bot protection, changes an OWASP mode unexpectedly, removes existing rules, or changes billing/plan. Import may reveal additional provider-managed defaults; reconcile those in code before applying. The import command is per state/workspace: **never perform it twice into two independent states**. Provision a secured, shared, locked backend first; `review.tfplan` is sensitive and must not be uploaded or committed.

## Activation checklist

1. Confirm the exact routes requiring a limit; avoid global rate limiting of HTML, static assets, `/robots.txt` or public documents. The `/api/` prefix may not cover a bare `/api` route.
2. Verify CI preview requests, ZAP scan requests and any external monitor can operate without IP-based WAF bypass. Prefer low-rate authorized testing over broad IP allowlisting.
3. Review real WAF events and false positives. Enable `enable_api_rate_limit=true` only after a reviewed plan; no production `apply` by the code author.
4. Smoke-test `https://www.bababou.com/`, localized NRE, document publication pages, PDF printing and API endpoints; record WAF rule IDs and rate-limit events.
5. Roll back through the previously reviewed Terraform state/plan after recording changes; do not overwrite WAF config with the REST PUT endpoint.

This staged config is **CODED / NOT VALIDATED / NOT IMPORTED / NOT APPLIED**. There is deliberately no automatic apply workflow. Coordinate ownership with Bababou's app security/DAST roadmap.

References:
- https://registry.terraform.io/providers/vercel/vercel/3.15.3/docs/resources/firewall_config
- https://vercel.com/kb/guide/firewall-terraform-configuration
- https://vercel.com/docs/vercel-firewall/firewall-api
