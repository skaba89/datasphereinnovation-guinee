import unittest
import json
from datetime import datetime,timezone
from prod_backup_retention_inventory import RetentionInventory,normalize
from prod_b2_cli import CAPABILITIES,BUCKET

ID='prod-bucket-id'
NOW=datetime(2026,11,26,tzinfo=timezone.utc)
OBJ='prod/2026/08/dsig-prod-20260801T011500Z.dsigbak'
class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.rows=[dict(bucketId=ID,fileName=OBJ,fileId='v1',action='upload',
            uploadTimestamp=1785546900000,fileRetention=dict(mode='compliance',retainUntilTimestamp=1788138900000),legalHold='off')]
        self.adapter=RetentionInventory(ID,run=self.fake)
        self.bucket=dict(bucketId=ID,bucketName=BUCKET,bucketType='allPrivate',defaultServerSideEncryption=dict(mode='SSE-B2',algorithm='AES256'),isFileLockEnabled=True,defaultRetention=dict(mode='compliance',period=dict(unit='days',duration=30)),lifecycleRules=[])
    def fake(self,args):
        self.calls.append(args)
        if args[:2]==['account','get']:return json.dumps(dict(isMasterKey=False,allowed=dict(capabilities=sorted(CAPABILITIES),namePrefix='prod/',buckets=[dict(id=ID,name=BUCKET)])))
        if args[:2]==['bucket','get']:return json.dumps(self.bucket)
        if args[0]=='ls':return json.dumps(self.rows)
        raise AssertionError('unexpected write')
    def test_empty(self):
        self.rows=[]
        result=self.adapter.collect(now=NOW)
        self.assertEqual(result['objects'],[])
        self.assertFalse(result['delete_authorized'])
    def test_qualification_excluded(self):
        self.rows=[dict(fileName='prod/qualification/v232-slots/'+'a'*32+'/2026-11-26-13/journal-anchor.json'),dict(fileName='prod/2026/11/dsig-prod-20261126T100822Z.dsigbak')]
        self.assertEqual(self.adapter.collect(now=NOW)['excluded_objects'],2)
    def test_unknown_hold_protected(self):
        self.rows[0]['legalHold']={'isClientAuthorizedToRead':False,'value':None}
        self.assertTrue(normalize(self.rows[0],ID)['legal_hold'])
    def test_wrapped_retention(self):
        self.rows[0]['fileRetention']={'isClientAuthorizedToRead':True,'value':self.rows[0]['fileRetention']}
        self.assertEqual(normalize(self.rows[0],ID)['lock_mode'],'compliance')
    def test_missing_retention(self):
        self.rows[0]['fileRetention']=None
        with self.assertRaises(ValueError):self.adapter.collect(now=NOW)
    def test_write_refused(self):
        with self.assertRaises(ValueError):self.adapter.create_only(BUCKET,OBJ,b'x')
        self.assertEqual(self.calls,[])
    def test_unknown_namespace(self):
        self.rows[0]['fileName']='prod/other/unknown'
        with self.assertRaises(ValueError):self.adapter.collect(now=NOW)
    def test_lifecycle_refused(self):
        self.bucket['lifecycleRules']=[{'fileNamePrefix':'prod/'}]
        with self.assertRaises(ValueError):self.adapter.collect(now=NOW)
