#!/usr/bin/env python3
"""Read-only reconciliation plan: digest template and cron main session.

Does not modify cron, create sessions, write databases, request models or read
secrets.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,HERE/path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


digest=load('openclaw_digest','diagnose-openclaw-digest-top.py')
parent=load('openclaw_parent','diagnose-openclaw-cron-parent.py')


def configured_agent(raw):
    try:
        doc=json.loads(raw)
        entries=doc if isinstance(doc,list) else doc.get('agents')
        if not isinstance(entries,list):
            return 'unverified'
        ids=[]
        for row in entries:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str):
                return 'unverified'
            ids.append(row['id'])
        return 'present' if 'cron' in ids else 'absent'
    except (ValueError,TypeError,AttributeError):
        return 'unverified'


def evaluate(digest_class,session_class,agent_state):
    if digest_class in ('skill_template_integer_valid','skill_template_fixed_integer','valid_top_five'):
        digest_action='none'
    elif digest_class=='skill_template_range_int_mismatch':
        digest_action='review_items_per_section_5_in_ui'
    else:
        digest_action='verify_installed_skill_and_cron'
    if session_class=='present':
        session_action='none'
    elif agent_state=='present' and session_class=='absent_in_reported_complete_catalog':
        session_action='create_new_cron_conversation_in_ui'
    elif agent_state=='absent':
        session_action='review_agent_configuration_first'
    else:
        session_action='verify_agent_and_session_catalog'
    return digest_action,session_action


def main() -> int:
    job_state,job=digest.read_runtime()
    template_state,template=digest.read_skill_template()
    digest_state,_=digest.classify_job(job,template)
    pstate='unverified'
    if parent.owned_binary(parent.NODE) and parent.owned_binary(parent.CLI):
        try:
            r=subprocess.run([str(parent.NODE),str(parent.CLI),'sessions','--agent','cron',
                '--limit','100','--json'],capture_output=True,timeout=25,check=False)
            if r.returncode==0:
                pstate=parent.classify(r.stdout)['cron_main_reference']
        except (OSError,subprocess.TimeoutExpired):
            pass
    agent_state='unverified'
    if parent.owned_binary(parent.NODE) and parent.owned_binary(parent.CLI):
        try:
            r=subprocess.run([str(parent.NODE),str(parent.CLI),'agents','list','--json'],
                             capture_output=True,timeout=25,check=False)
            if r.returncode==0 and len(r.stdout)<=1024*1024:
                agent_state=configured_agent(r.stdout)
        except (OSError,subprocess.TimeoutExpired):
            pass
    da,sa=evaluate(digest_state,pstate,agent_state)
    report={'digest_read':job_state,'template_read':template_state,
            'digest_state':digest_state,'digest_action':da,
            'cron_agent':agent_state,'cron_main_reference':pstate,'cron_main_action':sa,
            'mutations':0,'model_requests':0,'private_content_printed':False}
    print(json.dumps(report,sort_keys=True))
    return 0 if da=='none' and sa=='none' else 2


if __name__=='__main__':
    raise SystemExit(main())
