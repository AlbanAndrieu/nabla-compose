"""Hermetic contract checks for the TrueNAS FastAPI AI connectivity auditor."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
FILE = ROOT / "scripts/truenas/accept-fastapi-ai-connectivity.py"
SPEC = importlib.util.spec_from_file_location("accept_fastapi_ai", FILE)
assert SPEC is not None and SPEC.loader is not None
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)


def report(*, litellm="http_200", model="visible", ollama="http_200",
           backend="http_200", frontend="http_200", inference="not_requested"):
    return {
        "component": "fastapi_ai_acceptance",
        "litellm": litellm,
        "litellm_key": "present",
        "litellm_proxy_liveness": "http_200",
        "litellm_key_format": "sk_prefix",
        "litellm_model": model,
        "litellm_inference": inference,
        "ollama": ollama,
        "ollama_models_available": True,
        "openrag_backend": backend,
        "openrag_frontend": frontend,
        "openrag_mcp": "http_405",
        "openrag_integration": "not_wired_pending_private_acl",
        "openrag_private_retrieval": "not_tested",
    }


class FastApiAiConnectivityContract(unittest.TestCase):
    def test_all_transport_gates_accept_but_do_not_claim_rag_integration(self):
        data = report()
        self.assertTrue(subject.accepted(data, inference_smoke=False))
        self.assertEqual(data["openrag_integration"], "not_wired_pending_private_acl")
        self.assertEqual(data["openrag_private_retrieval"], "not_tested")

    def test_litellm_model_visibility_and_auth_required(self):
        for data in (
            report(litellm="http_401"),
            report(litellm="http_403"),
            report(model="not_visible"),
            report(litellm="missing_key"),
            report(ollama="timeout"),
            report(backend="dns_failure"),
            report(frontend="http_503"),
        ):
            with self.subTest(data=data):
                self.assertFalse(subject.accepted(data, inference_smoke=False))

    def test_inference_is_explicit_and_consumes_no_budget_by_default(self):
        self.assertTrue(subject.accepted(report(), inference_smoke=False))
        self.assertFalse(subject.accepted(report(), inference_smoke=True))
        self.assertTrue(subject.accepted(
            report(inference="response_received"), inference_smoke=True,
        ))
        self.assertIn('os.environ.get("FASTAPI_AI_INFERENCE_SMOKE") == "1"',
                      subject.CONTAINER_PROBE)
        self.assertIn('"max_tokens": 4', subject.CONTAINER_PROBE)
        self.assertIn('"content": "Reply only OK."', subject.CONTAINER_PROBE)

    @mock.patch.object(subject.subprocess, "run")
    @mock.patch.object(subject.os, "geteuid", return_value=0)
    def test_root_docker_read_only_and_no_secret_output(self, _, execute):
        execute.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(report()), stderr="secret-in-stderr",
        )
        result = subject.inspect()
        self.assertTrue(result["raw_secrets_printed"] is False)
        self.assertNotIn("secret-in-stderr", json.dumps(result))
        cmd = execute.call_args.args[0]
        self.assertEqual(cmd[:3], ["docker", "exec", "--env"])
        self.assertIn("FASTAPI_AI_INFERENCE_SMOKE=0", cmd)
        self.assertNotIn("printenv", " ".join(cmd[:7]))
        self.assertNotIn("secret-in-stderr", json.dumps(result))

    @mock.patch.object(subject.subprocess, "run")
    @mock.patch.object(subject.os, "geteuid", return_value=1000)
    def test_nonroot_uses_noninteractive_sudo(self, _, execute):
        execute.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(report()),
        )
        subject.inspect(inference_smoke=True)
        args = execute.call_args.args[0]
        self.assertEqual(args[:3], ["sudo", "-n", "docker"])
        self.assertIn("FASTAPI_AI_INFERENCE_SMOKE=1", args)

    @mock.patch.object(subject.subprocess, "run")
    def test_malformed_or_untrusted_output_not_relied_upon(self, execute):
        for output in (
            "LITELLM_API_KEY=secret!",
            '{"unexpected":"secret"}',
            json.dumps({**report(), "litellm": "secret-private-model"}),
            json.dumps({**report(), "openrag_mcp": {"untrusted": True}}),
            json.dumps({**report(), "litellm": ["http_200"]}),
            json.dumps({**report(), "ollama": None}),
            json.dumps({**report(), "openrag_backend": 200}),
        ):
            with self.subTest(output=output[:15]):
                execute.return_value = subprocess.CompletedProcess(
                    [], 0, stdout=output,
                )
                result = subject.inspect()
                self.assertEqual(
                    result,
                    {
                        "component": "fastapi_ai_acceptance",
                        "runtime": "invalid_probe_report",
                        "raw_secrets_printed": False,
                    },
                )

    @mock.patch.object(subject.subprocess, "run")
    def test_litellm_401_stays_distinct_from_proxy_liveness(self, execute):
        rejected = {
            **report(litellm="http_401", model="not_verified"),
            "litellm_proxy_liveness": "http_200",
            "litellm_key_format": "sk_prefix",
        }
        execute.return_value = subprocess.CompletedProcess(
            [], 0, stdout=json.dumps(rejected),
        )
        result = subject.inspect()
        self.assertEqual(result["litellm"], "http_401")
        self.assertEqual(result["litellm_proxy_liveness"], "http_200")
        self.assertEqual(result["litellm_key_format"], "sk_prefix")
        self.assertFalse(subject.accepted(result, inference_smoke=False))
        self.assertTrue(result["raw_secrets_printed"] is False)

    def test_key_shape_probe_returns_labels_only(self):
        source = subject.CONTAINER_PROBE
        self.assertIn('key.startswith("sk-")', source)
        self.assertIn('else "missing" if not key else "unexpected_format"', source)
        self.assertNotIn('print(key)', source)
        self.assertNotIn('repr(key)', source)

    @mock.patch.object(subject.subprocess, "run")
    def test_docker_denial_never_prints_stderr(self, execute):
        execute.return_value = subprocess.CompletedProcess(
            [], 1, stdout="", stderr="PRIVATE_SUDO_ERROR_TOKEN",
        )
        result = subject.inspect()
        self.assertEqual(result["runtime"], "container_missing_or_docker_denied")
        self.assertNotIn("PRIVATE_SUDO_ERROR_TOKEN", json.dumps(result))

    def test_upgrade_hooks_read_only_ai_validation_after_redeploy(self):
        deployment = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        self.assertIn("accept-fastapi-ai-connectivity.py --check", deployment)
        self.assertLess(
            deployment.index("step '5/6' 'Redeploy staging and verify health'"),
            deployment.index("ai_connectivity_state='not-run'"),
        )
        self.assertNotIn("--inference-smoke", deployment)
        self.assertIn("OpenRAG HTTP available", deployment)
        self.assertIn('AI transports=%s', deployment)

    def test_probe_uses_pinned_local_urls_and_no_redirect_or_proxy(self):
        text = subject.CONTAINER_PROBE
        self.assertIn('expected_base = "http://172.17.0.24:4000"', text)
        self.assertIn("ProxyHandler({})", text)
        self.assertIn("NoRedirect", text)
        self.assertIn('"/v1/models"', text)
        self.assertIn('"/health/liveliness"', text)
        self.assertIn('"litellm_key_format"', text)
        self.assertIn('"fastapi-qwen"', text)
        self.assertIn("http://172.17.0.24:30068/api/tags", text)
        self.assertIn("http://openrag-backend:8000/health", text)
        self.assertIn("http://openrag-frontend:3000/health/collective_health", text)
        self.assertIn("http://openrag-frontend:3000/mcp", text)
        self.assertIn('read_body=False', text)
        self.assertNotIn("/search", text)
        self.assertNotIn("/key/generate", text)
        self.assertNotIn("openrag_documents", text)


if __name__ == "__main__":
    unittest.main()
