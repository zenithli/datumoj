import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import test_export_jma as fixtures
from test_export_jma import HERE, SECRET
import export_jma as tool

class SafetyTests(fixtures.FixtureCase):
    def test_no_network_and_no_input_changes(self):
        before=self.hashes()
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.go()['status'],'complete')
        self.assertEqual(before,self.hashes())
    def test_read_only_connection(self):
        db=tool.dbopen(self.m,'manifest')
        try:
            with self.assertRaises(sqlite3.OperationalError): db.execute('DELETE FROM parsed')
        finally: db.close()
    def test_unknown_budget_code_is_partial(self):
        with sqlite3.connect(self.m) as db: db.execute('UPDATE parsed SET error=?',('budget_exceeded:'+SECRET,))
        out=self.go()
        self.assertEqual(out['status'],'partial')
        self.assertEqual(out['unsupported_or_unmatched_budget_records'],1)
        self.assertNotIn(SECRET,json.dumps(out))
    def test_different_version_is_partial(self):
        with sqlite3.connect(self.m) as db: db.execute("UPDATE parsed SET version='2'")
        self.assertEqual(self.go()['status'],'partial')
    def test_unknown_resource_type_is_partial(self):
        with sqlite3.connect(self.m) as db:
            meta={'resource_type':SECRET}
            fp=hashlib.sha256(tool.canon(['jp-jma',self.url,'application/xml',meta]).encode()).hexdigest()
            db.execute('UPDATE snapshots SET meta=?',(json.dumps(meta),))
            db.execute('UPDATE parsed SET context_fingerprint=?',(fp,))
        self.assertEqual(self.go()['status'],'partial')
    def test_incompatible_column_rejected(self):
        with sqlite3.connect(self.c) as db: db.execute('ALTER TABLE changes ADD COLUMN secret TEXT')
        with self.assertRaises(tool.Rejected): self.go()
    def test_unknown_table_rejected(self):
        with sqlite3.connect(self.m) as db: db.execute('CREATE TABLE surprise (x TEXT)')
        with self.assertRaises(tool.Rejected): self.go()
    def test_duplicate_json_keys_rejected(self):
        self.r.write_text('{"source_id":"jp-jma","source_id":"other"}\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_conflicting_final_duplicate_rejected(self):
        row=dict(self.run,failures={'parse_index_failed':2})
        with self.r.open('a') as f: f.write(json.dumps(row)+'\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_symlink_rejected(self):
        path=self.root/'alias.sqlite';path.symlink_to(self.m)
        with self.assertRaises(tool.Rejected): tool.export(path,self.c,self.r,frozen=True)
    def test_cli_error_never_echoes_input_or_path(self):
        self.r.write_text(SECRET)
        before=self.hashes()
        r=subprocess.run([sys.executable,str(HERE/'export_jma.py'),'--manifest',str(self.m),'--changes',str(self.c),'--runs',str(self.r),'--ack-frozen-consistent-copy'],text=True,capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertEqual(json.loads(r.stdout)['status'],'rejected')
        self.assertEqual(r.stderr,'')
        for x in (SECRET,str(self.root),'Traceback'): self.assertNotIn(x,r.stdout)
        self.assertEqual(before,self.hashes())
    def test_cli_unknown_argument_never_echoes_it(self):
        r=subprocess.run([sys.executable,str(HERE/'export_jma.py'),'--'+SECRET],text=True,capture_output=True)
        self.assertEqual(r.returncode,2)
        self.assertNotIn(SECRET,r.stdout+r.stderr)
    def test_partial_cli_nonzero(self):
        with sqlite3.connect(self.m) as db: db.execute("UPDATE parsed SET version='2'")
        r=subprocess.run([sys.executable,str(HERE/'export_jma.py'),'--manifest',str(self.m),'--changes',str(self.c),'--runs',str(self.r),'--ack-frozen-consistent-copy'],text=True,capture_output=True)
        self.assertEqual(r.returncode,3)
        self.assertEqual(json.loads(r.stdout)['status'],'partial')
    def test_removed_unique_constraint_rejected(self):
        with sqlite3.connect(self.c) as db:
            db.execute('DROP TABLE changes')
            db.execute('CREATE TABLE changes (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL, detected_at TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT NOT NULL, event_json TEXT NOT NULL)')
            db.execute('CREATE INDEX changes_time ON changes(detected_at,seq)')
        with self.assertRaises(tool.Rejected): self.go()
    def test_hidden_generated_column_rejected(self):
        with sqlite3.connect(self.c) as db: db.execute('ALTER TABLE changes ADD COLUMN hidden TEXT GENERATED ALWAYS AS (kind) VIRTUAL')
        with self.assertRaises(tool.Rejected): self.go()
    def test_full_final_conflict_rejected(self):
        row=dict(self.run,exit_status=0,new=2)
        with self.r.open('a') as f: f.write(json.dumps(row)+'\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_negative_counts_rejected(self):
        row=dict(self.run,new=-1)
        self.r.write_text(json.dumps(row)+'\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_end_before_start_rejected(self):
        row=dict(self.run,ended_at='2026-11-03T04:13:24.445332+00:00')
        self.r.write_text(json.dumps(row)+'\n')
        with self.assertRaises(tool.Rejected): self.go()
    def test_changed_inputs_rejected_without_exposing_data(self):
        original=tool.digest
        counter=[0]
        def different_on_final_check(path):
            counter[0]+=1
            return b'x' if counter[0]==4 else original(path)
        before=self.hashes()
        with patch.object(tool,'digest',side_effect=different_on_final_check):
            with self.assertRaisesRegex(tool.Rejected,'^inputs_changed$'): self.go()
        self.assertEqual(before,self.hashes())
    def test_sqlite_lookalike_table_rejected(self):
        with sqlite3.connect(self.m) as db: db.execute('CREATE TABLE sqliteXtrap (x TEXT)')
        with self.assertRaises(tool.Rejected): self.go()
    def test_sqlite_lookalike_trigger_rejected(self):
        with sqlite3.connect(self.m) as db: db.execute('CREATE TRIGGER sqliteXtrap AFTER INSERT ON parsed BEGIN SELECT 1; END')
        with self.assertRaises(tool.Rejected): self.go()
    def test_nonindex_collation_rejected(self):
        with sqlite3.connect(self.c) as db:
            db.execute('DROP TABLE changes')
            db.execute('CREATE TABLE changes (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, detected_at TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT COLLATE NOCASE NOT NULL, event_json TEXT NOT NULL)')
            db.execute('CREATE INDEX changes_time ON changes(detected_at,seq)')
        with self.assertRaises(tool.Rejected): self.go()
    def test_added_check_constraint_rejected(self):
        with sqlite3.connect(self.c) as db:
            db.execute('DROP TABLE changes')
            db.execute('CREATE TABLE changes (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, detected_at TEXT NOT NULL, source_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(length(kind)>0), event_json TEXT NOT NULL)')
            db.execute('CREATE INDEX changes_time ON changes(detected_at,seq)')
        with self.assertRaises(tool.Rejected): self.go()
