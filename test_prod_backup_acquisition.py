import json
import unittest
import prod_backup_acquisition as p
from test_prod_backup_source import SourceTests


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        fixture=SourceTests()
        fixture.setUp()
        self.c,self.v=fixture.c,fixture.v
        self.cid,self.image=fixture.cid,fixture.image
        self.c['State']['StartedAt']='2026-11-26T10:00:00Z'
        self.ids=[self.cid]
        self.calls=[]
        self.change=False

    def fake_run(self,args):
        self.calls.append(args)
        if args[:2]==['container','inspect']:
            self.assertNotIn('Config.Env',args[3])
            if self.change and len(self.calls)>3:
                self.c['State']['StartedAt']='2026-11-26T11:00:00Z'
            return json.dumps(self.c)
        if args[:2]==['volume','inspect']:
            return json.dumps(self.v)
        if args[:2]==['container','ls']:
            self.assertIn('--all',args)
            return '\n'.join(self.ids)
        raise AssertionError('unexpected command')

    def check(self,status='FAIL'):
        result=p.acquire(expected_container_id=self.cid,expected_image_id=self.image,run=self.fake_run)
        self.assertEqual(result['status'],status)
        self.assertFalse(result['local_daemon_used'])
        self.assertFalse(result['production_authorized'])
        self.assertFalse(result['database_verified'])

    def test_stable(self):
        self.check('PASS')
        self.assertEqual(len(self.calls),6)

    def test_restart_between_two_stable_acquisitions(self):
        args = dict(expected_container_id=self.cid, expected_image_id=self.image, run=self.fake_run)
        first = p.acquire(**args)
        self.assertEqual(first['source_started_at'], self.c['State']['StartedAt'])
        self.assertEqual(p.acquire(**args, expected_started_at=first['source_started_at'])['status'], 'PASS')
        self.c['State']['StartedAt'] = '2026-11-26T11:30:00Z'
        result = p.acquire(**args, expected_started_at=first['source_started_at'])
        self.assertEqual(result['status'], 'FAIL')
        self.assertIsNone(result['source_started_at'])

    def test_other_consumer(self):
        self.ids.append('d'*64)
        self.check()

    def test_missing_consumer(self):
        self.ids=[]
        self.check()

    def test_restarted(self):
        self.change=True
        self.check()

    def test_wrong_volume(self):
        self.v['Name']='dsig-rec_dsig-data'
        self.check()

    def test_invalid_pin(self):
        self.cid='--help'
        self.check()
        self.assertEqual(self.calls,[])

    def test_bad_json(self):
        result=p.acquire(expected_container_id=self.cid,expected_image_id=self.image,run=lambda args:'not-json')
        self.assertEqual(result['status'],'FAIL')
