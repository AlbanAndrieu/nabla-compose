from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "security" / "harden-pfsense-php-fpm.sh"


class PfSensePhpFpmHardeningContractTests(unittest.TestCase):
    def test_script_is_fail_closed_and_uses_pfsense_native_restart_paths(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('SUPPORTED_RELEASE_PREFIX="26.07-RELEASE"', text)
        self.assertIn('upstream="8/3600/2/7/5000"', text)
        self.assertIn('expected="${TARGET_MAX}/${TARGET_IDLE}/${TARGET_START}/${TARGET_SPARE}/${TARGET_REQ}"', text)
        self.assertIn('TARGET_MAX=4', text)
        self.assertIn('TARGET_IDLE=30', text)
        self.assertIn('TARGET_START=1', text)
        self.assertIn('TARGET_SPARE=2', text)
        self.assertIn('TARGET_REQ=500', text)
        self.assertIn('/etc/rc.php_ini_setup', text)
        self.assertIn('run_generator()', text)
        self.assertIn('php "${SOURCE}"', text)
        self.assertIn('worker_count()', text)
        self.assertIn("ps axww -o command= | awk", text)
        self.assertIn('/etc/rc.php-fpm_restart', text)
        self.assertIn('/etc/rc.restart_webgui', text)
        self.assertIn('/var/run/php-fpm.socket', text)
        self.assertIn('changes != 5', text)
        self.assertIn('unrecognized >1000 MiB generator profile', text)
        self.assertNotIn("pgrep -fc '^php-fpm: pool nginx'", text)
        self.assertNotIn('service php-fpm', text)
        self.assertNotIn('php-fpm -y /usr/local/lib/php-fpm.conf', text)

    def test_check_recognizes_reviewed_upstream_profile_without_mutation(self) -> None:
        generator = """\
PHPFPMMAX=3
PHPFPMIDLE=30
PHPFPMSTART=1
PHPFPMSPARE=2
PHPFPMREQ=500
if [ "${REALMEM}" -lt 512 ]; then
    PHPFPMMAX=2
    PHPFPMIDLE=5
    PHPFPMSTART=1
    PHPFPMSPARE=1
    PHPFPMREQ=500
elif [ "${REALMEM}" -gt 1000 ]; then
    PHPFPMMAX=8
    PHPFPMIDLE=3600
    PHPFPMSTART=2
    PHPFPMSPARE=7
    PHPFPMREQ=5000
fi
"""
        generated = """\
[global]
process.max = 8
[nginx]
pm = dynamic
pm.process_idle_timeout = 3600
pm.max_children = 8
pm.start_servers = 2
pm.max_requests = 5000
pm.min_spare_servers=1
pm.max_spare_servers= 7
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "rc.php_ini_setup"
            config = tmp / "php-fpm.conf"
            backup = tmp / "backup"
            source.write_text(generator, encoding="utf-8")
            config.write_text(generated, encoding="utf-8")

            result = subprocess.run(
                ["/bin/sh", str(SCRIPT), "--check"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "PFSENSE_PHP_FPM_GENERATOR": str(source),
                    "PFSENSE_PHP_FPM_CONFIG": str(config),
                    "PFSENSE_PHP_FPM_BACKUP": str(backup),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("generator >1000 MiB profile: 8/3600/2/7/5000", result.stdout)
            self.assertIn("generated PHP-FPM profile: 8/3600/2/7/5000", result.stdout)
            self.assertIn("WARN: generator still uses pfSense high-memory profile", result.stdout)
            self.assertEqual(source.read_text(encoding="utf-8"), generator)
            self.assertFalse(backup.exists())

    def test_check_rejects_unknown_generator_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            source = tmp / "rc.php_ini_setup"
            config = tmp / "php-fpm.conf"
            source.write_text(
                'elif [ "${REALMEM}" -gt 1000 ]; then\n'
                '    PHPFPMMAX=16\n'
                '    PHPFPMIDLE=3600\n'
                '    PHPFPMSTART=2\n'
                '    PHPFPMSPARE=15\n'
                '    PHPFPMREQ=5000\n'
                'fi\n',
                encoding="utf-8",
            )
            config.write_text("pm.max_children = 16\n", encoding="utf-8")

            result = subprocess.run(
                ["/bin/sh", str(SCRIPT), "--check"],
                check=False,
                capture_output=True,
                text=True,
                env={
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "PFSENSE_PHP_FPM_GENERATOR": str(source),
                    "PFSENSE_PHP_FPM_CONFIG": str(config),
                    "PFSENSE_PHP_FPM_BACKUP": str(tmp / "backup"),
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unrecognized >1000 MiB generator profile", result.stderr)


if __name__ == "__main__":
    unittest.main()
