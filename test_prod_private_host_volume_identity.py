import json
import stat
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import prod_private_host_volume_identity as identity

class HostVolumeTest(unittest.TestCase):
    def setUp(self):
        self.cid='a'*64
        self.iid='sha256:'+'b'*64
        self.c={'Id':self.cid,'Image':self.iid,'State':{'Running':False},
            'Config':{'User':'10001:10001','Labels':{'com.docker.compose.project':'dsig-prod','com.docker.compose.service':'app'}},
            'Mounts':[{'Destination':'/app/data','Type':'volume','Name':identity.VOLUME,'RW':True,'Source':str(identity.MOUNT)}],
            'HostConfig':{'Privileged':False,'ReadonlyRootfs':True}}
        self.v={'Name':identity.VOLUME,'Driver':'local','Scope':'local','Options':None,
            'Mountpoint':str(identity.MOUNT),'Labels':{'com.docker.compose.project':'dsig-prod','com.docker.compose.volume':'prod-data'}}
        self.ids=self.cid
        p=patch.object(identity,'host_identity',return_value='c'*64)
        self.host=p.start()
        self.addCleanup(p.stop)
        p=patch.object(identity.acquisition,'command',side_effect=self.command)
        p.start()
        self.addCleanup(p.stop)
        p=patch.object(type(identity.MOUNT),'lstat',return_value=SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_dev=1,st_ino=2,st_uid=10001,st_gid=10001))
        p.start()
        self.addCleanup(p.stop)
        p=patch.object(type(identity.MOUNT),'resolve',return_value=identity.MOUNT)
        p.start()
        self.addCleanup(p.stop)

    def command(self,args):
        if args[:2]==['container','inspect']:
            return json.dumps(self.c)
        if args[:2]==['volume','inspect']:
            return json.dumps(self.v)
        if args[:2]==['container','ls']:
            return self.ids
        raise ValueError('unexpected command')

    def measure(self):
        return identity.measure(container_id=self.cid,image_id=self.iid)

    def test_stable_identity(self):
        result=self.measure()
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(len(result['volume_identity_sha256']),64)
        self.assertFalse(result['startup_authorized'])
        self.assertEqual(result,self.measure())

    def test_additional_consumer(self):
        self.ids+='\n'+'d'*64
        self.assertEqual(self.measure()['status'],'FAIL')

    def test_running_consumer(self):
        self.c['State']['Running']=True
        self.assertEqual(self.measure()['status'],'FAIL')

    def test_wrong_volume_options(self):
        self.v['Options']={'type':'nfs'}
        self.assertEqual(self.measure()['status'],'FAIL')

    def test_host_changed(self):
        self.host.side_effect=['c'*64,'d'*64]
        self.assertEqual(self.measure()['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
