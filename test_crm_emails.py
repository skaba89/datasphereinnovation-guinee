"""Commercial email templates: defaults, placeholders, ADMIN management, preview, logging, history."""
import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import crm_emails
import server


class CrmEmailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        mfa = patch.dict(os.environ, {'DSIG_MFA_REQUIRED_ROLES': ''})
        mfa.start()
        self.addCleanup(mfa.stop)
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'emails.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.admin = self.headers(server.ADMIN_TOKEN)
        self.commercial = self.account('alice.mail', 'COMMERCIAL')
        self.direction = self.account('direction.mail', 'DIRECTION')
        opp = {'company': 'Société fictive', 'contact': 'Awa Fictive', 'email': 'awa@example.invalid', 'title': 'Audit data', 'mode': 'CONSEIL',
               'skills': '', 'consultant_id': '', 'next_action': '', 'followup': '', 'notes': '', 'status': 'QUALIFIE'}
        self.opp = self.call('POST', '/api/admin/crm', opp, self.admin, 201)['id']
        self.no_email = self.call('POST', '/api/admin/crm', opp | {'email': '', 'title': 'Sans e-mail'}, self.admin, 201)['id']

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    @staticmethod
    def headers(key):
        return {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}

    def account(self, username, role):
        return self.headers(self.call('POST', '/api/admin/accounts', {'username': username, 'role': role, 'consultant_id': ''}, self.admin, 201)['key'])

    def call(self, method, path, payload=None, headers=None, status=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request(method, path, None if payload is None else json.dumps(payload), headers or {})
        res = conn.getresponse()
        body = res.read()
        conn.close()
        if status is not None:
            self.assertEqual(res.status, status, body)
        return json.loads(body) if body else None

    def template(self, code='RELANCE', language='fr'):
        items = self.call('GET', '/api/admin/crm/email-templates', headers=self.commercial, status=200)['items']
        return next(t for t in items if t['code'] == code and t['language'] == language)

    def test_defaults_and_permissions(self):
        d = self.call('GET', '/api/admin/crm/email-templates', headers=self.commercial, status=200)
        self.assertEqual(len(d['items']), 6)
        self.assertEqual({(t['code'], t['language']) for t in d['items']},
                         {(c, l) for c in ('PRESENTATION', 'ENVOI_DEVIS', 'RELANCE') for l in ('fr', 'en')})
        self.assertEqual((d['can_compose'], d['can_manage']), (True, False))
        self.assertEqual(self.call('GET', '/api/admin/crm/email-templates', headers=self.direction, status=200)['can_compose'], False)
        new = {'name': 'Test', 'language': 'fr', 'active': True, 'subject': 'Objet', 'body': 'Bonjour {contact}'}
        self.call('POST', '/api/admin/crm/email-templates', new, self.commercial, 403)
        self.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': self.opp, 'template_id': d['items'][0]['id']}, self.direction, 403)
        self.call('GET', '/api/admin/crm/email-templates', status=401)

    def test_admin_manages_templates_with_placeholder_check_and_locking(self):
        base = {'name': 'Invitation', 'language': 'fr', 'active': True, 'subject': 'Invitation {societe}', 'body': 'Bonjour {contact},\nÀ bientôt.\n{commercial}'}
        for bad in ({'body': 'Bonjour {nom}'}, {'subject': 'Objet {societe'}, {'language': 'de'}, {'name': ''}, {'subject': 'a\nb'}, {'extra': 1}):
            self.call('POST', '/api/admin/crm/email-templates', base | bad, self.admin, 400)
        tid = self.call('POST', '/api/admin/crm/email-templates', base | {'code': 'INVITATION'}, self.admin, 201)['id']
        self.call('PATCH', '/api/admin/crm/email-templates/' + tid, base | {'active': False, 'version': 1}, self.admin, 200)
        self.call('PATCH', '/api/admin/crm/email-templates/' + tid, base | {'version': 1}, self.admin, 409)
        self.call('PATCH', '/api/admin/crm/email-templates/00000000-0000-0000-0000-000000000000', base | {'version': 1}, self.admin, 404)
        # Inactive templates are hidden from commercials and cannot be used.
        names = [t['name'] for t in self.call('GET', '/api/admin/crm/email-templates', headers=self.commercial, status=200)['items']]
        self.assertNotIn('Invitation', names)
        self.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': self.opp, 'template_id': tid}, self.commercial, 400)
        self.assertEqual(len(self.call('GET', '/api/admin/crm/email-templates', headers=self.admin, status=200)['items']), 7)

    def test_preview_record_and_history(self):
        t = self.template()
        preview = self.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': self.opp, 'template_id': t['id']}, self.commercial, 200)
        self.assertEqual(preview['to'], 'awa@example.invalid')
        self.assertEqual(preview['subject'], 'DSIG — Suite à notre échange : Audit data')
        self.assertTrue(preview['body'].startswith('Bonjour Awa Fictive,'))
        self.assertIn('alice.mail', preview['body'])
        self.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': self.no_email, 'template_id': t['id']}, self.commercial, 409)
        self.call('POST', '/api/admin/crm/emails/preview', {'opportunity_id': 'absente', 'template_id': t['id']}, self.commercial, 404)
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM crm_email_log').fetchone()[0], 0)  # preview never logs
        sent = {'opportunity_id': self.opp, 'template_id': t['id'], 'subject': 'Objet ajusté', 'body': preview['body'] + '\nPS : ajouté'}
        self.call('POST', '/api/admin/crm/emails', sent | {'subject': ''}, self.commercial, 400)
        logged = self.call('POST', '/api/admin/crm/emails', sent, self.commercial, 201)
        self.assertEqual((logged['to'], logged['subject']), ('awa@example.invalid', 'Objet ajusté'))
        history = self.call('GET', '/api/admin/crm/emails?opportunity_id=' + self.opp, headers=self.direction, status=200)['items']
        self.assertEqual([(h['subject'], h['actor'], h['template']) for h in history], [('Objet ajusté', 'alice.mail', 'Relance')])
        self.call('GET', '/api/admin/crm/emails?opportunity_id=bad', headers=self.commercial, status=400)
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM access_events WHERE action='EMAIL_COMMERCIAL_PREPARE'").fetchone()[0], 1)

    def test_client_overview_shows_emails_in_timeline(self):
        org = self.call('POST', '/api/admin/crm/organizations', {'name': 'Société fictive', 'kind': 'CLIENT', 'country': '', 'notes': ''}, self.admin, 201)['id']
        with server.connect() as db:
            db.execute('INSERT INTO organization_links(organization_id,opportunity_id) VALUES (?,?)', (org, self.opp))
        t = self.template('PRESENTATION', 'en')
        self.call('POST', '/api/admin/crm/emails', {'opportunity_id': self.opp, 'template_id': t['id'], 'subject': 'Hello', 'body': 'Body'}, self.commercial, 201)
        d = self.call('GET', '/api/admin/crm/organizations/' + org + '/overview', headers=self.commercial, status=200)
        self.assertEqual(d['emails'][0]['subject'], 'Hello')
        self.assertIn({'kind': 'EMAIL', 'label': 'E-mail préparé : Hello (alice.mail)'}, [{k: e[k] for k in ('kind', 'label')} for e in d['timeline']])

    def test_render_and_placeholder_helpers(self):
        self.assertEqual(crm_emails.render('Bonjour {contact} {inconnu}', {'contact': 'A'}), 'Bonjour A {inconnu}')
        with self.assertRaises(ValueError):
            crm_emails.check_placeholders('{societe} {montant}')


if __name__ == '__main__':
    unittest.main()
