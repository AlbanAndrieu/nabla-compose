"""Offline CrowdSec Loki evidence contracts, no Docker, SSH or network."""
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/truenas/diagnose-crowdsec-cutover.sh"
START = "pfsense_loki_event_observed=false\n"
END = "printf '\\n==> CrowdSec Loki datasource metric\\n'"


class CrowdSecLokiEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")
        assert cls.source.count(START) == 1, "Loki gate changed"
        assert cls.source.count(END) == 1, "Loki gate boundary changed"
        cls.gate = cls.source.split(START, 1)[1].split(END, 1)[0]

    def run_gate(self, scenario):
        # Replace only the read-only Loki query helper; exercise the real
        # classifier shell code without network calls, credentials or mocks
        # for pfSense/TrueNAS services.
        fixture = r"""
set -euo pipefail
SCENARIO="$1"
CALLS=0
PFSENSE_LOG_LOOKBACK=30m
pfsense_loki_event_observed=false
warnings=0
failures=0
ok() { printf 'OK: %s\n' "$*"; }
warn() { warnings=$((warnings+1)); printf 'WARN: %s\n' "$*"; }
error() { failures=$((failures+1)); printf 'ERROR: %s\n' "$*"; }
query_pfsense_loki() {
  CALLS=$((CALLS+1))
  case "$SCENARIO:$CALLS" in
    immediate:1|recovered:2|missing:3) return 0 ;;
    *) return 1 ;;
  esac
}
""" + START + self.gate + r"""
printf 'calls=%s observed=%s errors=%s warnings=%s\n' \
  "$CALLS" "$pfsense_loki_event_observed" "$failures" "$warnings"
"""
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", fixture, "fixture", scenario],
            check=False, capture_output=True, text=True, timeout=4,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_immediate_canonical_success(self):
        output = self.run_gate("immediate")
        self.assertIn("crowdsec_loki_classification=CANONICAL_CONFIRMED", output)
        self.assertIn("calls=1 observed=true errors=0 warnings=0", output)

    def test_transient_failure_recovers_once_with_warning(self):
        output = self.run_gate("recovered")
        self.assertIn("crowdsec_loki_classification=CANONICAL_RECOVERED_AFTER_RETRY", output)
        self.assertIn("calls=2 observed=true errors=0 warnings=1", output)

    def test_persistent_missing_canonical_fails_closed(self):
        output = self.run_gate("missing")
        self.assertIn("crowdsec_loki_classification=CANONICAL_MISSING_NONSMOKE_PRESENT", output)
        self.assertIn("calls=3 observed=false errors=1 warnings=0", output)

    def test_no_recent_events_fails_closed(self):
        output = self.run_gate("empty")
        self.assertIn("crowdsec_loki_classification=NO_CONFIRMED_RECENT_PFSENSE_EVENTS", output)
        self.assertIn("calls=3 observed=false errors=1 warnings=0", output)

    def test_bounded_query_and_no_mutation(self):
        self.assertIn("query_pfsense_loki() {", self.source)
        self.assertIn("--connect-timeout 4 --max-time 12", self.source)
        self.assertIn("--data-urlencode 'limit=1'", self.source)
        self.assertNotIn("docker restart", self.source)
        self.assertNotIn("midclt call -j app.redeploy", self.source)


if __name__ == "__main__":
    unittest.main()
