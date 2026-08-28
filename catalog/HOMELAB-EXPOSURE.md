# Homelab presentation and exposure catalog

`nabla-compose` owns the homelab presentation/exposure contract consumed by FastAPI Sample and security-policy dashboards.

- `homelab-services.json` describes internal/public endpoints and presentation metadata.
- `homelab-exposure-overrides.json` records explicit security-policy exceptions and exposure intent.
- `service-topology.json` remains the authoritative dependency graph used to derive service criticality tiers.

Do not maintain a second authoritative copy in `fastapi-sample`. Consumers may cache the remote contract, but changes to endpoint ownership, external exposure, tunnel policy or internal service addresses must originate here.

TrueNAS and Homarr are intentionally distinct:

- TrueNAS management/API: `https://truenas.albandrieu.com:7000` externally, `172.17.0.24:7000` on the host.
- Homarr native app: `http://172.17.0.24:30100/` internally and `https://homarr.albandrieu.com/` externally.
