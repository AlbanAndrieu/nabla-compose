#!/usr/bin/env python3
"""Classify structured Gateway journal failures without disclosing raw messages.

No model calls, quota writes, session edits or service restarts. Optional
capture persists only allowlisted classifications in private local state.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

MAX_BYTES = 1024 * 1024
STATUS = {401, 403, 429, 500, 502, 503, 504}
AGENTS = {'main','cron'}
REASONS = {'rate_limit', 'billing', 'auth', 'timeout', 'upstream', 'unknown'}


def classify(record: dict) -> dict | None:
    if not isinstance(record, dict):
        return None
    raw = record.get('MESSAGE')
    if not isinstance(raw, str) or len(raw) > 65536:
        return None
    try:
        message = json.loads(raw)
    except (ValueError, TypeError):
        # An arbitrary '429' inside a transcript is not proof of a failure.
        return None
    if not isinstance(message, dict):
        return None
    event = message.get('event', message)
    if not isinstance(event, dict):
        return None
    code = event.get('http_status', event.get('status_code'))
    if type(code) is not int or code not in STATUS:
        return None
    marker = event.get('type', event.get('event_type'))
    if marker not in ('http_error','model_request_error','upstream_error','rate_limit'):
        return None
    reason = event.get('error_code', 'unknown')
    if not isinstance(reason,str) or reason not in REASONS:
        reason = 'unknown'
    if code == 429 and reason == 'unknown':
        reason = 'rate_limit'
    agent = event.get('agent_id')
    if not isinstance(agent,str) or agent not in AGENTS:
        agent = 'unverified'
    cursor = record.get('__CURSOR')
    stamp = record.get('__REALTIME_TIMESTAMP')
    if not isinstance(cursor,str) or not 0 < len(cursor) <= 4096:
        return None
    if not isinstance(stamp,str) or not stamp.isascii() or not stamp.isdecimal() or len(stamp)>20:
        return None
    try:
        date = datetime.fromtimestamp(int(stamp)/1_000_000, timezone.utc).isoformat(timespec='seconds')
    except (OverflowError, OSError, ValueError):
        return None
    return {'event_id':hashlib.sha256(cursor.encode()).hexdigest()[:24],
            'timestamp_utc':date,'status':code,'reason':reason,'agent':agent}


def parse_lines(raw: bytes) -> list[dict]:
    if not raw or len(raw)>MAX_BYTES:
        return []
    results=[]
    for line in raw.splitlines()[:150]:
        try:
            obj=json.loads(line)
        except (UnicodeError,ValueError):
            continue
        event=classify(obj)
        if event:
            results.append(event)
    return results


def journal() -> tuple[str,bytes]:
    cmd=['journalctl','--user','-u','openclaw-gateway.service','--since','30 minutes ago',
         '-n','150','--output=json','--no-pager']
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                            timeout=12,check=False)
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable',b''
    if proc.returncode or len(proc.stdout)>MAX_BYTES:
        return 'unavailable',b''
    return 'available',proc.stdout


def persist(events:list[dict],base:Path) -> int:
    if not events:
        return 0
    try:
        base.mkdir(mode=0o700,parents=True,exist_ok=True)
        # Deny symlinked or group-writable ancestors as well as private leaf.
        for directory in (base.parents[2],base.parents[1],base.parent,base):
            s=directory.lstat()
            if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode & 0o022:
                raise ValueError('unsafe_store')
        s=base.lstat()
        if s.st_mode & 0o077:
            raise ValueError('unsafe_store')
        dest=base/'rate-limit-events.jsonl'
        fd=os.open(dest,os.O_CREAT|os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW,0o600)
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode & 0o077 or s.st_nlink!=1:
                raise ValueError('unsafe_events_file')
            with os.fdopen(fd,'r+',encoding='utf-8') as stream:
                fd=-1
                fcntl.flock(stream,fcntl.LOCK_EX)
                if s.st_size>1024*1024:
                    raise ValueError('rotate_required')
                seen=set()
                for line in stream:
                    try:
                        seen.add(json.loads(line).get('event_id'))
                    except ValueError:
                        raise ValueError('invalid_store') from None
                fresh=[e for e in events if e['event_id'] not in seen]
                for e in fresh:
                    stream.write(json.dumps(e,sort_keys=True)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
                return len(fresh)
        finally:
            if fd>=0:
                os.close(fd)
    except (OSError,ValueError):
        raise ValueError('private_store_unavailable') from None


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,help='Offline structured journal JSONL fixture')
    parser.add_argument('--capture',action='store_true',help='Explicit opt-in private append')
    args=parser.parse_args(argv)
    if args.fixture:
        if args.capture:
            parser.error('--fixture and --capture cannot be combined')
        try:
            if args.fixture.is_symlink() or args.fixture.stat().st_size>MAX_BYTES:
                raise OSError()
            data=args.fixture.read_bytes()
            source='fixture'
        except OSError:
            data=b'';source='unavailable'
    else:
        source,data=journal()
    events=parse_lines(data)
    counts=Counter(e['status'] for e in events)
    result={'source':source,'structured_events':len(events),
            'http_429':counts[429],'http_401':counts[401],
            'other_http_failures':sum(n for code,n in counts.items() if code not in (401,429)),
            'attribution':'structured_gateway_event' if events else 'unverified',
            'raw_logs_printed':False,'tokens_generated':0,'store':'not_requested'}
    exit_code=0 if source!='unavailable' else 2
    if args.capture:
        base=Path.home()/'.local/state/nabla-compose/openclaw'
        try:
            result['persisted_new_events']=persist(events,base)
            result['store']='private'
        except ValueError:
            result['store']='blocked';exit_code=2
    print(json.dumps(result,sort_keys=True))
    return exit_code


if __name__=='__main__':
    raise SystemExit(main())
