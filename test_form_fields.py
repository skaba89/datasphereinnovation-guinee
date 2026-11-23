"""Contact form fields aligned with issue #156: optional phone/WhatsApp and new request types."""
import json
import sqlite3
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import contact_ack
import server

BASE = {'nom': 'Contact fictif', 'org': 'Org fictive', 'email': 'contact@example.invalid', 'besoin': 'Demande de devis',
        'solution': '', 'message': 'Fictif', 'consent': True, 'website': ''}


class FormFieldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'form.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32

    def tearDown(self):
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def test_phone_validation(self):
        for phone in ('', '+224 620 00 00 00', '0033 6 12 34 56 78', '620000000', '+1 (555) 010-0000'):
            self.assertEqual(server.validate(BASE | {'telephone': phone})['telephone'], phone)
        self.assertEqual(server.validate(BASE)['telephone'], '')  # older clients without the field
        for bad in ('abc', '12', '+', '+224 620 00 00 00 00 00 00 00 00 00', '<script>', '620000000; DROP', 123):
            with self.assertRaises(ValueError):
                server.validate(BASE | {'telephone': bad})

    def test_new_request_types_and_acknowledgements(self):
        for need in ('Demande de devis', 'Formation', 'Autre demande'):
            self.assertEqual(server.validate(BASE | {'besoin': need})['besoin'], need)
            self.assertIn(need, contact_ack.TYPES)
            for language in ('fr', 'en'):
                subject, text, markup = contact_ack.render('ref', need, language)
                self.assertTrue(subject and text and markup)
        with self.assertRaises(ValueError):
            server.validate(BASE | {'besoin': 'Type inconnu'})

    def test_additive_migration_of_an_existing_database(self):
        legacy = sqlite3.connect(server.DB)
        legacy.execute("""CREATE TABLE requests (id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            nom TEXT NOT NULL, org TEXT NOT NULL, email TEXT NOT NULL, besoin TEXT NOT NULL, solution TEXT NOT NULL,
            message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'NOUVELLE')""")
        legacy.execute("INSERT INTO requests(id,nom,org,email,besoin,solution,message) VALUES ('old','N','O','e@example.invalid','Data & IA','','M')")
        legacy.commit()
        legacy.close()
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT telephone FROM requests WHERE id='old'").fetchone()[0], '')
        with server.connect() as db:  # idempotent
            self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(requests)')].count('telephone'), 1)

    def test_intake_stores_phone_and_admin_sees_it(self):
        server.RATE.clear()
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        try:
            def call(method, path, payload=None, headers=None):
                conn = HTTPConnection('127.0.0.1', http.server_address[1], timeout=5)
                conn.request(method, path, None if payload is None else json.dumps(payload), headers or {'Content-Type': 'application/json'})
                res = conn.getresponse()
                body = json.loads(res.read() or b'null')
                conn.close()
                return res.status, body
            status, body = call('POST', '/api/requests', BASE | {'besoin': 'Formation', 'telephone': '+224 620 00 00 00'})
            self.assertEqual(status, 201, body)
            self.assertEqual(call('POST', '/api/requests', BASE | {'telephone': 'pas un numéro'})[0], 400)
            status, listing = call('GET', '/api/admin/requests', headers={'Authorization': 'Bearer ' + server.ADMIN_TOKEN})
            self.assertEqual(status, 200)
            self.assertEqual((listing['items'][0]['besoin'], listing['items'][0]['telephone']), ('Formation', '+224 620 00 00 00'))
            # Erasure also removes the phone number.
            self.assertEqual(call('POST', f"/api/admin/requests/{body['id']}/erase", {}, {'Authorization': 'Bearer ' + server.ADMIN_TOKEN,
                                                                                         'Content-Type': 'application/json'})[0], 200)
            with server.connect() as db:
                self.assertEqual(db.execute('SELECT telephone,email FROM requests WHERE id=?', (body['id'],)).fetchone(), ('', ''))
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
