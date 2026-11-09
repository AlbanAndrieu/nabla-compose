"""Behaviour of scripts/lib/dataset-profiles.sh with fake zfs/midclt/stat/install.

The library is what bootstrap-repository-storage.sh uses to converge
config/truenas/dataset-profiles.json (cpool/media): --check never mutates,
--apply goes through the TrueNAS middleware and keeps the inherited ACL.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "lib" / "dataset-profiles.sh"
PROFILES = ROOT / "config" / "truenas" / "dataset-profiles.json"
TIB = 1024**4
GIB = 1024**3

FAKE_ZFS = r"""#!/usr/bin/env bash
state="${FAKE_STATE}"
case "$*" in
  "list -H -o name tank/media") exit 0 ;;
  "get -Hp -o value used,available tank") printf '%s\n%s\n' "$((4 * 1024**4))" "$((6 * 1024**4))" ;;
  "get -Hp -o value quota tank/media") cat "${state}/quota" ;;
  "get -H -o value "*" tank/media") cat "${state}/$5" ;;
  *) echo "unexpected zfs $*" >&2; exit 9 ;;
esac
"""
FAKE_MIDCLT = '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "${FAKE_STATE}/midclt.log"\n'
FAKE_STAT = r"""#!/usr/bin/env bash
path="${@: -1}"
if [[ -f "${path}/.owner" ]]; then cat "${path}/.owner"; else echo "0:0"; fi
"""
FAKE_INSTALL = r"""#!/usr/bin/env bash
owner="" group=""
while [[ "$1" == -* ]]; do
  case "$1" in -o) owner="$2"; shift 2 ;; -g) group="$2"; shift 2 ;; -d) shift ;; *) shift ;; esac
done
mkdir -p "$1" && printf '%s:%s\n' "${owner}" "${group}" > "$1/.owner"
"""


def make_bin(tmp: Path) -> Path:
    bin_dir = tmp / "bin"
    bin_dir.mkdir()
    for name, body in {"zfs": FAKE_ZFS, "midclt": FAKE_MIDCLT, "stat": FAKE_STAT, "install": FAKE_INSTALL}.items():
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def run_profile(tmp: Path, mode: str, props: dict, quota: int) -> tuple[str, int]:
    state = tmp / "state"
    state.mkdir(exist_ok=True)
    for key, value in props.items():
        (state / key).write_text(f"{value}\n", encoding="utf-8")
    (state / "quota").write_text(f"{quota}\n", encoding="utf-8")
    mount = tmp / "mnt"
    (mount / "media").mkdir(parents=True, exist_ok=True)
    driver = f"""
set -euo pipefail
fail() {{ echo "FAIL: $*" >&2; exit 1; }}
POOL=tank CANONICAL_MOUNT="{mount}" MODE="{mode}" PROFILES_FILE="{PROFILES}"
source "{LIB}"
reconcile_profile media
echo "DRIFT=${{profile_drift}}"
"""
    env = {**os.environ, "PATH": f"{make_bin_once(tmp)}:{os.environ['PATH']}", "FAKE_STATE": str(state)}
    result = subprocess.run(["bash", "-c", driver], capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    drift = int(result.stdout.rsplit("DRIFT=", 1)[1])
    return result.stdout, drift


_BIN_CACHE: dict[Path, Path] = {}


def make_bin_once(tmp: Path) -> Path:
    if tmp not in _BIN_CACHE:
        _BIN_CACHE[tmp] = make_bin(tmp)
    return _BIN_CACHE[tmp]


def expected_quota() -> int:
    percent = json.loads(PROFILES.read_text(encoding="utf-8"))["datasets"]["media"]["quotaPercentOfPool"]
    return 10 * TIB * percent // 100 // GIB * GIB


def directories() -> list[str]:
    return json.loads(PROFILES.read_text(encoding="utf-8"))["datasets"]["media"]["directories"]


def test_check_reports_drift_without_mutating(tmp_path: Path) -> None:
    out, drift = run_profile(tmp_path, "--check", {"recordsize": "128K", "compression": "lz4", "atime": "on"}, 0)
    assert drift == 3 + len(directories())  # recordsize, atime, quota + every directory
    assert not (tmp_path / "state" / "midclt.log").exists()
    assert not (tmp_path / "mnt" / "media" / "torrents").exists()
    assert "quota=0 expected 40%" in out


def test_apply_converges_through_the_middleware(tmp_path: Path) -> None:
    run_profile(tmp_path, "--apply", {"recordsize": "128K", "compression": "lz4", "atime": "on"}, 0)
    calls = (tmp_path / "state" / "midclt.log").read_text(encoding="utf-8").splitlines()
    assert len(calls) == 1
    assert calls[0].startswith("call pool.dataset.update tank/media ")
    body = json.loads(calls[0].split("tank/media ", 1)[1])
    assert body == {"recordsize": "1M", "atime": "OFF", "quota": expected_quota()}
    for directory in directories():
        owner = (tmp_path / "mnt" / "media" / directory / ".owner").read_text(encoding="utf-8").strip()
        assert owner == "568:568", directory


def test_converged_dataset_reports_no_drift(tmp_path: Path) -> None:
    for directory in directories():
        path = tmp_path / "mnt" / "media" / directory
        path.mkdir(parents=True)
        (path / ".owner").write_text("568:568\n", encoding="utf-8")
    _, drift = run_profile(tmp_path, "--apply", {"recordsize": "1M", "compression": "lz4", "atime": "off"}, expected_quota())
    assert drift == 0
    assert not (tmp_path / "state" / "midclt.log").exists()


def test_storage_bootstrap_sources_the_profiles_library() -> None:
    script = (ROOT / "scripts" / "truenas" / "bootstrap-repository-storage.sh").read_text(encoding="utf-8")
    assert 'PROFILES_FILE="config/truenas/dataset-profiles.json"' in script
    assert 'source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/dataset-profiles.sh"' in script
    assert 'reconcile_profile "${relative}"' in script
    lib = LIB.read_text(encoding="utf-8")
    assert "midclt call pool.dataset.update" in lib
    assert "chmod" not in lib.split("profile_drift=0", 1)[1], "never chmod: keep the inherited NFSv4 ACL"
