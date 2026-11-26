import json
import unittest
from prod_b2_cli import B2ReviewAdapter, CAPABILITIES, BUCKET

ID='prod-bucket-id'
OBJ='prod/2026/11/dsig-prod-20261126T021500Z.dsigbak'


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.account=dict(isMasterKey=False,allowed=dict(capabilities=sorted(CAPABILITIES),
                          namePrefix='prod/',buckets=[dict(id=ID,name=BUCKET)]))
        self.bucket=dict(bucketId=ID,bucketName=BUCKET,bucketType='allPrivate',isFileLockEnabled=True,
                         defaultRetention=dict(mode='compliance',period=dict(unit='days',duration=30)),
                         defaultServerSideEncryption=dict(mode='SSE-B2',algorithm='AES256'))
        self.rows=[]
        self.calls=[]
        self.adapter=B2ReviewAdapter(ID,run=self.run)

    def run(self,args):
        self.calls.append(args)
        if args[:2]==['account','get']:return json.dumps(self.account)
        if args[:2]==['bucket','get']:return json.dumps(self.bucket)
        if args[0]=='ls':return json.dumps(self.rows)
        raise AssertionError('unexpected command')

    def test_policy(self):
        self.assertEqual(self.adapter.bucket_info(BUCKET)['lock_days'],30)

    def test_excess_permissions(self):
        self.account['allowed']['capabilities'].append('deleteFiles')
        with self.assertRaises(ValueError):self.adapter.bucket_info(BUCKET)

    def test_bucket_identity(self):
        self.bucket['bucketId']='other-bucket-id'
        with self.assertRaises(ValueError):self.adapter.bucket_info(BUCKET)

    def test_absent(self):
        self.assertIsNone(self.adapter.read(BUCKET,OBJ))

    def test_duplicate_versions(self):
        self.rows=[dict(fileName=OBJ,action='upload')]*2
        with self.assertRaises(ValueError):self.adapter.read(BUCKET,OBJ)

    def test_hide_marker(self):
        self.rows=[dict(fileName=OBJ,action='hide')]
        with self.assertRaises(ValueError):self.adapter.read(BUCKET,OBJ)

    def test_other_namespace(self):
        with self.assertRaises(ValueError):self.adapter.read('dsig-backup',OBJ)
        self.assertEqual(self.calls,[])

    def test_existing_no_upload(self):
        self.rows=[dict(fileName=OBJ,action='upload')]
        with self.assertRaises(ValueError):self.adapter.create_only(BUCKET,OBJ,b'x')
        self.assertFalse(any(x[:2]==['file','upload'] for x in self.calls))
