# Runtime service recovery notes

This note complements `docs/roadmap.md` with short-lived operational evidence from the 2026-09-11 post-reboot stabilization.

## Current priority

1. Suricata restart-loop recovery.
2. Sentry synthetic event regression; the current runtime diagnostic is green.
3. Uptime Kuma / AutoKuma endpoint and migration follow-up.
4. Deferred non-blocking debt: nginx-proxy-manager, OpenArchiver and Paperless-ngx.

## Suricata

The repository-owned Suricata Compose definition uses host networking. On this TrueNAS host the LAN bridge is `br0`; therefore the default capture interface must not assume `eth0`.

Run the read-only diagnostic first:

```bash
sudo bash scripts/truenas/diagnose-suricata.sh
```

Only redeploy after reviewing the effective `SURICATA_OPTIONS`, Docker exit/restart state, recent logs and persistent path permissions.

Acceptance:

- TrueNAS App `suricata` is `RUNNING`;
- container is not restarting;
- `br0` exists and is the intended capture interface;
- Suricata starts without config/interface errors;
- `eve.json` receives fresh events;
- CrowdSec/Alloy consumers can read the expected Suricata log path.

## Sentry

The current post-reboot diagnostic is healthy. Keep the remaining work limited to a synthetic event/project-ingestion proof and regression coverage; do not introduce speculative runtime changes while all specialist checks are green.
