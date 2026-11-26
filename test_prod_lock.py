"""Production lock must precede all CLI side effects."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ProductionLockTests(unittest.TestCase):
    def test_all_entrypoints_fail_before_touching_data(self):
        commands = [[], ['--export'], ['--backup', 'backup.sqlite'],
                    ['--backup-encrypted', 'backup.enc'],
                    ['--restore-isolated', 'missing.enc', 'restore.sqlite'],
                    ['--check-db'], ['--rotate-documents', 'copy.sqlite'],
                    ['--refresh-notifications'], ['--send-contact-notifications'],
                    ['--send-account-invitations'], ['--contact-mail-status'],
                    ['--purge-requests', '--apply'], ['--automation-preview'],
                    ['--weekly-report'], ['--send-weekly-report']]
        for mode in ('PROD', 'production', ''):
            for args in commands:
                with self.subTest(mode=mode, args=args), tempfile.TemporaryDirectory() as tmp:
                    env = dict(os.environ, DSIG_ENV=mode,
                               DSIG_DB=str(Path(tmp) / 'data' / 'requests.sqlite3'))
                    result = subprocess.run([sys.executable, str(ROOT / 'server.py'), *args],
                                            cwd=tmp, env=env, input='{}', text=True,
                                            capture_output=True, timeout=15)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('Production bloquée', result.stderr)
                    self.assertEqual(list(Path(tmp).iterdir()), [])
