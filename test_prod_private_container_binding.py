import copy
import json
import unittest
from unittest.mock import patch
import prod_private_container_binding as binding

class ContainerBindingTest(unittest.TestCase):
    def setUp(self):
        self.cid='a'*64
        self.iid='sha256:'+'b'*64
        self.image='dsig@sha256:'+'c'*64
        self.kw=dict(container_id=self.cid,image_id=self.iid,expected_image=self.image,
                     compose_bytes=b'{"services":{"app":{"environment":{"DSIG_ENV":"PROD"}}}}')
        self.c=dict(Id=self.cid,Image=self.iid,State='created',
            Config=dict(Image=self.image,Labels={'com.docker.compose.project':'dsig-prod',
                'com.docker.compose.service':'app'},Entrypoint=binding.prod_compose.STOP,
                Cmd=None,Env=['DSIG_ENV=PROD','DSIG_CONTAINER=1'],User='10001:10001'),
            HostConfig=dict(Privileged=False,ReadonlyRootfs=True,CapDrop=['ALL'],
                SecurityOpt=['no-new-privileges:true'],PortBindings={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8320'}]},
                RestartPolicy={'Name':'no'},Memory=536870912,MemorySwap=536870912,
                NanoCpus=2000000000,PidsLimit=128,NetworkMode='dsig-prod_prod-private'),
            Mounts=[dict(Destination='/app/data',Type='volume',Name='dsig-prod_prod-data',RW=True),
                    dict(Destination='/run/dsig-clamav',Type='bind',Source='/run/clamav',RW=False)],
            Networks={'dsig-prod_prod-private':{}})
        p=patch.object(binding.prod_compose,'validate',return_value={'status':'PASS'})
        p.start()
        self.addCleanup(p.stop)

    def check(self,c):
        return binding.inspect(**self.kw,run=lambda _:json.dumps(c))

    def test_valid_review_is_not_authorization(self):
        result=self.check(self.c)
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['local_daemon_used'])

    def test_wrong_image_or_running_container(self):
        for key,value in [('Image','sha256:'+'d'*64),('State','running')]:
            with self.subTest(key=key):
                c=dict(self.c,**{key:value})
                self.assertEqual(self.check(c)['status'],'FAIL')

    def test_environment_mismatch(self):
        for value in ['DSIG_ENV=REC','DSIG_ENV=PROD','DSIG_ADMIN_TOKEN=secret']:
            c=copy.deepcopy(self.c)
            c['Config']['Env'].append(value)
            self.assertEqual(self.check(c)['status'],'FAIL')

    def test_public_port_and_privilege_rejected(self):
        for key,value in [('Privileged',True),('PortBindings',{'8080/tcp':[{'HostIp':'0.0.0.0','HostPort':'8320'}]})]:
            c=copy.deepcopy(self.c)
            c['HostConfig'][key]=value
            self.assertEqual(self.check(c)['status'],'FAIL')

    def test_changed_observation(self):
        observations=iter([self.c,dict(self.c,State='running')])
        result=binding.inspect(**self.kw,run=lambda _:json.dumps(next(observations)))
        self.assertEqual(result['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
