import ast
import dataclasses
import datetime
import enum
import pathlib
import time
from types import SimpleNamespace as NS

import argparse

cli = argparse.ArgumentParser(description='Offline JMA budget diagnosis; no production access.')
cli.add_argument('--repo', type=pathlib.Path, required=True, help='datumoj checkout at f7e665e')
args = cli.parse_args()
ROOT = args.repo / 'src/datumoj/rikolto'
SOURCE_PATHS = {'budget.py': 'core/budget.py', 'pipeline.py': 'pipeline.py', 'cloud.py': 'cloud.py'}
def extract(file, names, env):
    tree = ast.parse((ROOT / SOURCE_PATHS[file]).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
    module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), file, 'exec'), env)

class ParseStatus(enum.Enum):
    failed = 'failed'
    ok = 'ok'
class FetchOutcome(enum.Enum):
    ok = 'ok'

env = dict(dataclass=dataclasses.dataclass, field=dataclasses.field, time=time,
           ParseStatus=ParseStatus, FetchOutcome=FetchOutcome, ParseError=Exception,
           DEFAULT_MAX_PAGES=1000, DEFAULT_MAX_TEXT_CHARS=5000000,
           DEFAULT_MAX_OUTPUT_CHUNKS=10000, DEFAULT_MAX_PARSE_SECONDS=60,
           math=__import__('math'), datetime=datetime.datetime)
extract('budget.py', {'BudgetExceeded', 'ParseBudget', 'BudgetChecker'}, env)
extract('pipeline.py', {'ParseSummary', 'parse_pending', '_deadline_reached', '_process'}, env)
extract('cloud.py', {'_failure_streak', '_final_runs'}, env)

calls = {'parse': 0}
snap = NS(snapshot_id='synthetic-old-failure', source_id='jp-jma', sha256='synthetic-sha', outcome=FetchOutcome.ok, content_type='application/xml')
spec = NS(id='jp-jma', kind='jma_feed', scope={})
class Parser:
    name = 'jma_xml'
    version = '1'
    def parse(self, *args):
        calls['parse'] += 1
        return NS(chunks=[])
class Manifest:
    def raw_markers(self): return set()
    def snapshots_for(self, sid): return [snap]
    def snapshot_meta(self, sid): return {}
    def get_parse(self, *args): return NS(status=ParseStatus.failed, error='budget_exceeded:duration_seconds')
deps = NS(parsers={('jma_feed','application/xml'):Parser}, registry=NS(all=lambda:[spec]),
          manifest=Manifest(), change_log=None, deadline=None, _deadline_reached=False, _vector_remaining=None)
env.update(_start_vectors=lambda deps:None, _load_vector_state=lambda deps:{'missing':{}},
           _retry_vectors=lambda *args:None, _recover_staged=lambda *args:set(),
           select_parser=lambda *args:Parser, _parse_fingerprint=lambda *args:'synthetic-fingerprint',
           _maintain_vectors=lambda *args:None)
history=[]
for i in range(8):
    summary = env['parse_pending'](deps, 'jp-jma')
    assert summary.failed == {'synthetic-old-failure':'budget_exceeded:duration_seconds'}
    assert summary.skipped == 1 and summary.parsed == []
    history.append({'source_id':'jp-jma','run_id':str(i),'state':'final','started_at':f'2026-11-04T{10+i:02}:00:00+00:00',
                    'status':'incomplete','exit_status':1,'failures':{'parse_index_failed':len(summary.failed)},'stop_reason':'deadline'})
assert calls['parse']==0
assert env['_failure_streak'](history,'jp-jma')[0]==8
print('PASS: one persisted failure -> 8 failed summaries / streak 8 / zero parser calls')

clock=[0.0]
real_checker=env['BudgetChecker']
env['BudgetChecker']=lambda budget:real_checker(budget,clock=lambda:clock[0])
def slow_raw(sha):
    clock[0]+=61
    return b'synthetic tiny XML'
deps.raw=NS(get=slow_raw)
try:
    env['_process'](deps,Parser(),snap)
except env['BudgetExceeded'] as exc:
    assert exc.item=='duration_seconds'
else:
    raise AssertionError('expected raw retrieval to exhaust parse timer')
assert calls['parse']==1
print('PASS: 61s simulated raw.get + instant parser -> budget_exceeded:duration_seconds')
print('Scope: extracted original AST functions, mocked dependencies; not full repository suite or production replay.')
