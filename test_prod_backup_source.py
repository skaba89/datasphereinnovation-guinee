import unittest
import prod_backup_source as p


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.cid='a'*64
        self.image='sha256:'+'b'*64
        self.path='/var/lib/docker/volumes/dsig-prod_prod-data/_data'
        self.c={'Id':self.cid,'Image':self.image,'Config':{'User':'10001:10001','Labels':{
            'com.docker.compose.project':'dsig-prod','com.docker.compose.service':'app'}},
            'Mounts':[{'Destination':'/app/data','Type':'volume','Name':p.VOLUME,'RW':True,'Source':self.path}],
            'State':{'Running':True},'HostConfig':{'Privileged':False,'ReadonlyRootfs':True}}
        self.v={'Name':p.VOLUME,'Driver':'local','Scope':'local','Options':None,'Mountpoint':self.path,
            'Labels':{'com.docker.compose.project':'dsig-prod','com.docker.compose.volume':'prod-data'}}

    def check(self,status='FAIL'):
        result=p.inspect(self.c,self.v,expected_container_id=self.cid,expected_image_id=self.image)
        self.assertEqual(result['status'],status)
        self.assertFalse(result['production_authorized'])
        self.assertFalse(result['database_verified'])

    def test_valid_projection(self):
        self.check('PASS')

    def test_rec_project(self):
        self.c['Config']['Labels']['com.docker.compose.project']='dsig-rec'
        self.check()

    def test_candidate_volume(self):
        self.c['Mounts'][0]['Name']='dsig-prod-candidate_candidate-data'
        self.check()

    def test_wrong_image(self):
        self.c['Image']='sha256:'+'c'*64
        self.check()

    def test_nested_mount(self):
        self.c['Mounts'].append({'Destination':'/app/data/requests.sqlite3'})
        self.check()

    def test_bind_volume_options(self):
        self.v['Options']={'device':'/tmp/rec','type':'none','o':'bind'}
        self.check()

    def test_source_mismatch(self):
        self.c['Mounts'][0]['Source']='/tmp/rec'
        self.check()

    def test_stopped(self):
        self.c['State']['Running']=False
        self.check()

    def test_privileged(self):
        self.c['HostConfig']['Privileged']=True
        self.check()

    def test_missing(self):
        del self.c['Mounts']
        self.check()
