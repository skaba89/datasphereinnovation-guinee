import base64
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from test_prod_private_runtime_contract import RuntimeContractTest
import prod_private_launch_channel as channel
import prod_authorization as auth

class LaunchChannelTests(unittest.TestCase):
    def setUp(self):
        self.fixture=RuntimeContractTest()
        self.fixture.setUp()
        self.envelope=self.fixture.envelope()
        self.challenge=channel.challenge()
        now=datetime.now(timezone.utc)
        self.payload=dict(purpose=channel.PURPOSE,challenge=self.challenge,
            contract_sha256=hashlib.sha256(auth.canonical(self.envelope)).hexdigest(),
            container_id=self.fixture.expected['container_id'],
            issued_at=(now-timedelta(seconds=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            expires_at=(now+timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%SZ'))

    def receipt(self):
        return dict(payload=dict(self.payload),signature=base64.b64encode(
            self.fixture.key.sign(auth.canonical(self.payload))).decode())

    def verify(self,receipt=None):
        return channel.verify(self.receipt() if receipt is None else receipt,
            self.envelope,self.fixture.public,authority_pin=self.fixture.pin,
            expected=self.fixture.expected,challenge_value=self.challenge)

    def test_valid_is_not_start_authority(self):
        result=self.verify()
        self.assertEqual(result['status'],'PASS')
        self.assertFalse(result['startup_authorized'])

    def test_fresh_challenge(self):
        self.assertNotEqual(self.challenge,channel.challenge())
        self.challenge=channel.challenge()
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_container_substitution(self):
        self.payload['container_id']='f'*64
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_contract_substitution(self):
        self.payload['contract_sha256']='f'*64
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_expired(self):
        self.payload['expires_at']=self.payload['issued_at']
        self.assertEqual(self.verify()['status'],'FAIL')

    def test_tamper(self):
        receipt=self.receipt()
        receipt['payload']['purpose']='other'
        self.assertEqual(self.verify(receipt)['status'],'FAIL')

if __name__=='__main__':
    unittest.main()
