"""Contracts for the consolidated shared-PostgreSQL bootstrap (lib/postgres.sh)."""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unittest
from urllib.parse import quote, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts/lib/postgres.sh"
APP_DEPLOY_LIB = ROOT / "scripts/lib/app-deploy.sh"
BOOTSTRAP = ROOT / "scripts/truenas/bootstrap-app-postgres.sh"
BACKUP_ROLE = ROOT / "scripts/truenas/bootstrap-postgres-backup-role.sh"
WRAPPERS = {
    "joplin": ROOT / "scripts/truenas/bootstrap-joplin-postgres.sh",
    "scanopy": ROOT / "scripts/truenas/bootstrap-scanopy-postgres.sh",
    "homeassistant": ROOT / "scripts/truenas/bootstrap-homeassistant-postgres.sh",
}
SECURITY_WRAPPER = ROOT / "scripts/truenas/bootstrap-security-tooling-postgres.sh"
RUNTIME = "/mnt/cpool/secrets/runtime"
TABLE = {
    "homeassistant": ("homeassistant", "homeassistant", "POSTGRES_PASSWORD", f"{RUNTIME}/homeassistant/.env.secrets"),
    "joplin": ("joplin", "joplin", "POSTGRES_PASSWORD", f"{RUNTIME}/joplin/.env.secrets"),
    "scanopy": ("scanopy", "scanopy", "POSTGRES_PASSWORD", f"{RUNTIME}/scanopy/.env.secrets"),
    "plumber": ("jobs", "jobs", "JOBS_DB_PASSWORD", f"{RUNTIME}/plumber/.env.secrets"),
    "netbox": ("netbox", "netbox", "DB_PASSWORD", f"{RUNTIME}/netbox/.env.secrets"),
    "dependency-track": ("dependencytrack", "dependencytrack", "ALPINE_DATABASE_PASSWORD", f"{RUNTIME}/dependency-track/.env.secrets"),
    "defectdojo": ("defectdojo", "defectdojo", "DD_DATABASE_URL", f"{RUNTIME}/defectdojo/.env.secrets"),
    "keycloak": ("keycloak", "keycloak", "KC_DB_PASSWORD", "/mnt/cpool/keycloak/.env.secrets"),
}
FAKE_DOCKER = r"""#!/usr/bin/env bash
# Hermetic docker stand-in: records argv, environment hand-off and stdin.
record="${FAKE_DOCKER_DIR:?}"
printf '%s\n' "$*" >>"${record}/argv"
printf 'NABLA_DB_PASSWORD=%s\nPGPASSWORD=%s\n' "${NABLA_DB_PASSWORD:-}" "${PGPASSWORD:-}" >>"${record}/env"
case "$1" in
  ps) printf 'ix-postgres-postgres-1\n' ;;
  exec)
    if [[ "$*" == *'printf "%s" "${POSTGRES_USER:-postgres}"'* ]]; then
      printf 'postgres'
    elif [[ "$*" == *" -i "* ]]; then
      cat >>"${record}/stdin"
    elif [[ "$*" == *"SELECT 1"* ]]; then
      printf '1\n'
    else
      printf '1|1|joplin\n'
    fi
    ;;
esac
"""


def run(*args: str, env: dict[str, str] | None = None, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), capture_output=True, text=True, check=False, cwd=cwd, env=env)


class SyntaxAndStructureTests(unittest.TestCase):
    def test_bash_syntax(self) -> None:
        for path in (LIB, APP_DEPLOY_LIB, BOOTSTRAP, BACKUP_ROLE, SECURITY_WRAPPER, *WRAPPERS.values()):
            with self.subTest(script=path.name):
                result = run("bash", "-n", str(path))
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_library_is_read_only_when_sourced_and_never_prints_secrets(self) -> None:
        text = LIB.read_text(encoding="utf-8")
        self.assertIn("com.docker.compose.project=ix-postgres", text)
        self.assertIn("CREATE ROLE %I LOGIN PASSWORD %L", text)
        self.assertIn("ALTER ROLE %I PASSWORD %L", text)
        self.assertIn("CREATE DATABASE %I OWNER %I", text)
        self.assertIn("ALTER DATABASE %I OWNER TO %I", text)
        self.assertIn("docker exec -e PGPASSWORD", text)
        self.assertNotIn("echo ${NABLA_DB_PASSWORD}", text)
        self.assertNotIn("--password", text)
        # Sourcing must define functions only: no top-level docker/psql call
        # (heredoc bodies are data, not shell).
        shell_only = re.sub(r"<<'(SQL|PY)'\n.*?\n\1\n", "<<HEREDOC\n", text, flags=re.S)
        top_level = [line for line in shell_only.splitlines() if line and not line[0].isspace() and not line.startswith("#")]
        self.assertTrue(all(line.endswith("() {") or line == "}" for line in top_level), top_level)

    def test_wrappers_delegate_to_the_consolidated_script(self) -> None:
        for app, path in WRAPPERS.items():
            with self.subTest(app=app):
                text = path.read_text(encoding="utf-8")
                self.assertIn('exec bash "${SCRIPT_DIR}/bootstrap-app-postgres.sh" "${1:---check}" ' + app, text)
                self.assertIn(f"{app.upper()}_SECRETS_FILE", text)
                self.assertLess(len(text.splitlines()), 15)
        security = SECURITY_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("plumber | netbox | dependency-track | defectdojo", security)
        self.assertIn('exec bash "${SCRIPT_DIR}/bootstrap-app-postgres.sh" "${MODE}" "${APP}"', security)
        self.assertNotEqual(run("bash", str(SECURITY_WRAPPER), "--check", "scanopy").returncode, 0)

    def test_backup_role_uses_the_shared_library(self) -> None:
        text = BACKUP_ROLE.read_text(encoding="utf-8")
        self.assertIn("lib/postgres.sh", text)
        self.assertIn("postgres_shared_container", text)
        self.assertIn("postgres_database_exists", text)
        self.assertIn("postgres_assert_login", text)
        self.assertNotIn("docker ps", text)


class ConsolidatedBootstrapTests(unittest.TestCase):
    def test_describe_table_matches_the_compose_contracts(self) -> None:
        for app, (role, database, key, secret_file) in TABLE.items():
            with self.subTest(app=app):
                result = run("bash", str(BOOTSTRAP), "--describe", app)
                self.assertEqual(result.returncode, 0, result.stderr)
                fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
                self.assertEqual(fields["role"], role)
                self.assertEqual(fields["database"], database)
                self.assertEqual(fields["secret_key"], key)
                self.assertEqual(fields["secret_file"], secret_file)
                self.assertEqual(fields["host"], "172.17.0.24")
        self.assertEqual(
            dict(line.split("=", 1) for line in run("bash", str(BOOTSTRAP), "--describe", "scanopy").stdout.splitlines())["url_key"],
            "SCANOPY_DATABASE_URL",
        )
        self.assertEqual(
            dict(line.split("=", 1) for line in run("bash", str(BOOTSTRAP), "--describe", "defectdojo").stdout.splitlines())["password_source"],
            "url",
        )

    def test_argument_validation_happens_before_any_privilege_or_runtime_access(self) -> None:
        self.assertEqual(run("bash", str(BOOTSTRAP), "--bogus", "joplin").returncode, 1)
        self.assertEqual(run("bash", str(BOOTSTRAP), "--check").returncode, 1)
        unsupported = run("bash", str(BOOTSTRAP), "--check", "not-an-app")
        self.assertEqual(unsupported.returncode, 1)
        self.assertIn("unsupported app", unsupported.stderr)

    def test_check_mode_is_explicitly_non_mutating(self) -> None:
        text = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn("--check | --apply | --describe", text)
        self.assertIn('if [[ "${MODE}" == "--apply" ]]; then', text)
        self.assertIn("postgres_ensure_role_database", text)
        self.assertIn('"${APP}_postgres_mutations=0"', text)
        self.assertIn("dedicated role cannot authenticate", text)
        self.assertIn("password differs from", text)
        self.assertIn("unset db_password", text)
        self.assertNotIn('printf "%s" "${db_password}"', text)


class LibraryBehaviourTests(unittest.TestCase):
    """Drive lib/postgres.sh against a recording docker stand-in."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        self.record = Path(self.tmp.name) / "record"
        self.record.mkdir()
        docker = self.bin / "docker"
        docker.write_text(FAKE_DOCKER, encoding="utf-8")
        docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_DOCKER_DIR=str(self.record))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def bash(self, script: str, **extra: str) -> subprocess.CompletedProcess[str]:
        return run("bash", "-c", f'source "{LIB}"\n{script}', env={**self.env, **extra})

    def test_container_and_admin_resolution(self) -> None:
        result = self.bash('c="$(postgres_shared_container)"; a="$(postgres_admin_role "$c")"; printf "%s %s" "$c" "$a"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "ix-postgres-postgres-1 postgres")
        override = self.bash('postgres_shared_container', NABLA_POSTGRES_CONTAINER="custom-pg")
        self.assertEqual(override.stdout.strip(), "custom-pg")

    def test_provisioning_passes_the_password_through_the_environment_only(self) -> None:
        secret = "synthetic-fixture-not-a-runtime-credential"
        result = self.bash(
            'NABLA_DB_PASSWORD="$1" postgres_ensure_role_database ix-postgres-postgres-1 postgres joplin joplin',
        )
        self.assertNotEqual(result.returncode, 0)  # NABLA_DB_PASSWORD was not provided
        result = run(
            "bash", "-c",
            f'source "{LIB}"; NABLA_DB_PASSWORD="{secret}" postgres_ensure_role_database ix-postgres-postgres-1 postgres joplin joplin',
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = (self.record / "argv").read_text(encoding="utf-8")
        self.assertNotIn(secret, argv)
        self.assertIn("-e NABLA_DB_PASSWORD -e NABLA_DB_USER=joplin -e NABLA_DB_NAME=joplin", argv)
        self.assertIn(f"NABLA_DB_PASSWORD={secret}", (self.record / "env").read_text(encoding="utf-8"))
        self.assertIn("CREATE ROLE %I LOGIN PASSWORD %L", (self.record / "stdin").read_text(encoding="utf-8"))
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_login_check_and_identifier_validation(self) -> None:
        ok = run("bash", "-c", f'source "{LIB}"; PGPASSWORD=pw postgres_assert_login ix-postgres-postgres-1 joplin joplin', env=self.env)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertNotIn("pw", (self.record / "argv").read_text(encoding="utf-8").replace("PGPASSWORD", ""))
        bad = self.bash('postgres_role_database_state ix-postgres-postgres-1 postgres "Bad-Name" joplin')
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(self.bash('postgres_identifier_valid joplin && echo yes').stdout.strip(), "yes")
        self.assertNotEqual(self.bash('postgres_identifier_valid "x;drop"').returncode, 0)

    def test_url_components_are_parsed_without_leaking_the_url(self) -> None:
        # Built at runtime so no credential-shaped URI literal sits in the test source.
        user, test_value, authority = "scanopy", "fixture" + chr(64) + "token", "172.17.0.24:5432"
        password = quote(test_value)
        url = urlunsplit(("postgresql", f"{user}:{password}@{authority}", "/scanopy", "", ""))
        for component, expected in (("user", "scanopy"), ("password", test_value), ("host", "172.17.0.24"), ("port", "5432"), ("database", "scanopy")):
            result = self.bash(f'postgres_url_component {component}', NABLA_DB_URL=url)
            self.assertEqual(result.stdout, expected, result.stderr)
        other_scheme = urlunsplit(("mysql", "a:b@c", "/d", "", ""))
        rejected = self.bash("postgres_url_component user", NABLA_DB_URL=other_scheme)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertNotIn(other_scheme, rejected.stderr)


if __name__ == "__main__":
    unittest.main()
