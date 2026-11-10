"""Home Assistant read-only diagnostics: safety contracts and offline fixtures."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts/lib/homeassistant.sh"
MAIN = ROOT / "scripts/truenas/diagnose-homeassistant.sh"
USB = ROOT / "scripts/truenas/diagnose-homeassistant-usb.sh"
OVERKIZ = ROOT / "scripts/truenas/diagnose-homeassistant-overkiz.sh"
SCRIPTS = (MAIN, USB, OVERKIZ)

FORBIDDEN = (
    r"\bdocker (restart|stop|start|rm|kill|run|compose|update)\b",
    r"app\.(stop|start|update|delete|create|redeploy)",
    r"\bzfs (destroy|snapshot|rollback|set)\b",
    r"--request|-X (POST|PUT|PATCH|DELETE)",
    r"^\s*(rm|chmod|chown|mv|tee) ",
    r"printenv|Config\.Env|docker logs",
)

DOCKER_STUB = r"""#!/usr/bin/env bash
cmd="$1"; shift
case "${cmd}" in
  ps)
    [[ "$*" == *"project=ix-homeassistant"* ]] &&
      printf 'c0ffee ghcr.io/home-assistant/home-assistant:2026.10.4@sha256:abc\n'
    exit 0 ;;
  inspect)
    fmt=''
    args=("$@")
    for ((i = 0; i < ${#args[@]}; i++)); do
      [[ "${args[i]}" == --format ]] && fmt="${args[i + 1]}"
    done
    case "${fmt}" in
      '') cat "${NABLA_MOCK_DIR}/inspect.json" ;;
      *'{{.Id}}'*) echo c0ffee ;;
      *container=*) echo 'container=/homeassistant status=running privileged=false network_mode=bridge' ;;
      *'{{json .HostConfig.Devices}}'*) cat "${NABLA_MOCK_DIR}/devices.json" ;;
      *'{{.State.Status}}'*) echo running ;;
      *'{{.HostConfig.Privileged}}'*) echo false ;;
      *'{{.HostConfig.NetworkMode}}'*) echo bridge ;;
      *) echo unknown ;;
    esac ;;
  exec) exit 0 ;;
  *) exit 1 ;;
esac
"""

CURL_STUB = r"""#!/usr/bin/env bash
url="${!#}"
case "${url}" in
  *manifest.json) printf 200 ;;
  */api/) printf 401 ;;
  *) exit 7 ;;
esac
"""

MIDCLT_STUB = r"""#!/usr/bin/env bash
if [[ "$*" == *'"homeassistant"'* ]]; then printf '[{"state":"RUNNING"}]'; else printf '[]'; fi
"""

ENOCEAN_BY_ID = "usb-EnOcean_GmbH_EnOcean_USB_300_DC_FT00TEST-if00-port0"
ZIGBEE_BY_ID = "usb-ITead_Sonoff_Zigbee_3.0_USB_Dongle_Plus_0000TEST-if00-port0"


def _env_with_stubs(base: Path, **extra: str) -> dict[str, str]:
    """Forward docker/curl/midclt to stubs through BASH_ENV (noexec-safe)."""
    bin_dir = base / "bin"
    bin_dir.mkdir()
    for name, body in {"docker": DOCKER_STUB, "curl": CURL_STUB, "midclt": MIDCLT_STUB}.items():
        (bin_dir / name).write_text(body, encoding="utf-8")
    envfile = base / "stubs.sh"
    envfile.write_text(
        "".join(f'{name}() {{ BASH_ENV= /bin/bash "{bin_dir / name}" "$@"; }}\n' for name in ("docker", "curl", "midclt")),
        encoding="utf-8",
    )
    env = os.environ.copy()
    for key in ("NABLA_DIAGNOSTIC_WRAPPED", "DIAGNOSTIC_FULL_OUTPUT", "NABLA_HA_CONTAINER"):
        env.pop(key, None)
    env.update(
        {
            "BASH_ENV": str(envfile),
            "NABLA_MOCK_DIR": str(base),
            "DIAG_COLOR": "never",
            "DIAG_ICONS": "never",
            "NO_COLOR": "1",
            "NABLA_HA_SECRETS_FILE": str(base / "absent.env"),
            "NABLA_HA_CANONICAL_ROOT": str(base / "no-checkout"),
        }
    )
    env.update(extra)
    return env


def _ha_config(base: Path) -> Path:
    config = base / "ha-config"
    (config / ".storage").mkdir(parents=True)
    entries = {
        "version": 1,
        "key": "core.config_entries",
        "data": {
            "entries": [
                {
                    "domain": "enocean",
                    "title": "EnOcean",
                    "source": "usb",
                    "disabled_by": None,
                    "data": {"device": f"/dev/serial/by-id/{ENOCEAN_BY_ID}"},
                    "options": {},
                },
                {
                    "domain": "overkiz",
                    "title": "owner@example.invalid",
                    "source": "user",
                    "disabled_by": None,
                    "data": {"username": "owner@example.invalid", "note": "ENTRY-DATA-CANARY"},
                    "options": {},
                },
            ]
        },
    }
    (config / ".storage/core.config_entries").write_text(json.dumps(entries), encoding="utf-8")
    hacs = config / "custom_components/hacs"
    hacs.mkdir(parents=True)
    (hacs / "manifest.json").write_text('{"domain": "hacs", "version": "2.0.5"}', encoding="utf-8")
    (config / "configuration.yaml").write_text(
        "http:\n  use_x_forwarded_for: true\n  trusted_proxies:\n    - 172.16.0.0/12\nrecorder:\n  db_url: !secret recorder_db_url\n",
        encoding="utf-8",
    )
    secrets = config / "secrets.yaml"
    secrets.write_text("recorder_db_url: SECRETS-YAML-CANARY\n", encoding="utf-8")
    secrets.chmod(0o644)
    return config


def _usb_device(root: Path, name: str, vid: str, pid: str, manufacturer: str, product: str, tty: str, by_id: str) -> None:
    device = root / "sys/devices/usb1" / name
    port = device / f"{name}:1.0" / tty
    port.mkdir(parents=True)
    for field, value in {
        "idVendor": vid,
        "idProduct": pid,
        "manufacturer": manufacturer,
        "product": product,
        "bDeviceClass": "00",
        "serial": "SERIAL-LEAK-CANARY",
    }.items():
        (device / field).write_text(value + "\n", encoding="utf-8")
    (device / f"{name}:1.0/bInterfaceClass").write_text("ff\n", encoding="utf-8")
    driver = root / "sys/bus/usb-serial/drivers/serial_driver"
    driver.mkdir(parents=True, exist_ok=True)
    (port / "driver").symlink_to(driver)
    (root / "sys/bus/usb/devices").mkdir(parents=True, exist_ok=True)
    (root / "sys/bus/usb/devices" / name).symlink_to(device)
    (root / "sys/class/tty" / tty).mkdir(parents=True)
    (root / "sys/class/tty" / tty / "device").symlink_to(port)
    (root / "dev/serial/by-id").mkdir(parents=True, exist_ok=True)
    (root / "dev" / tty).write_text("", encoding="utf-8")
    (root / "dev/serial/by-id" / by_id).symlink_to(Path("../..") / tty)


def _run(script: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, env=env, check=False, timeout=120)  # noqa: S603, S607


@pytest.mark.parametrize("script", (*SCRIPTS, LIB), ids=lambda path: path.name)
def test_syntax_strict_mode_and_read_only(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0  # noqa: S603, S607
    source = script.read_text(encoding="utf-8")
    for pattern in FORBIDDEN:
        assert not re.search(pattern, source, re.MULTILINE), (script.name, pattern)
    if script is not LIB:
        assert script.stat().st_mode & stat.S_IXUSR
        assert "set -euo pipefail" in source
        assert "diag_summary" in source


def test_tokens_stay_out_of_argv_and_unverified_tls() -> None:
    for script in (LIB, OVERKIZ):
        source = script.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "Authorization" in line:
                assert "secrets_curl_headers Authorization" in line, (script.name, line)
    overkiz = OVERKIZ.read_text(encoding="utf-8")
    inventory = overkiz[overkiz.index('if ((LOCAL_API)) && [[ -n "${token}" ]]') :]
    assert inventory.index("if ((verified)); then") < inventory.index("secrets_curl_headers Authorization")
    assert overkiz.count("--insecure") == 1
    for script in (LIB, MAIN, USB):
        assert ".title" not in script.read_text(encoding="utf-8")


def test_usb_handoff_classifies_dongles_and_never_leaks() -> None:
    with tempfile.TemporaryDirectory(prefix=".ha-usb-mock-", dir=ROOT) as temp:
        base = Path(temp)
        host = base / "host"
        _usb_device(host, "1-2", "0403", "6001", "EnOcean GmbH", "EnOcean USB 300 DC", "ttyUSB0", ENOCEAN_BY_ID)
        _usb_device(host, "1-3", "10c4", "ea60", "ITead", "Sonoff Zigbee 3.0 USB Dongle Plus", "ttyUSB1", ZIGBEE_BY_ID)
        (base / "devices.json").write_text(
            json.dumps(
                [
                    {
                        "PathOnHost": f"/dev/serial/by-id/{ENOCEAN_BY_ID}",
                        "PathInContainer": f"/dev/serial/by-id/{ENOCEAN_BY_ID}",
                        "CgroupPermissions": "rwm",
                    }
                ]
            ),
            encoding="utf-8",
        )
        env = _env_with_stubs(base, NABLA_HOST_ROOT=str(host), NABLA_HA_CONFIG_DIR=str(_ha_config(base)))
        result = _run(USB, env)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "kind=enocean" in output and "kind=zigbee" in output
    assert f"/dev/serial/by-id/{ENOCEAN_BY_ID} reaches Home Assistant integration enocean" in output
    assert f"/dev/serial/by-id/{ZIGBEE_BY_ID} is not passed to Home Assistant" in output
    assert f"- /dev/serial/by-id/{ZIGBEE_BY_ID}:/dev/serial/by-id/{ZIGBEE_BY_ID}" in output
    for canary in ("ENTRY-DATA-CANARY", "example.invalid", "SERIAL-LEAK-CANARY"):
        assert canary not in output


def test_main_diagnostic_reports_ownership_hacs_and_hygiene_without_values() -> None:
    with tempfile.TemporaryDirectory(prefix=".ha-main-mock-", dir=ROOT) as temp:
        base = Path(temp)
        (base / "inspect.json").write_text(
            json.dumps(
                [
                    {
                        "State": {"Status": "running", "Health": {"Status": "healthy"}},
                        "HostConfig": {
                            "NetworkMode": "bridge",
                            "Privileged": False,
                            "SecurityOpt": ["no-new-privileges:true"],
                            "Devices": [],
                        },
                        "Config": {"Image": "ghcr.io/home-assistant/home-assistant:2026.10.4@sha256:abc"},
                        "Mounts": [{"Destination": "/config", "RW": True}],
                    }
                ]
            ),
            encoding="utf-8",
        )
        config = _ha_config(base)
        # Some mounts (VM shares) drop group/other bits: assert only what the FS keeps.
        world_readable = bool((config / "secrets.yaml").stat().st_mode & 0o007)
        env = _env_with_stubs(base, NABLA_HA_CONFIG_DIR=str(config))
        result = _run(MAIN, env)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Runtime owned by the repository Custom App homeassistant" in output
    assert "url=http://172.17.0.24:30103/manifest.json http=200" in output
    assert "custom_integration=hacs version=2.0.5" in output
    assert "http_use_x_forwarded_for=yes http_trusted_proxies=yes recorder_external_db=yes" in output
    assert ("secrets.yaml is readable by other users" in output) is world_readable
    assert "domain=overkiz entries=1" in output
    assert "recorder-postgres: tcp 172.17.0.24:5432 reachable" in output
    for canary in ("ENTRY-DATA-CANARY", "SECRETS-YAML-CANARY", "example.invalid"):
        assert canary not in output


def test_overkiz_usage_validation_and_unreachable_verdict() -> None:
    env = os.environ.copy()
    env.update({"DIAG_COLOR": "never", "DIAG_ICONS": "never", "NABLA_OVERKIZ_SECRETS_FILE": "/nonexistent/overkiz.env"})
    assert _run(OVERKIZ, env).returncode == 2
    assert _run(OVERKIZ, env, "--host", "gw;id").returncode == 2

    result = _run(OVERKIZ, env, "--host", "192.0.2.1")
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "Discovery skipped" in output
    assert "tcp=8443 closed-or-filtered" in output
    assert "Not identified as an Overkiz gateway" in output
