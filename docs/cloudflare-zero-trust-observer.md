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

A Cloudflare Tunnel **ingress rule** is the routing entry behind a Public Hostname. It answers:

> When Cloudflare receives traffic for this hostname through this Tunnel, which origin service should `cloudflared` contact?

For example, a dashboard Public Hostname can conceptually produce:

```text
2fauth.albandrieu.com
  -> Cloudflare Tunnel 1d98bede-6fa0-42a8-971c-cd390d74d7f6
  -> http://172.17.0.24:<origin-port>
```

The hostname-to-origin mapping is **not** an Access policy. Access decides whether the request is authorized; Tunnel ingress decides where an authorized request is routed.

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

## Read permissions

The read-only observer API token needs the relevant account-scoped permissions:

- Cloudflare Tunnel Read / Cloudflare One Connector: cloudflared Read;
- Access: Apps and Policies Read;
- Access: Service Tokens Read if Service Token inventory correlation is required.

Token verification and resource authorization are separate. A user-owned API token can be active through `/user/tokens/verify` while `/accounts/{account_id}/tokens/verify` returns 401; that alone does not invalidate the token.

## Diagnostic

Use the repository diagnostic from workstation, TrueNAS and finally the FastAPI container. For the current Tunnel and 2FAuth hostname:

```bash
python scripts/cloudflare/diagnose-cloudflare-api.py \
  --tunnel-id 1d98bede-6fa0-42a8-971c-cd390d74d7f6 \
  --expect-hostname 2fauth.albandrieu.com \
  --access-url https://2fauth.albandrieu.com/
```

The diagnostic performs direct Tunnel lookup as well as list calls. This matters when a list call unexpectedly returns HTTP 200 with `result_count=0`: the known Tunnel UUID lets us distinguish an account/token-scope mismatch from a list/filter/API issue.

The Access edge probe disables redirects. A normal interactive Access challenge is commonly a redirect; following it to a login page would incorrectly turn the first edge response into a final HTTP 200 and could produce a false `access_blocked=false` conclusion.

Expected strong proof for Service Auth is:

```text
anonymous request -> Access blocked/challenged
Service Token request -> allowed
```

If both anonymous and authenticated requests return an unblocked 200, the Service Token has **not** been proven by endpoint behavior. In that case, inspect the Access application/policy inventory and confirm that the application is actually protected.

## FastAPI health semantics

Cloudflare evidence is layered:

1. public DNS / HTTP / TLS;
2. Cloudflare edge headers;
3. Tunnel object and `config_src`;
4. Tunnel `config.ingress[]` hostname-to-origin mapping;
5. Access application;
6. policies attached to the application;
7. Service Token inventory and Service Auth selection;
8. live anonymous-vs-Service-Token edge probe.

Failure or timeout of the Cloudflare control-plane API is a **warning/unknown observation state**, not sufficient on its own to mark the application DOWN. Conversely, a reachable HTTP 200 does not prove that the declared Access protection is configured correctly.
