#!/usr/bin/env bash
# Offline OpenClaw snapshot: no service changes, no network, no secrets printed.
set -euo pipefail
umask 077

usage() {
  printf '%s\n' 'Usage: backup-openclaw.sh --check|--create|--verify ARCHIVE|--restore-test ARCHIVE'
  printf '%s\n' 'Create requires the user Gateway stopped; this script never stops or starts it.'
}
mode="${1:-}"
case "${mode}" in
  --check|--create) [[ $# -eq 1 ]] || { usage >&2; exit 2; } ;;
  --verify|--restore-test) [[ $# -eq 2 ]] || { usage >&2; exit 2; } ;;
  *) usage >&2; exit 2 ;;
esac

state="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
dest="${OPENCLAW_BACKUP_DIR:-${HOME}/Backups/openclaw}"
unit="${OPENCLAW_UNIT:-openclaw-gateway.service}"

if [[ -L "${state}" || ! -d "${state}" ]]; then
  printf 'ERROR: state directory missing or symlink: %s\n' "${state}" >&2
  exit 1
fi
if [[ "${mode}" == --check || "${mode}" == --create ]]; then
  printf 'State directory present. No state contents displayed.\n'
  if command -v systemctl >/dev/null 2>&1; then
    active="$(systemctl --user is-active "${unit}" 2>/dev/null || true)"
    if [[ "${active}" == active ]]; then
      if [[ "${mode}" == --create ]]; then
        echo 'ERROR: Gateway active; quiesce it explicitly before consistent backup.' >&2
        exit 1
      fi
      echo 'WARN: Gateway active; consistent backup requires operator-controlled quiesce.'
    fi
  fi
  if [[ "${mode}" == --check ]]; then exit 0; fi
fi

# Delegate tar safety, pathname validation and atomic output to the standard
# Python library. Refuse untrusted archives and any path traversal.
python3 - "${mode}" "${state}" "${dest}" "${2:-}" <<'PY'
import datetime
import hashlib
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile
import tempfile

mode, state_arg, dest_arg, archive_arg = sys.argv[1:]
state = Path(state_arg).resolve()
dest = Path(dest_arg).expanduser().resolve()

def validate(archive):
    with tarfile.open(archive, "r:gz") as tf:
        seen = set()
        count = 0
        for member in tf:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or not path.parts or path.parts[0] != "openclaw"
                    or any(part in (".", "..") for part in path.parts)
                    or not (member.isfile() or member.isdir())):
                raise ValueError("unsafe member type/path in archive")
            if member.name in seen:
                raise ValueError("duplicate archive member")
            seen.add(member.name)
            if member.isfile():
                stream = tf.extractfile(member)
                if stream is None:
                    raise ValueError("file cannot be read")
                while stream.read(1024 * 1024):
                    pass
                count += 1
    return count

def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()

if mode == "--create":
    if dest == state or state in dest.parents:
        raise SystemExit("ERROR: backup destination must not be inside OpenClaw state")
    dest.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(dest, 0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fd, tmp = tempfile.mkstemp(prefix=".openclaw-", suffix=".tar.gz", dir=dest)
    try:
        with os.fdopen(fd, "wb") as outfile:
            with tarfile.open(fileobj=outfile, mode="w:gz") as tf:
                tf.add(state, arcname="openclaw", recursive=True,
                       filter=lambda entry: entry if entry.isfile() or entry.isdir() else None)
        count = validate(Path(tmp))
        final = dest / f"openclaw-{stamp}-{os.getpid()}.tar.gz"
        os.replace(tmp, final)
        os.chmod(final, 0o600)
        print(f"CREATED {final}")
        print(f"VERIFIED files={count} sha256={digest(final)}")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
else:
    archive = Path(archive_arg).expanduser().resolve(strict=True)
    if not archive.is_file():
        raise SystemExit("ERROR: archive is not a regular file")
    count = validate(archive)
    if mode == "--restore-test":
        with tempfile.TemporaryDirectory(prefix="openclaw-restore-test-") as td:
            os.chmod(td, 0o700)
            with tarfile.open(archive, "r:gz") as tf:
                # Archive members were checked; manually extract regular files,
                # never invoking tarfile.extractall.
                for member in tf:
                    rel = PurePosixPath(member.name)
                    target = Path(td).joinpath(*rel.parts)
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        source = tf.extractfile(member)
                        if source is None:
                            raise ValueError("archive file unreadable")
                        with target.open("xb") as out:
                            while chunk := source.read(1024 * 1024):
                                out.write(chunk)
            print(f"RESTORE_TEST_OK files={count} (temporary copy removed)")
    print(f"VERIFIED files={count} sha256={digest(archive)}")
PY
