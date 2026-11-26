import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_anchored_execution as e
import prod_backup_cycle_journal as j
import prod_backup_orchestrator as guard
from prod_b2_cli import B2ReadTimeout

class Remote:
    def __init__(self):self.objects={}
    def bucket_info(self,b):return dict(bucketName='dsig-prod-backups',bucketId='prod-bucket-id',bucketType='allPrivate',encryption='SSE-B2',lock_mode='compliance',lock_days=30)
    def read(self,b,o):return self.objects.get(o)
    def create_only(self,b,o,data):
        if o in self.objects:raise ValueError('exists')
        self.objects[o]=data

class AnchoredExecutionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.root=base/'cycle'
        self.state=base/'retry'
        self.lock=base/'lock'
        for p in (self.root,self.root/'state',self.state,self.lock):p.mkdir(mode=0o700)
        self.signer=Ed25519PrivateKey.generate()
        public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(public).hexdigest()
        for stage,h,m in [('snapshot',1,20),('export',2,10),('audit',3,10)]:
            result=j.append(self.root/'state',now=datetime(2026,11,26,h,m,tzinfo=timezone.utc),stage=stage,archive_sha256='a'*64,signer=self.signer,pin=self.pin)
        self.head=result['head']
        self.now=datetime(2026,11,26,3,20,tzinfo=timezone.utc)
        self.remote=Remote()
    def run_once(self):
        return e.run(root=self.root,retry_state=self.state,execution_lock=self.lock,clock=lambda:self.now,signer=self.signer,pin=self.pin,key=b'key',run_id='a'*32,bucket_id='prod-bucket-id',remote=self.remote)
    def proof(self,**kw):
        return dict(status='PASS',remote_restore_verified=True,external_journal_anchor_verified=True,journal_head=self.head)
    def test_success(self):
        def publish(**kw):
            self.assertEqual(len(self.remote.objects),1)
            return self.proof()
        with patch.object(e.anchor,'publish',side_effect=publish) as p:
            result=self.run_once()
            self.assertTrue(result['remote_verified'])
            self.assertEqual(result['anchored_records'],2)
            self.assertFalse(self.run_once()['performed'])
            self.assertEqual(p.call_count,1)
    def test_timeout(self):
        with patch.object(e.anchor,'publish',side_effect=[B2ReadTimeout('timeout'),self.proof()]) as p:
            self.assertEqual(self.run_once()['outcome'],'NETWORK_TIMEOUT')
            self.assertFalse(self.run_once()['performed'])
            self.now=self.now.replace(minute=21)
            result=self.run_once()
            self.assertEqual(result['anchored_records'],4)
            self.assertEqual(result['attempts'],2)
            self.assertEqual(p.call_count,2)
    def test_missing_local(self):
        with patch.object(e.anchor,'publish',return_value=self.proof()) as p:
            self.run_once()
            next(self.state.glob('*.end.json')).unlink()
            with self.assertRaises(ValueError):self.run_once()
            self.assertEqual(p.call_count,1)
    def test_reservation_failure(self):
        with patch.object(self.remote,'create_only',side_effect=ValueError('uncertain')),patch.object(e.anchor,'publish') as p:
            with self.assertRaises(ValueError):self.run_once()
            p.assert_not_called()
    def test_concurrency(self):
        with guard.locked(self.lock),patch.object(e.anchor,'publish') as p:
            with self.assertRaises(ValueError):self.run_once()
            p.assert_not_called()
    def test_crash(self):
        with patch.object(e.anchor,'publish',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.run_once()
        self.assertEqual(self.run_once()['status'],'BLOCKED_UNCERTAIN')
