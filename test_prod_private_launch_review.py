import unittest
from unittest.mock import patch
import prod_private_launch_review as launch

class LaunchReviewTest(unittest.TestCase):
    def setUp(self):
        self.kw=dict(envelope={'payload':{},'signature':'test'},public=b'x'*32,
            authority_pin='a'*64,compose_bytes=b'{}',evidence_bytes=b'{}',
            rec={},candidate={},expected_commit='b'*40,expected_image='dsig@sha256:'+'c'*64,
            expected_image_id='sha256:'+'d'*64,container_id='e'*64)
        observed=dict(status='PASS',local_daemon_used=True,commit='b'*40,
            image_digest='sha256:'+'c'*64,config_sha256='f'*64,evidence_sha256='a'*64)
        for module,name,value,attr in ((launch.measurement,'measure',observed,'measure'),
                (launch.release,'verify',{'status':'PASS'},'verify'),
                (launch.binding,'inspect',{'status':'PASS','local_daemon_used':True},'binding')):
            p=patch.object(module,name,return_value=value)
            setattr(self,attr,p.start())
            self.addCleanup(p.stop)

    def test_success_is_review_only(self):
        result=launch.review(**self.kw)
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['nonce_consumed'])
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['production_authorized'])
        self.assertEqual(self.verify.call_count,2)

    def test_measurement_failure(self):
        self.measure.return_value={'status':'FAIL'}
        self.assertEqual(launch.review(**self.kw)['status'],'FAIL')
        self.verify.assert_not_called()
        self.binding.assert_not_called()

    def test_invalid_signature(self):
        self.verify.return_value={'status':'FAIL'}
        self.assertEqual(launch.review(**self.kw)['status'],'FAIL')
        self.binding.assert_not_called()

    def test_simulated_container(self):
        self.binding.return_value={'status':'PASS','local_daemon_used':False}
        self.assertEqual(launch.review(**self.kw)['status'],'FAIL')

    def test_expiry_during_inspection(self):
        self.verify.side_effect=[{'status':'PASS'},{'status':'FAIL'}]
        result=launch.review(**self.kw)
        self.assertEqual(result['status'],'FAIL')
        self.assertFalse(result['nonce_consumed'])

if __name__=='__main__':
    unittest.main()
