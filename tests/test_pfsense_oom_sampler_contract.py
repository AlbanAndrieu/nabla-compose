"""Offline contracts for the read-only Netgate 1100 OOM sampling session."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/sample-oom-pressure.sh"


def extract_remote_shell(source: str) -> str:
    match = re.search(
        r"(?m)^ssh[^\n]*<<'REMOTE'[^\n]*\n(?P<body>.*?)\nREMOTE(?=\n|\Z)",
        source, re.DOTALL,
    )
    if not match:
        raise AssertionError("missing remote shell heredoc")
    return match.group("body")


def run_fake_probe(*, failed=None, samples="2"):
    body = extract_remote_shell(SCRIPT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="pfsense-sampler-") as tmp:
        commands = {
            "date": "#!/bin/sh\necho 2026-10-26T02:09:00+0100\n",
            "sysctl": (
                "#!/bin/sh\n" + ("exit 45\n" if failed == "sysctl" else
                "case \"$2\" in\n"
                "vm.stats.vm.v_free_count) echo 12000;;\n"
                "vm.stats.vm.v_inactive_count) echo 8000;;\n"
                "vm.stats.vm.v_page_size) echo 4096;;\n"
                "*) exit 4;; esac\n")
            ),
            "ps": (
                "#!/bin/sh\n" + ("exit 46\n" if failed == "ps" else
                'echo "RSS %CPU COMMAND"\n'
                'echo "142000 4.2 unbound"\n'
                'echo "45000 40.0 snort"\n'
                'echo "14000 8.4 php"\n'
                'echo "12000 1.0 php-fpm"\n'
                'echo "70000 2.0 crowdsec"\n'
                'echo "500 10.0 SECRET-DO-NOT-LEAK"\n')
            ),
            "sleep": "#!/bin/sh\nexit 0\n",
        }
        for name, data in commands.items():
            path = Path(tmp) / name
            path.write_text(data, encoding="utf-8")
            path.chmod(0o755)
        env = os.environ | {"PATH": tmp + ":" + os.environ["PATH"]}
        return subprocess.run(
            ["/bin/sh", "-s", "--", samples, "5"], input=body,
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )


class PfSenseOomSamplerContract(unittest.TestCase):
    def test_validates_local_and_remote_shell(self):
        source = SCRIPT.read_text(encoding="utf-8")
        local = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True)
        self.assertEqual(local.returncode, 0, local.stderr)
        remote = subprocess.run(
            ["/bin/sh", "-n"], input=extract_remote_shell(source),
            capture_output=True, text=True,
        )
        self.assertEqual(remote.returncode, 0, remote.stderr)

    def test_invalid_budget_fails_before_ssh(self):
        for extra in (
            ("--samples", "0"), ("--samples", "17"),
            ("--samples", "16", "--interval-seconds", "30"),
            ("--interval-seconds", "4"), ("--interval-seconds", "31"),
            ("--samples", "junk"), ("--target", "host;echo_SECRET"),
            ("--port", "0"), ("--port", "65536"),
        ):
            with self.subTest(extra=extra):
                run = subprocess.run(
                    ["bash", str(SCRIPT), "--check", *extra],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                self.assertEqual(run.returncode, 2, run.stderr)

    def test_observed_groups_without_process_arguments(self):
        run = run_fake_probe()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.count("sample_seq="), 2)
        self.assertIn("available_kib=80000", run.stdout)
        self.assertIn("process_group=snort rss_sum_kib=45000", run.stdout)
        self.assertIn("process_group=unbound rss_sum_kib=142000", run.stdout)
        self.assertIn("process_group=php_fpm rss_sum_kib=12000", run.stdout)
        self.assertIn("process_group=crowdsec rss_sum_kib=70000", run.stdout)
        self.assertIn("timestamp=2026-10-26T02:09:00+0100", run.stdout)
        self.assertIn("sampled_memory_headroom=LOW_BELOW_128_MIB", run.stdout)
        self.assertNotIn("SECRET", run.stdout)

    def test_missing_kernel_memory_or_ps_is_incomplete(self):
        for failure in ("ps", "sysctl"):
            with self.subTest(failure=failure):
                output = run_fake_probe(failed=failure)
                self.assertNotEqual(output.returncode, 0)
                self.assertIn("ERROR: sampler_", output.stdout)
                self.assertNotIn("=== End of bounded", output.stdout)

    def test_no_mutation_and_no_unbounded_loop(self):
        code = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("BatchMode=yes", code)
        self.assertIn("StrictHostKeyChecking=yes", code)
        self.assertIn("<=240", code)
        self.assertIn("samples<=16", code)
        self.assertIn("rss_sum_is_not_unique_physical_ram=yes", code)
        self.assertIn("sample_scope=INSTANT_ONLY_PROCESS_NAMES_NO_ARGS", code)
        self.assertIn('ps axo rss,pcpu,comm', code)
        for forbidden in (
            "unbound-control reload", "pfctl -F", "service snort restart",
            "pkg upgrade", "sudo ", "curl ", "wget ", "fetch ",
            "kill -", "snort -D", "php /usr/local/pkg",
        ):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
