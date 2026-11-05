import ast
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import export_jma as tool

HERE = Path(__file__).parent
# Exact literal DDL captured from the pinned upstream schema.
DDL = (HERE / 'fixture_manifest.sql').read_text().split('CREATE TABLE raw_allowed_missing')[0]
CHANGES_DDL = '''CREATE TABLE changes (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, detected_at TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT NOT NULL, event_json TEXT NOT NULL); CREATE INDEX changes_time ON changes(detected_at, seq);'''
STAMP='2026-11-04T04:13:24.445332+00:00'
SECRET='SENSITIVE_SENTINEL_123'

def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)

class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.m,self.c,self.r=[self.root/x for x in ['manifest.sqlite','changes.sqlite','runs.jsonl']]
        with sqlite3.connect(self.m) as db:
            db.executescript(DDL)
            db.execute('INSERT INTO schema_version VALUES(4)')
            db.execute('CREATE TABLE raw_allowed_missing (sha256 TEXT PRIMARY KEY, marked_at TEXT NOT NULL)')
        with sqlite3.connect(self.c) as db: db.executescript(CHANGES_DDL)
        self.r.write_text('')
        self.url='https://synthetic.invalid/'+SECRET+'?token='+SECRET
        self.sha='a'*64
        self.sid='snapshot-'+SECRET
        self.meta={'resource_type':'entry','entry_id':self.url}
        self.snap={'snapshot_id':self.sid,'source_id':'jp-jma','resource_url':self.url,'fetched_at':STAMP,'outcome':'ok','sha256':self.sha,'size':1,'content_type':'application/xml'}
        self.fp=hashlib.sha256(canonical(['jp-jma',self.url,'application/xml',self.meta]).encode()).hexdigest()
        with sqlite3.connect(self.m) as db:
            db.execute('INSERT INTO snapshots(snapshot_id,source_id,resource_url,fetched_at,outcome,sha256,meta,snapshot) VALUES(?,?,?,?,?,?,?,?)',(self.sid,'jp-jma',self.url,'2026-11-04T04:13:24.445332','ok',self.sha,json.dumps(self.meta),json.dumps(self.snap)))
            db.execute('INSERT INTO parsed VALUES(?,?,?,?,?,?,?)',(self.sha,'jma_xml','1',self.fp,'failed','budget_exceeded:duration_seconds',None))
            db.execute('INSERT INTO publish_states VALUES(?,?,?)',(self.sid,'failed','budget_exceeded:duration_seconds'))
        self.event={'event_id':'b'*64,'source_id':'jp-jma','kind':'parse_failed','doc_key':None,'resource_url':self.url,'old_sha256':None,'new_sha256':self.sha,'detected_at':STAMP,'summary':f'解析失败 [policy]；快照 {self.sid}：budget_exceeded:duration_seconds','locator':None}
        self.event['event_id']=hashlib.sha256(json.dumps(['jp-jma','parse_failed',None,self.url,None,self.sha],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.add_event(self.event)
        self.run={'source_id':'jp-jma','run_id':SECRET,'state':'final','started_at':STAMP,'ended_at':STAMP,'status':'incomplete','exit_status':1,'new':1,'unchanged':0,'failures':{'parse_index_failed':1},'stop_reason':'deadline'}
        self.r.write_text(json.dumps(self.run)+'\n'+json.dumps(self.run)+'\n')
    def add_event(self,event):
        with sqlite3.connect(self.c) as db: db.execute('INSERT OR IGNORE INTO changes(event_id,detected_at,source_id,kind,event_json) VALUES(?,?,?,?,?)',(event['event_id'],event['detected_at'],event['source_id'],event['kind'],json.dumps(event)))
    def hashes(self): return [hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.m,self.c,self.r)]
    def go(self): return tool.export(self.m,self.c,self.r,frozen=True)

class Tests(FixtureCase):
    def test_export_exact_context_and_no_sensitive_data(self):
        before=self.hashes(); report=self.go()
        self.assertEqual(report.get('status'),'complete')
        row=report['snapshots'][0]
        self.assertEqual(row['budget_category'],'duration_seconds')
        self.assertEqual(row['resource_type'],'entry')
        self.assertEqual(row['retained_event_count'],1)
        self.assertEqual(row['earliest_retained_event_at'],STAMP)
        self.assertEqual(len(report['runs']),1)
        text=json.dumps(report)
        for secret in (SECRET,self.sha,self.sid,self.url,self.fp): self.assertNotIn(secret,text)
        self.assertEqual(before,self.hashes())
    def test_anonymous_ids_change_each_export(self):
        a=self.go(); b=self.go()
        self.assertIn('snapshots',a)
        self.assertNotEqual(a['snapshots'][0]['token'],b['snapshots'][0]['token'])
    def test_different_context_or_parser_not_joined(self):
        with sqlite3.connect(self.m) as db:
            db.execute('UPDATE parsed SET context_fingerprint=?',('c'*64,))
            db.execute('INSERT INTO parsed VALUES(?,?,?,?,?,?,?)',(self.sha,'other','9',self.fp,'failed','budget_exceeded:pages',None))
        report=self.go()
        self.assertEqual(report.get('status'),'partial')
        self.assertEqual(report['snapshots'],[])
        self.assertEqual(report['unsupported_or_unmatched_budget_records'],2)
    def test_cached_event_dedup_not_attempt_count(self):
        self.add_event(self.event)
        report=self.go()
        self.assertIn('snapshots',report)
        self.assertEqual(report['snapshots'][0]['retained_event_count'],1)
        self.assertNotIn('attempt_count',json.dumps(report))
    def test_requires_frozen_ack(self):
        with self.assertRaises(tool.Rejected): tool.export(self.m,self.c,self.r)
    def test_reject_schema_version_without_writing(self):
        with sqlite3.connect(self.m) as db: db.execute('UPDATE schema_version SET version=5')
        before=self.hashes()
        with self.assertRaises(tool.Rejected): self.go()
        self.assertEqual(before,self.hashes())
    def test_reject_added_table_and_view(self):
        with sqlite3.connect(self.m) as db: db.execute('CREATE VIEW trap AS SELECT * FROM snapshots')
        with self.assertRaises(tool.Rejected): self.go()
    def test_reject_wal_sidecar(self):
        Path(str(self.m)+'-wal').write_bytes(b'not a frozen copy')
        with self.assertRaises(tool.Rejected): self.go()
    def test_reject_corrupt_runs(self):
        self.r.write_text(SECRET+'\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_no_event_for_wrong_snapshot_summary(self):
        with sqlite3.connect(self.c) as db: db.execute('DELETE FROM changes')
        e=dict(self.event,summary='解析失败 [policy]；快照 OTHER：budget_exceeded:duration_seconds')
        self.add_event(e)
        report=self.go(); self.assertIn('snapshots',report)
        self.assertEqual(report['snapshots'][0]['retained_event_count'],0)
        self.assertIsNone(report['snapshots'][0]['earliest_retained_event_at'])
    def test_reject_snapshot_columns_disagree(self):
        with sqlite3.connect(self.m) as db: db.execute('UPDATE snapshots SET resource_url=?',('https://different.invalid',))
        with self.assertRaises(tool.Rejected): self.go()

if __name__=='__main__': unittest.main()
