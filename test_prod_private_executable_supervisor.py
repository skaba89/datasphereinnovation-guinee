import unittest
from unittest.mock import patch
import prod_private_executable_supervisor as supervisor
import prod_private_runtime_contract as contract

class SupervisorTest(unittest.TestCase):
    def setUp(self):
        self.kw=dict(compose_bytes=b'{}',evidence_bytes=b'{}',rec={},candidate={},
            expected_commit='a'*40,expected_image='dsig@sha256:'+'b'*64,
            expected_image_id='sha256:'+'c'*64,container_id='d'*64)
        a=dict(status='PASS',local_daemon_used=True,commit='a'*40,image_digest='sha256:'+'b'*64,
            image_id='sha256:'+'c'*64,config_sha256='e'*64,evidence_sha256='f'*64)
        b=dict(status='PASS',local_daemon_used=True,container_id='d'*64,image_id='sha256:'+'c'*64,
            runtime_sha256='1'*64)
        c=dict(status='PASS',local_daemon_used=True,host_identity_sha256='2'*64,volume_identity_sha256='3'*64)
        for name,module,value in (('host',supervisor.host,a),('runtime',supervisor.runtime,b),('identity',supervisor.identity,c)):
            p=patch.object(module,'measure',return_value=value)
            setattr(self,name,p.start())
            self.addCleanup(p.stop)

    def test_exact_runtime_contract_fields(self):
        result=supervisor.inspect(**self.kw)
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['nonce_consumed'])
        self.assertEqual(set(result['runtime_measurements']),set(contract.PATTERNS))
        self.assertFalse(result['production_authorized'])

    def test_changed_measurements(self):
        first=dict(self.identity.return_value)
        self.identity.side_effect=[first,dict(first,volume_identity_sha256='4'*64)]
        self.assertEqual(supervisor.inspect(**self.kw)['status'],'FAIL')

    def test_wrong_container(self):
        self.runtime.return_value['container_id']='0'*64
        self.assertEqual(supervisor.inspect(**self.kw)['status'],'FAIL')

    def test_simulated_source_rejected(self):
        self.host.return_value['local_daemon_used']=False
        self.assertEqual(supervisor.inspect(**self.kw)['status'],'FAIL')
        self.runtime.assert_not_called()

    def test_invalid_digest(self):
        self.identity.return_value['host_identity_sha256']='invalid'
        self.assertEqual(supervisor.inspect(**self.kw)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
