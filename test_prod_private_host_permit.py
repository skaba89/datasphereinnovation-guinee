import unittest
from unittest.mock import patch
import prod_private_host_permit as permit

class HostPermitTest(unittest.TestCase):
    def setUp(self):
        self.kw=dict(envelope={'payload':{},'signature':'test'},public=b'x'*32,
                     authority_pin='a'*64,ledger_path='/unused',
                     compose_bytes=b'{}',evidence_bytes=b'{}',rec={},candidate={},
                     expected_commit='b'*40,expected_image='dsig@sha256:'+'c'*64,
                     expected_image_id='sha256:'+'d'*64)
        self.expected=dict(commit='b'*40,image_digest='sha256:'+'c'*64,
                           config_sha256='e'*64,evidence_sha256='f'*64)
        p=patch.object(permit.measurement,'measure',return_value=dict(status='PASS',local_daemon_used=True,**self.expected))
        self.measure=p.start()
        self.addCleanup(p.stop)
        p=patch.object(permit.release,'verify',return_value={'status':'PASS'})
        self.verify=p.start()
        self.addCleanup(p.stop)
        p=patch.object(permit.replay,'consume',return_value={'status':'PASS'})
        self.consume=p.start()
        self.addCleanup(p.stop)

    def test_success_reserves_but_does_not_authorize(self):
        result=permit.reserve(**self.kw)
        self.assertEqual(result['status'],'PASS')
        self.assertTrue(result['nonce_consumed'])
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['production_authorized'])
        self.consume.assert_called_once_with('/unused',self.kw['envelope'],self.kw['public'],
                                             authority_pin=self.kw['authority_pin'],**self.expected)

    def test_failed_measurement_never_consumes(self):
        self.measure.return_value={'status':'FAIL','local_daemon_used':True}
        self.assertEqual(permit.reserve(**self.kw)['status'],'FAIL')
        self.verify.assert_not_called()
        self.consume.assert_not_called()

    def test_simulated_measurement_never_consumes(self):
        self.measure.return_value['local_daemon_used']=False
        self.assertEqual(permit.reserve(**self.kw)['status'],'FAIL')
        self.consume.assert_not_called()

    def test_invalid_signature_never_consumes(self):
        self.verify.return_value={'status':'FAIL'}
        self.assertEqual(permit.reserve(**self.kw)['status'],'FAIL')
        self.consume.assert_not_called()

    def test_replay_rejected(self):
        self.consume.return_value={'status':'FAIL'}
        result=permit.reserve(**self.kw)
        self.assertEqual(result['status'],'FAIL')
        self.assertFalse(result['nonce_consumed'])

if __name__=='__main__':
    unittest.main()
