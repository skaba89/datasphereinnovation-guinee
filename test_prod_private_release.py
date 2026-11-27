import base64
import hashlib
import unittest
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_authorization as auth
import prod_private_release as release

class PrivateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.public = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.expected = dict(commit='a'*40, image_digest='sha256:'+'b'*64, config_sha256='c'*64, evidence_sha256='d'*64)
        self.payload = dict(self.expected, purpose=release.PURPOSE, schema=1, nonce='e'*64, scope=release.SCOPE,
                            issued_at='2026-11-27T06:00:00Z', expires_at='2026-11-27T07:00:00Z')
        self.now = datetime(2026,11,27,6,30,tzinfo=timezone.utc)
        self.pin = hashlib.sha256(self.public).hexdigest()

    def envelope(self):
        return dict(payload=dict(self.payload), signature=base64.b64encode(self.key.sign(auth.canonical(self.payload))).decode())

    def verify(self, envelope=None):
        return release.verify(self.envelope() if envelope is None else envelope, self.public,
                              authority_pin=self.pin, now=self.now, **self.expected)

    def test_valid(self):
        result = self.verify()
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['startup_authorized'])
        self.assertFalse(result['production_authorized'])

    def test_review_domain(self):
        self.payload['purpose'] = auth.PURPOSE
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_public_scope(self):
        self.payload['scope'] = 'public'
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_expired(self):
        self.payload['expires_at'] = '2026-11-27T06:30:00Z'
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_future(self):
        self.payload['issued_at'] = '2026-11-27T06:31:00Z'
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_long_validity(self):
        self.payload['expires_at'] = '2026-11-27T07:01:00Z'
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_wrong_pin(self):
        self.pin = '0'*64
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_bindings(self):
        for field in self.expected:
            with self.subTest(field=field):
                old = self.payload[field]
                self.payload[field] = old[:-1]+'f'
                self.assertEqual(self.verify()['status'], 'FAIL')
                self.payload[field] = old

    def test_tamper(self):
        envelope = self.envelope()
        envelope['payload']['nonce'] = 'f'*64
        self.assertEqual(self.verify(envelope)['status'], 'FAIL')

    def test_missing_nonce(self):
        del self.payload['nonce']
        self.assertEqual(self.verify()['status'], 'FAIL')

    def test_missing_permit(self):
        self.assertEqual(self.verify({})['status'], 'FAIL')
