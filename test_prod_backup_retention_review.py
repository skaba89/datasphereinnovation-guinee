import unittest
from datetime import datetime,timedelta,timezone
import prod_backup_retention_review as r

NOW=datetime(2026,11,26,tzinfo=timezone.utc)
def row(day,version):
    stamp=NOW-timedelta(days=day)
    return dict(object=f'prod/{stamp:%Y/%m}/dsig-prod-{stamp:%Y%m%dT%H%M%SZ}.dsigbak',version=version,action='upload',uploaded_at=stamp,retain_until=stamp+timedelta(days=30),lock_mode='compliance',legal_hold=False)

class RetentionTests(unittest.TestCase):
    def bucket(self):
        return dict(bucketId='prod-bucket-id',bucketName=r.BUCKET,bucketType='allPrivate',defaultServerSideEncryption=dict(mode='SSE-B2',algorithm='AES256'),isFileLockEnabled=True,defaultRetention=dict(mode='compliance',period=dict(unit='days',duration=30)),lifecycleRules=[])
    def test_bucket(self):self.assertEqual(r.inspect_bucket(self.bucket(),'prod-bucket-id')['status'],'PASS')
    def test_lifecycle(self):
        b=self.bucket();b['lifecycleRules']=[{'fileNamePrefix':'prod/'}]
        self.assertEqual(r.inspect_bucket(b,'prod-bucket-id')['status'],'FAIL')
    def test_lock(self):
        b=self.bucket();b['defaultRetention']['mode']='governance'
        self.assertEqual(r.inspect_bucket(b,'prod-bucket-id')['status'],'FAIL')
    def test_plan(self):
        result=r.plan([row(1,'1'),row(5,'2'),row(100,'3'),row(101,'4')],now=NOW)
        self.assertEqual([x['decision'] for x in result['objects']],['LOCKED','LOCKED','KEEP_TIER_REVIEW','REVIEW_EXPIRED'])
        self.assertFalse(result['delete_authorized'])
        self.assertTrue(all(not x['delete_authorized'] for x in result['objects']))
    def test_hold(self):
        a=row(100,'1');a['legal_hold']=True
        self.assertEqual(r.plan([a],now=NOW)['objects'][0]['decision'],'LOCKED')
    def test_duplicate(self):
        a=row(100,'1')
        with self.assertRaises(ValueError):r.plan([a,dict(a,version='2')],now=NOW)
    def test_namespace(self):
        a=row(100,'1');a['object']='prod/qualification/'+a['object']
        with self.assertRaises(ValueError):r.plan([a],now=NOW)
    def test_missing_retention(self):
        a=row(100,'1');a['retain_until']=a['uploaded_at']
        with self.assertRaises(ValueError):r.plan([a],now=NOW)
    def test_hide(self):
        a=row(100,'1');a['action']='hide'
        with self.assertRaises(ValueError):r.plan([a],now=NOW)
    def test_future(self):
        with self.assertRaises(ValueError):r.plan([row(-1,'1')],now=NOW)
