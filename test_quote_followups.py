"""Automatic quote follow-up: eligibility, idempotency, exclusions and REC recipient rules."""
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import os
from datetime import date, timedelta
from http.client import HTTPConnection
from pathlib import Path

import contact_mail
import quote_followups
import server

CFG = {'api_key': 're_test_key', 'sender': 'notifications@dsig-consulting.com', 'test_recipient': 'test@example.invalid'}


class QuoteFollowupTests(unittest.TestCase):
    def setUp(self):
        # Follow-up mail is deliberately REC-only; do not inherit runner mode.
        mode = patch.dict(os.environ, {'DSIG_ENV': 'REC'})
        mode.start()
        self.addCleanup(mode.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'followups.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.admin = {'Authorization': 'Bearer ' + server.ADMIN_TOKEN, 'Content-Type': 'application/json'}
        self.later = date.today() + timedelta(days=quote_followups.DELAY_DAYS)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def call(self, method, path, payload=None, headers=None, status=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request(method, path, None if payload is None else json.dumps(payload), headers or {'Content-Type': 'application/json'})
        res = conn.getresponse()
        body = res.read()
        conn.close()
        if status is not None:
            self.assertEqual(res.status, status, body)
        return json.loads(body) if body else None

    def transmitted_quote(self, email='prospect@example.invalid', language='fr', valid_until='2099-01-01', besoin='Mission en régie'):
        server.RATE.clear()
        rid = self.call('POST', '/api/requests', {'nom': 'Contact fictif', 'org': 'Org ' + email, 'email': email, 'besoin': besoin,
            'solution': '', 'message': 'Fictif', 'consent': True, 'website': '', 'language': language}, status=201)['id']
        self.call('PATCH', '/api/admin/requests/' + rid, {'status': 'QUALIFIEE', 'previous': 'NOUVELLE'}, self.admin, 200)
        oid = self.call('POST', '/api/admin/requests/' + rid + '/convert', headers=self.admin, status=201)['opportunity_id']
        quote = {'opportunity_id': oid, 'title': 'Devis relance', 'scope': 'Fictif', 'mode': 'REGIE', 'currency': 'EUR', 'days': '5', 'rate': '500',
                 'daily_cost': '300', 'expenses': '0', 'fixed_price': '0', 'status': 'PROPOSE', 'valid_until': valid_until, 'terms': 'Fictif'}
        qid = self.call('POST', '/api/admin/quotes', quote, self.admin, 201)['id']
        self.call('POST', '/api/admin/quotes/' + qid + '/transmission', {'version': 1, 'action': 'TRANSMIS', 'evidence': 'Envoi fictif'}, self.admin, 200)
        return rid, oid, qid

    def schedule(self, day):
        with server.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return quote_followups.schedule(db, day)

    def followups(self):
        with server.connect() as db:
            return db.execute("SELECT request_id,kind,language,state FROM contact_mail WHERE kind LIKE 'followup-%'").fetchall()

    def test_one_followup_after_delay_and_idempotent(self):
        rid, _, qid = self.transmitted_quote(language='en')
        self.assertEqual(self.schedule(self.later - timedelta(days=1)), 0)
        self.assertEqual(self.schedule(self.later), 1)
        self.assertEqual(self.schedule(self.later + timedelta(days=3)), 0)
        version = self.followups()[0][1].rsplit('-v', 1)[1]
        self.assertEqual(self.followups(), [(rid, quote_followups.kind(qid, int(version)), 'en', 'PENDING')])
        with server.connect() as db:
            note = db.execute("SELECT note FROM request_workflow_events WHERE actor='SYSTEME:relances'").fetchone()[0]
            self.assertIn('Devis relance', note)
            self.assertEqual(db.execute("SELECT action FROM access_events WHERE actor='SYSTEME:relances'").fetchone()[0], 'RELANCE_DEVIS_PLANIFIEE')

    def test_exclusions(self):
        _, oid_lost, _ = self.transmitted_quote(email='lost@example.invalid')
        self.transmitted_quote(email='expired@example.invalid', valid_until=(date.today() + timedelta(days=2)).isoformat())
        _, _, qid_ok = self.transmitted_quote(email='accepted@example.invalid')
        self.call('POST', '/api/admin/quotes/' + qid_ok + '/transmission', {'version': 1, 'action': 'ACCEPTE', 'evidence': 'Accord fictif'}, self.admin, 200)
        with server.connect() as db:
            db.execute("UPDATE opportunities SET status='PERDU' WHERE id=?", (oid_lost,))
        self.assertEqual(self.schedule(self.later), 0)
        self.assertEqual(self.followups(), [])

    def test_worker_applies_rec_recipient_rules_and_template(self):
        rid, _, _ = self.transmitted_quote(email='allowed@example.invalid')
        other, _, _ = self.transmitted_quote(email='other@example.invalid')
        self.assertEqual(self.schedule(self.later), 2)
        with server.connect() as db:
            db.execute("UPDATE contact_mail SET state='ACCEPTED' WHERE kind NOT LIKE 'followup-%'")
        delivered = []
        def fake(cfg, request_id, kind, language, **kwargs):
            subject, plain, _ = quote_followups.render(request_id, language)
            delivered.append((request_id, kwargs.get('recipient'), subject))
            return 'provider-' + str(len(delivered))
        result = contact_mail.run(server.connect, CFG | {'rec_customer_recipients': ['allowed@example.invalid']}, deliver=fake)
        self.assertEqual(result['accepted'], 2)
        recipients = {r: to for r, to, _ in delivered}
        self.assertEqual(recipients[rid], 'allowed@example.invalid')
        self.assertEqual(recipients[other], 'test@example.invalid')
        self.assertTrue(all(s == '[REC TEST] DSIG — Suivi de notre proposition' for _, _, s in delivered))
        self.assertEqual({row[3] for row in self.followups()}, {'ACCEPTED'})

    def test_render_bilingual_without_quote_details(self):
        for language, expected in (('fr', 'Suivi de notre proposition'), ('en', 'Following up on our proposal')):
            subject, plain, markup = quote_followups.render('ref-<b>', language)
            self.assertIn(expected, subject)
            self.assertIn('ref-<b>', plain)
            self.assertIn('ref-&lt;b&gt;', markup)
            self.assertNotIn('EUR', plain)


if __name__ == '__main__':
    unittest.main()
