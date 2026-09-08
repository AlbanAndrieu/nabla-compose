from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "truenas" / "diagnose-sentry.sh"


class SentryDiagnosticsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = SCRIPT.read_text(encoding="utf-8")

    def test_diagnostic_is_read_only(self) -> None:
        forbidden = (
            "app.stop",
            "app.start",
            "app.update",
            "app.redeploy",
            "docker restart",
            "docker stop",
            "docker rm",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.script)

    def test_diagnostic_covers_truenas_and_docker_lifecycle(self) -> None:
        required = (
            "midclt call app.query",
            "midclt call core.get_jobs",
            "com.docker.compose.project",
            "State.Health.Status",
            "RestartCount",
            "snuba-migrate",
            "sentry-migrate",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.script)

    def test_diagnostic_distinguishes_deploying_health_starting(self) -> None:
        self.assertIn('app_state}" == "DEPLOYING"', self.script)
        self.assertIn("starting_count", self.script)
        self.assertIn("/tmp/health.txt", self.script)

    def test_diagnostic_keeps_functional_health_separate(self) -> None:
        self.assertIn("Sentry functional edge health", self.script)
        self.assertIn("Snuba API health", self.script)
        self.assertIn("TrueNAS lifecycle and functional health", self.script)


if __name__ == "__main__":
    unittest.main()
