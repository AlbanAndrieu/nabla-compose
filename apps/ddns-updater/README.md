# DDNS Updater

Dynamic DNS updater (`ghcr.io/qdm12/ddns-updater`), deployed as the TrueNAS
Custom App `ddns-updater` from [`compose.yml`](compose.yml) on
`172.17.0.24:30007`.

It replaces two earlier definitions:

- the TrueNAS **catalog** App `ddns-updater` (port `30007`), the runtime until
  the migration decided on 2026-11-06;
- the profile-gated `ddns-updater` service of `apps/traefik/compose.yml`
  (`COMPOSE_PROFILES=legacy-ddns`, port `8000`), never started by default. A
  slow healthcheck there could mark the whole Traefik Custom App `CRASHED`; a
  dedicated App keeps that failure domain isolated.

## Ownership and security

- `favonia/cloudflare-ddns` in the Traefik App remains the owner of the
  reviewed `*.int` exception records (`PUBLIC_INT_CLOUDFLARE_DNS_DOMAINS`).
  Do not configure the same records here: two updaters would fight over them.
- Never add `int.albandrieu.com` records. Private `*.int` routing belongs to
  pfSense/Traefik/Pi-hole.
- `/mnt/cpool/ddns-updater/config.json` holds the provider credentials
  (upstream design). Keep it `0600`, owned by `1000:1000`, and use a Cloudflare
  token scoped to `Zone:DNS:Edit` on the required zone only. The App does not
  read the Traefik secret bundle.
- The UI has no authentication: it is LAN-bound and its public hostname stays
  behind Cloudflare Access (see
  [probe remediation](../../docs/runbooks/2026-11-04-probe-remediation.md)).
- The container runs read-only, without capabilities, with
  `no-new-privileges`; the image is pinned and excluded from Watchtower.

## Migration from the TrueNAS catalog App

Run from the TrueNAS shell in `/mnt/cpool/compose/nabla-compose` once this
change is merged. Never print `config.json` or environment values.

1. **Inspect (read-only)** the catalog App version, state and storage:

   ```bash
   sudo midclt call app.query '[["name","=","ddns-updater"]]' \
     | jq '.[] | {name, state, version, custom_app, human_version}'
   sudo midclt call app.config ddns-updater | jq '.storage // .persistence // keys'
   ```

   If the catalog App keeps its provider configuration in an environment
   variable instead of `config.json`, write it to
   `/mnt/cpool/ddns-updater/config.json` (mode `0600`) during step 3.

2. **Prepare data.** Create `/mnt/cpool/ddns-updater` with the TrueNAS
   **Apps** preset if absent; snapshot the catalog App storage.

3. **Stop and copy.** `sudo midclt call -j app.stop ddns-updater`, copy
   `config.json` (and `updates.json` to keep history) into
   `/mnt/cpool/ddns-updater`, then `chown 1000:1000` and `chmod 600` the files.
   Check that no `int.albandrieu.com` or Traefik-owned `*.int` record is listed.

4. **Remove the catalog App, keep its volumes** (rollback source):

   ```bash
   sudo midclt call -j app.delete ddns-updater \
     '{"remove_images": false, "remove_ix_volumes": false}'
   ```

5. **Create the Custom App** from the include wrapper:

   ```bash
   DDNS_WRAPPER="$(
     cat <<'EOF'
   include:
     - /mnt/cpool/compose/nabla-compose/apps/ddns-updater/compose.yml
   EOF
   )"
   sudo midclt call -j app.create "$(
     jq -cn --arg compose "${DDNS_WRAPPER}" \
       '{app_name: "ddns-updater", custom_app: true, custom_compose_config_string: $compose}'
   )"
   ```

6. **Accept.** The container is `healthy`, `172.17.0.24:30007` answers, the
   Gatus probe `network/DDNS Updater` is green and the UI lists every record
   as up to date with the current public IP.

**Rollback:** delete the Custom App and reinstall the catalog App on its
retained volumes.
