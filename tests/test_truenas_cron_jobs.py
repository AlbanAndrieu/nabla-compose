"""Offline contract for reconcile-cron-jobs.py and reconcile-mail-settings.py."""

from __future__ import annotations

import contextlib
import importlib.util
from io import StringIO
from pathlib import Path
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), ROOT / "scripts/truenas" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cron = load("reconcile-cron-jobs")
mail = load("reconcile-mail-settings")


def every_job():
    return [*cron.OWNED, *cron.borrowed()]


def test_every_job_is_silent_unless_it_fails():
    for spec in every_job():
        assert (spec["stdout"], spec["stderr"]) == (True, True), spec["description"]
        assert spec["command"].startswith(f"{cron.NOTIFY} {spec['description']} -- "), spec["description"]
    names = [spec["description"] for spec in every_job()]
    assert len(names) == len(set(names))


def test_clamav_scans_run_inside_the_night_window():
    scans = {s["description"]: s for s in cron.OWNED if s["description"].startswith("clamav")}
    assert set(scans) == {"clamav-scan", "clamav-scan-exposed"}
    for spec in scans.values():
        assert (spec["schedule"]["hour"], spec["schedule"]["minute"]) == ("1", "30")
        assert "/scripts/truenas/clamav-scan.sh " in spec["command"]
    assert "clamav-cleanup" in cron.RETIRED


def run_apply(records):
    calls = []

    def fake(method, *arguments):
        if method == "cronjob.query":
            return records
        calls.append((method, *arguments))
        return {}

    with (
        mock.patch.object(sys, "argv", ["cron", "--apply"]),
        mock.patch.object(cron.os, "geteuid", return_value=0),
        mock.patch.object(cron, "CHECKOUT", ROOT),
        mock.patch.object(cron, "middleware", side_effect=fake),
        contextlib.redirect_stdout(StringIO()) as out,
    ):
        assert cron.main() == 0
    return calls, out.getvalue()


def test_apply_adopts_ui_jobs_wraps_borrowed_ones_and_retires_cleanup():
    night = cron.borrowed()[0]
    records = [
        {"id": 6, "description": "", "user": "albandrieu", "enabled": True, "stdout": False, "stderr": False,
         "schedule": {"minute": "0", "hour": "*", "dom": "*", "month": "*", "dow": "*"},
         "command": "bash /mnt/cpool/compose/nabla-compose/scripts/cron.sh /mnt/cpool/compose/nabla-compose"},
        {**night, "id": 9, "stderr": False, "command": "python3 old --start"},
        {"id": 12, "description": "clamav-cleanup", "command": "docker exec ix-clamav-clamav-1 find"},
    ]
    calls, out = run_apply(records)
    updates = {c[1]: c[2] for c in calls if c[0] == "cronjob.update"}
    assert set(updates[6]) == {"description", "command", "stdout", "stderr"}
    assert updates[6]["description"] == "nabla-hourly-sync"
    assert set(updates[9]) == {"command", "stderr"}  # schedule and `enabled` stay with their owner
    assert ("cronjob.delete", 12) in calls
    created = [c[1]["description"] for c in calls if c[0] == "cronjob.create"]
    assert "clamav-scan-exposed" in created and "smart-long-sdd" in created
    assert all("adopt" not in c[1] for c in calls if c[0] == "cronjob.create")
    assert "ABSENT: nabla-postgresbackup" in out


def test_apply_refuses_ambiguous_adoption():
    twice = [{"id": n, "description": "", "command": "bash x/scripts/cron.sh"} for n in (1, 2)]
    with pytest.raises(RuntimeError, match="several cron jobs"):
        run_apply(twice)


def run_mail(mode, send_fails=False):
    calls = []
    users = [{"id": 1, "username": "root", "email": "old@example.org"},
             {"id": 3, "username": "albandrieu", "email": mail.RECIPIENT}]
    services = [{"id": 4, "name": "mail", "type": "Mail", "attributes": {"email": "old@example.org"}},
                {"id": 5, "name": "default", "type": "Mail", "attributes": {"email": ""}},
                # Live v27 shape (28/11): the type sits in attributes, named after its address.
                {"id": 6, "name": "old2@example.org", "level": "INFO", "enabled": False,
                 "attributes": {"type": "Mail", "email": "old2@example.org"}}]

    def fake(method, *arguments, job=False):
        calls.append((method, *arguments))
        if method == "mail.send" and send_fails:
            raise RuntimeError("TrueNAS middleware mail.send failed")
        return {"mail.config": {"fromemail": "truenas@example.org", "fromname": "TrueNAS", "pass": "x"},
                "user.query": users, "alertservice.query": services}.get(method, {})

    with (
        mock.patch.object(sys, "argv", ["mail", mode]),
        mock.patch.object(mail.os, "geteuid", return_value=0),
        mock.patch.object(mail, "middleware", side_effect=fake),
        contextlib.redirect_stdout(StringIO()) as out,
    ):
        mail.main()
    return calls, out.getvalue()


def test_mail_check_only_reads_and_never_prints_the_password():
    calls, out = run_mail("--check")
    assert {c[0] for c in calls} == {"mail.config", "user.query", "alertservice.query"}
    assert "pass" not in out and "'x'" not in out


def test_mail_apply_sets_sender_tests_then_retargets_recipients():
    calls, _ = run_mail("--apply")
    methods = [c[0] for c in calls]
    assert methods.index("mail.update") < methods.index("mail.send") < methods.index("user.update")
    assert ("mail.update", {"fromemail": mail.SENDER, "fromname": mail.SENDER_NAME}) in calls
    assert ("user.update", 1, {"email": mail.RECIPIENT}) in calls
    assert not any(c[0] == "user.update" and c[1] == 3 for c in calls)
    # v27 refuses a partial update: name, level and enabled always go with the attributes.
    assert ("alertservice.update", 4, {"name": "mail", "level": "WARNING", "enabled": True,
                                       "attributes": {"email": mail.RECIPIENT}}) in calls
    assert ("alertservice.update", 6, {"name": mail.RECIPIENT, "level": "INFO", "enabled": False,
                                       "attributes": {"type": "Mail", "email": mail.RECIPIENT}}) in calls
    assert not any(c[0] == "alertservice.update" and c[1] == 5 for c in calls)


def test_mail_apply_restores_the_sender_when_the_relay_refuses_it():
    with pytest.raises(RuntimeError, match="previous sender restored"):
        run_mail("--apply", send_fails=True)


def test_hourly_sync_converges_cron_jobs_and_mail_settings():
    script = (ROOT / "scripts/cron.sh").read_text(encoding="utf-8")
    synced = script[script.index('if [[ "${synced}" == true ]]; then'):]
    synced = synced[:synced.index("\nfi\n")]
    assert "converge reconcile-mail-settings.py || status=1" in synced
    assert "converge reconcile-cron-jobs.py || status=1" in synced
    assert 'sudo -n python3 "${SCRIPT_DIR}/truenas/${script}" --apply' in script


def test_mail_apply_without_sender_change_sends_no_test_mail():
    calls = []

    def fake(method, *arguments, job=False):
        calls.append(method)
        return {"mail.config": {"fromemail": mail.SENDER, "fromname": mail.SENDER_NAME},
                "user.query": [], "alertservice.query": []}.get(method, {})

    with (
        mock.patch.object(sys, "argv", ["mail", "--apply"]),
        mock.patch.object(mail.os, "geteuid", return_value=0),
        mock.patch.object(mail, "middleware", side_effect=fake),
        contextlib.redirect_stdout(StringIO()),
    ):
        mail.main()
    assert "mail.send" not in calls and "mail.update" not in calls


def test_middleware_error_names_the_refused_fields():
    refused = mail.subprocess.CompletedProcess([], 1, "", "Traceback...\n[EINVAL] alert_service_update.name: Field required\n"
                                          "[EINVAL] alert_service_update.level: Field required\n")
    with mock.patch.object(mail.subprocess, "run", return_value=refused), pytest.raises(RuntimeError) as error:
        mail.middleware("alertservice.update", 3, {})
    assert str(error.value) == ("TrueNAS middleware alertservice.update failed: [EINVAL] alert_service_update.name: "
                                "Field required; [EINVAL] alert_service_update.level: Field required")
