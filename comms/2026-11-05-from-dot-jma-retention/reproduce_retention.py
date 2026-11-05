#!/usr/bin/env python3
"""Read-only source audit: extracted original functions, synthetic SQLite + memory objects.
No repository import, app execution, credentials, networking, R2, or real deletion.
Source commit: e602697f925e4d7f98cb01d4d5b42389ca39b68c.
Only serialization/validation models and object-store transport are stand-ins.
"""
import ast
import argparse
import hashlib
import json
import re
import sqlite3
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from types import SimpleNamespace, ModuleType

HERE = Path(__file__).resolve().parent
SRC = HERE / 'sources'
SOURCE_COMMIT = 'e602697f925e4d7f98cb01d4d5b42389ca39b68c'
SOURCE_BLOBS = {
    'src/datumoj/rikolto/core/state.py': '32f50eb87abd6730e1a106e32df0ce3c24bd86dc',
    'src/datumoj/rikolto/core/manifest.py': '136c62ad456cf7d7258a3508c45237bbc3535f8e',
}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, help='Read source from this datumoj checkout; requires exact source blobs from '+SOURCE_COMMIT)
ARGS = parser.parse_args()
SOURCE_TEXT = {}
for relative, expected in SOURCE_BLOBS.items():
    path = ARGS.repo / relative if ARGS.repo is not None else SRC / relative.replace('/', '__')
    data = path.read_bytes()
    actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if actual != expected:
        raise SystemExit(f'SOURCE MISMATCH: {relative}: expected Git blob {expected}, got {actual}; refusing to execute')
    SOURCE_TEXT[relative.replace('/', '__')] = (str(path), data.decode('utf-8'))
T0 = datetime(2026, 11, 1, tzinfo=UTC)
DAY = timedelta(days=1)
SHA = hashlib.sha256(b'synthetic entry').hexdigest()

class FetchOutcome(Enum):
    ok = 'ok'
    failed = 'failed'

class PublishState(Enum):
    published = 'published'
    staged = 'staged'
    failed = 'failed'

class Snapshot:
    @staticmethod
    def model_validate_json(text):
        d = json.loads(text)
        d['fetched_at'] = datetime.fromisoformat(d['fetched_at'])
        d['outcome'] = FetchOutcome(d['outcome'])
        return SimpleNamespace(**d)

# Original method's import and validators resolve only to safe stdlib stand-ins.
model_stub = ModuleType('datumoj.rikolto.core.models')
model_stub.Sha256 = str
sys.modules[model_stub.__name__] = model_stub
class TypeAdapter:
    def __init__(self, kind):
        self.kind = kind
    def validate_python(self, value):
        if self.kind is str:
            assert re.fullmatch(r'[a-f0-9]{64}', value)
        else:
            assert isinstance(value, datetime) and value.tzinfo is not None
        return value

AwareDatetime = datetime
StateError = type('StateError', (RuntimeError,), {})
SchemaVersionError = type('SchemaVersionError', (RuntimeError,), {})
check_key = lambda key: None
parse_context_fingerprint = lambda snap, meta: meta.get('context', 'synthetic-context')

def extract(filename, functions=(), classes=None, assignments=()):
    source_path, source_text = SOURCE_TEXT[filename]
    tree = ast.parse(source_text)
    selected = [ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in functions:
            selected.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in (classes or {}):
            wanted = classes[node.name]
            node.body = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in wanted] if wanted is not None else node.body
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in assignments for t in node.targets):
            selected.append(node)
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, source_path, 'exec'), globals())

extract('src__datumoj__rikolto__core__manifest.py', functions=['_ts', '_from_ts'],
        assignments=['SCHEMA_VERSION', '_SCHEMA'],
        classes={'SqliteManifest': ['__init__', '_init_schema', '_tx', 'close', 'raw_markers', 'mark_raw_optional']})
extract('src__datumoj__rikolto__core__state.py', functions=['_ro', '_raw_key', '_raw_refs'],
        assignments=['_SHA', '_CLEANUP_MAX_SECONDS'],
        classes={'_CleanupTimeout': None, 'StateManager': ['raw_retention', 'mark_raw', 'cleanup']})

class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.deleted = []
    def list_objects(self, prefix):
        return [obj for key, obj in self.objects.items() if key.startswith(prefix)]
    def put(self, key):
        self.objects[key] = SimpleNamespace(key=key, size_bytes=1, etag='synthetic')

def delete_retired_object(store, obj, check):
    assert isinstance(store, MemoryStore), 'Never permit external stores'
    check()
    del store.objects[obj.key]
    store.deleted.append(obj.key)

class Fixture:
    def __init__(self, root, days):
        self.root = root
        root.mkdir()
        self.path = root / 'manifest.sqlite'
        with closing(SqliteManifest(self.path)):
            pass
        self.store = MemoryStore()
        self.store.put(_raw_key('raw', SHA))
        self.generations = {}
        self.specs = [SimpleNamespace(id='jp-jma', scope={'raw_retention_days': days, 'raw_expire_latest_types': ['entry']})]
        self.manager = StateManager()
        self.manager.data_dir = root
        self.manager.store = self.store
        self.manager.last_timings = {}
        self.manager._current = lambda: (max(self.generations, default=0), 'synthetic')
        self.manager._generation = lambda n: self.generations[n]
    def add(self, id='entry', fetched=T0, kind='entry', status='published', source='jp-jma', sha=SHA, url='https://example.invalid/entry'):
        snap = dict(snapshot_id=id, fetched_at=fetched.isoformat(), source_id=source, resource_url=url, sha256=sha, outcome='ok')
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('INSERT INTO snapshots(snapshot_id,source_id,resource_url,fetched_at,outcome,sha256,meta,snapshot) VALUES(?,?,?,?,?,?,?,?)',
                       (id, source, url, _ts(fetched), 'ok', sha, json.dumps({'resource_type': kind}), json.dumps(snap)))
            if status is not None:
                db.execute('INSERT INTO publish_states(snapshot_id,state) VALUES(?,?)', (id,status))
            db.commit()
    def publish(self, when):
        n = max(self.generations, default=0) + 1
        self.generations[n] = SimpleNamespace(generation=n, created_at=when, stores=[])
        self.store.put(f'generations/{n}.json')
    def markers(self):
        with closing(SqliteManifest(self.path)) as m:
            return m.raw_markers()
    def tick(self, day, mark=True, raw_enabled=True):
        when = T0 + DAY*day
        marked = self.manager.mark_raw(self.specs, when) if mark else 0
        self.publish(when)
        report = self.manager.cleanup(self.specs, now=when, check=lambda: None, raw_enabled=raw_enabled, marked=marked)
        assert report['failures'] == 0, report
        return {'day':day, 'marked_at_day':((self.markers()[SHA]-T0)/DAY if SHA in self.markers() else None),
                'marked_new':marked, 'raw_deleted':report['raw_deleted'], 'reclaimable_raw':report['reclaimable_raw'],
                'generation_deleted':report['generations_deleted']}

results = {}
with tempfile.TemporaryDirectory(prefix='jma-retention-pure-stdlib-') as temp:
    base = Path(temp)
    for days in (3,7):
        f=Fixture(base/f'steady-{days}', days); f.add()
        rows=[f.tick(day) for day in range(days+1)]
        assert next(row['day'] for row in rows if row['raw_deleted']) == days
        assert f.markers()[SHA] == T0 + DAY*(days-3)
        results[f'steady_{days}_days'] = rows
    f=Fixture(base/'migration-new-marker', 7); f.add()
    f.specs[0].scope['raw_retention_days']=3
    rows=[f.tick(day) for day in (2,3,4,5)]
    assert rows[-1]['raw_deleted']==1 and not any(r['raw_deleted'] for r in rows[:-1])
    results['migration_at_day_2_first_marker_then_delete_day_5']=rows
    f=Fixture(base/'migration-aged-marker', 7); f.add(); f.tick(4, raw_enabled=False)
    f.specs[0].scope['raw_retention_days']=3
    rows=[f.tick(day) for day in (6,7)]
    assert rows[-1]['raw_deleted']==1 and f.markers()[SHA]==T0+4*DAY
    results['migration_does_not_reset_marker']=rows
    f=Fixture(base/'late-new-marker', 3); f.add()
    rows=[f.tick(day) for day in (10,12,13)]
    assert rows[-1]['raw_deleted']==1 and not any(r['raw_deleted'] for r in rows[:-1])
    results['first_mark_after_outage_day_10_delete_day_13']=rows
    protection={}
    for name,kind,status,expected in [('feed','feed','published',False),('entry','entry','published',True),
                                     ('pending','entry',None,False),('staged','entry','staged',False),('failed','entry','failed',False)]:
        f=Fixture(base/f'protection-{name}',3);f.add(kind=kind,status=status)
        eligible=SHA in f.manager.raw_retention(f.specs,T0+40*DAY)
        assert eligible == expected
        protection[name]=eligible
    f=Fixture(base/'cross-source',3);f.add();f.add(id='other',source='other',fetched=T0+DAY)
    f.specs.append(SimpleNamespace(id='other',scope={'raw_retention_days':30,'raw_expire_latest_types':['entry']}))
    expiry=f.manager.raw_retention(f.specs,T0)[SHA]
    assert expiry==T0+31*DAY
    protection['shared_sha_expiry_day']=31
    results['raw_retention_protections']=protection
    f=Fixture(base/'refs-vs-protection',3);f.add()
    assert SHA in _raw_refs(f.root)
    f.manager.mark_raw(f.specs,T0)
    assert SHA not in _raw_refs(f.root)
    f.add(id='pending-repeat',fetched=T0+DAY,status=None)
    assert SHA not in _raw_refs(f.root) and SHA not in f.manager.raw_retention(f.specs,T0+10*DAY)
    r=f.tick(10)
    assert r['raw_deleted']==0
    results['marked_sha_not_raw_ref_but_pending_blocks_cleanup']=r
    f=Fixture(base/'generation-boundary',3);f.add();f.publish(T0-timedelta(microseconds=1))
    f.tick(0);r=f.tick(3)
    assert r['raw_deleted']==1 and 'generations/1.json' in f.store.deleted
    results['premark_generation_expires_before_raw_deletion']=r
    f=Fixture(base/'microsecond-boundary',3);f.add();f.tick(0)
    before=T0+3*DAY-timedelta(microseconds=1)
    f.publish(before)
    r=f.manager.cleanup(f.specs,now=before,check=lambda:None,raw_enabled=True)
    assert r['raw_deleted']==0 and r['failures']==0
    exact=f.tick(3)
    assert exact['raw_deleted']==1
    results['exact_72h_boundary']={'one_microsecond_early_deleted':r['raw_deleted'],'at_72h_deleted':exact['raw_deleted']}
    f=Fixture(base/'refetch',3);f.add();f.tick(0)
    f.add(id='refetch',fetched=T0+2*DAY)
    rows=[f.tick(day) for day in (3,4,5)]
    assert rows[-1]['raw_deleted']==1 and not any(r['raw_deleted'] for r in rows[:-1])
    assert f.markers()[SHA]==T0
    results['refetch_extends_expiry_without_resetting_mark']=rows
    f=Fixture(base/'raw-disabled',3);f.add();f.tick(0)
    disabled=f.tick(3,raw_enabled=False)
    enabled=f.tick(4)
    assert disabled['reclaimable_raw']==1 and disabled['raw_deleted']==0 and enabled['raw_deleted']==1
    results['enabling_raw_cleanup_does_not_restart_grace']=[disabled,enabled]
    f=Fixture(base/'already-aged-before-config-change',7);f.add();f.tick(4,raw_enabled=False)
    f.specs[0].scope['raw_retention_days']=3
    r=f.tick(8)
    assert r['raw_deleted']==1 and r['marked_at_day']==4
    results['old_mark_config_change_can_delete_same_round']=r
    # A current generation always survives, even old; ordinary flow publishes first.
    results['retained_rule']='current OR age <= 72 hours; older non-current descriptors deleted before raw'
print(json.dumps({'source_commit':'e602697f925e4d7f98cb01d4d5b42389ca39b68c','scope':'original AST functions; synthetic SQLite and in-memory store only','results':results},indent=2))
