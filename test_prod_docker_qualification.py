import unittest
import json
import prod_backup_source as source
import prod_backup_acquisition as acquisition
import test_prod_backup_source as fixtures


class QualificationTests(unittest.TestCase):
    def setUp(self):
        f=fixtures.SourceTests()
        f.setUp()
        self.c,self.v=f.c,f.v
        self.cid,self.image=f.cid,f.image
        self.run_id='1234567890abcdef'
        project='dsig-qualification-'+self.run_id
        name=project+'_prod-data'
        path='/var/lib/docker/volumes/'+name+'/_data'
        self.c['Config']['Labels']['com.docker.compose.project']=project
        self.c['Mounts'][0].update(Name=name,Source=path)
        self.c['State']['StartedAt']='2026-11-26T12:00:00Z'
        self.v.update(Name=name,Mountpoint=path)
        self.v['Labels']['com.docker.compose.project']=project

    def fake(self,args):
        if args[:2]==['container','inspect']:return json.dumps(self.c)
        if args[:2]==['volume','inspect']:return json.dumps(self.v)
        if args[:2]==['container','ls']:return self.cid
        raise AssertionError('unexpected command')

    def test_qualification_pass(self):
        r=acquisition.acquire_qualification(expected_container_id=self.cid,expected_image_id=self.image,run_id=self.run_id,run=self.fake)
        self.assertEqual(r['status'],'PASS')
        self.assertTrue(r['qualification_only'])
        self.assertFalse(r['production_authorized'])

    def test_prod_rejects_qualification(self):
        r=source.inspect(self.c,self.v,expected_container_id=self.cid,expected_image_id=self.image)
        self.assertEqual(r['status'],'FAIL')

    def test_wrong_run_id(self):
        r=acquisition.acquire_qualification(expected_container_id=self.cid,expected_image_id=self.image,run_id='0'*16,run=self.fake)
        self.assertEqual(r['status'],'FAIL')

    def test_invalid_namespace(self):
        with self.assertRaises(ValueError):
            acquisition.acquire_qualification(expected_container_id=self.cid,expected_image_id=self.image,run_id='dsig-prod',run=self.fake)
