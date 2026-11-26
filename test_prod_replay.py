import hashlib
import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import test_prod_trust
import prod_replay as p


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.fixture = test_prod_trust.ProdTrustTests()
        self.fixture.setUp()
        self.registry = json.dumps(self.fixture.registry).encode()
        self.pin = hashlib.sha256(self.registry).hexdigest()
        self.envelope = self.fixture.envelope()
        p.initialize(self.path)

    def consume(self, envelope=None):
        result = p.consume(self.path, self.envelope if envelope is None else envelope,
                           self.registry, self.pin, now=self.fixture.now, **self.fixture.expected)
        self.assertFalse(result['production_authorized'])
        return result['status']

    def test_single_use(self):
        self.assertEqual(self.consume(), 'PASS')
        self.assertEqual(self.consume(), 'FAIL')

    def test_concurrent(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _: self.consume(), range(8)))
        self.assertEqual(results.count('PASS'), 1)
        self.assertEqual(results.count('FAIL'), 7)

    def test_invalid_signature_not_consumed(self):
        bad=dict(self.envelope, signature='bad')
        self.assertEqual(self.consume(bad), 'FAIL')
        self.assertEqual(self.consume(), 'PASS')

    def test_existing_ledger_no_reset(self):
        self.assertEqual(self.consume(), 'PASS')
        with self.assertRaises(FileExistsError):
            p.initialize(self.path)
        self.assertEqual(self.consume(), 'FAIL')

    def test_missing_ledger(self):
        self.path.unlink()
        self.assertEqual(self.consume(), 'FAIL')
        self.assertFalse(self.path.exists())

    def test_unsafe_mode(self):
        os.chmod(self.path, 0o644)
        self.assertEqual(self.consume(), 'FAIL')

    def test_symlink(self):
        real=self.path.with_name('real.sqlite')
        self.path.rename(real)
        self.path.symlink_to(real)
        self.assertEqual(self.consume(), 'FAIL')

    def test_wrong_schema(self):
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA user_version=0')
        self.assertEqual(self.consume(), 'FAIL')
