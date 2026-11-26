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
import prod_backup_remote_qualification as q
from prod_b2_cli import B2QualificationAdapter,B2ReviewAdapter
import operations

class Remote:
    def __init__(self):
        self.data=None
        self.writes=0
        self.policy=dict(bucketName='dsig-prod-backups',bucketId='prod-bucket-id',bucketType='allPrivate',encryption='SSE-B2',lock_mode='compliance',lock_days=30)
    def bucket_info(self,b):return self.policy
    def read(self,b,o):return self.data
    def create_only(self,b,o,data):
        self.writes+=1
        self.data=data

class QualificationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        for n in ('state','locks','archives','replica'):(self.root/n).mkdir(mode=0o700)
        self.key=Fernet.generate_key()
        self.data=Fernet(self.key).encrypt(b'synthetic')
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.remote=Remote()
        self.digest=hashlib.sha256(self.data).hexdigest()
        self.name='dsig-prod-20261126T011500Z.dsigbak'
        for n in ('archives','replica'):operations.write_new(self.root/n/self.name,self.data)
        for stage,h,m in [('snapshot',1,20),('export',2,10),('audit',3,10)]:
            j.append(self.root/'state',now=self.at(h,m),stage=stage,archive_sha256=self.digest,signer=self.signer,pin=self.pin)
        p=patch.object(q.export,'verify_archive',side_effect=lambda data,key:Fernet(key).decrypt(data))
        p.start()
        self.addCleanup(p.stop)
    def at(self,h,m):return datetime(2026,11,26,h,m,tzinfo=timezone.utc)
    def run_remote(self,run_id='a'*32):
        return q.verify_remote(root=self.root,now=self.at(3,20),public=self.public,pin=self.pin,key=self.key,run_id=run_id,bucket_id='prod-bucket-id',remote=self.remote)
    def test_roundtrip(self):
        first=self.run_remote()
        self.assertTrue(first['remote_restore_verified'])
        self.assertFalse(first['production_authorized'])
        self.assertTrue(first['object'].startswith('prod/qualification/v232/'))
        self.assertFalse(self.run_remote()['uploaded'])
        self.assertEqual(self.remote.writes,1)
    def test_changed_remote(self):
        self.remote.data=b'bad'
        with self.assertRaises(ValueError):self.run_remote()
        self.assertEqual(self.remote.writes,0)
    def test_wrong_policy(self):
        self.remote.policy['lock_days']=29
        with self.assertRaises(ValueError):self.run_remote()
        self.assertEqual(self.remote.writes,0)
    def test_incomplete(self):
        (self.root/'state'/'2026-11-26.audit.json').unlink()
        with self.assertRaises(ValueError):self.run_remote()
        self.assertEqual(self.remote.writes,0)
    def test_wrong_id(self):
        with self.assertRaises(ValueError):self.run_remote('../bad')
    def test_namespace(self):
        business='prod/2026/11/'+self.name
        qualification='prod/qualification/v232/'+'a'*32+'/'+self.name
        a=B2QualificationAdapter('prod-bucket-id')
        b=B2ReviewAdapter('prod-bucket-id')
        self.assertTrue(a._allowed_object(qualification))
        self.assertFalse(a._allowed_object(business))
        self.assertTrue(b._allowed_object(business))
        self.assertFalse(b._allowed_object(qualification))
