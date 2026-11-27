# ClamAV

`clamd` for the TrueNAS datasets, deployed as the TrueNAS Custom App `clamav`
from [`compose.yml`](compose.yml), TCP/3310 on `172.17.0.24:30005`.

## Scans

The scans are TrueNAS cron jobs declared in
[`scripts/truenas/reconcile-cron-jobs.py`](../../scripts/truenas/reconcile-cron-jobs.py)
(moved from ansible-workstation on 26/11/2026). Each one runs
[`clamav-scan.sh`](../../scripts/truenas/clamav-scan.sh) through
`cron-notify.sh`. The script:

- starts the App when it is stopped (it is a night-window App);
- waits up to 30 minutes for `clamd` (`clamdscan --ping`);
- holds the App, so the 07:00 night-window stop is deferred until the scan ends;
- runs `clamdscan --multiscan --fdpass --infected`, logging to
  `/mnt/cpool/logs/clamav-scan-*.log`;
- deletes the logs older than 90 days;
- puts the App back in its previous state.

A clean scan sends nothing. Infected files or an error send a short summary to
OpenClaw (mail and Slack).

| Cron | When | Scope |
| --- | --- | --- |
| `clamav-scan` | 1st of the month, 01:30 | the whole pool (`/scandir`) |
| `clamav-scan-exposed` | Saturday, 01:30 | SMB/NFS shares, mail, uploads, ISOs |

On 21/11/2026, the Saturday 04:00 scan lost `clamd` halfway through:
`Communication error`, then `Connection refused` for the remaining paths. The
likely cause is the 07:00 night-window stop of `clamav`. An out-of-memory kill
at the 2 GiB limit is the other suspect. The scan log was not read, so this is
not confirmed; `clamav-scan.sh` now reports an OOM kill when it happens.

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
