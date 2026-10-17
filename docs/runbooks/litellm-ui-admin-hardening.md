# LiteLLM TrueNAS admin UI hardening — staged P1

**Status:** planned, **not applied**. Scope: `http://172.17.0.24:4000/ui/`, externally named `https://litellm.albandrieu.com/`. Never assume the external hostname has an access-control policy merely because it uses HTTPS.

## Threat model

LiteLLM UI reports **Environment-credential login is enabled**. Shared `UI_USERNAME`/`UI_PASSWORD` or a fallback master key may authenticate as a proxy admin. This reduces attribution and creates a high-impact static-secret login path. A compromise of the shared `LITELLM_MASTER_KEY` can administer **both** proxies (confirmed by authenticated `/key/list` through SSH tunnel), so rotate to separate master keys after inventory and dependency review. Do not print secrets or copy them into Git.

## Controlled rollout (manual approval gates)

1. Confirm the live TrueNAS LiteLLM image/version, active config path, database persistence, and that the public hostname is protected by an explicit access policy (Cloudflare Access or equivalent, MFA, allowlist). Restrict UI/admin routes at ingress; avoid public master-key administration. Confirm CSRF/session-cookie settings supported by that release.
2. Back up the LiteLLM database and active configuration; verify restore capability. Keep a tested out-of-band recovery method and do not restart LiteLLM blindly.
3. While the current login still works, create a **separate persistent admin account** through the supported UI flow (or documented API). Use unique credentials from a secret manager. Prefer supported SSO/OIDC + MFA where available. Log out and verify fresh-session login and permissions (models, keys, budgets).
4. Only after the fresh-session acceptance, uncomment `general_settings.disable_env_credential_login: true` in `apps/litellm/config.yaml`, deploy through the normal TrueNAS change procedure, and validate config parsing before restart. Confirm static environment login fails, named admin succeeds, API virtual keys still work, and UI remains behind ingress protection.
5. Roll back the single setting if named-admin login fails; investigate before further changes. Remove or rotate unused UI env credentials **only after** acceptance. Keep master keys separate per proxy.

## Budget migration scope (no historical spend)

The workstation `/key/list` returned **5** keys and TrueNAS **0** at audit time; the endpoints are not a full inventory of team/user budgets. Historical spend, counters, spend logs, key hashes and reset timestamps are **not** to be migrated. Preserve source historical data for audit. Desired state: consumer identity, model allowlist, max budget, budget duration, RPM, TPM, expiry and team assignment; create new scoped TrueNAS virtual keys via authenticated encrypted admin transport, distribute through secret manager, validate one consumer at a time, then revoke retired keys. Never copy master keys into applications.

Use `python3 scripts/workstation/audit-litellm-budget-migration.py --truenas-transport tunnel` as a **read-only authorization preflight**, not as a migration. No Terraform/provider is assumed: prefer a reviewed, idempotent API reconciler with dry-run and explicit apply gate. Avoid resetting live budgets without approved cutover.

## Acceptance after named admin creation (2026-10-17)

Operator confirmed `aa@albandrieu.com` has `proxy_admin`, a separately configured password, and can access models, users and budgets. Operator also confirmed Cloudflare Access on the public hostname. This is not independent proof of the Access policy's MFA, bypass exceptions, or full endpoint coverage.

Git configuration now declares `disable_env_credential_login: true`; **runtime application is not confirmed**. Before deployment, back up database/config, ensure a recovery path and validate the running LiteLLM version accepts the setting. After deployment, verify a fresh named-admin login and failure of the former shared environment login; verify virtual-key API consumers. Never test login by supplying the master key to the public hostname.

Read-only checks from the workstation:

```bash
python3 scripts/workstation/check-litellm-ui-hardening.py
python3 scripts/workstation/check-litellm-ui-hardening.py --probe-public --probe-tunnel
```

The second command requires the optional SSH forward `127.0.0.1:14000 -> 127.0.0.1:4000` for its tunnel check. A redirect to Cloudflare Access is a **positive signal only**, not proof of an adequate Access policy. Review the Cloudflare Zero Trust application policy for identity, MFA, service tokens, bypass rules, and all admin/API paths.

Budget migration remains a separate change: copy policy intent only; **do not transfer historical consumption or reset state**.

## Post-merge runtime validation — PR #258

PR #257 has been merged and the operator restarted the TrueNAS LiteLLM app. Previous check output still says `runtime_setting=not_verified` because the checker observes **declared Git configuration**, Cloudflare Access redirect, and basic process health; none proves the application has loaded the setting or rejects environment credentials.

Run from the workstation with the established SSH forward to TrueNAS:

```bash
python3 scripts/workstation/check-litellm-ui-hardening.py --probe-public --probe-tunnel --probe-tunnel-ui
```

Acceptance must be done in two fresh, independent browser sessions: (1) `aa@albandrieu.com` logs in and can access models/users/budgets; (2) a controlled attempt to use the **old UI environment credential** is rejected, without pasting a master key into a browser. Review proxy logs for errors without disclosing credential material. If the second test unexpectedly succeeds, treat the setting as not applied and inspect TrueNAS **effective mounted config** and LiteLLM version before attempting further hardening. Do **not** automatically rotate the master key: it remains an API administration credential and is potentially shared by both proxies.

Cloudflare Access redirect observed at `/ui/` is a useful outside-in check but does not independently verify all admin endpoints, MFA, or bypass policies. Historical spend migration is explicitly **out of scope**; only future budget policy and scoped key permissions should be reconciled.
