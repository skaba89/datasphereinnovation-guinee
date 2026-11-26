import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_cycle_journal as j

class JournalTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state=Path(tmp.name)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()

    def time(self,h,m):return datetime(2026,11,26,h,m,tzinfo=timezone.utc)
    def add(self,stage,h,m,digest='a'*64):
        return j.append(self.state,now=self.time(h,m),stage=stage,archive_sha256=digest,signer=self.signer,pin=self.pin)
    def read(self,h,m):
        return j.read(self.state,now=self.time(h,m),public=self.public,pin=self.pin)
    def test_resume(self):
        self.add('snapshot',1,20)
        self.assertEqual(self.read(2,5)['next_stage'],'export')
        self.add('export',2,10)
        result=self.add('audit',3,10)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertTrue(result['completion_authenticated'])
        self.assertFalse(result['production_authorized'])
    def test_duplicate(self):
        self.add('snapshot',1,20)
        with self.assertRaises(ValueError):self.add('snapshot',1,21)
    def test_out_of_order(self):
        with self.assertRaises(ValueError):self.add('export',2,10)
    def test_digest_change(self):
        self.add('snapshot',1,20)
        with self.assertRaises(ValueError):self.add('export',2,10,'b'*64)
    def test_tamper(self):
        self.add('snapshot',1,20)
        p=self.state/'2026-11-26.snapshot.json'
        p.write_bytes(p.read_bytes().replace(b'a'*64,b'b'*64))
        with self.assertRaises(ValueError):self.read(2,5)
    def test_missing_predecessor(self):
        self.add('snapshot',1,20)
        self.add('export',2,10)
        (self.state/'2026-11-26.snapshot.json').unlink()
        with self.assertRaises(ValueError):self.read(3,0)
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):j.read(self.state,now=self.time(1,20),public=self.public,pin='b'*64)
    def test_missed_window(self):
        with self.assertRaises(ValueError):self.add('snapshot',2,6)
