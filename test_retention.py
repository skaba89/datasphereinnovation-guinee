"""Retention (automatic anonymization) and erasure on request of contact-request personal data."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import retention
import server

TODAY = date(2026, 11, 23)


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        mfa = patch.dict(os.environ, {'DSIG_MFA_REQUIRED_ROLES': ''})
        mfa.start()
        self.addCleanup(mfa.stop)
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'retention.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        with server.connect() as db:
            req = "INSERT INTO requests(id,created_at,nom,org,email,besoin,solution,message,status) VALUES (?,?,?,?,?,'Data & IA','',?,?)"
            db.execute(req, ('00000000-0000-0000-0000-00000000000a', '2022-01-10 09:00:00', 'Ancien Prospect', 'Org ancienne', 'ancien@example.invalid', 'Message ancien', 'PERDUE'))
            db.execute(req, ('00000000-0000-0000-0000-00000000000b', '2022-01-10 09:00:00', 'Actif Récent', 'Org active', 'actif@example.invalid', 'Message actif', 'EN_COURS'))
            db.execute("INSERT INTO request_events(request_id,created_at,previous_status,new_status) VALUES ('00000000-0000-0000-0000-00000000000b','2026-06-01 10:00:00','NOUVELLE','EN_COURS')")
            db.execute(req, ('00000000-0000-0000-0000-00000000000c', '2022-01-10 09:00:00', 'Client Qualifié', 'Org cliente', 'client@example.invalid', 'Message client', 'GAGNEE'))
            db.execute(req, ('00000000-0000-0000-0000-00000000000d', '2026-11-01 09:00:00', 'Récent', 'Org récente', 'recent@example.invalid', 'Message récent', 'NOUVELLE'))
            opp = "INSERT INTO opportunities(id,company,contact,email,title,mode,skills,consultant_id,next_action,followup,notes,status) VALUES (?,?,?,?,'Titre','CONSEIL','','','','',?,?)"
            db.execute(opp, ('o-lead', 'Org ancienne', 'Ancien Prospect', 'ancien@example.invalid', 'Notes privées', 'PROSPECT'))
            db.execute(opp, ('o-client', 'Org cliente', 'Client Qualifié', 'client@example.invalid', 'Notes client', 'GAGNE'))
            db.execute("INSERT INTO request_leads(request_id,opportunity_id,outcome) VALUES ('00000000-0000-0000-0000-00000000000a','o-lead','CREATED')")
            db.execute("INSERT INTO request_opportunities(request_id,opportunity_id,actor) VALUES ('00000000-0000-0000-0000-00000000000c','o-client','test')")
            db.execute("INSERT INTO request_workflow_events(request_id,actor,owner_id,priority,due_date,note,created_at) VALUES ('00000000-0000-0000-0000-00000000000a','x','','NORMALE','','Appelé M. Ancien au 620','2022-01-11 09:00:00')")
            db.execute("INSERT INTO contact_mail(request_id,kind,language,created,next_attempt) VALUES ('00000000-0000-0000-0000-00000000000a','status-QUALIFIEE','fr',0,0)")
            db.execute("INSERT INTO contact_mail_recipient VALUES ('00000000-0000-0000-0000-00000000000a','ack','ancien@example.invalid')")

    def tearDown(self):
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def dump(self):
        with server.connect() as db:
            return '\n'.join(str(row) for table in ('requests', 'opportunities', 'request_workflow_events', 'contact_mail_recipient')
                             for row in db.execute(f'SELECT * FROM {table}'))

    def test_dry_run_then_apply_only_inactive_unqualified(self):
        with server.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(retention.purge(db, TODAY, apply=False), {'retention_days': 1095, 'eligible': 1, 'anonymized': 0, 'applied': False})
        self.assertIn('ancien@example.invalid', self.dump())
        with server.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(retention.purge(db, TODAY, apply=True)['anonymized'], 1)
            self.assertEqual(retention.purge(db, TODAY, apply=True)['eligible'], 0)  # idempotent
            row = db.execute("SELECT nom,org,email,message,besoin,status FROM requests WHERE id='00000000-0000-0000-0000-00000000000a'").fetchone()
            self.assertEqual(row, ('[supprimé]', '[supprimé]', '', '[supprimé]', 'Data & IA', 'PERDUE'))  # statistics kept
            self.assertEqual(db.execute("SELECT state FROM contact_mail WHERE kind='status-QUALIFIEE'").fetchone()[0], 'FAILED')
            self.assertEqual(db.execute("SELECT action,resource FROM access_events WHERE action='DEMANDE_ANONYMISEE'").fetchone(),
                             ('DEMANDE_ANONYMISEE', '00000000-0000-0000-0000-00000000000a (inactivité > 1095 j)'))
        dump = self.dump()
        for gone in ('ancien@example.invalid', 'Ancien Prospect', 'Message ancien', 'Notes privées', 'M. Ancien'):
            self.assertNotIn(gone, dump)
        for kept in ('actif@example.invalid', 'client@example.invalid', 'recent@example.invalid', 'Notes client'):
            self.assertIn(kept, dump)

    def test_retention_days_configuration(self):
        for bad in ('0', '29', '3651', 'abc', '-5'):
            with patch.dict(os.environ, {'DSIG_REQUEST_RETENTION_DAYS': bad}), self.assertRaises(ValueError):
                retention.retention_days()
        with patch.dict(os.environ, {'DSIG_REQUEST_RETENTION_DAYS': '30'}), server.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.assertEqual(retention.purge(db, TODAY)['eligible'], 2)  # also the request active in June; not the one from 2026-11-01 (22 days)

    def test_erasure_endpoint_admin_only(self):
        server.RATE.clear()
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            def call(path, key):
                conn = HTTPConnection('127.0.0.1', http.server_address[1], timeout=5)
                conn.request('POST', path, '{}', {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'} if key else {})
                res = conn.getresponse()
                body = json.loads(res.read() or b'null')
                conn.close()
                return res.status, body
            admin = server.ADMIN_TOKEN
            conn = HTTPConnection('127.0.0.1', http.server_address[1], timeout=5)
            conn.request('POST', '/api/admin/accounts', json.dumps({'username': 'commercial.erase', 'role': 'COMMERCIAL', 'consultant_id': ''}),
                         {'Authorization': 'Bearer ' + admin, 'Content-Type': 'application/json'})
            commercial = json.loads(conn.getresponse().read())['key']
            conn.close()
            target = '/api/admin/requests/00000000-0000-0000-0000-00000000000c/erase'
            self.assertEqual(call(target, '')[0], 401)
            self.assertEqual(call(target, commercial)[0], 403)
            self.assertEqual(call('/api/admin/requests/00000000-0000-0000-0000-0000000000ff/erase', admin)[0], 404)
            self.assertEqual(call(target, admin), (200, {'status': 'ANONYMISEE'}))
            self.assertEqual(call(target, admin), (200, {'status': 'DEJA_ANONYMISEE'}))
        finally:
            http.shutdown()
            http.server_close()
            thread.join()
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT email FROM requests WHERE id='00000000-0000-0000-0000-00000000000c'").fetchone()[0], '')
            # A real client relationship (won opportunity) keeps its CRM record.
            self.assertEqual(db.execute("SELECT email FROM opportunities WHERE id='o-client'").fetchone()[0], 'client@example.invalid')

    def test_fresh_database_allows_cli_transactions(self):
        # Regression: schema seeding (default email templates) used to leave a transaction open,
        # so the scheduled jobs failed with "cannot start a transaction within a transaction".
        fresh = Path(self.tmp.name) / 'fresh' / 'new.sqlite3'
        env = os.environ | {'DSIG_DB': str(fresh), 'DSIG_ENV': 'REC'}
        root = Path(server.__file__).resolve().parent
        for args in (['--purge-requests'], ['--automation-preview']):
            fresh.parent.mkdir(exist_ok=True)
            if fresh.exists():
                fresh.unlink()
            result = subprocess.run([sys.executable, 'server.py', *args], cwd=root, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))
        with server.connect() as db:
            self.assertFalse(db.in_transaction)


if __name__ == '__main__':
    unittest.main()
