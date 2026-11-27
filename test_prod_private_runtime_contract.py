import base64
import hashlib
import unittest
from datetime import datetime,timedelta,timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_private_runtime_contract as contract
import prod_authorization as auth

class RuntimeContractTest(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.expected={k:('sha256:'+'a'*64 if k in ('image_id','image_digest') else 'a'*(40 if k=='commit' else 64)) for k in contract.PATTERNS}
        now=datetime.now(timezone.utc)
        self.payload=dict(self.expected,schema=2,purpose=contract.PURPOSE,scope=contract.SCOPE,nonce='b'*64,
            issued_at=(now-timedelta(seconds=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            expires_at=(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))

    def envelope(self):
        return dict(payload=dict(self.payload),signature=base64.b64encode(self.key.sign(auth.canonical(self.payload))).decode())

    def verify(self,envelope=None):
        return contract.verify(self.envelope() if envelope is None else envelope,self.public,authority_pin=self.pin,expected=self.expected)

    def test_valid_signature_is_not_startup_authorization(self):
        result=self.verify()
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['nonce_consumed'])

    def test_every_binding_is_required(self):
        for k in self.expected:
            with self.subTest(field=k):
                original=self.payload[k]
                self.payload[k]=original[:-1]+'f'
                self.assertEqual(self.verify()['status'],'FAIL')
                self.payload[k]=original

    def test_tampering(self):
        envelope=self.envelope()
        envelope['payload']['nonce']='c'*64
        self.assertEqual(self.verify(envelope)['status'],'FAIL')

    def test_wrong_authority(self):
        self.pin='0'*64
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_wrong_domain(self):
        self.payload['purpose']='DSIG-PROD-PRIVATE-START-V1'
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_expiry(self):
        self.payload['expires_at']=self.payload['issued_at']
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_missing_expected_binding(self):
        del self.expected['container_id']
        self.assertEqual(self.verify()['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
