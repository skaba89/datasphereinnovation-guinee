"""Commercial tasks: creation, personal/team lists, ownership rules, locking and notifications."""
import json
import os
import tempfile
import threading
import unittest
from datetime import date, timedelta
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import crm_tasks
import notifications
import server

TODAY = date.today()


class CrmTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Read-only DIRECTION check without the MFA enrolment flow (covered elsewhere).
        mfa = patch.dict(os.environ, {'DSIG_MFA_REQUIRED_ROLES': ''})
        mfa.start()
        self.addCleanup(mfa.stop)
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'tasks.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.admin = self.headers(server.ADMIN_TOKEN)
        self.alice_id, self.alice = self.account('alice.tasks', 'COMMERCIAL')
        self.bob_id, self.bob = self.account('bob.tasks', 'COMMERCIAL')
        _, self.direction = self.account('direction.tasks', 'DIRECTION')
        _, self.rh = self.account('rh.tasks', 'RH')
        opp = {'company': 'Client tâches fictif', 'contact': '', 'email': '', 'title': 'Audit fictif', 'mode': 'CONSEIL', 'skills': '',
               'consultant_id': '', 'next_action': '', 'followup': '', 'notes': '', 'status': 'QUALIFIE'}
        self.opp = self.call('POST', '/api/admin/crm', opp, self.admin, 201)['id']

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
        body = self.call('POST', '/api/admin/accounts', {'username': username, 'role': role, 'consultant_id': ''}, self.admin, 201)
        with server.connect() as db:
            account_id = db.execute('SELECT id FROM accounts WHERE username=?', (username,)).fetchone()[0]
        return account_id, self.headers(body['key'])

    def call(self, method, path, payload=None, headers=None, status=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        conn.request(method, path, None if payload is None else json.dumps(payload), headers or {})
        res = conn.getresponse()
        body = res.read()
        conn.close()
        if status is not None:
            self.assertEqual(res.status, status, body)
        return json.loads(body) if body else None

    def task(self, headers, **values):
        payload = {'title': 'Appeler le client', 'kind': 'APPEL', 'due_date': TODAY.isoformat(), 'opportunity_id': self.opp, 'owner_id': 'me'} | values
        return self.call('POST', '/api/admin/crm/tasks', payload, headers, 201)['id']

    def tasks(self, headers, query='?view=mine'):
        return self.call('GET', '/api/admin/crm/tasks' + query, headers=headers, status=200)

    def test_personal_list_buckets_and_counts(self):
        self.task(self.alice, title='En retard', due_date=(TODAY - timedelta(days=2)).isoformat())
        self.task(self.alice, title='Du jour')
        self.task(self.alice, title='Plus tard', due_date=(TODAY + timedelta(days=3)).isoformat(), opportunity_id='')
        self.task(self.bob, title='Tâche de Bob')
        mine = self.tasks(self.alice)
        self.assertEqual([(t['title'], t['bucket']) for t in mine['items']], [('En retard', 'late'), ('Du jour', 'today'), ('Plus tard', 'upcoming')])
        self.assertEqual(mine['counts'], {'late': 1, 'today': 1, 'week': 1})
        self.assertEqual(mine['items'][0]['company'], 'Client tâches fictif')
        self.assertEqual(mine['items'][0]['owner'], 'alice.tasks')
        self.assertTrue(mine['can_write'])
        self.assertFalse(mine['manage_all'])
        self.assertEqual(len(self.tasks(self.alice, '?view=team')['items']), 4)

    def test_validation(self):
        base = {'title': 'x', 'kind': 'APPEL', 'due_date': TODAY.isoformat(), 'opportunity_id': '', 'owner_id': 'me'}
        for bad in ({'kind': 'FAX'}, {'title': ''}, {'title': 'a' * 181}, {'title': 'a\nb'}, {'due_date': '2026-02-30'},
                    {'opportunity_id': 'absente'}, {'owner_id': 'inconnu'}, {'extra': 1}):
            self.call('POST', '/api/admin/crm/tasks', base | bad, self.alice, 400)
        with server.connect() as db:
            rh_id = db.execute("SELECT id FROM accounts WHERE username='rh.tasks'").fetchone()[0]
        self.call('POST', '/api/admin/crm/tasks', base | {'owner_id': rh_id}, self.alice, 400)  # owner must be commercial/admin
        self.call('POST', '/api/admin/crm/tasks', base | {'owner_id': self.bob_id}, self.alice, 201)  # assigning a colleague is allowed
        self.call('GET', '/api/admin/crm/tasks?view=all', headers=self.alice, status=400)

    def test_ownership_locking_and_permissions(self):
        tid = self.task(self.alice)
        self.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'FAIT', 'version': 1}, self.bob, 403)
        self.call('PATCH', '/api/admin/crm/tasks/' + tid, {'due_date': (TODAY + timedelta(days=1)).isoformat(), 'version': 1}, self.alice, 200)
        self.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'FAIT', 'version': 1}, self.alice, 409)
        self.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'FAIT', 'version': 2}, self.alice, 200)
        self.call('PATCH', '/api/admin/crm/tasks/' + tid, {'status': 'ANNULEE', 'version': 3}, self.alice, 409)
        self.call('PATCH', '/api/admin/crm/tasks/00000000-0000-0000-0000-000000000000', {'status': 'FAIT', 'version': 1}, self.alice, 404)
        done = self.tasks(self.alice, '?view=mine&state=done')['items']
        self.assertEqual((done[0]['status'], done[0]['bucket']), ('FAIT', 'done'))
        self.assertEqual(self.tasks(self.alice)['items'], [])
        # Unassigned tasks may be closed by any commercial; ADMIN may close anyone's task.
        free = self.task(self.alice, owner_id='')
        self.call('PATCH', '/api/admin/crm/tasks/' + free, {'status': 'ANNULEE', 'version': 1}, self.bob, 200)
        bobs = self.task(self.bob)
        self.call('PATCH', '/api/admin/crm/tasks/' + bobs, {'status': 'FAIT', 'version': 1}, self.admin, 200)
        # Read-only and unauthorized roles.
        team = self.tasks(self.direction, '?view=team')
        self.assertFalse(team['can_write'])
        self.assertEqual((team['owners'], team['opportunities']), ([], []))
        self.call('POST', '/api/admin/crm/tasks', {'title': 'x', 'kind': 'APPEL', 'due_date': TODAY.isoformat(), 'opportunity_id': '', 'owner_id': ''}, self.direction, 403)
        self.call('GET', '/api/admin/crm/tasks', headers=self.rh, status=403)
        self.call('GET', '/api/admin/crm/tasks', status=401)
        with server.connect() as db:
            actions = {r[0] for r in db.execute("SELECT action FROM access_events WHERE action LIKE 'TACHE_%'")}
        self.assertEqual(actions, {'TACHE_CREEE', 'TACHE_REPORTEE', 'TACHE_TERMINEE', 'TACHE_ANNULEE'})

    def test_overdue_tasks_feed_notifications(self):
        late = self.task(self.alice, title='Relance en retard', due_date=(TODAY - timedelta(days=1)).isoformat())
        self.task(self.alice, title='Pas encore')
        with server.connect() as db:
            items = crm_tasks.reminders(db, TODAY)
            self.assertEqual([(x['kind'], x['id'], x['priority']) for x in items], [('TACHE_EN_RETARD', late, 'URGENT')])
            self.assertIn('alice.tasks', items[0]['details'])
            notifications.run(db, TODAY)
            self.assertEqual(db.execute("SELECT count(*) FROM notifications WHERE kind='TACHE_EN_RETARD' AND active=1").fetchone()[0], 1)
        self.call('PATCH', '/api/admin/crm/tasks/' + late, {'status': 'FAIT', 'version': 1}, self.alice, 200)
        with server.connect() as db:
            notifications.run(db, TODAY)
            self.assertEqual(db.execute("SELECT count(*) FROM notifications WHERE kind='TACHE_EN_RETARD' AND active=1").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
