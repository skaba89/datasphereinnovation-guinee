import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_cycle_journal as j
import prod_backup_journal_anchor as a
from prod_b2_cli import B2QualificationAdapter,B2ReviewAdapter
import operations

class Remote:
    def __init__(self):
        self.objects={}
        self.writes=0
    def bucket_info(self,b):
        return dict(bucketName='dsig-prod-backups',bucketId='prod-bucket-id',bucketType='allPrivate',encryption='SSE-B2',lock_mode='compliance',lock_days=30)
    def read(self,b,o):return self.objects.get(o)
    def create_only(self,b,o,data):
        if o in self.objects:raise ValueError('exists')
        self.objects[o]=data
        self.writes+=1

class AnchorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        for n in ('state','locks','archives','replica'):(self.root/n).mkdir(mode=0o700)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.key=Fernet.generate_key()
        data=Fernet(self.key).encrypt(b'synthetic')
        digest=hashlib.sha256(data).hexdigest()
        for n in ('archives','replica'):operations.write_new(self.root/n/'dsig-prod-20261126T011500Z.dsigbak',data)
        for stage,h,m in [('snapshot',1,20),('export',2,10),('audit',3,10)]:
            j.append(self.root/'state',now=datetime(2026,11,26,h,m,tzinfo=timezone.utc),stage=stage,archive_sha256=digest,signer=self.signer,pin=self.pin)
        self.now=datetime(2026,11,26,3,20,tzinfo=timezone.utc)
        self.remote=Remote()
        self.run_id='a'*32
        p=patch('prod_b2_export.verify_archive',side_effect=lambda data,key:Fernet(key).decrypt(data))
        p.start()
        self.addCleanup(p.stop)
    def publish(self):
        return a.publish(root=self.root,now=self.now,signer=self.signer,pin=self.pin,key=self.key,run_id=self.run_id,bucket_id='prod-bucket-id',remote=self.remote)
    def verify(self,run_id=None):
        return a.verify(state=self.root/'state',now=self.now,public=self.public,pin=self.pin,run_id=run_id or self.run_id,bucket_id='prod-bucket-id',remote=self.remote)
    def test_idempotence(self):
        first=self.publish()
        self.assertTrue(first['created'])
        self.assertTrue(self.verify()['external_journal_anchor_verified'])
        self.assertFalse(self.publish()['created'])
        self.assertEqual(self.remote.writes,2)
    def test_suffix_deleted(self):
        self.publish()
        (self.root/'state'/'2026-11-26.audit.json').unlink()
        with self.assertRaises(ValueError):self.verify()
        with self.assertRaises(ValueError):self.publish()
        self.assertEqual(self.remote.writes,2)
    def test_modified(self):
        self.publish()
        self.remote.objects[a.object_name(self.run_id)]=b'{}'
        with self.assertRaises(ValueError):self.verify()
    def test_replay(self):
        self.publish()
        other='b'*32
        self.remote.objects[a.object_name(other)]=self.remote.objects[a.object_name(self.run_id)]
        with self.assertRaises(ValueError):self.verify(other)
    def test_missing(self):
        with self.assertRaises(ValueError):self.verify()
    def test_namespace(self):
        obj=a.object_name(self.run_id)
        self.assertTrue(B2QualificationAdapter('prod-bucket-id')._allowed_object(obj))
        self.assertFalse(B2ReviewAdapter('prod-bucket-id')._allowed_object(obj))
