import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_retry_execution as e
import prod_backup_cycle_journal as j
from prod_b2_cli import B2ReadTimeout

class ExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.root=base/'cycle'
        self.state=base/'retry'
        for p in (self.root,self.state,self.root/'state'):p.mkdir(mode=0o700)
        self.signer=Ed25519PrivateKey.generate()
        public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(public).hexdigest()
        for stage,h,m in [('snapshot',1,20),('export',2,10),('audit',3,10)]:
            j.append(self.root/'state',now=datetime(2026,11,26,h,m,tzinfo=timezone.utc),stage=stage,archive_sha256='a'*64,signer=self.signer,pin=self.pin)
        self.now=datetime(2026,11,26,3,20,tzinfo=timezone.utc)
    def run_once(self):
        return e.run(root=self.root,retry_state=self.state,clock=lambda:self.now,signer=self.signer,pin=self.pin,key=b'key',run_id='a'*32,bucket_id='prod-bucket-id',remote=object())
    def test_success(self):
        with patch.object(e.anchor,'publish',return_value=dict(status='PASS',remote_restore_verified=True,external_journal_anchor_verified=True)) as p:
            self.assertTrue(self.run_once()['remote_verified'])
            self.assertFalse(self.run_once()['performed'])
            self.assertEqual(p.call_count,1)
    def test_timeout(self):
        with patch.object(e.anchor,'publish',side_effect=B2ReadTimeout('timeout')) as p:
            self.assertEqual(self.run_once()['outcome'],'NETWORK_TIMEOUT')
            self.assertFalse(self.run_once()['performed'])
            self.now=self.now.replace(minute=21)
            self.assertEqual(self.run_once()['attempts'],2)
            self.assertEqual(p.call_count,2)
    def test_unknown_blocks(self):
        with patch.object(e.anchor,'publish',side_effect=ValueError('uncertain')) as p:
            self.assertEqual(self.run_once()['status'],'BLOCKED_PERMANENT')
            self.assertFalse(self.run_once()['performed'])
            self.assertEqual(p.call_count,1)
    def test_incomplete_proof(self):
        with patch.object(e.anchor,'publish',return_value={'status':'PASS'}):
            self.assertFalse(self.run_once()['remote_verified'])
    def test_crash(self):
        with patch.object(e.anchor,'publish',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.run_once()
        self.assertEqual(self.run_once()['status'],'BLOCKED_UNCERTAIN')
