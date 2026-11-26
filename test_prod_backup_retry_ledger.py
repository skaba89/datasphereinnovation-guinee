import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_retry_ledger as l

class LedgerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state=Path(tmp.name)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.args=dict(day='2026-11-26',stage='export',run_id='a'*32,pin=self.pin)
    def at(self,m,s=0):return datetime(2026,11,26,2,m,s,tzinfo=timezone.utc)
    def record(self,m,event,code):
        return l.record(self.state,now=self.at(m),signer=self.signer,event=event,code=code,**self.args)
    def inspect(self,m):
        return l.inspect(self.state,now=self.at(m),public=self.public,**self.args)
    def test_crash_blocks(self):
        self.record(5,'start','START')
        self.assertEqual(self.inspect(6)['status'],'BLOCKED_UNCERTAIN')
        with self.assertRaises(ValueError):self.record(6,'start','START')
    def test_retry_resume(self):
        self.record(5,'start','START')
        self.record(5,'end','NETWORK_TIMEOUT')
        self.assertEqual(self.inspect(5)['status'],'WAIT')
        self.assertEqual(self.inspect(6)['status'],'DUE')
        self.record(6,'start','START')
        result=self.record(6,'end','SUCCESS')
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['attempts'],2)
        self.assertFalse(result['production_authorized'])
    def test_permanent(self):
        self.record(5,'start','START')
        self.record(5,'end','INTEGRITY')
        self.assertEqual(self.inspect(7)['status'],'BLOCKED_PERMANENT')
    def test_missing_start(self):
        self.record(5,'start','START')
        self.record(5,'end','SUCCESS')
        next(self.state.glob('*.start.json')).unlink()
        with self.assertRaises(ValueError):self.inspect(7)
    def test_no_unreserved_end(self):
        with self.assertRaises(ValueError):self.record(5,'end','SUCCESS')
    def test_no_early_retry(self):
        self.record(5,'start','START')
        self.record(5,'end','NETWORK_TIMEOUT')
        with self.assertRaises(ValueError):self.record(5,'start','START')
    def test_exhausted(self):
        for m in (5,6,8,12,20):
            self.record(m,'start','START')
            self.record(m,'end','NETWORK_TIMEOUT')
        self.assertEqual(self.inspect(30)['status'],'EXHAUSTED')
