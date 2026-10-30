"""Offline contract tests: no DNS, Docker, LLM call, CI or browser needed."""
from __future__ import annotations

import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/truenas/diagnose-fastapi-stack.py'
spec = importlib.util.spec_from_file_location('fastapi_stack_consolidated', SCRIPT)
assert spec and spec.loader
stack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stack)


class FakeResponse:
    def __init__(self, status):
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class FakeOpener:
    def __init__(self, code):
        self.code = code
    def open(self, request, timeout):
        return FakeResponse(self.code)


class ContractTests(unittest.TestCase):
    def test_ui_http_success_is_transport_only(self):
        with patch.object(stack, 'build_opener', return_value=FakeOpener(200)):
            rows = stack.ui_http()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['verdict'] == 'PASS' for r in rows))
        self.assertEqual(rows[-1]['services_http'], 200)

    def test_ui_http_403_is_denied_not_service_failure(self):
        with patch.object(stack, 'build_opener', return_value=FakeOpener(403)):
            rows = stack.ui_http()
        self.assertTrue(all(r['verdict'] == 'DENIED' for r in rows))
        self.assertEqual(rows[0]['state'], 'authorization_or_access_policy')

    def test_json_scraper_error_does_not_echo_exception(self):
        with patch.object(stack, 'get_json', side_effect=OSError('TOKEN=PRIVATE')):
            records, evidence = stack.prometheus()
        self.assertEqual(records[0]['verdict'], 'UNVERIFIED')
        self.assertNotIn('PRIVATE', str(records))
        self.assertEqual(evidence, {})

    def test_upstream_key_absent_is_fail(self):
        with patch.object(stack, 'child_report', return_value=('nonzero', {
            'host_context': 'truenas_verified',
            'truenas_upstream_key_state': 'missing_runtime_upstream_key',
            'workstation_liveliness': 'http_200',
        })):
            result = stack.upstream()[0]
        self.assertEqual(result['verdict'], 'FAIL')

    def test_two_key_states_differ(self):
        report = {'checks': {
            'LITELLM_API_KEY': {'container_state': 'container_key_present',
                                'file_state': 'file_key_ambiguous',
                                'file_vs_container': 'not_comparable'},
            'LITELLM_FASTAPI_WORKSTATION_API_KEY': {'container_state': 'container_key_absent',
                                                   'file_state': 'file_key_ambiguous',
                                                   'file_vs_container': 'not_comparable'},
        }}
        with patch.object(stack, 'child_report', return_value=('nonzero', report)):
            rows = stack.lite_keys()
        self.assertEqual(rows[0]['verdict'], 'UNVERIFIED')
        self.assertEqual(rows[1]['verdict'], 'FAIL')

    def test_mcp_406_is_not_handshake_success(self):
        report = {'component': 'fastapi_truenas_ai_rag',
                  'declared': {'fastapi_openrag_mcp': 'not_wired_pending_private_acl'},
                  'runtime': {'litellm': 'http_200', 'ollama': 'http_200',
                              'openrag_backend': 'http_200', 'openrag_mcp': 'http_406'}}
        with patch.object(stack, 'child_report', return_value=('nonzero', report)):
            rows = stack.ai_chain()
        self.assertEqual(next(r for r in rows if r['component'] == 'ai_transport_openrag_mcp')['verdict'],
                         'UNVERIFIED')
        self.assertEqual(next(r for r in rows if r['component'] == 'ai_openrag_integration')['state'],
                         'private_acl_pending')

    def test_ai_connectivity_401_is_denied_and_no_inference(self):
        called = []
        def fake(script, *args, **kwargs):
            called.append((script, args))
            return ('nonzero', {'component': 'fastapi_ai_acceptance', 'litellm': 'http_401',
                                'litellm_model': 'not_visible', 'openrag_mcp': 'http_406'})
        with patch.object(stack, 'child_report', side_effect=fake):
            rows = stack.ai_connectivity()
        self.assertEqual(rows[0]['verdict'], 'DENIED')
        self.assertEqual(rows[4]['verdict'], 'UNVERIFIED')
        self.assertNotIn('--inference-smoke', called[0][1])

    def test_readiness_healthy_is_only_readiness(self):
        report = {'services': [{'service': 'openrag', 'state': 'RUNNING', 'status': 'HEALTHY'},
                               {'service': 'litellm', 'state': 'RUNNING', 'status': 'HEALTHY'},
                               {'service': 'prometheus', 'state': 'RUNNING', 'status': 'HEALTHY'}]}
        with patch.object(stack, 'child_report', return_value=('ok', report)):
            rows = stack.readiness()
        self.assertTrue(all(r['state'] == 'readiness_healthy' for r in rows))

    def test_metrics_script_missing_is_not_run(self):
        self.assertEqual(stack.metrics_auth(None)[0]['verdict'], 'NOT_RUN')

    def test_browser_not_run_without_checkout(self):
        self.assertEqual(stack.browser(None)[0]['verdict'], 'NOT_RUN')

    def test_browser_preflight_missing_skips_navigation(self):
        with patch.object(stack, 'run', return_value=('nonzero', {'state': 'playwright_python_missing'}, '')) as run:
            with patch.object(Path, 'is_file', return_value=True):
                rows = stack.browser(Path('/tmp/fake'))
        self.assertEqual(rows[0]['verdict'], 'NOT_RUN')
        self.assertEqual(run.call_count, 1)

    def test_deep_prometheus_exit_1_with_valid_config_is_pass_for_config_only(self):
        output = ('host and mounted Prometheus config match\n'
                  'running-container Prometheus config is syntactically valid\n'
                  'one or more Prometheus targets are not UP')
        with patch.object(Path, 'is_file', return_value=True):
            with patch.object(stack, 'run', return_value=('nonzero', {}, output)):
                row = stack.deep_prometheus()[0]
        self.assertEqual(row['verdict'], 'PASS')
        self.assertEqual(row['state'], 'config_valid_and_in_sync')

    def test_untrusted_child_data_filtered(self):
        r = stack.row('safe', 'UNVERIFIED', 'secret=sk-fake', extra='PASSWORD: SECRET')
        self.assertEqual(r['state'], 'unverified')
        self.assertNotIn('extra', r)

    def test_scope_ui_no_ai_or_prometheus_calls(self):
        with patch.object(stack, 'ui_http', return_value=[stack.row('ui', 'DENIED', 'restricted')]):
            with patch.object(stack, 'prometheus', side_effect=AssertionError('should not probe')):
                with patch.object(stack, 'readiness', side_effect=AssertionError('should not probe')):
                    with redirect_stdout(io.StringIO()) as output:
                        exit_code = stack.main(['--check', '--scope', 'ui', '--json'])
        self.assertEqual(exit_code, 2)
        data = json.loads(output.getvalue())
        self.assertEqual(data['summary']['DENIED'], 1)

    def test_no_false_success_for_incomplete(self):
        with patch.object(stack, 'ui_http', return_value=[stack.row('ui', 'NOT_RUN', 'browser_not_installed')]):
            with redirect_stdout(io.StringIO()) as output:
                code = stack.main(['--check', '--scope', 'ui', '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['decision'], 'INCOMPLETE')

    def test_ai_outside_truenas_does_not_use_local_docker(self):
        with patch.object(stack, 'is_truenas', return_value=False):
            with patch.object(stack, 'readiness', side_effect=AssertionError('wrong Docker host')):
                with redirect_stdout(io.StringIO()) as output:
                    code = stack.main(['--check', '--scope', 'ai', '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['checks'][0]['state'],
                         'truenas_host_required')

    def test_openrag_misconfigured_is_not_pass(self):
        with patch.object(Path, 'is_file', return_value=True):
            with patch.object(stack, 'run', return_value=('nonzero', {},
                    'BLOCKED: frontend is not running+healthy')):
                result = stack.openrag_dependencies()[0]
        self.assertEqual(result['verdict'], 'FAIL')

    def test_fail_returns_code_one(self):
        with patch.object(stack, 'ui_http', return_value=[stack.row('ui', 'FAIL', 'bad')]):
            with redirect_stdout(io.StringIO()) as output:
                code = stack.main(['--check', '--scope', 'ui', '--json'])
        self.assertEqual(code, 1)

    def test_brief_filters_pass_and_deduplicates_only_proven_litellm_root_cause(self):
        rows = [
            stack.row('ui_truenas', 'PASS', 'three_http_200'),
            stack.row('litellm_upstream_key', 'FAIL', 'container_key_absent'),
            stack.row('litellm_upstream', 'FAIL', 'missing_runtime_upstream_key'),
            stack.row('litellm', 'DENIED', 'authenticated_request_denied'),
            stack.row('openrag_mcp', 'UNVERIFIED', 'mcp_handshake_not_verified'),
            stack.row('ai_transport_openrag_mcp', 'UNVERIFIED', 'mcp_protocol_not_authenticated'),
            stack.row('openrag_private_retrieval', 'NOT_RUN', 'private_retrieval_not_verified'),
        ]
        compact = stack.brief_rows(rows)
        names = [r['component'] for r in compact]
        self.assertNotIn('ui_truenas', names)
        self.assertIn('litellm_upstream_key', names)
        self.assertNotIn('litellm_upstream', names)
        self.assertIn('litellm', names)
        self.assertIn('openrag_mcp', names)
        self.assertNotIn('ai_transport_openrag_mcp', names)
        self.assertIn('openrag_private_retrieval', names)
        self.assertEqual(stack.summarize(rows)['FAIL'], 2)

    def test_brief_does_not_hide_distinct_upstream_failure(self):
        rows = [
            stack.row('litellm_upstream_key', 'FAIL', 'container_key_absent'),
            stack.row('litellm_upstream', 'FAIL', 'workstation_unreachable'),
        ]
        self.assertEqual(len(stack.brief_rows(rows)), 2)

    def test_brief_option_remains_readonly_and_reports_raw_summary(self):
        with patch.object(stack, 'ui_http', return_value=[
            stack.row('ui_truenas', 'PASS', 'three_http_200'),
            stack.row('ui_cloud', 'DENIED', 'authorization_or_access_policy'),
        ]):
            with redirect_stdout(io.StringIO()) as output:
                code = stack.main(['--check', '--scope', 'ui', '--brief'])
        self.assertEqual(code, 2)
        self.assertIn('ui_cloud', output.getvalue())
        self.assertNotIn('ui_truenas', output.getvalue())
        self.assertIn('PASS=1', output.getvalue())
        self.assertIn('DENIED=1', output.getvalue())

    def test_vaultwarden_operator_requires_own_shell(self):
        with patch.object(stack.os, 'geteuid', return_value=0):
            with patch.object(stack, 'run', side_effect=AssertionError('no bw under sudo')):
                result = stack.vaultwarden_operator()
        self.assertEqual(result[0]['state'], 'unprivileged_operator_required')

    def test_vaultwarden_unlocked_without_session_export(self):
        with patch.object(stack.os, 'geteuid', return_value=1000), \
             patch.dict(stack.os.environ, {'BW_SESSION': ''}), \
             patch.object(stack, 'run', return_value=('ok', {
                  'status': 'unlocked', 'serverUrl': 'PRIVATE-URL'}, '')):
            result = stack.vaultwarden_operator()
        self.assertEqual(result[0]['state'], 'bw_session_export_missing')
        self.assertNotIn('PRIVATE-URL', str(result))
        self.assertIn('bw unlock --raw', stack.vaultwarden_next_step(result))

    def test_locked_cli_produces_readonly_unlock_instruction(self):
        with patch.object(stack.os, 'geteuid', return_value=1000), \
             patch.object(stack, 'run', return_value=('ok', {'status': 'locked'}, '')):
            result = stack.vaultwarden_operator()
        self.assertEqual(result[0]['verdict'], 'DENIED')
        self.assertIn('bw unlock --raw', stack.vaultwarden_next_step(result))

    def test_vaultwarden_source_metadata_stages_are_redacted(self):
        calls = []
        def fake_run(argv, timeout=20):
            calls.append(argv)
            if argv[:2] == ['bw', 'status']:
                return ('ok', {'status': 'unlocked', 'userEmail': 'PRIVATE-EMAIL'}, '')
            if 'check-fastapi-litellm-sample-source.py' in ' '.join(argv):
                return ('nonzero', {'field_state': 'vaultwarden_folder_failed'}, '')
            return ('ok', {'field_state': 'field_present_nonempty_hidden'}, '')
        with patch.object(stack.os, 'geteuid', return_value=1000), \
             patch.dict(stack.os.environ, {'BW_SESSION': 'PRIVATE-SESSION'}), \
             patch.object(Path, 'is_file', return_value=True), \
             patch.object(stack, 'run', side_effect=fake_run):
            result = stack.vaultwarden_operator()
        self.assertEqual([r['verdict'] for r in result], ['PASS', 'UNVERIFIED', 'PASS'])
        self.assertEqual(result[1]['state'], 'vaultwarden_folder_failed')
        self.assertNotIn('PRIVATE-SESSION', str(result))
        self.assertNotIn('PRIVATE-EMAIL', str(result))
        self.assertEqual(len(calls), 3)

    def test_vaultwarden_scope_skips_runtime_and_prints_login(self):
        with patch.object(stack, 'vaultwarden_operator',
                          return_value=[stack.row('vaultwarden_cli', 'DENIED', 'bw_login_required')]), \
             patch.object(stack, 'ui_http', side_effect=AssertionError('no UI')), \
             patch.object(stack, 'prometheus', side_effect=AssertionError('no Prometheus')), \
             patch.object(stack, 'readiness', side_effect=AssertionError('no Docker')):
            with redirect_stdout(io.StringIO()) as out:
                code = stack.main(['--check', '--scope', 'vaultwarden', '--brief'])
        self.assertEqual(code, 2)
        self.assertIn('bw login', out.getvalue())


if __name__ == '__main__':
    unittest.main()
