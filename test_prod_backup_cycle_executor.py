import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_cycle_executor as e
import operations

class ExecutorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.root=base/'review'
        self.root.mkdir(mode=0o700)
        for name in ('state','locks','archives','replica'):
            (self.root/name).mkdir(mode=0o700)
        source=base/'source'
        source.mkdir(mode=0o700)
        self.active=source/'requests.sqlite3'
        self.signer=Ed25519PrivateKey.generate()
        self.pin=hashlib.sha256(self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()
        self.key=Fernet.generate_key()
        self.data=Fernet(self.key).encrypt(b'synthetic')
        self.name='dsig-prod-20261126T011500Z.dsigbak'
        self.archive=self.root/'archives'/self.name
        self.replica=self.root/'replica'/self.name
        def fake_snapshot(active,destination,*,backup_key,source_check):
            operations.write_new(destination,self.data)
            return {'sha256':hashlib.sha256(self.data).hexdigest()}
        p=patch.object(e.snapshot,'create_review_snapshot',side_effect=fake_snapshot)
        self.snapshot=p.start()
        self.addCleanup(p.stop)
        p=patch.object(e.export,'verify_archive',side_effect=lambda data,key:Fernet(key).decrypt(data))
        p.start()
        self.addCleanup(p.stop)

    def run_at(self,h,m):
        return e.run(root=self.root,active=self.active,now=datetime(2026,11,26,h,m,tzinfo=timezone.utc),key=self.key,signer=self.signer,pin=self.pin,source_check=lambda:{'status':'PASS'})
    def test_cycle(self):
        self.assertEqual(self.run_at(1,20)['performed_stage'],'snapshot')
        self.assertFalse(self.run_at(1,21)['performed'])
        self.assertEqual(self.run_at(2,10)['performed_stage'],'export')
        result=self.run_at(3,10)
        self.assertEqual(result['status'],'COMPLETE')
        self.assertFalse(result['remote_verified'])
        self.assertFalse(result['production_authorized'])
        self.assertFalse(self.run_at(3,11)['performed'])
        self.snapshot.assert_called_once()
    def test_orphan_snapshot(self):
        operations.write_new(self.archive,self.data)
        with self.assertRaises(ValueError):self.run_at(1,20)
    def test_resume_copy(self):
        self.run_at(1,20)
        operations.write_new(self.replica,self.data)
        self.assertEqual(self.run_at(2,10)['performed_stage'],'export')
    def test_tampered_replica(self):
        self.run_at(1,20)
        self.run_at(2,10)
        self.replica.write_bytes(Fernet(self.key).encrypt(b'other'))
        with self.assertRaises(ValueError):self.run_at(3,10)
    def test_missing_archive(self):
        self.run_at(1,20)
        self.archive.unlink()
        with self.assertRaises(FileNotFoundError):self.run_at(2,10)
    def test_late(self):
        self.assertEqual(self.run_at(2,10)['status'],'MISSED_WINDOW')
        self.snapshot.assert_not_called()
    def test_failed_snapshot(self):
        self.snapshot.side_effect=ValueError('source failed')
        with self.assertRaises(ValueError):self.run_at(1,20)
        self.assertEqual(list((self.root/'state').glob('*.json')),[])
