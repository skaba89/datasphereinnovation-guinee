import unittest
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_slot_journal as j
import prod_backup_slot_anchored_execution as e
import prod_backup_slot_anchor as a
import prod_backup_slot_retry as retry
from prod_b2_cli import B2SlotQualificationAdapter,B2ReadTimeout
import operations

class Remote:
    def __init__(self):self.objects={}
    def bucket_info(self,b):return dict(bucketName='dsig-prod-backups',bucketId='prod-bucket-id',bucketType='allPrivate',encryption='SSE-B2',lock_mode='compliance',lock_days=30)
    def read(self,b,o):return self.objects.get(o)
    def create_only(self,b,o,data):
        if o in self.objects:raise ValueError('exists')
        self.objects[o]=data
    def read_slot_retry_records(self,b,r,d):
        prefix=f'prod/qualification/v232-slots/{r}/{d}/retry/audit/'
        return {k:v for k,v in self.objects.items() if k.startswith(prefix)}

class SlotRemoteTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base=Path(tmp.name)
        self.root=base/'cycle'
        self.state=base/'retry'
        self.lock=base/'lock'
        for p in (self.root,self.root/'state',self.root/'locks',self.root/'archives',self.root/'replica',self.state,self.lock):p.mkdir(mode=0o700)
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.remote=Remote()
        self.run_id='a'*32
        for offset in (0,12):
            blob=f'archive-{offset}'.encode()
            name=f'dsig-prod-20261126T{1+offset:02d}1500Z.dsigbak'
            for directory in ('archives','replica'):operations.write_new(self.root/directory/name,blob)
            for h,m,stage in ((1,20,'snapshot'),(2,10,'export'),(3,10,'audit')):
                j.append(self.root/'state',now=self.at(h+offset,m),stage=stage,archive_sha256=hashlib.sha256(blob).hexdigest(),signer=self.signer,pin=self.pin)
    def at(self,h,m):return datetime(2026,11,26,h,m,tzinfo=timezone.utc)
    def run_once(self,h,m):
        return e.run(root=self.root,retry_state=self.state,execution_lock=self.lock,clock=lambda:self.at(h,m),signer=self.signer,pin=self.pin,key=b'key',run_id=self.run_id,bucket_id='prod-bucket-id',remote=self.remote)
    def test_two_slots(self):
        with patch('prod_b2_export.verify_archive'):
            for h in (3,15):
                result=self.run_once(h,20)
                self.assertEqual(result['status'],'COMPLETE')
                self.assertTrue(result['remote_verified'])
                self.assertFalse(self.run_once(h,21)['performed'])
        self.assertEqual(len(self.remote.objects),8)
    def test_afternoon_retry(self):
        with patch.object(e.anchor,'publish',side_effect=B2ReadTimeout('timeout')):
            self.assertEqual(self.run_once(15,20)['status'],'WAIT')
            self.assertFalse(self.run_once(15,20)['performed'])
        with patch('prod_b2_export.verify_archive'):
            result=self.run_once(15,21)
        self.assertEqual(result['anchored_records'],4)
        self.assertEqual(result['status'],'COMPLETE')
    def test_missing_anchored_archive(self):
        args=dict(root=self.root,now=self.at(15,20),signer=self.signer,pin=self.pin,key=b'key',run_id=self.run_id,bucket_id='prod-bucket-id',remote=self.remote)
        with patch('prod_b2_export.verify_archive'):
            a.publish(**args)
            name=next(k for k in self.remote.objects if k.endswith('.dsigbak'))
            del self.remote.objects[name]
            with self.assertRaises(ValueError):a.publish(**args)
            self.assertNotIn(name,self.remote.objects)
    def test_namespace(self):
        adapter=B2SlotQualificationAdapter('prod-bucket-id')
        prefix='prod/qualification/v232-slots/'+self.run_id+'/2026-11-26-13/'
        self.assertTrue(adapter._allowed_object(prefix+'dsig-prod-20261126T131500Z.dsigbak'))
        self.assertFalse(adapter._allowed_object(prefix+'dsig-prod-20261126T011500Z.dsigbak'))
        self.assertFalse(adapter._allowed_object('prod/qualification/v232/'+self.run_id+'/journal-anchor.json'))
    def test_afternoon_window(self):
        self.assertEqual(retry.decide(now=self.at(15,20),cycle_day='2026-11-26-13',stage='audit',failures=[])['status'],'DUE')
        self.assertEqual(retry.decide(now=self.at(16,0),cycle_day='2026-11-26-13',stage='audit',failures=[])['status'],'MISSED_WINDOW')
