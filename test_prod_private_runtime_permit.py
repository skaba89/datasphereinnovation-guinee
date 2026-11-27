import hashlib
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import prod_private_runtime_permit as permit
import prod_private_runtime_contract as contract

class PermitTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.approved={k:('a'*40 if k=='commit' else 'sha256:'+'b'*64 if k in ('image_digest','image_id') else 'c'*64) for k in contract.PATTERNS}
        self.kw=dict(signing_key=self.key,authority_pin=self.pin,
            approved_measurements=self.approved,measurement_inputs={})
        p=patch.object(permit.supervisor,'inspect',return_value=dict(status='PASS',
            domain=permit.supervisor.DOMAIN,runtime_measurements=dict(self.approved)))
        self.measure=p.start()
        self.addCleanup(p.stop)

    def test_signed_permit(self):
        a=permit.issue(**self.kw)
        b=permit.issue(**self.kw)
        self.assertEqual(a['status'],'PASS')
        self.assertEqual(contract.verify(a['envelope'],self.public,
            authority_pin=self.pin,expected=self.approved)['status'],'PASS')
        self.assertNotEqual(a['envelope']['payload']['nonce'],b['envelope']['payload']['nonce'])
        self.assertFalse(a['nonce_consumed'])
        self.assertFalse(a['startup_authorized'])
        self.assertFalse(a['production_authorized'])

    def test_wrong_pin(self):
        self.assertEqual(permit.issue(**dict(self.kw,authority_pin='0'*64))['status'],'FAIL')
        self.measure.assert_not_called()

    def test_changed_measurement(self):
        self.measure.return_value['runtime_measurements']['container_id']='d'*64
        self.assertEqual(permit.issue(**self.kw)['status'],'FAIL')

    def test_failed_or_review_measurement(self):
        for report in ({'status':'FAIL'},dict(self.measure.return_value,domain='review')):
            self.measure.return_value=report
            self.assertEqual(permit.issue(**self.kw)['status'],'FAIL')

    def test_incomplete_approval(self):
        self.assertEqual(permit.issue(**dict(self.kw,approved_measurements={}))['status'],'FAIL')
        self.measure.assert_not_called()

if __name__=='__main__':
    unittest.main()
