# Cyberbro provider onboarding roadmap

Cyberbro can run before any premium/external provider credential is configured. The initial Vaultwarden item `nabla/prod/cyberbro` intentionally contains the complete 27-field secret contract with optional values empty. Provider enrollment is a follow-up hardening/enrichment activity, not a prerequisite for deploying the application.

The upstream Cyberbro `.env.sample` is the compatibility reference for provider variable names. This repository keeps provider values in Vaultwarden and renders them into `/mnt/cpool/secrets/runtime/cyberbro/.env.secrets`; no provider credential belongs in Git.

## Operator rules

- Create a dedicated homelab account/application identity where the provider supports it; do not reuse production/customer credentials.
- Prefer free/read-only API plans first and grant the minimum scopes required for reputation/lookup operations.
- Record recovery ownership and account email/tenant metadata in the password manager, but never in tracked repository files.
- Import/update through `scripts/secrets/import_env_to_bitwarden.py --app cyberbro --update-existing`; omitted optional variables preserve their existing Vaultwarden values.
- Render from the unprivileged workstation shell that owns `BW_SESSION`; do not expose the Bitwarden session to `sudo`.
- Validate one provider or one small provider batch at a time, then prove the corresponding Cyberbro engine before continuing.
- Never print the rendered `.env.secrets` file. Validate only mode, mapping count and application behavior.

## Provider/account backlog

| Provider/integration | Vaultwarden/Cyberbro mapping | Account/application action | Status |
| --- | --- | --- | --- |
| AbuseIPDB | `ABUSEIPDB` | Create/reuse dedicated homelab API account/key | pending |
| AlienVault OTX | `ALIENVAULT` | Create/reuse dedicated OTX account/API key | pending |
| Criminal IP | `CRIMINALIP_API_KEY` | Create/reuse dedicated API account/key | pending |
| CrowdStrike Falcon | `CROWDSTRIKE_CLIENT_ID`, `CROWDSTRIKE_CLIENT_SECRET` | Create least-privilege Falcon API client if the homelab tenant permits it | pending |
| DFIR-IRIS | `DFIR_IRIS_API_KEY` | Create dedicated API identity/token on the selected IRIS instance | pending |
| Google Programmable Search | `GOOGLE_CSE_CX`, `GOOGLE_CSE_KEY` | Create/select CSE and API credential restricted to the required API | pending |
| Google Safe Browsing | `GOOGLE_SAFE_BROWSING` | Create restricted API key/project credential | pending |
| Hister | `HISTER_TOKEN` | Create/obtain token for the selected Hister endpoint | pending |
| ipapi | `IPAPI` | Create/reuse dedicated API key | pending |
| IPinfo | `IPINFO` | Create/reuse dedicated API token | pending |
| Microsoft Defender for Endpoint | `MDE_CLIENT_ID`, `MDE_CLIENT_SECRET`, `MDE_TENANT_ID` | Create least-privilege Entra application/service principal only if MDE is available | pending |
| MISP | `MISP_API_KEY` | Create dedicated read-only/lookup automation user/key on the selected MISP instance | pending |
| MISP feedback | `MISP_FEEDBACK_TOKEN` | Create a dedicated feedback token only if the feedback server is enabled | pending |
| OpenCTI | `OPENCTI_API_KEY` | Create dedicated API user/token on the selected OpenCTI instance | pending |
| Ransomware.live | `RANSOMWARE_LIVE_API_KEY` | Create/obtain API token if required by the selected service tier | pending |
| ReversingLabs Analyze | `RL_ANALYZE_API_KEY` | Create dedicated API credential for the configured Analyze/Spectra endpoint | pending |
| Rosti | `ROSTI_API_KEY` | Create/obtain provider API key | pending |
| Shodan | `SHODAN` | Create/reuse dedicated API key | pending |
| Spur | `SPUR_US` | Create/reuse dedicated API token | pending |
| ThreatFox | `THREATFOX` | Create/obtain API token if required by the selected endpoint/tier | pending |
| VirusTotal | `VIRUSTOTAL` | Create/reuse dedicated API key; start with the least-privilege/free tier | pending |
| WebScout | `WEBSCOUT` | Create/obtain provider token if required | pending |
| Outbound proxy | `PROXY_URL` | Configuration only; no provider account. Enable only if an explicit egress proxy is required. | optional |

## Enrollment sequence

1. Deploy Cyberbro with the current empty optional-provider contract and prove the UI/API plus MCP baseline.
2. Start with low-risk external reputation providers such as VirusTotal, AbuseIPDB, AlienVault OTX, Shodan, IPinfo/ipapi and ThreatFox where suitable accounts are available.
3. Add Google CSE/Safe Browsing with project/API-key restrictions.
4. Add self-hosted/platform integrations (DFIR-IRIS, MISP, OpenCTI) only after their own service identities and network paths are accepted.
5. Add enterprise integrations (CrowdStrike Falcon and Microsoft Defender for Endpoint) last, with explicit tenant/app registration and least-privilege review.
6. Add remaining specialist providers in bounded batches, validating Cyberbro engine behavior after every change.
7. After the first complete provider pass, review quotas/rate limits, cache policy and any terms-of-service restrictions before increasing automated use through MCP/LiteLLM.

## Vaultwarden/platform debt discovered during bootstrap

### Transient Cloudflare token-refresh 502

During initial Cyberbro item creation, Vaultwarden accepted the item and returned `200` for the cipher creation, but the Bitwarden CLI later received a transient Cloudflare `502 origin_bad_gateway` while refreshing/synchronizing. The direct TrueNAS origin remained healthy and a later `bw sync` succeeded.

Required follow-up:

- keep post-write sync failures warning-only after a confirmed create/edit;
- never automatically retry `--apply` after an ambiguous post-write failure;
- correlate recurrence with Cloudflare, tunnel/reverse-proxy and Vaultwarden request latency;
- add an alert/diagnostic threshold if authentication/token requests repeatedly approach proxy timeouts.

### Vaultwarden icon-fetch certificate-name mismatch

Vaultwarden logs also showed icon retrieval attempting TLS against raw IP `82.66.4.247` while the presented certificate was valid only for `*.int.albandrieu.com`. This warning is independent of the transient Bitwarden CLI 502.

Required follow-up:

- identify the vault item URI or redirect that causes the raw-IP icon lookup;
- prefer a DNS hostname covered by the intended certificate instead of raw-IP HTTPS;
- if that URI cannot be made certificate-valid, suppress/disable the corresponding icon-fetch path rather than weakening TLS verification;
- keep TLS verification enabled globally.

## Acceptance criteria

Provider onboarding is complete only when:

- every desired provider has an explicitly owned account/application/token or is marked intentionally unused;
- all configured values are present only in Vaultwarden/runtime materialization and remain absent from Git/history/logs;
- each enabled Cyberbro engine has a bounded functional smoke result;
- quotas/rate limits and least-privilege scopes are recorded without secret values;
- Cyberbro still starts successfully when optional providers are unavailable;
- LiteLLM/MCP use remains subject to LiteLLM access policy and does not bypass provider authorization boundaries.
