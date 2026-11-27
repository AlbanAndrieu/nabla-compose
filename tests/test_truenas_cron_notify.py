"""cron-notify.sh, clamav-scan.sh and the night-window hold, with fake midclt/docker/curl."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTIFY = ROOT / "scripts/truenas/cron-notify.sh"
SCAN = ROOT / "scripts/truenas/clamav-scan.sh"
RESTORE = ROOT / "scripts/truenas/restore-optional-apps.sh"

# The 21/11 clamav-scan-exposed mail: clamd went away in the middle of the scan.
BROKEN_SCAN = "\n".join(
    ["ERROR: Communication error"]
    + ["LibClamAV Error: File tree walk aborted."] * 9
    + ["ERROR: Could not connect to clamd on LocalSocket /tmp/clamd.sock: Connection refused"] * 9
)

FAKES = {
    "midclt": r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_STATE}/midclt.log"
case "$*" in
  *app.query*) printf '[{"id":"clamav","state":"%s"}]\n' "${FAKE_APP_STATE:-RUNNING}" ;;
  *mail.send*) printf '%s' "$4" > "${FAKE_STATE}/mail.json" ;;
esac
""",
    "docker": r"""#!/usr/bin/env bash
case "$*" in
  inspect*) echo false ;;
  *--ping*) exit 0 ;;
  *clamdscan*) printf '%s\n' "$*" > "${FAKE_STATE}/scan.args"; cat "${FAKE_STATE}/scan.out"; exit "${FAKE_SCAN_RC:-0}" ;;
esac
""",
    "curl": r"""#!/usr/bin/env bash
printf '%s\n' "$*" > "${FAKE_STATE}/curl.args"
cat > "${FAKE_STATE}/curl.body"
for ((i = 1; i <= $#; i++)); do [[ "${!i}" == -K ]] && { j=$((i + 1)); cat "${!j}" > "${FAKE_STATE}/curl.config"; }; done
""",
    "logger": "#!/usr/bin/env bash\nexit 0\n",
    "sudo": '#!/usr/bin/env bash\n[[ "$1" == -n ]] && shift\nexec "$@"\n',
}


@pytest.fixture
def env(tmp_path):
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "FAKE_STATE": str(state),
        "NABLA_CRON_LOG_DIR": str(tmp_path / "logs"),
        "NABLA_CRON_NOTIFY_ENV": str(tmp_path / "notify.env"),
        "NABLA_APP_LOCK_DIR": str(tmp_path),
    }


def run(argv, env, root=False):
    if root:  # user-namespace root: the scripts refuse non-root callers
        argv = ["unshare", "--user", "--map-root-user", *argv]
    return subprocess.run(argv, env=env, capture_output=True, text=True, check=False, timeout=60)


def namespace_root_available() -> bool:
    try:
        return subprocess.run(["unshare", "--user", "--map-root-user", "true"], check=False).returncode == 0
    except FileNotFoundError:
        return False


needs_root = pytest.mark.skipif(not namespace_root_available(), reason="unprivileged user namespaces unavailable")


def test_success_is_silent(env, tmp_path):
    result = run(["bash", str(NOTIFY), "demo", "--", "bash", "-c", "echo all good"], env)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert not (tmp_path / "state" / "midclt.log").exists()


def test_failure_sends_one_short_summary(env, tmp_path):
    (tmp_path / "notify.env").write_text("NABLA_CRON_SLACK_WEBHOOK_URL='https://hooks.slack.com/services/T/B/x'\n")
    script = f"cat <<'EOF'\n{BROKEN_SCAN}\nEOF\nexit 2"
    result = run(["bash", str(NOTIFY), "clamav-scan-exposed", "--", "bash", "-c", script], env)
    assert result.returncode == 2
    mail = json.loads((tmp_path / "state" / "mail.json").read_text(encoding="utf-8"))
    assert mail["to"] == ["openclaw@albandrieu.com"]
    assert mail["subject"].startswith("❌ [") and "clamav-scan-exposed" in mail["subject"]
    assert "9× LibClamAV Error: File tree walk aborted." in mail["text"]
    assert mail["text"].count("Connection refused") == 1
    assert "If you don't wish" not in mail["text"]
    assert "#d92d20" in mail["html"]
    state = tmp_path / "state"
    assert "hooks.slack.com" not in (state / "curl.args").read_text()  # credential kept out of argv
    assert "hooks.slack.com/services/T/B/x" in (state / "curl.config").read_text()
    assert "9× LibClamAV" in json.loads((state / "curl.body").read_text())["text"]


@needs_root
def test_scan_starts_waits_and_restores_a_stopped_app(env, tmp_path):
    state = tmp_path / "state"
    (state / "scan.out").write_text("----------- SCAN SUMMARY -----------\nInfected files: 0\nTime: 12.0 sec\n")
    result = run(["bash", str(SCAN), "exposed"], {**env, "FAKE_APP_STATE": "STOPPED"}, root=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("✅ ClamAV exposed : 0 infecté(s), 0 erreur(s)")
    assert len(result.stdout.splitlines()) == 1
    calls = (state / "midclt.log").read_text().splitlines()
    assert [c for c in calls if "app.st" in c] == ["call -j app.start clamav", "call -j app.stop clamav"]
    args = (state / "scan.args").read_text()
    assert "--fdpass --infected" in args and "/scandir/ftp" in args and "/scandir/openwebui" in args


@needs_root
def test_infected_files_exit_1_and_running_app_stays_up(env, tmp_path):
    state = tmp_path / "state"
    (state / "scan.out").write_text("/scandir/iso/x.exe: Win.Test.EICAR_HDB-1 FOUND\nInfected files: 1\n")
    result = run(["bash", str(SCAN), "full"], {**env, "FAKE_SCAN_RC": "1"}, root=True)
    assert result.returncode == 1
    assert result.stdout.splitlines()[0].endswith("FOUND")
    assert "🦠 ClamAV full : 1 infecté(s)" in result.stdout
    assert "app.stop" not in (state / "midclt.log").read_text()


@needs_root
def test_night_window_stop_defers_a_held_app(env, tmp_path):
    apps = tmp_path / "apps.txt"
    apps.write_text("clamav\n")
    lock = tmp_path / "nabla-app-clamav.lock"
    holder = subprocess.Popen(["flock", str(lock), "sleep", "30"])
    try:
        for _ in range(50):
            if lock.exists():
                break
            subprocess.run(["sleep", "0.1"], check=True)
        result = run(["bash", str(RESTORE), "--stop"], {**env, "NABLA_OPTIONAL_APPS_FILE": str(apps)}, root=True)
    finally:
        holder.kill()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HELD" in result.stdout
    assert (tmp_path / "nabla-app-clamav.lock.stop-pending").exists()
    assert "app.stop" not in (tmp_path / "state" / "midclt.log").read_text()
