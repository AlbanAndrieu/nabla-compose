"""disk-temperature-guard.py: one mail per state change, per disk serial, HDDs only."""

from __future__ import annotations

import contextlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("disk_temperature_guard", ROOT / "scripts/truenas/disk-temperature-guard.py")
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

DISKS = [{"name": "sda", "serial": "WD-A", "type": "HDD"}, {"name": "sdb", "serial": "WD-B", "type": "HDD"},
         {"name": "sde", "serial": "SSD-BOOT", "type": "SSD"}]


def run(tmp_path, temps):
    mails, asked = [], []

    def fake(*argv):
        if argv[0] == "disk.query":
            return DISKS
        if argv[0] == "disk.temperatures":
            asked.append(json.loads(argv[1]))
            return temps
        assert argv[:2] == ("-j", "mail.send")
        mails.append(json.loads(argv[2]))
        return None

    with (mock.patch.object(guard, "STATE_DIR", tmp_path), mock.patch.object(guard, "midclt", side_effect=fake),
          contextlib.redirect_stdout(StringIO())):
        assert guard.main() == 0
    return mails, asked


def test_hysteresis_mails_each_transition_once(tmp_path):
    mails, asked = run(tmp_path, {"sda": 61, "sdb": 40})
    assert asked == [["sda", "sdb"]]  # the SSD boot disk is not guarded
    assert [m["subject"] for m in mails] == ["🌡️ [TrueNAS] WARNING disk temperature: WD-A"]
    assert mails[0]["to"] == ["openclaw@albandrieu.com"]
    assert run(tmp_path, {"sda": 59, "sdb": 40})[0] == []  # between 57 and 60: stays WARNING, no mail
    assert "CRITICAL" in run(tmp_path, {"sda": [66, 0], "sdb": None})[0][0]["subject"]
    assert "recovered" in run(tmp_path, {"sda": 57, "sdb": 40})[0][0]["subject"]
    assert (tmp_path / "WD-A").read_text() == "OK" and (tmp_path / "WD-B").read_text() == "OK"


def test_failed_mail_leaves_the_state_for_a_retry(tmp_path):
    def fake(*argv):
        if argv[0] == "disk.query":
            return DISKS
        if argv[0] == "disk.temperatures":
            return {"sda": 70}
        raise guard.subprocess.CalledProcessError(1, "midclt")

    with mock.patch.object(guard, "STATE_DIR", tmp_path), mock.patch.object(guard, "midclt", side_effect=fake):
        with contextlib.suppress(guard.subprocess.CalledProcessError):
            guard.main()
    assert not (tmp_path / "WD-A").exists()
