"""Pinned 8f5bc7a JMA metadata export: stdlib, offline, no input writes.

Requires a mutually consistent, quiescent, standalone SQLite/JSONL copy.
This tool cannot establish cross-file production generation consistency.
"""
import argparse
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

BASELINE = '8f5bc7a5204c1b7eb235004c4c304fa72aea600a'
BUDGETS = {'pages', 'text_chars', 'output_chunks', 'duration_seconds'}
HEX = re.compile(r'[0-9a-f]{64}')
MAX_BYTES = 2 * 1024**3
CONTRACT_SHA256 = '78db00adf5ea5d9d72f016efc7e24aad628dcd78b5c1b6bf02ac68cd58da3cf5'
class Rejected(Exception):
    """Only fixed error codes are allowed to cross the CLI boundary."""

def need(value, code='incompatible_data'):
    if not value:
        raise Rejected(code)

def js(text):
    def pairs(items):
        result = {}
        for k,v in items:
            need(k not in result)
            result[k] = v
        return result
    def invalid(_):
        raise Rejected('incompatible_data')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)

def stamp(value, naive=False):
    need(isinstance(value,str))
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        need(naive)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec='microseconds')

def pathcheck(path):
    p = Path(path).absolute()
    need(p.is_file() and not any(x.is_symlink() for x in [p,*p.parents]), 'unsafe_input')
    need(p.stat().st_size <= MAX_BYTES, 'input_limit')
    for suffix in ('-wal','-shm','-journal'):
        need(not Path(str(p)+suffix).exists(), 'not_standalone_copy')
    return p

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):
            h.update(block)
    return h.digest()

def normalize_ddl(sql):
    # Pinned DDL contains no string literals; strip comments/whitespace only.
    sql=re.sub(r'--[^\n]*','',sql or '')
    return ''.join(re.findall(r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]',sql)).lower()

def dbopen(p,kind):
    db = sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1', uri=True)
    try:
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('PRAGMA query_only=ON')
        # Structural contract captured from upstream literal DDL, not live schema.
        contract_bytes=Path(__file__).with_name('schema_contract.json').read_bytes()
        need(hashlib.sha256(contract_bytes).hexdigest()==CONTRACT_SHA256,'incompatible_schema')
        contracts=js(contract_bytes)
        expected=contracts[kind]
        objects=db.execute("SELECT type,name FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'").fetchall()
        need(all(t in {'table','index'} for t,n in objects),'incompatible_schema')
        need({n for t,n in objects if t=='table'}==set(expected),'incompatible_schema')
        for table,definition in expected.items():
            need(re.fullmatch('[a-z_]+',table),'incompatible_schema')
            table_sql=db.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()[0]
            need(normalize_ddl(table_sql)==definition['ddl'],'incompatible_schema')
            need([list(r) for r in db.execute('PRAGMA table_xinfo('+table+')')]==definition['columns'],'incompatible_schema')
            indexes={}
            for seq,name,unique,origin,partial in db.execute('PRAGMA index_list('+table+')'):
                need(re.fullmatch('[a-zA-Z0-9_]+',name),'incompatible_schema')
                indexes[name]={'unique':unique,'origin':origin,'partial':partial,
                    'columns':[list(r) for r in db.execute('PRAGMA index_xinfo('+name+')')],
                    'ddl':normalize_ddl(db.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('index',name)).fetchone()[0])}
            need(indexes==definition['indexes'],'incompatible_schema')
        need(db.execute('PRAGMA quick_check').fetchall()==[('ok',)],'invalid_sqlite')
        if kind=='manifest':
            need(db.execute('SELECT version FROM schema_version').fetchall()==[(4,)],'incompatible_schema')
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        return db
    except BaseException:
        db.close()
        raise

def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',',':'), allow_nan=False)

def _export(manifest,changes,runs,*,frozen):
    need(frozen is True,'frozen_copy_ack_required')
    paths=[pathcheck(x) for x in (manifest,changes,runs)]
    need(len(set(paths))==3,'unsafe_input')
    before=[digest(p) for p in paths]
    salt=secrets.token_bytes(32)
    def token(parts):
        return hmac.new(salt,canon(parts).encode(),hashlib.sha256).hexdigest()[:24]
    m=c=None
    try:
        m=dbopen(paths[0],'manifest');c=dbopen(paths[1],'changes')
        snapshots=[]; matched=set(); candidate_keys=set(); events=[]
        for row in c.execute("SELECT * FROM changes WHERE source_id='jp-jma' AND kind='parse_failed'"):
            e=js(row['event_json'])
            need(isinstance(e,dict))
            for key in ('event_id','source_id','kind'):
                need(e.get(key)==row[key])
            need(stamp(e.get('detected_at'))==stamp(row['detected_at']))
            need(isinstance(e.get('summary'),str))
            identity=[e.get(k) for k in ('source_id','kind','doc_key','resource_url','old_sha256','new_sha256')]
            eid=hashlib.sha256(json.dumps(identity,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            need(eid==e['event_id'])
            events.append(e)
        for row in m.execute("SELECT * FROM snapshots WHERE source_id='jp-jma' AND outcome='ok'"):
            s=js(row['snapshot']); meta=js(row['meta'])
            need(isinstance(s,dict) and isinstance(meta,dict))
            for k in ('snapshot_id','source_id','resource_url','outcome','sha256'):
                need(s.get(k)==row[k])
            need(stamp(s.get('fetched_at'))==stamp(row['fetched_at'],naive=True))
            need(isinstance(row['sha256'],str) and HEX.fullmatch(row['sha256']))
            need(isinstance(row['snapshot_id'],str) and isinstance(row['resource_url'],str))
            # Fixed JmaXmlParser v1 at the pinned default-budget source profile.
            fp=hashlib.sha256(canon(['jp-jma',row['resource_url'],s.get('content_type'),meta]).encode()).hexdigest()
            candidates=m.execute("SELECT * FROM parsed WHERE sha256=? AND status='failed' AND error LIKE 'budget_exceeded:%'",(row['sha256'],)).fetchall()
            for p in candidates:
                candidate_keys.add(tuple(p[k] for k in ('sha256','parser','version','context_fingerprint')))
            p=m.execute("SELECT * FROM parsed WHERE sha256=? AND parser='jma_xml' AND version='1' AND context_fingerprint=? AND status='failed'",(row['sha256'],fp)).fetchone()
            if p is None or not (p['error'] or '').startswith('budget_exceeded:'):
                continue
            subtype=p['error'].removeprefix('budget_exceeded:')
            if subtype not in BUDGETS or meta.get('resource_type') not in {'feed','entry'}:
                continue
            key=tuple(p[k] for k in ('sha256','parser','version','context_fingerprint'))
            matched.add(key)
            # Events have no parser/version/context: exact snapshot summary + URL/SHA
            # narrows correlation but cannot establish which parse context failed.
            prefix=f"解析失败 [policy]；快照 {row['snapshot_id']}："
            related=[e for e in events if e.get('resource_url')==row['resource_url'] and e.get('new_sha256')==row['sha256']
                     and any(e['summary']==prefix+'budget_exceeded:'+b for b in BUDGETS)]
            times=[stamp(e['detected_at']) for e in related]
            snapshots.append({'token':token(['snapshot',row['snapshot_id']]),'parse_group':token(['parse',*key]),
                'budget_category':subtype,'resource_type':meta['resource_type'],
                'retained_event_count':len(related),'earliest_retained_event_at':min(times) if times else None,
                'event_context_attribution':'unavailable'})
        finals={};final_raw={};ignored_running=0
        with paths[2].open(encoding='utf-8') as f:
            for line in f:
                need(len(line)<=4*1024*1024,'input_limit')
                row=js(line)
                need(isinstance(row,dict) and isinstance(row.get('source_id'),str))
                if row['source_id']!='jp-jma':
                    continue
                need(isinstance(row.get('run_id'),str) and row['run_id'])
                need(row.get('state') in {'running','final'})
                stamp(row.get('started_at'))
                if row['state']=='running':
                    ignored_running+=1
                    continue
                need(row.get('status') in {'completed','failed','incomplete','interrupted'})
                need(type(row.get('exit_status')) is int and row['exit_status'] in {0,1})
                need(all(type(row.get(k)) is int and row[k]>=0 for k in ('new','unchanged')))
                for k in ('parsed','embedding_deferred'):
                    if k in row: need(type(row[k]) is int and row[k]>=0)
                need(stamp(row.get('ended_at'))>=stamp(row['started_at']))
                need(isinstance(row.get('failures'),dict))
                need(all(type(v) is int and v>=0 for v in row['failures'].values()))
                count=row['failures'].get('parse_index_failed',0)
                need(type(count) is int and count>=0)
                need(row.get('stop_reason') in {None,'deadline','source_failed'})
                out={'token':token(['run',row['run_id']]),'started_at':stamp(row['started_at']),
                     'parse_index_failed':count,'status':row['status'],'stop_reason':row['stop_reason']}
                if row['run_id'] in finals:
                    need(final_raw[row['run_id']]==canon(row),'conflicting_final_runs')
                finals[row['run_id']]=out
                final_raw[row['run_id']]=canon(row)
        unmatched=len(candidate_keys-matched)
        report={'format_version':1,'baseline':BASELINE,'profile':'jp-jma/jma_xml-v1/default-budget',
                'status':'partial' if unmatched else 'complete',
                'unsupported_or_unmatched_budget_records':unmatched,
                'snapshots':snapshots,'runs':sorted(finals.values(),key=lambda r:r['started_at']),
                'ignored_running_records':ignored_running,
                'event_semantics':'deduplicated_retained_events_not_failure_attempts',
                'copy_consistency':'operator_attested_not_proven','tokens':'single_export_only'}
        need(before==[digest(p) for p in paths],'inputs_changed')
        for p in paths: pathcheck(p)
        return report
    finally:
        if c is not None: c.close()
        if m is not None: m.close()

def export(manifest,changes,runs,*,frozen=False):
    try:
        return _export(manifest,changes,runs,frozen=frozen)
    except Rejected:
        raise
    except Exception:
        raise Rejected('invalid_or_unreadable_input') from None

def main():
    # Do not echo arbitrary arguments or filesystem paths on parse failures.
    class Parser(argparse.ArgumentParser):
        def error(self,message):
            raise Rejected('invalid_arguments')
    try:
        p=Parser(description=__doc__)
        p.add_argument('--manifest',required=True)
        p.add_argument('--changes',required=True)
        p.add_argument('--runs',required=True)
        p.add_argument('--ack-frozen-consistent-copy',action='store_true')
        args=p.parse_args()
        result=export(args.manifest,args.changes,args.runs,frozen=args.ack_frozen_consistent_copy)
        print(json.dumps(result,ensure_ascii=True,sort_keys=True))
        return 3 if result['status']=='partial' else 0
    except Rejected as exc:
        print(json.dumps({'status':'rejected','reason':str(exc)}))
        return 2

if __name__=='__main__':
    sys.exit(main())
