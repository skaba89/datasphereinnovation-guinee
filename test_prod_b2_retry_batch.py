import json
import unittest
from pathlib import Path
from prod_b2_cli import B2QualificationAdapter,BUCKET,CAPABILITIES

ID='prod-bucket-id'
RUN='a'*32
DAY='2026-11-26'
PREFIX=f'prod/qualification/v232/{RUN}/retry/{DAY}/audit/'
OBJ=PREFIX+'1.start.json'

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        self.rows=[dict(fileName=OBJ,action='upload',fileId='version1')]
        self.list_count=0
        self.change=False
        self.adapter=B2QualificationAdapter(ID,run=self.fake)
    def fake(self,args):
        self.calls.append(args)
        if args[:2]==['account','get']:
            return json.dumps(dict(isMasterKey=False,allowed=dict(capabilities=sorted(CAPABILITIES),namePrefix='prod/',buckets=[dict(id=ID,name=BUCKET)])))
        if args[:2]==['bucket','get']:
            return json.dumps(dict(bucketId=ID,bucketName=BUCKET,bucketType='allPrivate',isFileLockEnabled=True,defaultRetention=dict(mode='compliance',period=dict(unit='days',duration=30)),defaultServerSideEncryption=dict(mode='SSE-B2',algorithm='AES256')))
        if args[0]=='ls':
            self.list_count+=1
            if self.change and self.list_count==2:return json.dumps([dict(self.rows[0],fileId='version2')])
            return json.dumps(self.rows)
        if args[:2]==['file','download']:
            Path(args[-1]).write_bytes(b'proof')
            return b''
        raise AssertionError(args)
    def read(self):return self.adapter.read_retry_records(BUCKET,RUN,DAY)
    def test_batch(self):
        self.assertEqual(self.read(),{OBJ:b'proof'})
        self.assertEqual(self.list_count,2)
        self.assertEqual(len(self.calls),7)
    def test_empty(self):
        self.rows=[]
        self.assertEqual(self.read(),{})
        self.assertEqual(self.list_count,2)
    def test_changed_version(self):
        self.change=True
        with self.assertRaises(ValueError):self.read()
    def test_duplicate(self):
        self.rows*=2
        with self.assertRaises(ValueError):self.read()
    def test_hide(self):
        self.rows[0]['action']='hide'
        with self.assertRaises(ValueError):self.read()
    def test_unknown_object(self):
        self.rows[0]['fileName']=PREFIX+'6.start.json'
        with self.assertRaises(ValueError):self.read()
    def test_invalid_scope(self):
        with self.assertRaises(ValueError):self.adapter.read_retry_records(BUCKET,'../x',DAY)
        self.assertEqual(self.calls,[])
