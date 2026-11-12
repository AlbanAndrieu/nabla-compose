# Uptime Kuma on TrueNAS

Repository-owned Uptime Kuma monitoring engine/UI. It replaces the removed
native TrueNAS Uptime Kuma App and is the server that
[AutoKuma](../autokuma/README.md) reconciles generated Nabla monitors into.

- TrueNAS Custom App: `uptime-kuma` (`config/truenas/custom-apps.yml`);
- image: `louislam/uptime-kuma` rootless 2.x, run as the TrueNAS `apps` user
  (`568:568`);
- endpoint: `http://172.17.0.24:31050` (container port `3001`), internal only,
  with no Traefik or Cloudflare route;
- data: ZFS dataset `cpool/uptime-kuma` mounted at `/mnt/cpool/uptime-kuma`,
  covered by the snapshot task in `config/truenas/snapshot-tasks.json`.

No secret is stored in Git: the admin account is created once in the UI and
lives in the Uptime Kuma database.

## Deployment order

1. Create the dataset `cpool/uptime-kuma` owned by `568:568`, then deploy the
   `uptime-kuma` Custom App with the repository include:

   ```yaml
   include:
     - /mnt/cpool/compose/nabla-compose/apps/uptime-kuma/compose.yml
   ```

2. Open `http://172.17.0.24:31050`, choose SQLite and create the admin user.
3. Mint the AutoKuma token and deploy AutoKuma:

   ```bash
   sudo bash scripts/truenas/bootstrap-autokuma-token.sh \
     --url http://172.17.0.24:31050 --username <user>
   bash scripts/truenas/deploy-autokuma.sh
   ```

## Acceptance

```bash
curl -fsS --max-time 5 http://172.17.0.24:31050/ >/dev/null &&
echo 'Uptime Kuma reachable'
```
