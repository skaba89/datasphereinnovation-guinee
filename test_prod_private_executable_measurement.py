import copy
import json
import unittest
from unittest.mock import patch
import prod_private_executable_binding as binding
import prod_private_executable_measurement as measurement
from test_prod_private_launch_topology import proposed
from test_prod_compose import IMAGE

class ExecutableMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.cid='a'*64
        self.iid='sha256:'+'b'*64
        config=proposed()
        env=config['services']['app']['environment']
        self.kw=dict(container_id=self.cid,image_id=self.iid,expected_image=IMAGE,
                     compose_bytes=json.dumps(config).encode())
        self.c=dict(Id=self.cid,Image=self.iid,State='created',
            Config=dict(Image=IMAGE,Labels={'com.docker.compose.project':'dsig-prod',
                'com.docker.compose.service':'app'},Entrypoint=binding.topology.ENTRYPOINT,
                Cmd=None,Env=[k+'='+v for k,v in env.items()]+['DSIG_CONTAINER=1'],User='10001:10001'),
            HostConfig=dict(Privileged=False,ReadonlyRootfs=True,CapDrop=['ALL'],
                SecurityOpt=['no-new-privileges:true'],PortBindings={'8080/tcp':[{'HostIp':'127.0.0.1','HostPort':'8320'}]},
                RestartPolicy={'Name':'no'},Memory=536870912,MemorySwap=536870912,
                MemoryReservation=134217728,NanoCpus=2000000000,PidsLimit=128,
                NetworkMode='dsig-prod_prod-private',GroupAdd=['109'],
                Tmpfs={'/tmp':'rw,noexec,nosuid,nodev,size=64m'},
                LogConfig={'Type':'json-file','Config':{'max-size':'10m','max-file':'5'}},
                PublishAllPorts=False,Mounts=[dict(Type='bind',Source=binding.topology.HOST_CHANNEL,
                    Target=binding.topology.CHANNEL,ReadOnly=True,BindOptions={'CreateMountpoint':False})]),
            Mounts=[dict(Destination='/app/data',Type='volume',Name='dsig-prod_prod-data',RW=True),
                    dict(Destination='/run/dsig-clamav',Type='bind',Source='/run/clamav',RW=False),
                    dict(Destination=binding.topology.CHANNEL,Type='bind',Source=binding.topology.HOST_CHANNEL,RW=False)],
            Networks={'dsig-prod_prod-private':{}})

    def measure(self,c):
        with patch.object(measurement.acquisition,'command',return_value=json.dumps(c)):
            return measurement.measure(**self.kw)

    def test_valid_measurement_is_not_authorization(self):
        report=self.measure(self.c)
        self.assertEqual(report['status'],'PASS')
        self.assertRegex(report['runtime_sha256'],r'^[0-9a-f]{64}$')
        self.assertFalse(report['startup_authorized'])
        self.assertFalse(report['production_authorized'])
        self.assertNotIn('fake',str(report))

    def test_review_entrypoint_rejected(self):
        c=copy.deepcopy(self.c)
        c['Config']['Entrypoint']=binding.topology.prod_compose.STOP
        self.assertEqual(self.measure(c)['status'],'FAIL')

    def test_channel_and_group_rejected(self):
        c=copy.deepcopy(self.c)
        c['Mounts'][-1]['RW']=True
        self.assertEqual(self.measure(c)['status'],'FAIL')
        c=copy.deepcopy(self.c)
        c['HostConfig']['GroupAdd']=['0']
        self.assertEqual(self.measure(c)['status'],'FAIL')

    def test_host_namespace_and_devices_rejected(self):
        for field,value in [('PidMode','host'),('IpcMode','host'),('Devices',[{'PathOnHost':'/dev/sda'}])]:
            c=copy.deepcopy(self.c)
            c['HostConfig'][field]=value
            self.assertEqual(self.measure(c)['status'],'FAIL')

    def test_engine_create_mountpoint_rejected(self):
        c=copy.deepcopy(self.c)
        c['HostConfig']['Mounts'][0]['BindOptions']['CreateMountpoint']=True
        self.assertEqual(self.measure(c)['status'],'FAIL')

    def test_changed_observation_rejected(self):
        with patch.object(measurement.acquisition,'command',side_effect=[
                json.dumps(self.c),json.dumps(dict(self.c,State='running'))]):
            self.assertEqual(measurement.measure(**self.kw)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
