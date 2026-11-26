import base64
import unittest
from datetime import datetime, timezone
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import prod_authorization as a


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.pub = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.expected = dict(commit='a'*40, image_digest='sha256:'+'b'*64,
                             config_sha256='c'*64, evidence_sha256='d'*64)
        self.p = dict(schema=1, purpose=a.PURPOSE, **self.expected,
                      issued_at='2026-11-26T06:00:00Z', expires_at='2026-11-26T07:00:00Z')
        self.now = datetime(2026,11,26,6,30,tzinfo=timezone.utc)

    def envelope(self):
        return dict(payload=self.p.copy(), signature=base64.b64encode(
            self.key.sign(a.canonical(self.p))).decode())

    def check(self, envelope=None, pub=None):
        report = a.verify(self.envelope() if envelope is None else envelope,
                          self.pub if pub is None else pub, now=self.now, **self.expected)
        self.assertFalse(report['production_authorized'])
        return report['status']

    def test_valid(self):
        self.assertEqual(self.check(), 'PASS')

    def test_tamper(self):
        e = self.envelope()
        e['payload']['commit'] = 'e'*40
        self.assertEqual(self.check(e), 'FAIL')

    def test_wrong_expected_binding(self):
        for key in self.expected:
            old = self.expected[key]
            self.expected[key] = old[:-1] + '0'
            self.assertEqual(self.check(), 'FAIL')
            self.expected[key] = old

    def test_wrong_key(self):
        pub = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.assertEqual(self.check(pub=pub), 'FAIL')

    def test_expired(self):
        self.p['expires_at'] = '2026-11-26T06:30:00Z'
        self.assertEqual(self.check(), 'FAIL')

    def test_future(self):
        self.p['issued_at'] = '2026-11-26T06:31:00Z'
        self.assertEqual(self.check(), 'FAIL')

    def test_long_validity(self):
        self.p['expires_at'] = '2026-11-28T06:00:00Z'
        self.assertEqual(self.check(), 'FAIL')

    def test_wrong_purpose(self):
        self.p['purpose'] = 'PUBLIC-PROD'
        self.assertEqual(self.check(), 'FAIL')

    def test_missing_and_extra_fields(self):
        for name in tuple(self.p):
            old = self.p.pop(name)
            self.assertEqual(self.check(), 'FAIL')
            self.p[name] = old
        self.p['extra'] = True
        self.assertEqual(self.check(), 'FAIL')

    def test_invalid_signature(self):
        e = self.envelope()
        e['signature'] = 'not base64!'
        self.assertEqual(self.check(e), 'FAIL')
