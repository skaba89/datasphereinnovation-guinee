"""Automatic CRM lead from web requests: creation, deduplication, assignment, promotion."""
import datetime
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import lead_automation
import server


class LeadAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'leads.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.auth = {'Authorization': 'Bearer ' + server.ADMIN_TOKEN, 'Content-Type': 'application/json'}

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def call(self, method, path, payload=None, headers=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request(method, path, None if payload is None else json.dumps(payload), headers or {'Content-Type': 'application/json'})
        res = conn.getresponse()
        body = res.read()
        conn.close()
        return res.status, json.loads(body) if body else None

    def submit(self, **changes):
        payload = {'nom': 'Contact fictif', 'org': 'Organisation fictive', 'email': 'lead@example.invalid',
                   'besoin': 'Mission en régie', 'solution': '', 'message': 'Besoin fictif',
                   'consent': True, 'website': ''} | changes
        server.RATE.clear()
        status, body = self.call('POST', '/api/requests', payload)
        self.assertEqual(status, 201, body)
        return body['id']

    def rows(self, sql, args=()):
        with server.connect() as db:
            return db.execute(sql, args).fetchall()

    def test_request_creates_prospect_with_sla_and_history(self):
        rid = self.submit()
        due = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
        (oid, company, contact, title, mode, status, followup, version), = self.rows(
            'SELECT id,company,contact,title,mode,status,followup,version FROM opportunities')
        self.assertEqual((company, contact, title, mode, status, followup, version),
                         ('Organisation fictive', 'Contact fictif', 'Mission en régie', 'REGIE', 'PROSPECT', due, 1))
        self.assertEqual(self.rows('SELECT status FROM opportunity_events WHERE opportunity_id=?', (oid,)), [('PROSPECT',)])
        self.assertEqual(self.rows('SELECT outcome FROM request_leads WHERE request_id=?', (rid,)), [('CREATED',)])
        self.assertEqual(self.rows("SELECT action FROM access_events WHERE actor='SYSTEME:site-web'"), [('PROSPECT_AUTO_CREATED',)])
        status, data = self.call('GET', '/api/admin/requests', headers=self.auth)
        self.assertEqual(status, 200)
        item = data['items'][0]
        self.assertEqual((item['lead']['opportunity_id'], item['lead']['status']), (oid, 'PROSPECT'))
        self.assertIsNone(item['conversion'])
        status, crm = self.call('GET', '/api/admin/crm?status=PROSPECT', headers=self.auth)
        self.assertEqual([x['id'] for x in crm['items']], [oid])

    def test_same_email_links_open_opportunity_without_duplicate(self):
        self.submit()
        rid = self.submit(email='LEAD@example.invalid ', org='Autre libellé fictif', besoin='Data & IA')
        self.assertEqual(self.rows('SELECT count(*) FROM opportunities'), [(1,)])
        self.assertEqual(self.rows('SELECT outcome FROM request_leads WHERE request_id=?', (rid,)), [('DUPLICATE',)])
        # A closed opportunity no longer absorbs new requests.
        with server.connect() as db:
            db.execute("UPDATE opportunities SET status='PERDU'")
        self.submit()
        self.assertEqual(self.rows('SELECT count(*) FROM opportunities'), [(2,)])

    def test_spontaneous_application_never_reaches_crm(self):
        rid = self.submit(besoin='Candidature spontanée')
        self.assertEqual(self.rows('SELECT count(*) FROM opportunities'), [(0,)])
        self.assertEqual(self.rows('SELECT count(*) FROM request_leads'), [(0,)])
        self.assertEqual(self.rows('SELECT count(*) FROM request_workflow WHERE request_id=?', (rid,)), [(0,)])

    def test_assignment_balances_open_workload_and_demo_priority(self):
        with server.connect() as db:
            for uid, name in (('alpha', 'commercial.alpha'), ('beta', 'commercial.beta')):
                db.execute("INSERT INTO accounts(id,username,role,key_hash) VALUES (?,?,'COMMERCIAL',?)", (uid, name, 'fictional-hash-' + uid))
            db.execute("INSERT INTO accounts(id,username,role,key_hash,enabled) VALUES ('off','commercial.off','COMMERCIAL','fictional-hash-off',0)")
        owners = [self.rows('SELECT owner_id FROM request_workflow WHERE request_id=?', (self.submit(email=f'p{i}@example.invalid'),))[0][0] for i in range(4)]
        self.assertEqual(sorted(owners), ['alpha', 'alpha', 'beta', 'beta'])
        rid = self.submit(email='demo@example.invalid', besoin='Demande de démonstration', solution='Plateforme fictive')
        self.assertEqual(self.rows('SELECT priority FROM request_workflow WHERE request_id=?', (rid,)), [('HAUTE',)])
        self.assertEqual(self.rows('SELECT title FROM opportunities WHERE email=?', ('demo@example.invalid',)),
                         [('Demande de démonstration — Plateforme fictive',)])

    def test_qualification_promotes_automatic_lead(self):
        rid = self.submit()
        route = '/api/admin/requests/' + rid
        self.assertEqual(self.call('POST', route + '/convert', headers=self.auth)[0], 409)
        self.assertEqual(self.call('PATCH', route, {'status': 'QUALIFIEE', 'previous': 'NOUVELLE'}, self.auth)[0], 200)
        status, result = self.call('POST', route + '/convert', headers=self.auth)
        self.assertEqual(status, 201)
        (oid, opp_status, version, next_action), = self.rows('SELECT id,status,version,next_action FROM opportunities')
        self.assertEqual((result['opportunity_id'], opp_status, version), (oid, 'QUALIFIE', 2))
        self.assertEqual(next_action, 'Prendre contact et cadrer le besoin')
        self.assertEqual([r[0] for r in self.rows('SELECT status FROM opportunity_events WHERE opportunity_id=? ORDER BY id', (oid,))],
                         ['PROSPECT', 'QUALIFIE'])
        self.assertEqual(self.rows('SELECT count(*) FROM organization_links WHERE opportunity_id=?', (oid,)), [(1,)])
        self.assertEqual(self.call('POST', route + '/convert', headers=self.auth), (200, result))

    def test_lead_failure_rolls_back_intake(self):
        original = lead_automation.on_request
        def broken(*args, **kwargs):
            raise server.sqlite3.OperationalError('fictional failure')
        lead_automation.on_request = broken
        try:
            status, _ = self.call('POST', '/api/requests', {'nom': 'Contact fictif', 'org': 'Org fictive', 'email': 'x@example.invalid',
                'besoin': 'Mission en régie', 'solution': '', 'message': 'Fictif', 'consent': True, 'website': ''})
        finally:
            lead_automation.on_request = original
        self.assertEqual(status, 503)
        self.assertEqual(self.rows('SELECT count(*) FROM requests'), [(0,)])


if __name__ == '__main__':
    unittest.main()
