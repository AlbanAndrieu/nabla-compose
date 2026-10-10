"""Contracts for the repository-owned OWASP DSOMM deployment."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps" / "dsomm" / "compose.yml"
META = ROOT / "apps" / "dsomm" / "config" / "meta.yaml"
DOCKERFILE = ROOT / "apps" / "dsomm" / "baseline" / "Dockerfile"
RUNNER = ROOT / "apps" / "dsomm" / "baseline" / "run-baseline.sh"
README = ROOT / "apps" / "dsomm" / "README.md"
INITIAL_REVIEW = ROOT / "apps" / "dsomm" / "INITIAL_REVIEW.md"
SEED_ACTIVITIES = ROOT / "apps" / "dsomm" / "config" / "seed-activities.yaml"
MODEL_INDEX = ROOT / "apps" / "dsomm" / "config" / "model-activity-index.json"
SEED_PROGRESS = ROOT / "apps" / "dsomm" / "config" / "team-progress.seed.yaml"
SEED_EVIDENCE = ROOT / "apps" / "dsomm" / "config" / "team-evidence.seed.yaml"
SEED_VALIDATOR = ROOT / "scripts" / "dsomm" / "validate-seed.py"
DEPLOY = ROOT / "scripts" / "truenas" / "deploy-dsomm.sh"


class DsommContractTests(unittest.TestCase):
    def test_ui_service_is_internal_repository_owned_dsomm(self) -> None:
        payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = payload["services"]["dsomm"]
        self.assertIn("wurstbrot/dsomm:4.4.1", service["image"])
        port = service["ports"][0]
        self.assertEqual(8080, port["target"])
        self.assertEqual("31088", port["published"])
        self.assertEqual("172.17.0.24", port["host_ip"])
        self.assertEqual("dsomm", service["x-nabla"]["id"])
        self.assertEqual("planned", service["x-nabla"]["status"])
        self.assertIn("healthcheck", service)
        self.assertEqual(["ALL"], service["cap_drop"])
        self.assertEqual(["NET_BIND_SERVICE"], service["cap_add"])
        self.assertNotIn("privileged", service)
        self.assertIn("no-new-privileges=true", service["security_opt"])
        self.assertEqual("truenas-app", service["x-nabla"]["runtime"]["provider"])
        self.assertEqual(31088, service["x-nabla"]["monitoring"]["port"])
        self.assertTrue(
            any("/srv/assets/YAML/meta.yaml:ro" in volume for volume in service["volumes"])
        )
        self.assertTrue(
            any(
                "team-progress.yaml:/srv/assets/YAML/team-progress.yaml:ro" in volume
                for volume in service["volumes"]
            )
        )
        self.assertTrue(
            any(
                "team-evidence.yaml:/srv/assets/YAML/team-evidence.yaml:ro" in volume
                for volume in service["volumes"]
            )
        )
        self.assertTrue(
            any(
                "model.yaml:/srv/assets/YAML/default/model.yaml:ro" in volume
                for volume in service["volumes"]
            )
        )

    def test_direct_smoke_keeps_caddy_file_capability(self) -> None:
        script = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("--cap-drop ALL", script)
        self.assertIn("--cap-add NET_BIND_SERVICE", script)
        self.assertIn('if [[ "${MODE}" == "--check" && "${state}" == "STOPPED" ]]', script)
        self.assertIn("--security-opt no-new-privileges=true", script)
        self.assertNotIn("--privileged", script)

    def test_baseline_is_manual_pinned_and_secret_backed(self) -> None:
        payload = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
        service = payload["services"]["dsomm-baseline"]
        self.assertEqual(["manual"], service["profiles"])
        self.assertEqual("planned", service["x-nabla"]["status"])
        self.assertEqual("no", service["restart"])
        env_file = service["env_file"][0]
        self.assertEqual("/mnt/cpool/secrets/runtime/dsomm/.env.secrets", env_file["path"])
        self.assertFalse(env_file["required"])
        self.assertNotIn("GH_TOKEN", service.get("environment", {}))
        self.assertIn("/mnt/cpool/dsomm/reports:/reports", service["volumes"])
        self.assertTrue(
            any(
                "repository-contexts.yaml:/config/repository-contexts.yaml:ro" in volume
                for volume in service["volumes"]
            )
        )
        self.assertTrue(service["read_only"])
        self.assertEqual(["ALL"], service["cap_drop"])
        self.assertIn("no-new-privileges=true", service["security_opt"])
        self.assertIn("/tmp:rw,noexec,nosuid,nodev,size=64m", service["tmpfs"])
        self.assertIn("AlbanAndrieu/fastapi-sample", service["environment"]["DSOMM_BASELINE_REPOS"])
        self.assertEqual(
            "${DSOMM_BASELINE_SUMMARY_OUTPUT:-/reports/dsomm-baseline.md}",
            service["environment"]["DSOMM_BASELINE_SUMMARY_OUTPUT"],
        )
        self.assertEqual("automates", service["x-nabla"]["relations"][0]["type"])
        self.assertIn(
            "3255561bc9162e335d2c79b72e12b1478075e610",
            COMPOSE.read_text(encoding="utf-8"),
        )

    def test_baseline_image_and_runner_fail_closed(self) -> None:
        dockerfile = DOCKERFILE.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("python:3.13-slim", dockerfile)
        self.assertIn(
            "apt-get install -y --no-install-recommends ca-certificates git gh",
            dockerfile,
        )
        self.assertIn("git -C /opt/dsomm-baseline fetch --depth 1 origin", dockerfile)
        self.assertIn("rev-parse HEAD", dockerfile)
        self.assertIn("DSOMM_BASELINE_REF", dockerfile)
        self.assertIn("PyYAML==6.0.3", dockerfile)
        self.assertIn("tabulate==0.10.0", dockerfile)
        self.assertNotIn("-r /opt/dsomm-baseline/requirements.txt", dockerfile)
        self.assertIn('[[ -n "${GH_TOKEN:-}" ]]', runner)
        self.assertIn("/reports/*", runner)
        self.assertIn("gh auth status --hostname github.com", runner)
        self.assertIn("ALL", runner)
        self.assertIn("summarize-dsomm-baseline.py", dockerfile)
        self.assertIn("summarize-dsomm-baseline.py", runner)
        self.assertIn('chmod 0600 "${output}"', runner)
        self.assertIn("DSOMM_BASELINE_SUMMARY_OUTPUT", runner)
        self.assertIn("--context-map /config/repository-contexts.yaml", runner)

    def test_default_meta_uses_nabla_contexts_without_evidence_in_git(self) -> None:
        payload = yaml.safe_load(META.read_text(encoding="utf-8"))
        self.assertEqual(
            ["Nabla Platform", "Nabla Applications"],
            payload["teams"],
        )
        self.assertEqual(["default/model.yaml"], payload["activityFiles"])
        self.assertNotIn("evidence", payload)
        self.assertEqual("team-evidence.yaml", payload["teamEvidenceFile"])

    def test_deployer_uses_supported_truenas_custom_app_path(self) -> None:
        text = DEPLOY.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("#!/usr/bin/env bash"))
        self.assertIn('MODE="${1:---check}"', text)
        self.assertIn("bootstrap-repository-storage.sh", text)
        self.assertIn("team-progress.yaml", text)
        self.assertIn("team-evidence.yaml", text)
        self.assertIn("team-progress.seed.yaml", text)
        self.assertIn("team-evidence.seed.yaml", text)
        self.assertIn("wurstbrot/dsomm:4.4.1", text)
        self.assertIn("docker manifest inspect", text)
        self.assertIn("a2c1b7e6c7cc22de0d478027d76fd8d02c41fd7a", text)
        self.assertIn('state_root="/mnt/cpool/dsomm/state"', text)
        self.assertIn('model_file="${state_root}/model.yaml"', text)
        self.assertIn("version: ${DSOMM_MODEL_VERSION}", text)
        self.assertIn("python3 scripts/dsomm/validate-seed.py", text)
        self.assertIn('install -m 0600 "${state_seed}" "${state_file}"', text)
        self.assertNotIn("printf '%s:\\n' \"${state_key}\"", text)
        self.assertIn("chmod 0600", text)
        self.assertIn("DSOMM direct container smoke", text)
        self.assertIn("docker network inspect intranet", text)
        self.assertIn("docker run -d \\", text)
        self.assertNotIn("docker run -d --rm", text)
        self.assertIn("trap cleanup_dsomm_smoke EXIT", text)
        self.assertIn("docker logs --tail 80", text)
        self.assertIn("exit_code={{.State.ExitCode}}", text)
        self.assertIn("error={{.State.Error}}", text)
        self.assertIn("wget -q --spider http://127.0.0.1:8080/", text)
        self.assertIn("runtime_compose_json", text)
        self.assertIn("docker compose -f", text)
        self.assertIn("config --format json", text)
        self.assertIn('del(.["x-nabla"])', text)
        self.assertIn('custom_compose_config: $compose', text)
        self.assertIn('custom_compose_config_string', text)
        self.assertNotIn("include:\\n  - %s", text)
        self.assertIn('if [[ "${state}" == "STOPPED" ]]', text)
        self.assertIn('truenas_job_compact app.start "${APP_ID}"', text)
        self.assertIn("docker pull", text)
        self.assertIn("truenas_lifecycle_mark", text)
        self.assertIn("truenas_lifecycle_errors_since", text)
        self.assertIn("core.get_jobs", text)
        self.assertIn("arguments intentionally omitted", text)
        self.assertIn("truenas_wait_app_running", text)
        self.assertIn("generate-service-topology.py --check", text)
        self.assertIn("generate-service-consumers.py --check", text)
        self.assertIn("x-nabla.status remains planned", text)

    def test_apply_preserves_existing_dsomm_model(self) -> None:
        script = DEPLOY.read_text(encoding="utf-8")
        self.assertIn('if [[ -e "${model_file}" || -L "${model_file}" ]]', script)
        self.assertIn(
            "preserving existing pinned DSOMM model without replacement",
            script,
        )
        self.assertIn("existing DSOMM model version mismatch", script)
        self.assertIn("existing DSOMM model contains no activity UUIDs", script)
        self.assertIn('else\n    model_tmp="$(mktemp', script)
        self.assertIn('install -o root -g root -m 0600 "${model_tmp}" "${model_file}"', script)

    def test_deployer_fails_closed_if_truenas_loses_caddy_capability(self) -> None:
        script = DEPLOY.read_text(encoding="utf-8")
        self.assertIn(
            '(.services.dsomm.cap_add // [] | index("NET_BIND_SERVICE") != null)',
            script,
        )
        self.assertIn(
            '(.services.dsomm.cap_drop // [] | index("ALL") != null)',
            script,
        )
        self.assertIn(
            '(.services.dsomm.security_opt // [] | index("no-new-privileges=true") != null)',
            script,
        )
        self.assertIn(
            "live container lacks NET_BIND_SERVICE", script
        )
        self.assertIn(
            "DSOMM runtime NET_BIND_SERVICE capability present", script
        )
        self.assertNotIn("--privileged", script)

    def test_assessment_seed_is_offline_validated_and_conservative(self) -> None:
        activities = yaml.safe_load(SEED_ACTIVITIES.read_text(encoding="utf-8"))
        progress = yaml.safe_load(SEED_PROGRESS.read_text(encoding="utf-8"))
        evidence = yaml.safe_load(SEED_EVIDENCE.read_text(encoding="utf-8"))

        self.assertEqual("5.0.2", activities["model"]["version"])
        self.assertEqual(
            "a2c1b7e6c7cc22de0d478027d76fd8d02c41fd7a",
            activities["model"]["sourceCommit"],
        )
        self.assertEqual(
            {"Nabla Platform", "Nabla Applications"},
            {
                team
                for activity in progress["progress"].values()
                for team in activity
            },
        )
        self.assertEqual(
            "Fully implemented",
            list(
                progress["progress"]["066084c6-1135-4635-9cc5-9e75c7c5459f"][
                    "Nabla Platform"
                ]
            )[-1],
        )
        pra = progress["progress"]["c72da779-86cc-45b1-a339-190ce5093171"][
            "Nabla Platform"
        ]
        self.assertIn("Partly implemented", pra)
        self.assertNotIn("Fully implemented", pra)

        evidence_text = SEED_EVIDENCE.read_text(encoding="utf-8")
        self.assertIn("target was breached", evidence_text)
        self.assertIn("RPO was not exercised", evidence_text)
        self.assertIn("master as unprotected", evidence_text)
        self.assertTrue(evidence["evidence"])
        self.assertTrue(SEED_VALIDATOR.is_file())

    def test_conservative_seed_matches_full_pinned_model_index(self) -> None:
        seed = yaml.safe_load(SEED_ACTIVITIES.read_text(encoding="utf-8"))
        model_index = json.loads(MODEL_INDEX.read_text(encoding="utf-8"))

        self.assertEqual(seed["model"]["version"], model_index["model"]["version"])
        self.assertEqual(
            seed["model"]["sourceCommit"],
            model_index["model"]["sourceCommit"],
        )
        self.assertEqual(249, len(model_index["activities"]))
        self.assertEqual(22, len(seed["activities"]))

        for activity_uuid, activity in seed["activities"].items():
            with self.subTest(activity_uuid=activity_uuid):
                canonical = model_index["activities"][activity_uuid]
                self.assertEqual(activity["name"], canonical["name"])
                self.assertEqual(activity["level"], canonical["level"])

    def test_readme_keeps_baseline_as_supporting_evidence(self) -> None:
        text = README.read_text(encoding="utf-8")
        self.assertIn("evidence", text.lower())
        self.assertIn("not a maturity verdict", text)
        self.assertIn("least privilege", text)
        self.assertIn("Not Supported - Manual Process", text)
        self.assertIn("DSOMM 5.0", text)
        self.assertIn("Agentic AI", text)
        self.assertIn("Identity", text)
        self.assertIn("INITIAL_REVIEW.md", text)

        initial = INITIAL_REVIEW.read_text(encoding="utf-8")
        self.assertIn("pre-fill aid", initial)
        self.assertIn("Nabla Platform", initial)
        self.assertIn("Nabla Applications", initial)
        self.assertIn("AlbanAndrieu/fastapi-sample", initial)
        self.assertIn("AlbanAndrieu/nabla-site-alban", initial)
        self.assertIn("AlbanAndrieu/nabla-site-bababou", initial)
        self.assertIn("Do not convert", initial)


if __name__ == "__main__":
    unittest.main()
