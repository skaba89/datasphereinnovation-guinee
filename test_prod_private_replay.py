import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import prod_private_replay as p
import prod_private_release as release
import test_prod_private_release

class PrivateReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'private.sqlite'
        self.fixture=test_prod_private_release.PrivateReleaseTests()
        self.fixture.setUp()
        original=release.verify
        mock=patch.object(release,'verify',side_effect=lambda *a,**k:original(*a,now=self.fixture.now,**k))
        mock.start()
        self.addCleanup(mock.stop)
        p.initialize(self.path)
    def consume(self,envelope=None):
        f=self.fixture
        result=p.consume(self.path,f.envelope() if envelope is None else envelope,f.public,authority_pin=f.pin,**f.expected)
        self.assertFalse(result['startup_authorized'])
        return result['status']
    def test_single_use(self):
        self.assertEqual(self.consume(),'PASS')
        self.assertEqual(self.consume(),'FAIL')
    def test_reissued_nonce(self):
        self.assertEqual(self.consume(),'PASS')
        self.fixture.payload['issued_at']='2026-11-27T06:01:00Z'
        self.assertEqual(self.consume(),'FAIL')
    def test_concurrency(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.consume(),range(8)))
        self.assertEqual(results.count('PASS'),1)
    def test_invalid_signature(self):
        e=self.fixture.envelope();e['signature']='bad'
        self.assertEqual(self.consume(e),'FAIL')
        self.assertEqual(self.consume(),'PASS')
    def test_missing(self):
        self.path.unlink()
        self.assertEqual(self.consume(),'FAIL')
        self.assertFalse(self.path.exists())
    def test_no_reset(self):
        with self.assertRaises(FileExistsError):p.initialize(self.path)
    def test_mode(self):
        os.chmod(self.path,0o644)
        self.assertEqual(self.consume(),'FAIL')
    def test_symlink(self):
        target=self.path.with_name('target')
        self.path.rename(target)
        self.path.symlink_to(target)
        self.assertEqual(self.consume(),'FAIL')
    def test_schema(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE unexpected(id INTEGER)')
        self.assertEqual(self.consume(),'FAIL')
    def test_caller_clock(self):
        f=self.fixture
        with self.assertRaises(ValueError):
            p.consume(self.path,f.envelope(),f.public,authority_pin=f.pin,now=f.now,**f.expected)
