"""Hermetic contracts; no Gateway, journal, network, LLM or session changes."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def load(rel,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runtime=load('scripts/workstation/check-openclaw-runtime-alignment.py','alignment')
observer=load('scripts/workstation/observe-openclaw-rate-limits.py','observer')


class RuntimeContracts(unittest.TestCase):
    def test_contract_pin_matches_mise(self):
        node,version=runtime.expected(ROOT)
        self.assertEqual((node,version),('24.22.1','2026.10.7'))

    def test_fail_closed_on_mismatched_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'mise.toml').write_text('[tools]\nnode="24.18.1"\n')
            (root/'apps/openclaw/workstation').mkdir(parents=True)
            (root/'apps/openclaw/workstation/runtime-contract.json').write_text(
                json.dumps({'node_version':'24.22.1'}))
            with self.assertRaises(ValueError):
                runtime.expected(root)

    def test_exact_systemd_entry_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            root=home/'.local/share/mise/installs/node/24.22.1'
            node=root/'bin/node'
            cli=root/'lib/node_modules/openclaw/openclaw.mjs'
            manifest=cli.parent/'package.json'
            for f in (node,cli,manifest):
                f.parent.mkdir(parents=True,exist_ok=True)
                f.write_text('test')
                f.chmod(0o600)
            manifest.write_text(json.dumps({'name':'openclaw','version':'2026.10.7',
                                            'bin':{'openclaw':'openclaw.mjs'}}))
            unit=f'path={node} ; argv[]={node} --max-old-space-size=16053 {cli} gateway --port 18789'
            def fake(cmd):
                if cmd[1:]==['--version']:
                    return 0,'v24.22.1\n'
                if cmd[-1]=='--version':
                    return 0,'OpenClaw 2026.10.7\n'
                return 0,unit
            checks=runtime.classify('24.22.1','2026.10.7',home,fake)
            self.assertEqual(checks,{'node_binary':'match','openclaw_package':'match','systemd_exec':'match'})
            mismatched=runtime.classify('24.22.1','2026.10.7',home,lambda c:(0,unit.replace('24.22.1','24.18.1')))
            self.assertEqual(mismatched['systemd_exec'],'mismatch_or_unavailable')
            manifest.chmod(0o666)
            self.assertEqual(runtime.classify('24.22.1','2026.10.7',home,fake)['node_binary'],'unsafe_or_absent')


class ObserverContracts(unittest.TestCase):
    def event(self,status=429,agent='main',text='test',cursor='s=abc'):
        return {'MESSAGE':json.dumps({'event':{'type':'model_request_error',
                   'status_code':status,'agent_id':agent,'error_code':'rate_limit',
                   'secret':text}}),
                '__CURSOR':cursor,'__REALTIME_TIMESTAMP':'1793200000000000'}

    def test_structured_429_only_and_redaction(self):
        x=observer.classify(self.event(text='sk-PRIVATE'))
        self.assertEqual(x['status'],429)
        self.assertEqual(x['reason'],'rate_limit')
        self.assertNotIn('PRIVATE',json.dumps(x))
        self.assertIsNone(observer.classify({**self.event(),'MESSAGE':'Hello 429 rate limit sk-PRIVATE'}))

    def test_reject_non_status_and_unknown_agent(self):
        e=self.event(status=429,agent='private-client')
        self.assertEqual(observer.classify(e)['agent'],'unverified')
        e['MESSAGE']=json.dumps({'event':{'type':'model_request_error','status_code':'429'}})
        self.assertIsNone(observer.classify(e))

    def test_private_store_deduplication_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'.local/state/nabla-compose/openclaw'
            e=observer.classify(self.event())
            self.assertEqual(observer.persist([e],dest),1)
            self.assertEqual(observer.persist([e],dest),0)
            file=dest/'rate-limit-events.jsonl'
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            file.chmod(0o644)
            with self.assertRaises(ValueError):
                observer.persist([e],dest)

    def test_fixture_no_disclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=Path(tmp)/'data.jsonl'
            fixture.write_text(json.dumps(self.event(text='sk-NEVERPRINT'))+'\n')
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(observer.main(['--fixture',str(fixture)]),0)
            data=json.loads(out.getvalue())
            self.assertEqual(data['http_429'],1)
            self.assertEqual(data['store'],'not_requested')
            self.assertNotIn('NEVERPRINT',out.getvalue())


if __name__=='__main__':
    unittest.main()
