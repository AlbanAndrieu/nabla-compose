# OpenClaw workstation backup

The approved destination is `/media/backup/lab/infra/openclaw`. The NFSv4.2 mountpoint is `/media/backup/lab`, sourced from `nabla:/mnt/cpool/backup/lab`.

Layout: `archives/`, `sqlite/main/`, `sqlite/cron/`, `sqlite/global/`, `sqlite/workboard/`, `recovery/`, `manifests/`.

Use `python3 scripts/workstation/backup-openclaw-nfs.py --dry-run` to check NFS and `python3 scripts/workstation/backup-openclaw-nfs.py` to create native OpenClaw archive and agent/global snapshots plus Workboard online SQLite copy. This requires verifying encryption and access controls before routine use.

The script verifies SHA-256 and creates an exclusive JSON manifest. This is not WORM: actual immutable retention needs enforcement on TrueNAS/ZFS or compatible object storage under separate credentials. OpenClaw native tar.gz is not encrypted and NFS sec=sys does not encrypt traffic. Verify restores to a separate recovery directory. Do not delete original local backups until transferred and verified.

The heartbeat scratch is separate from `workspace/HEARTBEAT.md`. Keep the original scratch only in protected backups; only the reviewed sanitized template belongs to this Git repository.
