# CrowdSec

This deployment is the **central CrowdSec Security Engine + Local API (LAPI)** for the homelab.
pfSense should run in CrowdSec **Small / remediation-only** mode and consume decisions from this LAPI instead of hosting the Security Engine itself.

## Target architecture

```text
pfSense RFC5424 ──> Alloy UDP/1514 ──> Loki ─┐
                                              ├──> CrowdSec Security Engine + LAPI on TrueNAS
Suricata eve.json ─────────────────────────────┘                  │
                                                  │ tcp/8084, LAN only
                                                  ▼
                                     pfSense firewall bouncer
                                                  │
                                                  ▼
                                            PF block tables
```

This removes CrowdSec parsing, scenarios, SQLite/LAPI work and CAPI synchronization from the resource-constrained pfSense appliance while keeping packet remediation at the firewall.

## Current incident mitigation — 2026-10-10

The pfSense read-only diagnostic now proves the problematic path rather than
merely correlating it:

- Security Engine: stopped;
- firewall bouncer: still running;
- `crowdsec_pf_scan_stuck_lines=19213`;
- `max_failed_sent=19899999`;
- `max_attempts=19900000`;
- `max_sigclosed=0`.

That shape is consistent with a live leaky bucket whose input cannot accept the
event, causing the producer to busy-spin. CrowdSec upstream issue
[crowdsecurity/crowdsec#1519](https://github.com/crowdsecurity/crowdsec/issues/1519)
describes the same tight-loop failure mode. The current CrowdSec 1.8.1 source
still contains the non-blocking retry path, so upgrading alone is not treated as
a fix.

The central TrueNAS engine is therefore pinned to CrowdSec 1.8.1 **and**
temporarily removes only the offending Hub scenario through the official
container variable:

```text
DISABLE_SCENARIOS=firewallservices/pf-scan-multi_ports
```

The rest of `crowdsecurity/pfsense` remains installed. Do not re-enable the
pfSense Security Engine while this incident is open merely to regain this one
port-scan scenario.

## Runtime variables

The central engine can bootstrap without a bouncer secret. The optional
`/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` file is loaded only when present, so a
missing secret file no longer makes the entire TrueNAS Compose model invalid.

Before switching pfSense to the remote LAPI, materialize the required
`BOUNCER_KEY_PFSENSE_FIREWALL` from the existing Vaultwarden manifest. Do not
invent or rotate a key merely to make the runtime gate green.

### Bitwarden CLI compatibility preflight (TrueNAS)

As accepted on 2026-10-10, use the checksum-pinned `bw 2026.8.0`
with Vaultwarden `1.37.3`. Bitwarden CLI `2026.9.0` repeatedly
failed `POST /api/accounts/key-management/user-key-id` with 404
(`KeyIdBackfillError`). Do not change Vaultwarden cryptographic data
or treat a previous `unlocked` status as proof that a new unlock works.

```bash
NABLA_BITWARDEN_CLI_VERSION=2026.8.0 \
  bash scripts/truenas/bootstrap-bitwarden-cli.sh --check
bash scripts/truenas/configure-bitwarden-cli-local.sh --check
bash scripts/truenas/diagnose-vaultwarden-cli.sh
bw status | jq '{status,serverUrl}'
# If locked: export BW_SESSION="$(bw unlock --raw)"
python3 scripts/secrets/inventory_vaultwarden.py --app crowdsec
python3 scripts/secrets/inventory_vaultwarden.py \
  --app crowdsec --discover-candidates
```

The observed inventory currently reports `crowdsec: missing`. The optional
candidate discovery command prints only matching **item names** plus whether
an item is in the `expected`, `other` or `unfiled` folder scope; it never
prints item IDs, usernames, URLs, fields, notes, passwords or secret values.
This means the exact `nabla/prod/crowdsec` item is not present in
the manifest's `TrueNAS` folder, **not** that the registered
pfSense bouncer key can be recovered from CrowdSec. Halt secret
rendering until the previously issued key has been sourced and
stored through an approved operator-controlled procedure. The
diagnostic never prints raw Docker logs or credential fields.
On TrueNAS, use the canonical checkout `/mnt/cpool/compose/nabla-compose`;
the workstation uses its own local checkout path.

Run the renderer from the **unprivileged operator shell** that owns the unlocked
`BW_SESSION`; never pass that session through `sudo -E`:

```bash
python scripts/secrets/render_from_bitwarden.py --check
python scripts/secrets/render_from_bitwarden.py \
  --app crowdsec \
  --output-file /tmp/crowdsec.env.secrets

sudo install -d -o root -g root -m 700 \
  /mnt/cpool/secrets/runtime/crowdsec
sudo install -o root -g root -m 600 \
  /tmp/crowdsec.env.secrets \
  /mnt/cpool/secrets/runtime/crowdsec/.env.secrets
rm -f /tmp/crowdsec.env.secrets

sudo bash scripts/truenas/bootstrap-repository-env-files.sh --check crowdsec
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

The repository manifest maps legacy `CROWDSEC_PFSENSE_BOUNCER_KEY` to the
container-facing `BOUNCER_KEY_PFSENSE_FIREWALL`. If Vaultwarden cannot render
that field, stop the cutover: an existing CrowdSec bouncer registration does not
reveal its API key. Rotation is a separate explicit operator transaction and is
never performed by `deploy-crowdsec.sh`.

The same bouncer key must be obtained **directly from Vaultwarden** when
configuring pfSense from the workstation/operator session. Do not `cat`, copy
or SCP the TrueNAS runtime secret to the workstation, and do not grant TrueNAS
SSH/API access to pfSense merely for this migration.

Optional:

```text
CROWDSEC_LAPI_BIND_ADDRESS=172.17.0.24
CROWDSEC_LAPI_PORT=8084
CROWDSEC_METRICS_BIND_ADDRESS=172.17.0.24
CROWDSEC_METRICS_PORT=6060
SURICATA_LOG_DIR=/mnt/cpool/suricata/log
TZ=Europe/Paris
```

The LAPI port must remain reachable from trusted LAN hosts only. Do not publish TCP/8084 through pfSense, Cloudflare Tunnel, HAProxy or any Internet-facing ingress.

## TrueNAS Custom App deployment

The app may be installed before the bouncer secret exists. For the final
pfSense cutover, render `/mnt/cpool/secrets/runtime/crowdsec/.env.secrets` and redeploy it.
Register the missing Custom App with the canonical repository include:

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

Before changing pfSense, use the scoped repository deployer. Its default mode is
read-only. A missing bouncer credential is reported as a **cutover warning**,
not as a blocker for repairing the central TrueNAS runtime. Uncommitted changes
inside the CrowdSec deployment scope remain a blocking precondition.

```bash
sudo bash scripts/truenas/deploy-crowdsec.sh --check
sudo bash scripts/truenas/deploy-crowdsec.sh --apply
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --runtime

# Only after the canonical bouncer credential is materialized:
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
```

`--apply` reconciles **only** the TrueNAS CrowdSec Custom App; it does not
change pfSense, create/delete a bouncer, rotate a key or start the local pfSense
Security Engine. The post-reconcile `--runtime` gate proves the image, scenario
exclusion, LAPI/listeners and Loki acquisition independently from cutover
credentials.

The stronger `--check` gate additionally verifies the canonical bouncer-secret
contract and central `PFSENSE_FIREWALL` registration. It never creates a
bouncer, prints a key, redeploys an App or restarts a service.

After pfSense is switched to the remote LAPI, require the stronger acceptance
gate:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

`--accept` additionally requires that the pfSense firewall bouncer has polled
the central LAPI at least once.

The acceptance is intentionally split by trust boundary:

**On TrueNAS only** — validate the central engine/LAPI/Loki path and observe
`crowdsec_active_decisions`:

```bash
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --check
sudo bash scripts/truenas/diagnose-crowdsec-cutover.sh --accept
```

TrueNAS never SSHes to pfSense.

**On the workstation only** — run the pre-cutover gate over the workstation's
existing SSH path. This checks that pfSense can reach the TrueNAS LAPI without
requiring the bouncer to have switched yet:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --preflight
```

The current legacy URL `http://172.17.0.1:8089` is a warning in preflight
mode. After changing the CrowdSec package settings, use the strict gate:

```bash
bash scripts/workstation/verify-crowdsec-pfsense.sh --accept
```

It verifies that the local Security Engine is absent, the firewall bouncer is
running, its `api_url` targets `http://172.17.0.24:8084`, and the
`crowdsec_blacklists` / `crowdsec6_blacklists` PF tables exist. Empty tables
are a warning by default because they are legitimate when no active ban exists.
When the TrueNAS diagnostic reports `crowdsec_active_decisions>0`, rerun the
workstation helper with `--require-nonempty-table`; an empty PF table then
becomes a failure. Do not run `docker exec` from the workstation.

## Migration from pfSense Large to Small

1. Keep the existing pfSense **firewall bouncer** running, but keep the local
   Security Engine stopped while the backpressure incident remains open.
2. Deploy the central TrueNAS CrowdSec container and verify that
   `firewallservices/pf-scan-multi_ports` is absent while the remaining
   `crowdsecurity/pfsense` collection is installed.
3. Recover the **existing approved** `PFSENSE_FIREWALL` bouncer key from an
   operator-controlled source, store it as the manifest field
   `CROWDSEC_PFSENSE_BOUNCER_KEY`, then materialize it for TrueNAS. If the key
   cannot be recovered, stop: creating/rotating a bouncer key is a separate
   explicitly approved transaction, not part of this cutover.
4. Run `diagnose-crowdsec-cutover.sh --check`; require zero failures before
   touching pfSense.
5. From pfSense, verify that `172.17.0.24:8084` is reachable over the trusted LAN.
6. In **Services > CrowdSec** on pfSense:
   - keep **Remediation Component** enabled;
   - keep **Log Processor** disabled;
   - keep **Local API** disabled;
   - configure the remote LAPI URL as `http://172.17.0.24:8084`;
   - configure the firewall bouncer with the shared key.
7. Save/apply, then run `diagnose-crowdsec-cutover.sh --accept` on TrueNAS and
   require a non-empty `last_pull` for `PFSENSE_FIREWALL`.
8. Confirm that pfSense still receives CrowdSec decisions in its PF table before
   considering the migration complete.

Rollback the **cutover**, not the incident mitigation: restore the previous
bouncer/LAPI settings from the backed-up pfSense configuration, but do not
automatically re-enable the local Security Engine. An emergency local-engine
rollback must first exclude `firewallservices/pf-scan-multi_ports` and must be
observed with bounded CPU/RSS and free-memory headroom.

## Detection sources

The central engine currently acquires:

- pfSense RFC5424 events from the **existing Loki stream**
  `{job="pfsense", device="pfsense"}`, produced by Alloy on TrueNAS;
- Suricata `eve.json` from `${SURICATA_LOG_DIR}`.

This intentionally avoids a second syslog receiver and avoids inventing a
`/mnt/cpool/logs/pfsense/*.log` persistence path that the observability stack
does not create. CrowdSec's Loki datasource starts at the current time, so
post-redeploy acceptance must generate/observe fresh pfSense activity.

The pfSense logs are parsed centrally on TrueNAS after migration, so pfSense
Small mode does not need to run the CrowdSec Log Processor.

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

## pfSense tcsh-safe central LAPI authentication probe

pfSense admin's interactive shell is `tcsh`, not POSIX `sh`.
Never paste shell assignments such as `KEY=$(...)` directly into that
prompt. Use the repository script through an explicitly selected
POSIX interpreter **from the workstation checkout**:

```bash
ssh -T home.albandrieu.com 'sudo /bin/sh -s' < scripts/pfsense/check-central-crowdsec-bouncer.sh
```

The script reads the existing pfSense bouncer key locally, does **not**
print it or include it in curl argv, and reports only
`central_lapi_http=200` (authenticated) or a safe error/status.
It sends one GET for test address `192.0.2.1`, does not change
firewall configuration or PF tables, and may update LAPI polling
metadata. Run only on trusted pfSense via the workstation's authenticated
SSH channel. A 401/403 means the key is not accepted; do not infer
matching credentials from the names `pfsense-firewall` and
`PFSENSE_FIREWALL`.

