"""PROD contact service: gates, validation, encryption, duplicates, rate limits, notifications, erasure."""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import date
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

import contact_service

ORIGIN = 'https://dsig-consulting.com'
FORM = {'nom': 'Awa Fictive', 'org': 'Org fictive', 'email': 'awa@example.invalid', 'telephone': '+224 620 00 00 00',
        'besoin': 'Demande de devis', 'solution': '', 'message': 'Besoin fictif', 'consent': True, 'website': '', 'language': 'fr'}


class ContactServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key().decode()
        self.env = patch.dict(os.environ, {'DSIG_CONTACT_DB': str(Path(self.tmp.name) / 'contact.sqlite3'), 'DSIG_CONTACT_KEY': self.key,
                                           'DSIG_CONTACT_ENABLED': '1', 'DSIG_CONTACT_ORIGIN': ORIGIN, 'DSIG_TRUSTED_HOPS': '2'})
        self.env.start()
        contact_service.LIMITER = contact_service.RateLimiter()
        self.http = contact_service.ThreadingHTTPServer(('127.0.0.1', 0), contact_service.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.env.stop()
        self.tmp.cleanup()

    def post(self, payload, headers=None, path='/api/contact', raw=None):
        conn = HTTPConnection('127.0.0.1', self.http.server_address[1], timeout=5)
        body = raw if raw is not None else json.dumps(payload)
        conn.request('POST', path, body, {'Content-Type': 'application/json', 'Origin': ORIGIN,
                                          'X-Forwarded-For': '203.0.113.7, 10.0.0.2'} | (headers or {}))
        res = conn.getresponse()
        data = json.loads(res.read() or b'null')
        conn.close()
        return res.status, data

    def rows(self):
        with contact_service.connect() as db:
            return db.execute('SELECT id,besoin,status,payload FROM contact_requests').fetchall()

    def test_accepts_valid_request_encrypted_at_rest(self):
        status, body = self.post(FORM)
        self.assertEqual(status, 201)
        self.assertTrue(body['message'].endswith(body['id']))
        raw = Path(os.environ['DSIG_CONTACT_DB']).read_bytes()
        for secret in (b'awa@example.invalid', b'Awa Fictive', b'620 00 00', b'Besoin fictif'):
            self.assertNotIn(secret, raw)  # nothing personal in clear in the database file
        shown = contact_service.show(body['id'], Fernet(self.key.encode()))
        self.assertEqual((shown['email'], shown['telephone'], shown['besoin']), ('awa@example.invalid', '+224 620 00 00 00', 'Demande de devis'))
        with contact_service.connect() as db:
            self.assertEqual([r[0] for r in db.execute('SELECT action FROM contact_audit ORDER BY id')], ['DEMANDE_RECUE', 'DEMANDE_CONSULTEE'])

    def test_gates_and_validation(self):
        with patch.dict(os.environ, {'DSIG_CONTACT_ENABLED': '0'}):
            self.assertEqual(self.post(FORM)[0], 503)
        self.assertEqual(self.post(FORM, {'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.post(FORM, {'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.post(FORM, path='/api/admin/requests')[0], 404)
        self.assertEqual(self.post(None, raw='x' * 9000)[0], 400)
        self.assertEqual(self.post(None, raw='{not json')[0], 400)
        self.assertEqual(self.post(FORM, {'Content-Type': 'text/plain'})[0], 400)
        for bad in ({'besoin': 'Candidature spontanée'}, {'besoin': 'Mission en régie'}, {'email': 'pas-un-email'}, {'consent': False},
                    {'telephone': 'abc'}, {'message': 'x' * 4001}, {'extra': 'champ'}, {'language': 'de'}):
            # Distinct visitors: invalid requests also count toward the per-client limit (abuse protection).
            self.assertEqual(self.post(FORM | bad, {'X-Forwarded-For': f'198.51.100.{len(str(bad))}, 10.0.0.2'})[0], 400, bad)
        self.assertEqual(self.post(FORM | {'besoin': 'Demande de démonstration'})[0], 201)  # no product selection on the public form
        self.assertEqual(len(self.rows()), 1)

    def test_honeypot_duplicates_and_rate_limits(self):
        status, body = self.post(FORM | {'website': 'http://spam.example'})
        self.assertEqual(status, 201)
        self.assertEqual(self.rows(), [])  # silently dropped
        first = self.post(FORM)
        again = self.post(FORM)  # double submission
        self.assertEqual((first[0], again[0]), (201, 200))
        self.assertEqual(first[1]['id'], again[1]['id'])
        for i in range(2):
            self.assertEqual(self.post(FORM | {'message': f'Autre {i}'})[0], 201)
        self.assertEqual(self.post(FORM | {'message': 'De trop'})[0], 429)  # 5 per client / 10 min (honeypot and duplicate counted)
        # Another visitor (different first hop) is not affected.
        self.assertEqual(self.post(FORM | {'message': 'Autre visiteur'}, {'X-Forwarded-For': '198.51.100.9, 10.0.0.2'})[0], 201)

    def test_client_address_uses_trusted_hops_only(self):
        class H:
            client_address = ('10.0.0.3', 1)
            def __init__(self, xff):
                self.headers = {'X-Forwarded-For': xff} if xff else {}
        self.assertEqual(contact_service.client_address(H('1.1.1.1, 203.0.113.7, 10.0.0.2')), '203.0.113.7')  # spoofed first value ignored
        self.assertEqual(contact_service.client_address(H('')), '10.0.0.3')

    def test_notifications_without_personal_data_and_retry(self):
        rid = self.post(FORM)[1]['id']
        config = {'api_key': 're_test', 'sender': 'contact@dsig-consulting.com', 'recipients': ['direction@example.invalid']}
        sent = []
        def broken(cfg, request_id, subject, text):
            raise OSError('outage')
        self.assertEqual(contact_service.notify(config, broken), {'sent': 0, 'retry': 1, 'failed': 0})
        self.assertEqual(contact_service.notify(config, lambda *a: sent.append(a) or 'p1'), {'sent': 0, 'retry': 0, 'failed': 0})  # backoff
        future = contact_service.time.time() + 3600
        self.assertEqual(contact_service.notify(config, lambda *a: sent.append(a) or 'p1', now=future)['sent'], 1)
        _, request_id, subject, text = sent[0]
        self.assertEqual(request_id, rid)
        for secret in ('awa@example.invalid', 'Awa', 'Org fictive', '620', 'Besoin fictif'):
            self.assertNotIn(secret, subject + text)
        for bad in ({'recipients': []}, {'recipients': 'a@b.c'}, {'recipients': ['x'] }):
            with self.assertRaises(ValueError):
                contact_service.notify(config | bad)

    def test_status_erasure_and_retention(self):
        rid = self.post(FORM)[1]['id']
        contact_service.set_status(rid, 'REPONDUE')
        with self.assertRaises(ValueError):
            contact_service.set_status(rid, 'INCONNU')
        self.assertTrue(contact_service.erase(rid))
        self.assertFalse(contact_service.erase(rid))
        self.assertEqual(self.rows(), [(rid, 'Demande de devis', 'REPONDUE', None)])  # statistics kept, personal data gone
        self.assertNotIn('email', contact_service.show(rid, Fernet(self.key.encode())))
        other = self.post(FORM | {'message': 'Ancienne'})[1]['id']
        with contact_service.connect() as db:
            db.execute("UPDATE contact_requests SET created_at='2020-01-01 00:00:00' WHERE id=?", (other,))
        self.assertEqual(contact_service.purge(today=date(2026, 11, 23)), {'retention_days': 1095, 'eligible': 1, 'erased': 0, 'applied': False})
        self.assertEqual(contact_service.purge(apply=True, today=date(2026, 11, 23))['erased'], 1)
        with self.assertRaises(ValueError):
            contact_service.purge(days=10)

    def test_refuses_to_start_without_key(self):
        with patch.dict(os.environ, {'DSIG_CONTACT_KEY': ''}), self.assertRaises(SystemExit):
            contact_service.cipher()
        rid = self.post(FORM)[1]['id']
        with patch.dict(os.environ, {'DSIG_CONTACT_KEY': Fernet.generate_key().decode()}), self.assertRaises(SystemExit):
            contact_service.show(rid, contact_service.cipher())  # wrong key cannot decrypt



class HardeningTests(unittest.TestCase):
    def test_redirect_never_forwards_the_api_key(self):
        from http.server import BaseHTTPRequestHandler
        seen = []
        class Thief(BaseHTTPRequestHandler):
            def do_GET(self):  # urllib turns a redirected POST into a GET
                seen.append(self.headers.get('Authorization'))
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"id":"stolen"}')
            do_POST = do_GET
            def log_message(self, *a): pass
        thief = contact_service.ThreadingHTTPServer(('127.0.0.1', 0), Thief)
        class Redirector(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(302); self.send_header('Location', f'http://127.0.0.1:{thief.server_address[1]}/'); self.end_headers()
            def log_message(self, *a): pass
        redirector = contact_service.ThreadingHTTPServer(('127.0.0.1', 0), Redirector)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (thief, redirector)]
        for t in threads: t.start()
        try:
            with patch.object(contact_service, 'RESEND_URL', f'http://127.0.0.1:{redirector.server_address[1]}/emails'):
                with self.assertRaises(OSError):  # HTTPError 302 surfaces; notify() turns it into a retry
                    contact_service.resend({'sender': 's@dsig-consulting.com', 'recipients': ['d@example.invalid'], 'api_key': 're_secret'}, 'rid', 'S', 'T')
            self.assertEqual(seen, [])  # the key never reached the redirect target
        finally:
            for s in (thief, redirector): s.shutdown(); s.server_close()

    def test_bounded_server_refuses_beyond_capacity(self):
        server = contact_service.BoundedServer(('127.0.0.1', 0), contact_service.Handler)
        try:
            for _ in range(server.MAX_HANDLERS):
                self.assertTrue(server.slots.acquire(blocking=False))
            closed = []
            server.shutdown_request = lambda request: closed.append(request)
            server.process_request('connexion-de-trop', ('203.0.113.1', 1))
            self.assertEqual(closed, ['connexion-de-trop'])  # closed immediately, no thread started
        finally:
            server.server_close()

    def test_slow_client_is_cut_and_slot_released(self):
        import socket as socketlib
        server = contact_service.BoundedServer(('127.0.0.1', 0), contact_service.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.object(contact_service, 'REQUEST_BUDGET', 1):
                client = socketlib.create_connection(server.server_address, timeout=5)
                client.sendall(b'POST /api/contact HTTP/1.1' + bytes([13, 10]) + b'Host: x' + bytes([13, 10]))
                started = contact_service.time.monotonic()
                closed = False
                for _ in range(8):  # trickle one header byte every 0.4 s: each read alone stays under the socket timeout
                    contact_service.time.sleep(0.4)
                    try:
                        client.sendall(b'X')
                        if client.recv(1, socketlib.MSG_PEEK) == b'':
                            closed = True
                            break
                    except (BlockingIOError, socketlib.timeout):
                        continue
                    except OSError:
                        closed = True
                        break
                client.close()
            self.assertTrue(closed, 'slow connection was not cut')
            self.assertLess(contact_service.time.monotonic() - started, 4)
            for _ in range(20):  # the handler slot comes back
                if server.slots._value == server.MAX_HANDLERS:
                    break
                contact_service.time.sleep(0.1)
            self.assertEqual(server.slots._value, server.MAX_HANDLERS)
        finally:
            server.shutdown()
            server.server_close()

    def test_errors_are_logged_without_ip(self):
        import io
        from contextlib import redirect_stderr
        server = contact_service.BoundedServer(('127.0.0.1', 0), contact_service.Handler)
        try:
            buffer = io.StringIO()
            with redirect_stderr(buffer):
                try:
                    raise BrokenPipeError('coupée')
                except BrokenPipeError:
                    server.handle_error(None, ('203.0.113.77', 4242))
            self.assertEqual(buffer.getvalue(), 'connexion interrompue' + chr(10))
        finally:
            server.server_close()

    def test_service_uses_bounded_server(self):
        import inspect
        self.assertIn('BoundedServer((', inspect.getsource(contact_service.main))


if __name__ == '__main__':
    unittest.main()
