import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_retry_anchor as a
from prod_b2_cli import B2QualificationAdapter,B2ReviewAdapter

class Remote:
    def __init__(self):self.objects={}
    def bucket_info(self,b):
        return dict(bucketName='dsig-prod-backups',bucketId='prod-bucket-id',bucketType='allPrivate',encryption='SSE-B2',lock_mode='compliance',lock_days=30)
    def read(self,b,o):return self.objects.get(o)
    def create_only(self,b,o,data):
        if o in self.objects:raise ValueError('exists')
        self.objects[o]=data

class RetryAnchorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state=Path(tmp.name)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.remote=Remote()
        self.args=dict(now=datetime(2026,11,26,3,20,tzinfo=timezone.utc),day='2026-11-26',run_id='a'*32,pin=hashlib.sha256(self.public).hexdigest(),bucket_id='prod-bucket-id',remote=self.remote)
    def step(self,event,code):
        return a.transition(self.state,signer=self.signer,event=event,code=code,**self.args)
    def verify(self):return a.verify(self.state,public=self.public,**self.args)
    def test_roundtrip(self):
        self.assertEqual(self.step('start','START')['anchored_records'],1)
        self.assertEqual(self.step('end','SUCCESS')['status'],'COMPLETE')
        self.assertEqual(self.verify()['anchored_records'],2)
    def test_suffix_deleted(self):
        self.step('start','START')
        self.step('end','SUCCESS')
        next(self.state.glob('*.end.json')).unlink()
        with self.assertRaises(ValueError):self.verify()
    def test_remote_missing(self):
        self.step('start','START')
        self.remote.objects.clear()
        with self.assertRaises(ValueError):self.verify()
        with self.assertRaises(ValueError):self.step('end','SUCCESS')
        self.assertEqual(len(self.remote.objects),0)
    def test_remote_tampered(self):
        self.step('start','START')
        self.remote.objects[next(iter(self.remote.objects))]=b'bad'
        with self.assertRaises(ValueError):self.verify()
    def test_namespace(self):
        obj='prod/qualification/v232/'+'a'*32+'/retry/2026-11-26/audit/1.start.json'
        self.assertTrue(B2QualificationAdapter('prod-bucket-id')._allowed_object(obj))
        self.assertFalse(B2ReviewAdapter('prod-bucket-id')._allowed_object(obj))
    def test_partial_publication_blocks(self):
        from unittest.mock import patch
        with patch.object(self.remote,'create_only',side_effect=ValueError('upload uncertain')):
            with self.assertRaises(ValueError):self.step('start','START')
        with self.assertRaises(ValueError):self.verify()
