# ClamAV

`clamd` for the TrueNAS datasets, deployed as the TrueNAS Custom App `clamav`
from [`compose.yml`](compose.yml), TCP/3310 on `172.17.0.24:30005`.

## Scans

The scans are TrueNAS cron jobs declared in ansible-workstation
`playbooks/truenas-stabilize.yml`. They run `clamdscan --fdpass` in
`ix-clamav-clamav-1` and log to `/mnt/cpool/logs/clamav-scan-*.log`:

| Cron | When | Scope |
| --- | --- | --- |
| `clamav-scan` | 1st of the month, 06:00 | the whole pool (`/scandir`) |
| `clamav-scan-exposed` | Saturday, 04:00 | SMB/NFS shares, mail, uploads, ISOs |
| `clamav-cleanup` | 1st of the month, 04:50 | logs older than 90 days |

The workstation scans its own disks (ansible-workstation
`files/clamav-scan-local-disks.sh`), never the TrueNAS shares.

## Storage

- `/mnt/cpool/clamav` → `/var/lib/clamav`: signature database, kept from the
  catalog App.
- `/mnt/cpool/logs` → `/mnt/logs`: scan logs.
- `/mnt/cpool` → `/scandir`, read-only with `rslave` propagation: a dataset
  unmounted on the host leaves the container too, so `zfs destroy` no longer
  needs a ClamAV restart. `--fdpass` lets `clamd` read files it has no
  permission on.

## Migration from the TrueNAS catalog App (2026-11-13)

Same App name as the catalog App: remove it first, keeping its host paths.
Run from the TrueNAS shell, in `/mnt/cpool/compose/nabla-compose`, with this
change merged.

```bash
sudo midclt call -j app.stop clamav
sudo midclt call -j app.delete clamav '{"remove_images": false, "remove_ix_volumes": false}'
python3 scripts/truenas/reconcile-custom-apps.py --check
sudo python3 scripts/truenas/reconcile-custom-apps.py --apply \
  --expected-plan-hash <hash> --acknowledge I_ACCEPT_TRUENAS_CUSTOM_APP_RECONCILE
```

Accept: `midclt call app.query '[["id","=","clamav"]]'` shows a running
Custom App, `ss -ltn | grep 172.17.0.24:30005` lists the listener and
`docker exec ix-clamav-clamav-1 clamdscan --fdpass /scandir/iso` ends with
`Infected files: 0`.

**Rollback:** delete the Custom App and reinstall the catalog App `clamav` on
the same host paths (`/mnt/cpool/clamav`, `/mnt/cpool/logs`, `/mnt/cpool`).
