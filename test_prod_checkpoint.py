import base64
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import prod_authorization as a
import prod_checkpoint as c
import prod_replay


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'ledger.sqlite'
        prod_replay.initialize(self.path)
        self.key=Ed25519PrivateKey.generate()
        self.pub=self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.registry=b'{"schema":1,"keys":[]}'
        self.now=datetime(2026,11,26,7,0,tzinfo=timezone.utc)
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO consumed VALUES (?)', ('a'*64,))
        self.payload=dict(schema=1,purpose=c.PURPOSE,sequence=2,
                          registry_sha256=hashlib.sha256(self.registry).hexdigest(),
                          ledger_sha256=c.ledger_digest(self.path),
                          issued_at='2026-11-26T06:00:00Z',expires_at='2026-11-26T08:00:00Z')

    def verify(self, **overrides):
        envelope=dict(payload=self.payload.copy(),signature=base64.b64encode(
            self.key.sign(a.canonical(self.payload))).decode())
        args=dict(anchor_public_key=self.pub,expected_sequence=2,
                  registry_bytes=self.registry,ledger_path=self.path,now=self.now)
        result=c.verify(envelope,**dict(args,**overrides))
        self.assertFalse(result['production_authorized'])
        return result['status']

    def test_valid(self):
        self.assertEqual(self.verify(),'PASS')

    def test_old_sequence(self):
        self.assertEqual(self.verify(expected_sequence=3),'FAIL')

    def test_ledger_rollback(self):
        with sqlite3.connect(self.path) as db:
            db.execute('DELETE FROM consumed')
        self.assertEqual(self.verify(),'FAIL')

    def test_registry_rollback(self):
        self.assertEqual(self.verify(registry_bytes=b'old'),'FAIL')

    def test_expiry(self):
        self.assertEqual(self.verify(now=datetime(2026,11,26,8,0,tzinfo=timezone.utc)),'FAIL')

    def test_clock_before_issue(self):
        self.assertEqual(self.verify(now=datetime(2026,11,26,5,0,tzinfo=timezone.utc)),'FAIL')

    def test_wrong_anchor(self):
        key=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.assertEqual(self.verify(anchor_public_key=key),'FAIL')

    def test_missing_ledger(self):
        self.path.unlink()
        self.assertEqual(self.verify(),'FAIL')

    def test_invalid_signature(self):
        envelope=dict(payload=self.payload,signature='bad')
        self.assertEqual(c.verify(envelope,anchor_public_key=self.pub,expected_sequence=2,
                                  registry_bytes=self.registry,ledger_path=self.path,
                                  now=self.now)['status'],'FAIL')
