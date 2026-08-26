# Homarr generated desired state

`generated-apps.json` is generated from every tracked `apps/**/compose*.yml` plus `overrides.yaml`.

It is a Nabla desired-state contract, not a private Homarr database export. Reconcile it through Homarr's authenticated API or MCP (`/api/mcp/mcp`; Homarr v2 prefers `/api/mcp`).

Infrastructure cards for TrueNAS, Docker/TrueNAS Apps and pfSense live in `overrides.yaml` because they are not normal Compose application services.

Regenerate with:

```bash
python scripts/generate-service-consumers.py
```
