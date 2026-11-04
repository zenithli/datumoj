from __future__ import annotations
import ast, dataclasses, enum, json, pathlib, re, string, time, unicodedata
from types import SimpleNamespace
from urllib.parse import quote
from html.parser import HTMLParser
from typing import Any
from collections.abc import Mapping
import argparse
cli=argparse.ArgumentParser(description='Offline e-Gov failure classification checks; no production access.')
cli.add_argument('--repo',type=pathlib.Path,required=True,help='datumoj checkout at f7e665e')
args=cli.parse_args()
ROOT=args.repo/'src/datumoj/rikolto'
SOURCE_PATHS={'http.py':'core/http.py','ckan.py':'crawlers/ckan.py','runner.py':'core/runner.py'}
class FetchOutcome(enum.Enum):
 ok='ok'; empty_body='empty_body'; too_large='too_large'; not_modified='not_modified'; spa_shell='spa_shell'
def extracted(file,names,env):
 tree=ast.parse((ROOT/SOURCE_PATHS[file]).read_text())
 tree.body=[n for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.Assign)) and (getattr(n,'name',None) in names or isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets))]
 exec(compile(tree,str(ROOT/SOURCE_PATHS[file]),'exec'),env)
 return env
base=dict(globals(),dataclass=dataclasses.dataclass,Callable=__import__('typing').Callable)
r=extracted('http.py',{'_UNRESERVED','_robots_norm','_robots_regex','RobotsRules','RobotsCache'},base)
clock=[0]; calls=[]
cache=r['RobotsCache'](clock=lambda:clock[0])
def load():
 calls.append(1);return r['RobotsRules'](unreachable='robots.txt HTTP 503')
for target in ['/first.csv','/second.csv']:
 assert cache.get('https://example.go.jp/robots.txt',load).blocked_reason(target)=='robots.txt HTTP 503'
assert len(calls)==1
clock[0]=86400
cache.get('https://example.go.jp/robots.txt',load)
assert len(calls)==2
print('PASS: two distinct targets share cached robots failure; reload occurs at 24h')
# Execute original classify method and helpers, not a rewritten approximation.
tree=ast.parse((ROOT/'crawlers/ckan.py').read_text()); method=next(n for n in next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CkanCrawler').body if isinstance(n,ast.FunctionDef) and n.name=='classify')
env=dict(globals());extracted('ckan.py',{'_API_ROLES','_HTML_FORMATS','_HTML_HEADS','_norm_format','_json_object','_api_ok'},env)
exec(compile(ast.Module(body=[method],type_ignores=[]),'classify','exec'),env)
classify=env['classify']
for role,body in [('package_search',b'{"success":false}'),('package_show',b'not json'),('resource',b'<html><body>404 missing</body></html>')]:
 assert classify(None,SimpleNamespace(meta={'role':role,'format':'csv'}),SimpleNamespace(outcome=FetchOutcome.ok,content=body)) is FetchOutcome.empty_body
print('PASS: API false, invalid JSON and HTML resource response all classify as empty_body')
class Result:
 def model_dump(self):return {'content':b'<html>Error</html>','outcome':FetchOutcome.ok,'error':None}
 @classmethod
 def model_validate(cls,fields):return fields
 @property
 def error(self):return None
env=dict(globals(),FAILED_OUTCOMES={FetchOutcome.too_large},FetchResult=Result)
extracted('runner.py',{'_with_outcome'},env)
assert env['_with_outcome'](Result(),FetchOutcome.empty_body)['content']==b'<html>Error</html>'
print('PASS: empty_body reclassification retains content for raw.put (FAILED_OUTCOMES excludes empty_body)')
