"""Global search: CRM permission, role-filtered sources, accent-insensitive matching."""
import json
import os
from unittest.mock import patch
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import server


class GlobalSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'search.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.admin = {'Authorization': 'Bearer ' + server.ADMIN_TOKEN, 'Content-Type': 'application/json'}

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

    def key(self, role):
        status, data = self.call('POST', '/api/admin/accounts', {'username': 'search.' + role.lower(), 'role': role, 'consultant_id': ''}, self.admin)
        self.assertEqual(status, 201)
        return {'Authorization': 'Bearer ' + data['key']}

    def seed(self):
        server.RATE.clear()
        status, req = self.call('POST', '/api/requests', {'nom': 'Mariam Fictive', 'org': 'Énergie Fictive SA', 'email': 'energie@example.invalid',
            'besoin': 'Projet au forfait', 'solution': '', 'message': 'Fictif', 'consent': True, 'website': ''})
        self.assertEqual(status, 201)
        rid = req['id']
        self.assertEqual(self.call('PATCH', '/api/admin/requests/' + rid, {'status': 'QUALIFIEE', 'previous': 'NOUVELLE'}, self.admin)[0], 200)
        status, conv = self.call('POST', '/api/admin/requests/' + rid + '/convert', headers=self.admin)
        self.assertEqual(status, 201)
        quote = {'opportunity_id': conv['opportunity_id'], 'title': 'Audit énergie', 'scope': 'Fictif', 'mode': 'FORFAIT', 'currency': 'EUR',
                 'days': '5', 'rate': '0', 'daily_cost': '400', 'expenses': '0', 'fixed_price': '9000', 'status': 'PROPOSE', 'valid_until': '2099-01-01', 'terms': 'Fictif'}
        self.assertEqual(self.call('POST', '/api/admin/quotes', quote, self.admin)[0], 201)

    def test_admin_finds_every_source_accent_insensitive(self):
        self.seed()
        status, data = self.call('GET', '/api/admin/crm/search?q=%C3%A9nergie', headers=self.admin)
        self.assertEqual(status, 200)
        kinds = [x['kind'] for x in data['items']]
        self.assertEqual(sorted(set(kinds)), ['DEMANDE', 'DEVIS', 'OPPORTUNITE', 'ORGANISATION'])
        org = next(x for x in data['items'] if x['kind'] == 'ORGANISATION')
        self.assertEqual(org['label'], 'Énergie Fictive SA')
        self.assertTrue(org['url'].startswith('client.html?id='))
        # Uppercase/accents in the query and in the data both fold.
        self.assertEqual(len(self.call('GET', '/api/admin/crm/search?q=ENERGIE%20FICTIVE', headers=self.admin)[1]['items']), 4)
        self.assertEqual(self.call('GET', '/api/admin/crm/search?q=mariam', headers=self.admin)[1]['items'][0]['kind'], 'OPPORTUNITE')

    def test_sources_follow_role_permissions(self):
        self.seed()
        direction = self.key('DIRECTION')
        # DIRECTION needs MFA by default: refused before activation.
        self.assertIn(self.call('GET', '/api/admin/crm/search?q=fictive', headers=direction)[0], (401, 403))
        with patch.dict(os.environ, {'DSIG_MFA_REQUIRED_ROLES': ''}):
            kinds = {x['kind'] for x in self.call('GET', '/api/admin/crm/search?q=fictive', headers=direction)[1]['items']}
        self.assertEqual(kinds, {'ORGANISATION', 'OPPORTUNITE', 'DEVIS'})  # no requests permission
        commercial = self.key('COMMERCIAL')
        kinds = {x['kind'] for x in self.call('GET', '/api/admin/crm/search?q=fictive', headers=commercial)[1]['items']}
        self.assertEqual(kinds, {'ORGANISATION', 'OPPORTUNITE', 'DEMANDE', 'DEVIS'})
        self.assertEqual(self.call('GET', '/api/admin/crm/search?q=fictive', headers=self.key('PROJET'))[0], 403)
        self.assertEqual(self.call('GET', '/api/admin/crm/search?q=fictive')[0], 401)

    def test_query_validation(self):
        for q in ('', 'a', '%20%20a%20', 'x' * 81):
            self.assertEqual(self.call('GET', '/api/admin/crm/search?q=' + q, headers=self.admin)[0], 400, q)
        self.assertEqual(self.call('GET', '/api/admin/crm/search?q=inexistant', headers=self.admin)[1]['items'], [])


if __name__ == '__main__':
    unittest.main()
