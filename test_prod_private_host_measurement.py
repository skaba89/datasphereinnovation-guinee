import json
import unittest
from unittest.mock import patch
import prod_private_host_measurement as host

class HostMeasurementTest(unittest.TestCase):
    def setUp(self):
        self.commit='a'*40
        self.image='example/dsig@sha256:'+'b'*64
        self.image_id='sha256:'+'c'*64
        self.obs=dict(Id=self.image_id,RepoDigests=[self.image],User='10001:10001',Revision=self.commit)
        self.kw=dict(compose_bytes=b'{"services":{"app":{"environment":{}}}}',
                     evidence_bytes=b'{}',rec={},candidate={},expected_commit=self.commit,
                     expected_image=self.image,expected_image_id=self.image_id)
        for target in ('prod_compose.validate','prod_config.inspect'):
            p=patch(target,return_value={'status':'PASS'})
            p.start()
            self.addCleanup(p.stop)
        p=patch('prod_review.complete',return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def test_valid_measurement_is_not_authorization(self):
        result=host.measure(**self.kw,run=lambda _:json.dumps(self.obs))
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['production_authorized'])
        self.assertFalse(result['local_daemon_used'])

    def test_identity_mismatch(self):
        for key,value in [('Id','sha256:'+'d'*64),('RepoDigests',[]),
                          ('User','0:0'),('Revision','d'*40)]:
            with self.subTest(key=key):
                self.assertEqual(host.measure(**self.kw,run=lambda _:json.dumps(dict(self.obs,**{key:value})))['status'],'FAIL')

    def test_unstable_observation(self):
        observations=iter([self.obs,dict(self.obs,Revision='d'*40)])
        self.assertEqual(host.measure(**self.kw,run=lambda _:json.dumps(next(observations)))['status'],'FAIL')

    def test_configuration_rejected_before_docker(self):
        with patch('prod_config.inspect',return_value={'status':'FAIL'}):
            def forbidden(_):
                self.fail('Docker must not be inspected')
            self.assertEqual(host.measure(**self.kw,run=forbidden)['status'],'FAIL')

    def test_duplicate_json_rejected(self):
        self.kw['compose_bytes']=b'{"services":{},"services":{}}'
        self.assertEqual(host.measure(**self.kw,run=lambda _:self.fail('unexpected Docker'))['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
