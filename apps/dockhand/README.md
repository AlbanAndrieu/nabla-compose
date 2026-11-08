# Dockhand

Docker container management UI, deployed as the TrueNAS Custom App `dockhand`
from [`compose.yml`](compose.yml) on `172.17.0.24:3050`.

## Security posture

- Dockhand mounts `/var/run/docker.sock` **read-write**: it starts, stops and
  deploys containers, which the shared read-only
  [`docker-socket-proxy`](../docker-socket-proxy/README.md) (`POST=0`) cannot
  serve. Treat the UI as **root-equivalent on TrueNAS**.
- The web port is bound to the LAN address only. Never publish Dockhand through
  Traefik, AutoXpose or a Cloudflare tunnel.
- Keep Dockhand authentication enabled; an unauthenticated UI gives any LAN
  client root on the NAS.
- The image is pinned (`fnsys/dockhand:v1.0.57`) and excluded from Watchtower;
  Renovate proposes updates for review.

## Migration from the TrueNAS catalog App (decided 2026-11-06)

Until this migration, Dockhand ran as the TrueNAS **catalog** App `dockhand` on
port `30328`, while monitoring probed the Custom App port `3050`. The Custom App
keeps the same App name, so the catalog App must be removed (keeping its
volumes) before the Custom App is created. Run from the TrueNAS shell, in the
canonical checkout `/mnt/cpool/compose/nabla-compose`, with this branch merged.

1. **Inspect (read-only).** Record version, state and storage of the catalog
   App; do not print environment values.

   ```bash
   sudo midclt call app.query '[["name","=","dockhand"]]' \
     | jq '.[] | {name, state, version, custom_app, human_version}'
   sudo midclt call app.config dockhand | jq '.storage // .persistence // keys'
   ```

   The catalog version must not be newer than the pinned image; otherwise bump
   the pin first to avoid a database downgrade.

2. **Prepare data.** Create `/mnt/cpool/dockhand` as a TrueNAS dataset with the
   **Apps** preset if it does not exist, then snapshot the catalog App storage.

3. **Stop and copy.** Stop the catalog App, then copy its data directory into
   `/mnt/cpool/dockhand` with ownership preserved (`rsync -aHAX`).

   ```bash
   sudo midclt call -j app.stop dockhand
   ```

4. **Remove the catalog App, keep its volumes** (rollback source):

   ```bash
   sudo midclt call -j app.delete dockhand \
     '{"remove_images": false, "remove_ix_volumes": false}'
   ```

5. **Create the Custom App** from the include wrapper (do not paste a copy of
   `compose.yml`):

   ```bash
   DOCKHAND_WRAPPER="$(
     cat <<'EOF'
   include:
     - /mnt/cpool/compose/nabla-compose/apps/dockhand/compose.yml
   EOF
   )"
   sudo midclt call -j app.create "$(
     jq -cn --arg compose "${DOCKHAND_WRAPPER}" \
       '{app_name: "dockhand", custom_app: true, custom_compose_config_string: $compose}'
   )"
   ```

6. **Accept.** `ss -ltn | grep '172.17.0.24:3050'` lists the listener, the
   Gatus probe `operations/Dockhand` turns green, the login page requires
   authentication and the existing Docker environments are present.

**Rollback:** delete the Custom App, reinstall the catalog App on its retained
volumes and restore the snapshot if data changed.
