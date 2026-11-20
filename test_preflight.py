import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
import operations
import preflight


class PreflightTests(unittest.TestCase):
    def test_valid_rec_and_missing_antivirus_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'db.sqlite3'
            with sqlite3.connect(path) as db:
                for table in operations.REQUIRED_TABLES:
                    db.execute(f'CREATE TABLE "{table}" (id INTEGER)')
            path.chmod(0o600)
            env = {'DSIG_ENV': 'REC', 'DSIG_HTTPS_ORIGIN': 'https://rec.example.org',
                   'DSIG_ADMIN_TOKEN': 'a' * 48}
            env.update({name: Fernet.generate_key().decode() for name in preflight.KEYS})
            before = path.read_bytes()
            with patch.dict(os.environ, env, clear=True), patch.object(preflight.server, 'DB', path):
                report = preflight.inspect()
                self.assertEqual(report['status'], 'WARN')
                self.assertEqual(report['checks']['antivirus_socket_present'], 'WARN')
                self.assertFalse(report['production_authorized'])
                for name in preflight.KEYS:
                    self.assertNotIn(env[name], str(report))
                self.assertNotIn(env['DSIG_ADMIN_TOKEN'], str(report))
                self.assertEqual(path.read_bytes(), before)
                os.environ['DSIG_BACKUP_KEY'] = env['DSIG_MFA_KEY']
                self.assertEqual(preflight.inspect()['checks']['independent_keys'], 'FAIL')
                os.environ['DSIG_MFA_REQUIRED_ROLES'] = ''
                self.assertEqual(preflight.inspect()['checks']['privileged_mfa_policy'], 'FAIL')

    def test_missing_db_and_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing.sqlite3'
            with patch.dict(os.environ, {'DSIG_ENV': 'PROD', 'DSIG_HTTPS_ORIGIN': 'http://example.org'}, clear=True), patch.object(preflight.server, 'DB', path):
                report = preflight.inspect()
                self.assertEqual(report['status'], 'FAIL')
                self.assertEqual(report['checks']['database_integrity'], 'FAIL')
                self.assertEqual(report['checks']['https_origin_configured'], 'FAIL')
                self.assertFalse(path.exists())
