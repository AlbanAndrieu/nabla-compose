# FastAPI Sample — LiteLLM TrueNAS → workstation Qwen

**État : GitOps préparé, secrets/runtime NON PROVISIONNÉS / NON VALIDÉS.**
Concerne `sample` TrueNAS uniquement, PAS le runtime public de
`fastapi-sample.fastapicloud.dev` (pas de chemin LAN privé prouvé).

## Architecture et responsabilités

```text
FastAPI Sample /run (staging TrueNAS)
  DEFAULT_CHAT_MODEL=fastapi-qwen
  LITELLM_URL=http://172.17.0.24:4000
  LITELLM_API_KEY  [sample Virtual Key, scoped fastapi-qwen]
                   ↓
TrueNAS LiteLLM proxy :4000
  model fastapi-qwen -> openai/qwen
  LITELLM_WORKSTATION_API_BASE=http://172.17.0.57:4000/v1
  LITELLM_FASTAPI_WORKSTATION_API_KEY [workstation Virtual Key, scoped qwen]
                   ↓
Workstation LiteLLM proxy :4000
  model qwen -> local GPU inference
```

`apps/litellm/config.yaml` had an example `workstation-qwen`
and an `embedding` route to the workstation; this change **reuses the
architecture**, not the existing general-purpose `LITELLM_IDE_API_KEY`.
Key-scoped authorization is required independently on each proxy.
Do not use the LiteLLM **master key** as `LITELLM_API_KEY`.

## Budget demandé : 10 EUR maximum

LiteLLM virtual keys use **USD** for `max_budget`, and **require a working
database** to enforce spending. Therefore, the provisioner records
`max_budget=8 USD` **lifetime** (`budget_duration=null`, never
auto-reset) for each of two different gatekeepers. This is deliberately
**more restrictive** than the 10 EUR target at ordinary FX rates, not an
exact EUR-based accounting guarantee; FX fluctuations and external
provider costs must still be audited. **Do not add** the two budget figures:
both keys meter the same logical request across two proxy hops.

The TrueNAS `fastapi-qwen` route has *synthetic/internal* token accounting
(`input_cost_per_token=0.000001`, `output_cost_per_token=0.000002`
USD/token) to avoid a free on-prem Qwen bypassing its budget gate. **This
is not a paid model tariff or a bill.** Verify the proxy version
actually attributes nonzero spend and denies over-budget requests.
The upstream proxy may meter different amounts. The stronger bound is
the downstream TrueNAS key plus both model allowlists and rate limits.
A USD budget cannot guarantee a hard EUR-denominated monetary charge
with all FX/provider/pricing scenarios.

Both keys: `rpm_limit=5`, `tpm_limit=15000`,
`max_parallel_requests=1`. Disable access to fallback models for
that key. `enforce_fallback_model_access: true` and an empty explicit
`fastapi-qwen` fallback are declared; **test that they are supported
on the installed LiteLLM version** before enabling. The current
`store_model_in_db: true` can cause YAML/database drift: audit the
effective model list, not only the checked-in YAML.

## Provisionnement contrôlé : deux identités distinctes

Source of truth: `config/fastapi-sample/litellm-key-policy.json`.
`scripts/workstation/provision-fastapi-litellm-keys.py` defaults to
**offline --check**. It refuses output overwrite/symlink, writes keys
only into local operator-owned `0600` files and never prints them.
Do not run it as root.

```bash
# On the workstation (no network calls):
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target workstation --check
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target truenas --check

# Apply requires an operator-owned LiteLLM master credential on the local
# workstation proxy. NEVER place a master key in Git/GHA or a command argument.
# Supply LITELLM_MASTER_KEY privately, then:
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target workstation --apply

# TrueNAS admin traffic needs an SSH local port forward to localhost:14000,
# forwarding to TrueNAS loopback :4000. Only then set
# LITELLM_TRUENAS_MASTER_KEY privately and run:
python3 scripts/workstation/provision-fastapi-litellm-keys.py --target truenas --apply
```

Stop if the key already exists. Inspect/revoke orphan keys in proxy UI
before retrying an ambiguous HTTP failure. Never copy the TrueNAS master
credential through insecure LAN HTTP.

The two generated files are **transitional**:
`~/.local/share/nabla-compose/fastapi-litellm/{workstation,truenas}.key`.
Import separately into the Vaultwarden folder `TrueNAS` using the
manifest-declared items (both fields hidden/custom fields):

| Key / source | Vaultwarden item | Runtime consumer |
| --- | --- | --- |
| workstation key (qwen only) | `nabla/prod/litellm-fastapi-upstream` field `LITELLM_FASTAPI_WORKSTATION_API_KEY` | `/mnt/cpool/secrets/runtime/litellm/.env.secrets` |
| TrueNAS key (fastapi-qwen only) | `nabla/prod/sample-litellm` field `LITELLM_API_KEY` | `/mnt/cpool/secrets/runtime/sample/.env.secrets` |

Use the existing unprivileged `bw` importer and
`scripts/secrets/render_from_bitwarden.py` in `--app` mode.
**Merge the new field into existing env files** rather than overwriting
the entire `sample/.env.secrets` containing DB, pfSense and other
credentials. Review resulting root:root 0600 file ownership and avoid
leaking values in CI, `docker inspect` or shell history. Remove the
operator transitional key files only after Vaultwarden and runtime
materialization are independently verified.

## Gates before deployment

1. **Workstation** : `qwen` exists and accepts a small
   `/v1/chat/completions` request with its dedicated restricted key.
   Wrong model must return 403/400; do not test using a master key.
2. **TrueNAS proxy** : `fastapi-qwen` exists and reaches the upstream
   `qwen` alias. Confirm scoped key cannot request `gpt-4.1`,
   `llama3.2` or fallback. Intentionally break upstream only in a
   safe isolated test, not by disrupting running services.
3. **Budget** : verify both DB connections, `/key/info` shows the
   model list, `max_budget=8`, no reset and enforced spend. Confirm
   nonzero TrueNAS synthetic accounting and 429/403 on a *separate
   tiny-budget disposable test key*, not on the service key.
4. **Secrets** : no key in Git or logs; runtime files 0600, no
   extra proxy-wide admin privileges. Validate `docker compose config`
   without printing raw secrets into the shared session.
5. **Application** : TrueNAS `/run` returns an expected safe
   response via Qwen, supports required function/tool calls and does
   not disclose PII to the workstation. Ensure operator auth before
   exposing `/run` publicly: PR #353 still has a staged
   `OPS_ROUTE_POLICY_STRICT` cutover. Fail closed if key unavailable.
6. **Cloud production** : not connected to LAN. A future
   Cloudflare Access or tunnel route needs its own security design and
   a distinct service token. Do not route the public Cloud app through
   an unauthenticated private HTTP endpoint.

**No actual proxy key, Vaultwarden item or deployment was created from
GitHub.** All runtime checks remain `NOT_RUN` pending authorized LAN access.
