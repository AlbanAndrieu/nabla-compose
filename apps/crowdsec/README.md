# CrowdSec

This deployment is the **central CrowdSec Security Engine + Local API (LAPI)** for the homelab.
pfSense should run in CrowdSec **Small / remediation-only** mode and consume decisions from this LAPI instead of hosting the Security Engine itself.

## Target architecture

```text
pfSense filter/nginx/auth logs ─┐
                               ├──> CrowdSec Security Engine + LAPI on TrueNAS
Suricata eve.json ──────────────┘                  │
                                                  │ tcp/8084, LAN only
                                                  ▼
                                     pfSense firewall bouncer
                                                  │
                                                  ▼
                                            PF block tables
```

This removes CrowdSec parsing, scenarios, SQLite/LAPI work and CAPI synchronization from the resource-constrained pfSense appliance while keeping packet remediation at the firewall.

## Runtime variables

Required runtime secret in `/mnt/cpool/crowdsec/.env.secrets`:

```text
BOUNCER_KEY_PFSENSE_FIREWALL=<random secret shared with the pfSense firewall bouncer>
```

The file must be mode `0600`. The repository Vaultwarden manifest imports the
legacy `CROWDSEC_PFSENSE_BOUNCER_KEY` name and renders the container-facing
`BOUNCER_KEY_PFSENSE_FIREWALL` variable, so Compose parsing does not depend on
a secret exported in the TrueNAS middleware environment.

Optional:

```text
CROWDSEC_LAPI_BIND_ADDRESS=172.17.0.24
CROWDSEC_LAPI_PORT=8084
CROWDSEC_METRICS_BIND_ADDRESS=172.17.0.24
CROWDSEC_METRICS_PORT=6060
PFSENSE_LOG_DIR=/mnt/cpool/logs/pfsense
SURICATA_LOG_DIR=/mnt/cpool/suricata/log
TZ=Europe/Paris
```

The LAPI port must remain reachable from trusted LAN hosts only. Do not publish TCP/8084 through pfSense, Cloudflare Tunnel, HAProxy or any Internet-facing ingress.

## TrueNAS Custom App deployment

Render or create `/mnt/cpool/crowdsec/.env.secrets` before installation, then
register the missing Custom App with the canonical repository include:

```bash
CROWDSEC_WRAPPER="$(
  cat <<'EOF'
include:
  - /mnt/cpool/compose/nabla-compose/apps/crowdsec/compose.yml
EOF
)"

sudo midclt call -j app.create "$(
  jq -cn \
    --arg compose "${CROWDSEC_WRAPPER}" \
    '{
      app_name: "crowdsec",
      custom_app: true,
      custom_compose_config_string: $compose
    }'
)"
```

Use `app.redeploy crowdsec` only after `app.query` confirms the app exists.

## Migration from pfSense Large to Small

1. Keep the existing pfSense CrowdSec installation running while this container is deployed and validated.
2. Generate a new strong `BOUNCER_KEY_PFSENSE_FIREWALL` and configure it in the TrueNAS application environment.
3. Start this CrowdSec container and verify:

   ```sh
   docker exec crowdsec cscli lapi status
   docker exec crowdsec cscli metrics
   docker exec crowdsec cscli bouncers list
   ```

4. From pfSense, verify that `172.17.0.24:8084` is reachable over the trusted LAN.
5. In **Services > CrowdSec** on pfSense:
   - keep **Remediation Component** enabled;
   - disable **Log Processor**;
   - disable **Local API**;
   - configure the remote LAPI URL as `http://172.17.0.24:8084`;
   - configure the firewall bouncer with the shared key.
6. Save/apply and verify on the central LAPI that the pfSense bouncer is valid and polling.
7. Confirm that pfSense still receives CrowdSec decisions in its PF table before considering the migration complete.

Rollback is simply to re-enable the pfSense Log Processor and Local API using the previously backed-up pfSense configuration.

## Detection sources

The central engine currently acquires:

- pfSense syslog files from `${PFSENSE_LOG_DIR}`;
- Suricata `eve.json` from `${SURICATA_LOG_DIR}`.

The pfSense logs are intentionally parsed on TrueNAS after migration, so pfSense Small mode does not need to run the CrowdSec Log Processor.

## Motivation and current pfSense evidence

Before migration, pfSense CrowdSec was the dominant CPU consumer. `filter.log` generated a very high parse workload compared with useful events, and `firewallservices/pf-scan-multi_ports` repeatedly reported event-delivery backpressure with millions of failed send attempts. The firewall bouncer itself remained healthy and inexpensive, so the remediation component should stay on pfSense while the Security Engine/LAPI moves here.

## Validation after cutover

On TrueNAS:

```sh
docker exec crowdsec cscli metrics
docker exec crowdsec cscli decisions list
docker exec crowdsec cscli bouncers list
```

On pfSense:

```sh
pfctl -T show -t crowdsec_blacklists | head
ps auxww | grep -Ei '[c]rowdsec|[c]rowdsec-firewall-bouncer'
uptime
```

Expected result: the firewall bouncer continues polling and populating PF tables, while the `crowdsec` Security Engine process no longer runs locally on pfSense.
