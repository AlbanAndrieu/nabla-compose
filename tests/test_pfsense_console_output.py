"""Pure local regressions for the pfSense workstation color renderer."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/pfsense/console.sh"


def render(payload: str, mode="compact", color="never", no_color=None):
    env = os.environ.copy()
    env.update(PFSENSE_OUTPUT=mode, PFSENSE_COLOR=color, TERM="xterm-256color")
    env.pop("NO_COLOR", None)
    if no_color:
        env["NO_COLOR"] = no_color
    return subprocess.run(
        ["bash", "-c", 'source "$1"; pfsense_ui_render', "bash", str(HELPER)],
        input=payload, capture_output=True, text=True, env=env, check=False,
    )


class ConsoleContract(unittest.TestCase):
    def test_all_pfsense_bash_scripts_parse(self):
        for script in (ROOT / "scripts/pfsense").glob("*.sh"):
            if script.name == "check-central-crowdsec-bouncer.sh":
                # FreeBSD native POSIX sh.
                continue
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_tty_is_byte_identical(self):
        payload = '=== Unbound ===\n{"result":"OK","private":"token"}\n'
        for mode in ("raw", "auto"):
            with self.subTest(mode=mode):
                response = render(payload, mode=mode, color="always")
                self.assertEqual(response.returncode, 0)
                self.assertEqual(response.stdout, payload)

    def test_color_and_no_color(self):
        data = "=== DNS ===\nWARN: status unknown\n"
        self.assertIn("\x1b[", render(data, color="always").stdout)
        self.assertNotIn("\x1b[", render(data, color="always", no_color="1").stdout)

    def test_rfc5424_oom_redaction(self):
        log = ("=== OOM ===\n<3>1 2026-10-24T02:10:50.474019+02:00 "
               "kernel - - - failed to reclaim memory token=PRIVATE\n")
        output = render(log)
        self.assertEqual(output.returncode, 0, output.stderr)
        # Compact aggregates historical kills by minute (including UTC offset).
        self.assertIn("Historical OOM minute=2026-10-24T02:10 +02:00", output.stdout)
        self.assertNotIn("02:10:50.474019+02:00", output.stdout)
        self.assertIn("1 distinct historical OOM records", output.stdout)
        self.assertNotIn("PRIVATE", output.stdout)
        # Verbose preserves complete RFC 5424 timestamps without raw syslog text.
        detail = render(log, mode="verbose")
        self.assertEqual(detail.returncode, 0, detail.stderr)
        self.assertIn("Historical kernel OOM timestamp=2026-10-24T02:10:50.474019+02:00", detail.stdout)
        self.assertNotIn("PRIVATE", detail.stdout)

    def test_snort_unknown_collapse_and_verbose(self):
        payload = "=== Snort ===\n" + "source=snort event=snort_update_start timestamp=unknown\n" * 21
        self.assertIn("21 events with unknown timestamps", render(payload).stdout)
        self.assertIn("source=snort", render(payload, mode="verbose").stdout)

    def test_csv_pretty_tty_but_raw_when_redirected(self):
        csv = ("timestamp,available_mib,free_mib,inactive_mib,wired_mib,active_mib,"
               "unbound_pid,unbound_rss_kib,pfblocker_cron_count,php_fpm_rss_kib\n"
               "2026-10-24T02:09:00+0200,220.3,200,20.3,300,400,21619,132000,0,290000\n")
        self.assertIn("available=220.3 MiB", render(csv).stdout)
        self.assertEqual(render(csv, mode="auto").stdout, csv)

    def test_pipefail_preserves_upstream_failure(self):
        env = os.environ | {"PFSENSE_OUTPUT": "compact", "TERM": "dumb"}
        result = subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; (exit 17) | pfsense_ui_render', "bash", str(HELPER)],
            capture_output=True, env=env, check=False,
        )
        self.assertEqual(result.returncode, 17)

    def test_oom_records_are_deduplicated_across_log_sections(self):
        stamps = (
            "2026-10-24T02:10:50.474019+02:00",
            "2026-10-24T02:10:51.881022+02:00",
            "2026-10-22T22:03:33.361041+02:00",
        )
        events = "=== historical chronology ===\n"
        events += "".join(f"source=system event=kernel_oom timestamp={ts}\n" for ts in stamps)
        events += "=== resolver archives ===\n"
        events += "".join(
            f"<3>1 {ts} host kernel - - - failed to reclaim memory token=PRIVATE\n"
            for ts in stamps
        )
        result = render(events, mode="verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("Historical kernel OOM timestamp="), 3)
        self.assertIn("3 distinct historical OOM records", result.stdout)
        self.assertIn("3 duplicate lines suppressed", result.stdout)
        self.assertIn("2 OOM minutes", result.stdout)
        self.assertNotIn("PRIVATE", result.stdout)
        self.assertNotIn("❌ 3 error signals", result.stdout)

    def test_unbound_start_is_not_attributed_to_oom(self):
        process = (
            "=== Unbound daemon and readiness ===\n"
            "12710 Sat Oct 24 23:38:57 2026 124624 6.9 "
            "/usr/local/sbin/unbound -c /var/unbound/unbound.conf\n"
        )
        result = render(process)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pid=12710 started=Oct 24 23:38:57", result.stdout)
        self.assertIn("restart cause UNKNOWN", result.stdout)

    def test_free_inactive_memory_snapshot_is_explicit(self):
        metrics = (
            "=== Memory budget and OOM evidence ===\n"
            "vm.stats.vm.v_free_count: 28172\n"
            "vm.stats.vm.v_inactive_count: 8568\n"
            "vm.stats.vm.v_page_size: 4096\n"
        )
        result = render(metrics)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("143.5 MiB", result.stdout)
        self.assertIn("not nocturnal headroom", result.stdout)

    def test_syslog_categories_hide_sensitive_contents(self):
        data = (
            "=== Resolver failures ===\n"
            "<29>1 2026-10-22T21:42:08.401695+02:00 host "
            "address already in use password=SECRET\n"
            "<30>1 2026-10-24T23:39:23.470342+02:00 host "
            "pfb_unbound.py script exiting token=SECRET\n"
        )
        result = render(data, mode="verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("resolver_event=unbound_bind_conflict", result.stdout)
        self.assertIn("resolver_event=dnsbl_python_exit", result.stdout)
        self.assertNotIn("SECRET", result.stdout)

    def test_compact_oom_groups_kernel_kills_by_minute(self):
        events = (
            "=== Incident history ===\n"
            "source=system event=kernel_oom timestamp=2026-10-24T02:10:47.469850+02:00\n"
            "source=system event=kernel_oom timestamp=2026-10-24T02:10:50.474019+02:00\n"
            "source=system event=kernel_oom timestamp=2026-10-22T22:03:33.361041+02:00\n"
            "=== Resolver archives ===\n"
            "<3>1 2026-10-24T02:10:47.469850+02:00 fw kernel failed to reclaim memory SECRET\n"
        )
        out = render(events)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Historical OOM minute=2026-10-24T02:10", out.stdout)
        self.assertIn("kernel kills=2", out.stdout)
        self.assertEqual(out.stdout.count("Historical OOM minute="), 2)
        self.assertIn("3 distinct historical OOM records", out.stdout)
        self.assertIn("1 duplicate lines suppressed", out.stdout)
        self.assertNotIn("SECRET", out.stdout)

    def test_unbound_ps_freebsd_leading_space(self):
        process = (
            "=== Unbound daemon and readiness ===\n"
            " 2135 Sun Oct 25 00:04:56 2026 124572 5.1 "
            "/usr/local/sbin/unbound -c /var/unbound/unbound.conf\n"
        )
        out = render(process)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Unbound process pid=2135 started=Oct 25 00:04:56", out.stdout)
        self.assertIn("restart cause UNKNOWN", out.stdout)

    def test_dst_repeated_local_minute_keeps_utc_offsets(self):
        events = (
            "=== DST OOM chronology ===\n"
            "source=system event=kernel_oom timestamp=2026-10-25T02:10:30+02:00\n"
            "source=system event=kernel_oom timestamp=2026-10-25T02:10:31+01:00\n"
            "source=system event=kernel_oom timestamp=2026-10-25T02:10:33+02:00\n"
        )
        result = render(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Historical OOM minute=2026-10-25T02:10 +02:00", result.stdout)
        self.assertIn("Historical OOM minute=2026-10-25T02:10 +01:00", result.stdout)
        self.assertEqual(result.stdout.count("Historical OOM minute="), 2)
        self.assertIn("3 distinct historical OOM records", result.stdout)
        self.assertIn("2 OOM minutes", result.stdout)
        self.assertIn("kernel kills=2", result.stdout)

    def test_typed_unbound_oom_is_counted_and_labeled(self):
        fixture = (
            "=== system lifecycle events (bounded, redacted) ===\n"
            "WARN: signal_source=system event=kernel_oom_unbound "
            "timestamp=2026-10-24T02:10:50.474019+02:00\n"
            "signal_source=system event=kernel_oom_other "
            "timestamp=2026-10-24T02:10:51.881022+02:00\n"
            "=== archived system lifecycle events ===\n"
            "WARN: signal_source=system event=kernel_oom_unbound "
            "timestamp=2026-10-24T02:10:50.474019+02:00\n"
        )
        compact = render(fixture)
        self.assertEqual(compact.returncode, 0, compact.stderr)
        self.assertIn("kernel kills=2", compact.stdout)
        self.assertIn("unbound kills=1", compact.stdout)
        self.assertIn("2 distinct historical OOM records", compact.stdout)
        self.assertIn("1 duplicate lines suppressed", compact.stdout)
        self.assertNotIn("0 distinct historical OOM records", compact.stdout)
        verbose = render(fixture, mode="verbose")
        self.assertEqual(verbose.returncode, 0, verbose.stderr)
        self.assertIn(
            "Historical kernel OOM victim=unbound "
            "timestamp=2026-10-24T02:10:50.474019+02:00",
            verbose.stdout,
        )
        self.assertIn("Historical kernel OOM victim=other", verbose.stdout)
        self.assertEqual(verbose.stdout.count("victim=unbound"), 1)

    def test_typed_oom_during_dst_keeps_two_minutes_separate(self):
        # The remote collector always emits an explicit section before events.
        # An event-only fragment without a section is incomplete evidence.
        sample = (
            "=== system lifecycle events (bounded, redacted) ===\n"
            "WARN: signal_source=system event=kernel_oom_unbound "
            "timestamp=2026-10-25T02:09:11+02:00\n"
            "WARN: signal_source=system event=kernel_oom_unbound "
            "timestamp=2026-10-25T02:09:15+01:00\n"
        )
        output = render(sample)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("Historical OOM minute=2026-10-25T02:09 +02:00", output.stdout)
        self.assertIn("Historical OOM minute=2026-10-25T02:09 +01:00", output.stdout)
        self.assertEqual(output.stdout.count("unbound kills=1"), 2)
        self.assertIn("2 OOM minutes", output.stdout)

    def test_failed_remote_classifier_marks_report_incomplete(self):
        payload = (
            "=== system lifecycle events ===\n"
            "ERROR: lifecycle_classifier_failed source=system\n"
        )
        result = render(payload, mode="verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("❌ EVIDENCE INCOMPLETE", result.stdout)
        self.assertIn("OOM totals are NOT reliable", result.stdout)
        self.assertNotIn("0 distinct historical OOM records", result.stdout)

    def test_unframed_oom_signals_remain_incomplete(self):
        # Recognizing an OOM signal is not evidence that a collector
        # completed; preserve the fail-closed report semantics.
        sample = (
            "WARN: signal_source=system event=kernel_oom_unbound "
            "timestamp=2026-10-25T02:09:11+02:00\n"
        )
        result = render(sample, mode="compact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Historical OOM minute=2026-10-25T02:09 +02:00", result.stdout)
        self.assertIn("EVIDENCE INCOMPLETE", result.stdout)
        self.assertNotIn("1 distinct historical OOM records", result.stdout)

    def test_memory_window_summary_never_claims_zero_kernel_oom(self):
        sample = (
            "=== Memory-pressure time-series (instantaneous) ===\n"
            "sampler_budget=samples=3 interval_seconds=15\n"
            "sample_seq=1 timestamp=2026-10-25T21:23:57+0100 "
            "available_kib=182976 free_kib=156144 inactive_kib=26832\n"
            "sample_seq=2 timestamp=2026-10-25T21:24:42+0100 "
            "available_kib=128260 free_kib=55136 inactive_kib=73124\n"
            "WARN: sampled_memory_headroom=LOW_BELOW_128_MIB\n"
            "sample_seq=3 timestamp=2026-10-25T21:24:58+0100 "
            "available_kib=196532 free_kib=177332 inactive_kib=19200\n"
            "sample_scope=INSTANT_ONLY_PROCESS_NAMES_NO_ARGS\n"
            "=== End of bounded memory-pressure sampling ===\n"
        )
        for mode in ("compact", "verbose"):
            with self.subTest(mode=mode):
                result = render(sample, mode=mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Memory window · 3 samples", result.stdout)
                self.assertIn("available min=125.3 MiB", result.stdout)
                self.assertIn("max=191.9 MiB", result.stdout)
                self.assertIn("below 128 MiB=1", result.stdout)
                self.assertIn("Historical OOM events NOT_EVALUATED", result.stdout)
                self.assertNotIn("0 distinct historical OOM records", result.stdout)
                self.assertNotIn("EVIDENCE INCOMPLETE", result.stdout)

    def test_one_memory_sample_uses_singular_and_not_evaluated_oom(self):
        sample = (
            "=== Memory-pressure time-series (instantaneous) ===\n"
            "sampler_budget=samples=1 interval_seconds=15\n"
            "sample_seq=1 timestamp=2026-10-25T23:56:19+0100 "
            "available_kib=252948 free_kib=135424 inactive_kib=117524\n"
            "=== End of bounded memory-pressure sampling ===\n"
        )
        result = render(sample, mode="verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Memory window · 1 sample", result.stdout)
        self.assertIn("available min=247.0 MiB", result.stdout)
        self.assertNotIn("1 samples", result.stdout)
        self.assertIn("Historical OOM events NOT_EVALUATED", result.stdout)
        self.assertNotIn("0 distinct historical OOM records", result.stdout)

    def test_missing_sampler_samples_are_incomplete(self):
        sample = (
            "=== Memory-pressure time-series (instantaneous) ===\n"
            "sampler_budget=samples=2 interval_seconds=15\n"
            "sample_seq=1 timestamp=2026-10-25T21:23:57+0100 "
            "available_kib=182976 free_kib=156144 inactive_kib=26832\n"
        )
        result = render(sample, mode="verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INCOMPLETE", result.stdout)
        self.assertNotIn("0 distinct historical OOM records", result.stdout)

    def test_sampler_command_failure_is_incomplete(self):
        sample = (
            "=== Memory-pressure time-series (instantaneous) ===\n"
            "sampler_budget=samples=1 interval_seconds=15\n"
            "ERROR: sampler_ps_failed\n"
        )
        result = render(sample)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INCOMPLETE", result.stdout)
        self.assertNotIn("0 distinct historical OOM records", result.stdout)

    def test_zero_sections_cannot_be_presented_as_zero_oom(self):
        result = render("", mode="compact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INCOMPLETE", result.stdout)
        self.assertNotIn("0 distinct historical OOM records", result.stdout)


if __name__ == "__main__":
    unittest.main()
