# Cloudflare Zero Trust observer contract

This homelab manages its Cloudflare Tunnel and Access posture in the Cloudflare Zero Trust dashboard. The observer is read-only: it must reconcile dashboard/API state with the declared topology, never mutate Cloudflare configuration.

## Canonical dashboard surfaces

For the current account, operators use these dashboard surfaces:

- **Tunnel & Mesh / Cloudflare Tunnel / Public Hostnames**: <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/networks/connectors/cloudflare-tunnels/cloudflared/1d98bede-6fa0-42a8-971c-cd390d74d7f6/edit/public-hostname>
- **Access Applications**: <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/apps>
- **Access reusable Policies**: <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/policies>
- **Access Service Tokens**: <https://dash.cloudflare.com/bdfe00eeee5845782ab91adfbff71ee1/one/access-controls/service-credentials/service-tokens>

The dashboard account ID is not a secret, but API tokens and Service Token secrets must never be logged or committed.

## What an ingress rule means

A Cloudflare Tunnel **ingress rule** is the API representation of the routing entry behind a dashboard Public Hostname. In operator-facing UI and documentation, prefer **Tunnel Public Hostname** and reserve `config.ingress[]` for the Cloudflare API field name.

It answers:

> When Cloudflare receives traffic for this hostname through this Tunnel, which origin service should `cloudflared` contact?

For example, a dashboard Public Hostname can conceptually produce:

```text
2fauth.albandrieu.com
  -> Cloudflare Tunnel 1d98bede-6fa0-42a8-971c-cd390d74d7f6
  -> http://172.17.0.24:<origin-port>
```

The hostname-to-origin mapping is **not** an Access policy. Access decides whether the request is authorized; the Tunnel Public Hostname decides where an authorized request is routed.

For a dashboard-managed Tunnel, Cloudflare reports `config_src=cloudflare`. The public-hostname routes are stored in Cloudflare and are available through:

```text
GET /accounts/{account_id}/cfd_tunnel
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}
GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations
```

The configuration response contains:

```text
result.config.ingress[]
  hostname
  service
  originRequest
```

A local `cloudflared` YAML file is only authoritative for a genuinely locally-managed Tunnel (`config_src=local`). It must not be required to observe this dashboard-managed Tunnel.

## Access API surfaces

The observer also reads the Cloudflare Access objects that correspond to the dashboard:

```text
GET /accounts/{account_id}/access/apps
GET /accounts/{account_id}/access/apps/{app_id}/policies
GET /accounts/{account_id}/access/policies
GET /accounts/{account_id}/access/service_tokens
```

Interpretation:

- **Application**: protected hostname/path and application settings.
- **Application policies**: policies actually attached to that application, including reusable policies.
- **Reusable policies**: account-level policy objects available for assignment.
- **Service Tokens**: machine credentials that can be selected by a `Service Auth` policy.

A machine-to-machine policy normally uses action **Service Auth** and an Include rule selecting the intended Service Token. A Service Token being present in the account does not prove that it is assigned to the application.

## Read permissions and resource scope

The canonical read-only observer API token must be account-scoped to account `bdfe00eeee5845782ab91adfbff71ee1` and needs all read capabilities required by the observer:

- **Cloudflare Tunnel Read** or **Cloudflare One Connector: cloudflared Read**;
- **Access: Apps and Policies Read**;
- **Access: Service Tokens Read** when Service Token inventory correlation is enabled.

Prefer the narrow resource scope **Include → Specific account → bdfe00eeee5845782ab91adfbff71ee1** instead of broad all-account access.

Token validity and resource authorization are separate. A user-owned API token can be active through `/user/tokens/verify` while `/accounts/{account_id}/tokens/verify` returns `401`; that does not invalidate the token. More importantly, Cloudflare Tunnel list endpoints are authorization-aware and can return only the resources visible to the principal. Therefore **HTTP 200 with an empty Tunnel list is not proof that the account has no Tunnels**. A direct lookup of a known Tunnel returning `401 Not authorized` proves insufficient resource visibility/permission for that token.

The same conservative rule applies to Access inventory: a reachable account endpoint returning an empty list must not be converted into a positive claim that no Application, Policy or Service Token exists when live edge evidence or dashboard state proves otherwise.

### Observed diagnosis — 2026-09-12

The current observer credentials were tested from the workstation and the FastAPI container:

```text
/user/tokens/verify                                  -> 200 active
/accounts/{account}/tokens/verify                   -> 401 (user-owned token; informational)
/accounts/{account}/cfd_tunnel                      -> 200, empty
/accounts/{account}/cfd_tunnel/{known_tunnel}       -> 401 Not authorized
/accounts/{account}/cfd_tunnel/{known}/configurations -> 401 Not authorized
/accounts/{account}/access/apps                     -> 200, empty
/accounts/{account}/access/policies                 -> 200, empty
/accounts/{account}/access/service_tokens           -> 200, empty
```

The Account ID matches the Zero Trust dashboard. This isolates the remaining control-plane issue to the API token permissions/resource scope, not DNS, TLS, Account ID or outbound network connectivity.

The live Access proof for `2fauth.albandrieu.com` is healthy when redirects are disabled:

```text
anonymous request   -> HTTP 302 Access challenge/block
Service Token       -> HTTP 200 allowed
```

Therefore the Service Token and its effective Access path work at the edge even while the read-only API observer cannot currently enumerate the control-plane objects.

## Diagnostic

Use the repository diagnostic from workstation, TrueNAS and finally the FastAPI container. For the current Tunnel and 2FAuth hostname:

```bash
python scripts/cloudflare/diagnose-cloudflare-api.py \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname 2fauth.albandrieu.com \
  --access-url https://2fauth.albandrieu.com/
```

The diagnostic performs direct Tunnel lookup as well as list calls. This matters when a list call unexpectedly returns HTTP 200 with `result_count=0`: the known Tunnel UUID distinguishes a genuinely empty inventory from an authorization-filtered list.

The Access edge probe disables redirects. A normal interactive Access challenge is commonly a redirect; following it to a login page would incorrectly turn the first edge response into a final HTTP 200 and could produce a false `access_blocked=false` conclusion.

Expected strong proof for Service Auth is:

```text
anonymous request -> Access blocked/challenged
Service Token request -> allowed
```

If both anonymous and authenticated requests return an unblocked 200, the Service Token has **not** been proven by endpoint behavior. In that case, inspect the Access application/policy inventory and confirm that the application is actually protected.

### TrueNAS shell without mise

`mise` is not required to run the diagnostic. If the Cloudflare variables only exist in shell-compatible `.env.local` / `.env.secrets` files, explicitly export them before invoking Python:

```bash
set -a
[ ! -f .env.local ] || . ./.env.local
[ ! -f .env.secrets ] || . ./.env.secrets
set +a

python3 scripts/cloudflare/diagnose-cloudflare-api.py \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname 2fauth.albandrieu.com \
  --access-url https://2fauth.albandrieu.com/
```

Do not print the environment after sourcing the secrets. The FastAPI container is a separate execution context: its `env_file`/Compose environment must independently contain the canonical observer credentials.

To test exactly what FastAPI sees, execute the current repository script through stdin while passing the same diagnostic arguments:

```bash
docker exec -i fastapi-sample python - \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname 2fauth.albandrieu.com \
  --access-url https://2fauth.albandrieu.com/ \
  < scripts/cloudflare/diagnose-cloudflare-api.py
```

## FastAPI health semantics

Cloudflare evidence is layered:

1. public DNS / HTTP / TLS;
2. Cloudflare edge headers;
3. Tunnel object and `config_src`;
4. Tunnel Public Hostname (`config.ingress[]`) hostname-to-origin mapping;
5. Access application;
6. policies attached to the application;
7. Service Token inventory and Service Auth selection;
8. live anonymous-vs-Service-Token edge probe.

Failure, timeout, authorization filtering or an unexpectedly empty Cloudflare control-plane inventory is a **warning/unknown observation state**, not sufficient on its own to mark the application DOWN or to assert that a Tunnel/Application is absent. Conversely, a reachable HTTP 200 alone does not prove that the declared Access protection is configured correctly.
