import json
import unittest
from unittest.mock import patch
import prod_private_runtime_measurement as m

class RuntimeMeasurementTest(unittest.TestCase):
    def setUp(self):
        self.kw=dict(container_id='a'*64,image_id='sha256:'+'b'*64,
            expected_image='dsig@sha256:'+'c'*64,compose_bytes=b'{}')
        self.obs={'Id':self.kw['container_id'],'Config':{'Env':['DSIG_SECRET=synthetic']}}
        p=patch.object(m.binding,'inspect',return_value={'status':'PASS'})
        self.validator=p.start()
        self.addCleanup(p.stop)

    def measure(self,*observations):
        with patch.object(m.acquisition,'command',side_effect=list(observations)):
            return m.measure(**self.kw)

    def test_stable_canonical_hash(self):
        a=json.dumps(self.obs)
        b=json.dumps(self.obs,sort_keys=True,indent=2)
        result=self.measure(a,b)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(len(result['runtime_sha256']),64)
        self.assertNotIn('synthetic',str(result))
        self.assertFalse(result['startup_authorized'])

    def test_changed_observation(self):
        self.assertEqual(self.measure(json.dumps(self.obs),'{}')['status'],'FAIL')

    def test_validator_rejection(self):
        self.validator.return_value={'status':'FAIL'}
        self.assertEqual(self.measure(json.dumps(self.obs))['status'],'FAIL')

    def test_duplicate_keys(self):
        self.assertEqual(self.measure('{"Id":"a","Id":"b"}')['status'],'FAIL')

    def test_exact_observation_passed_to_validator(self):
        def validate(**kwargs):
            args=['container','inspect','--format',m.binding.FORMAT,self.kw['container_id']]
            self.assertEqual(json.loads(kwargs['run'](args)),self.obs)
            return {'status':'PASS'}
        self.validator.side_effect=validate
        self.assertEqual(self.measure(json.dumps(self.obs),json.dumps(self.obs))['status'],'PASS')

if __name__=='__main__':
    unittest.main()
