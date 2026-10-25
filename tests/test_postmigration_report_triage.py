"""Offline regression tests; no LAN, Docker, or private TrueNAS files."""
import importlib.util
import json
from pathlib import Path

PATH = Path(__file__).resolve().parents[1] / 'scripts/truenas/triage-postmigration-report.py'
spec = importlib.util.spec_from_file_location('report_triage', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def session(tmp_path, rows):
    root = tmp_path / 'evidence'
    root.mkdir()
    folder = root / 'session-Ab123456'
    folder.mkdir()
    content = ['phase\tresult\tlog']
    for name, state, payload in rows:
        log = folder / (name + '.log')
        log.write_text(payload)
        content.append(f'{name}\t{state}\t{log}')
    (folder / 'summary.tsv').write_text('\n'.join(content) + '\n')
    return root, folder


def test_categories_no_secret_echo(tmp_path):
    root, folder = session(tmp_path, [
        ('postmigration-catalog', 'FAIL', 'generated drift TOKEN=very-secret https://internal.local/private'),
        ('postmigration-service-readiness', 'FAIL', 'healthcheck unhealthy BEARER never-show'),
        ('postmigration-gatus', 'FAIL', json.dumps({'source':'gatus_lan_read_only','declared':85,'runtime':85,'up':61,'down':24,'unverified':0})),
        ('postmigration-prometheus', 'FAIL', 'Unhealthy targets HTTP 401 Authorization abc'),
    ])
    res = module.analyze(folder, root)
    assert res['failed'] == 4
    assert [x['category'] for x in res['checks']] == [
        'generated_catalog_drift', 'runtime_or_healthcheck_failed',
        'observed_monitors_down', 'prometheus_scrape_degraded',
    ]
    assert res['checks'][2]['evidence']['down'] == 24
    assert all(v not in json.dumps(res) for v in ['very-secret', 'never-show', 'abc', 'internal.local'])


def test_apisix_unknown_without_pretending_failure(tmp_path):
    root, folder = session(tmp_path,[('apisix-runtime','WARN','runtime=not_deployed_or_ambiguous http=not_checked')])
    res=module.analyze(folder, root)
    assert res['failed'] == 0 and res['unverified'] == 1
    assert res['checks'][0]['category'] == 'optional_gateway_unverified'


def test_bad_summary_rejected(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','hello')])
    summary=folder/'summary.tsv'
    summary.write_text('phase\tresult\tlog\nunknown-service\tPASS\t/etc/passwd\n')
    try:
        module.analyze(folder,root)
    except ValueError:
        pass
    else:
        assert False


def test_symlink_log_not_read(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','no such file SECRET=abc')])
    bad=folder/'postmigration-catalog.log'
    bad.unlink()
    bad.symlink_to('/etc/passwd')
    res=module.analyze(folder,root)
    assert res['checks'][0]['category'] == 'log_unavailable'


def test_symlink_session_rejected(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','PASS','ok')])
    link=root/'session-XY123456'
    link.symlink_to(folder,target_is_directory=True)
    try:
        module.analyze(link,root)
    except ValueError:
        pass
    else:
        assert False


def test_large_log_not_loaded(tmp_path):
    root, folder=session(tmp_path,[('postmigration-catalog','FAIL','SECRET\n' * 30000)])
    res=module.analyze(folder,root)
    assert res['checks'][0]['category'] in {'log_unavailable','catalog_check_failed'}
