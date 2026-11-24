"""The automated REC acceptance script passes against a local server and reports failures honestly."""
import importlib.util
import io
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import server

spec = importlib.util.spec_from_file_location('acceptance_rec', Path(__file__).resolve().parent / 'scripts' / 'acceptance-rec.py')
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


class AcceptanceScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original, self.original_token = server.DB, server.ADMIN_TOKEN
        server.DB = Path(self.tmp.name) / 'acceptance.sqlite3'
        server.ADMIN_TOKEN = 'test-token-only-' + 'x' * 32
        server.RATE.clear()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_address[1]}'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB, server.ADMIN_TOKEN = self.original, self.original_token
        self.tmp.cleanup()

    def test_full_run_passes_and_cleans_up(self):
        report = acceptance.run(acceptance.Client(self.base, server.ADMIN_TOKEN))
        self.assertEqual(report['status'], 'PASS', report)
        self.assertEqual(len(report['steps']), 8)
        self.assertFalse(report['production_authorized'])
        self.assertNotIn(server.ADMIN_TOKEN, str(report))
        with server.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM requests WHERE email LIKE 'recette-auto-%'").fetchone()[0], 0)  # erased

    def test_via_loopback_presents_the_rec_host(self):
        # REC behind the shared proxy: the app only accepts its own Host and Origin.
        with patch.dict(os.environ, {'DSIG_HTTPS_ORIGIN': 'https://rec.dsig-consulting.com'}):
            direct = acceptance.run(acceptance.Client(self.base, server.ADMIN_TOKEN))
            self.assertEqual(direct['status'], 'FAIL')  # wrong Host -> 403 Invalid host
            report = acceptance.run(acceptance.Client('https://rec.dsig-consulting.com', server.ADMIN_TOKEN, via=self.base))
        self.assertEqual(report['status'], 'PASS', report)

    def test_wrong_token_fails_without_crashing(self):
        report = acceptance.run(acceptance.Client(self.base, 'mauvais-jeton-' + 'y' * 32))
        self.assertEqual(report['status'], 'FAIL')
        failed = [s['step'] for s in report['steps'] if s['status'] == 'FAIL']
        self.assertIn('1. Formulaire → demande + prospect CRM', failed)
        self.assertIn('6. Protection des API', [s['step'] for s in report['steps'] if s['status'] == 'PASS'])

    def test_cli_guards(self):
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            with patch.dict(os.environ, {'DSIG_ADMIN_TOKEN': ''}):
                self.assertEqual(acceptance.main(['--base', self.base]), 2)
            with patch.dict(os.environ, {'DSIG_ADMIN_TOKEN': server.ADMIN_TOKEN}):
                self.assertEqual(acceptance.main(['--base', 'https://dsig-consulting.com']), 2)  # never the public/production site
                self.assertEqual(acceptance.main(['--base', self.base]), 0)
                self.assertEqual(acceptance.main(['--via', 'http://evil.example:80']), 2)  # loopback only


if __name__ == '__main__':
    unittest.main()
