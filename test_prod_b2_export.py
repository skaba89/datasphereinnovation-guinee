import tempfile
import unittest
from pathlib import Path
import prod_b2_export as p


class Remote:
    def __init__(self):
        self.info=dict(bucketName=p.BUCKET,bucketId='prod-bucket-id',bucketType='allPrivate',
                       encryption='SSE-B2',lock_mode='compliance',lock_days=30)
        self.objects={}
        self.writes=0
    def bucket_info(self,bucket):
        return self.info
    def read(self,bucket,obj):
        return self.objects.get((bucket,obj))
    def create_only(self,bucket,obj,data):
        if (bucket,obj) in self.objects:
            raise ValueError('already exists')
        self.writes+=1
        self.objects[bucket,obj]=data


class ProdExportTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/'dsig-prod-20261126T021500Z.dsigbak'
        self.path.write_bytes(b'synthetic archive bytes')
        self.path.chmod(0o600)
        self.remote=Remote()

    def export(self):
        return p.export_review(self.path,expected_bucket_id='prod-bucket-id',remote=self.remote)

    def test_idempotent(self):
        first=self.export()
        second=self.export()
        self.assertTrue(first['uploaded'])
        self.assertFalse(second['uploaded'])
        self.assertEqual(first['sha256'],second['sha256'])
        self.assertEqual(self.remote.writes,1)
        self.assertFalse(first['production_authorized'])

    def test_remote_mismatch(self):
        result=self.export()
        self.remote.objects[p.BUCKET,result['object']]=b'different'
        with self.assertRaises(ValueError):self.export()
        self.assertEqual(self.remote.writes,1)

    def test_policy(self):
        for key,value in [('bucketId','rec-bucket-id'),('bucketType','allPublic'),
                          ('encryption','none'),('lock_mode','governance'),('lock_days',29)]:
            original=self.remote.info[key]
            self.remote.info[key]=value
            with self.assertRaises(ValueError):self.export()
            self.remote.info[key]=original
        self.assertEqual(self.remote.writes,0)

    def test_reject_rec_name(self):
        other=self.path.with_name('dsig-rec-20261126T021500Z.dsigbak')
        self.path.rename(other)
        self.path=other
        with self.assertRaises(ValueError):self.export()

    def test_symlink(self):
        target=self.path.with_name('target')
        self.path.rename(target)
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):self.export()

    def test_permissions(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):self.export()
