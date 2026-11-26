import tempfile
import unittest
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_slot_cycle as cycle
import prod_backup_slot_journal as journal
import prod_backup_slot_executor as executor
import prod_backup_cycle_journal as legacy
import operations

class SlotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.root=self.base/'root'
        self.source=self.base/'source'
        for p in (self.root,self.source,self.root/'state',self.root/'locks',self.root/'archives',self.root/'replica'):p.mkdir(mode=0o700)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
    def at(self,h,m=0):return datetime(2026,11,26,h,m,tzinfo=timezone.utc)
    def append(self,h,m,stage,digest):
        return journal.append(self.root/'state',now=self.at(h,m),stage=stage,archive_sha256=digest,signer=self.signer,pin=self.pin)
    def test_two_slots(self):
        for offset,digest in ((0,'a'*64),(12,'b'*64)):
            for h,m,stage in ((1,20,'snapshot'),(2,10,'export'),(3,10,'audit')):
                result=self.append(h+offset,m,stage,digest)
            self.assertEqual(result['status'],'COMPLETE')
            self.assertEqual(result['archive_sha256'],digest)
        self.assertEqual(len(list((self.root/'state').glob('*.json'))),6)
    def test_no_cross_slot_replay(self):
        self.append(1,20,'snapshot','a'*64)
        p=self.root/'state'/'2026-11-26-01.snapshot.json'
        operations.write_new(self.root/'state'/'2026-11-26-13.snapshot.json',p.read_bytes())
        with self.assertRaises(ValueError):journal.read(self.root/'state',now=self.at(13,20),public=self.public,pin=self.pin)
    def test_legacy_separate(self):
        legacy.append(self.root/'state',now=self.at(1,20),stage='snapshot',archive_sha256='a'*64,signer=self.signer,pin=self.pin)
        self.assertIsNone(journal.read(self.root/'state',now=self.at(1,20),public=self.public,pin=self.pin)['archive_sha256'])
    def test_end_exclusive(self):
        with self.assertRaises(ValueError):cycle.plan(self.at(14,5),{'snapshot':self.at(14,5)})
    def test_missed(self):
        self.assertEqual(cycle.plan(self.at(15),{})['status'],'MISSED_WINDOW')
    def test_archive_names(self):
        def fake(active,destination,**kw):
            data=destination.name.encode()
            operations.write_new(destination,data)
            return {'sha256':hashlib.sha256(data).hexdigest()}
        with patch.object(executor.snapshot,'create_review_snapshot',side_effect=fake),patch.object(executor.export,'verify_archive'):
            for offset in (0,12):
                for h,m in ((1,20),(2,10),(3,10)):
                    result=executor.run(root=self.root,active=self.source/'db',now=self.at(h+offset,m),key=b'key',signer=self.signer,pin=self.pin,source_check=lambda:{'status':'PASS'})
                self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(sorted(p.name for p in (self.root/'archives').iterdir()),['dsig-prod-20261126T011500Z.dsigbak','dsig-prod-20261126T131500Z.dsigbak'])
