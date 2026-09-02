# Homelab presentation and exposure catalog

`nabla-compose` owns the homelab presentation/exposure contract consumed by FastAPI Sample and security-policy dashboards.

- `homelab-services.json` describes internal/public endpoints and presentation metadata.
- `homelab-exposure-overrides.json` records explicit security-policy exceptions and exposure intent.
- `service-topology.json` remains the authoritative dependency graph used to derive service criticality tiers.

Do not maintain a second authoritative copy in `fastapi-sample`. Consumers may cache the remote contract, but changes to endpoint ownership, external exposure, tunnel policy or internal service addresses must originate here.

Consumers must merge `homelab-exposure-overrides.json` **after** `homelab-services.json`. For fields present in both files, the override value is authoritative for exposure/security policy. Do not interpret `homelab-services.json` in isolation when deciding whether a service is external, Cloudflare-tunneled, or an accepted direct-exposure exception.

This precedence is currently material for the Home/pfSense `home.albandrieu.com:10443` entry: the base catalog still carries legacy presentation metadata with `tunnelSecure=true`, while the exposure override explicitly sets `tunnelSecure=false` and describes the source-aware direct pfSense REST/API exception required by FastAPI Cloud. Consumers must use the merged result. Normalize the base entry in a future catalog cleanup so presentation metadata and policy no longer disagree.

TrueNAS and Homarr are intentionally distinct:

- TrueNAS management/API: `https://truenas.albandrieu.com:7000` externally, `172.17.0.24:7000` on the host.
- Homarr native app: `http://172.17.0.24:30100/` internally and `https://homarr.albandrieu.com/` externally.
