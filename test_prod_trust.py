import base64
import hashlib
import json
import unittest
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import prod_authorization as a
import prod_trust as t


class ProdTrustTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.item = dict(id=hashlib.sha256(raw).hexdigest(), public_key=base64.b64encode(raw).decode(),
                         not_before='2026-11-26T00:00:00Z', not_after='2026-11-27T00:00:00Z',
                         revoked=False)
        self.registry = dict(schema=1, keys=[self.item])
        self.expected = dict(commit='a'*40, image_digest='sha256:'+'b'*64,
                             config_sha256='c'*64, evidence_sha256='d'*64)
        self.payload = dict(schema=1, purpose=a.PURPOSE, **self.expected,
                            issued_at='2026-11-26T06:00:00Z', expires_at='2026-11-26T07:00:00Z')
        self.now = datetime(2026,11,26,6,30,tzinfo=timezone.utc)

    def envelope(self):
        return dict(key_id=self.item['id'], payload=self.payload.copy(),
                    signature=base64.b64encode(self.key.sign(a.canonical(self.payload))).decode())

    def check(self, expected='FAIL', *, envelope=None, data=None, pin=None):
        if data is None:
            data=json.dumps(self.registry).encode()
        if pin is None:
            pin=hashlib.sha256(data).hexdigest()
        result=t.verify(self.envelope() if envelope is None else envelope, data, pin,
                        now=self.now, **self.expected)
        self.assertEqual(result['status'], expected)
        self.assertFalse(result['production_authorized'])

    def test_valid(self):
        self.check('PASS')

    def test_revoked(self):
        self.item['revoked']=True
        self.check()

    def test_pin_mismatch(self):
        self.check(pin='0'*64)

    def test_wrong_signer(self):
        e=self.envelope();e['key_id']='0'*64
        self.check(envelope=e)

    def test_key_substitution(self):
        raw=Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
        self.item['public_key']=base64.b64encode(raw).decode()
        self.check()

    def test_expired_key_and_outside_key_window(self):
        self.item['not_after']='2026-11-26T06:45:00Z'
        self.check()
        self.item['not_after']='2026-11-26T06:15:00Z'
        self.check()
        self.item['not_after']='2026-11-27T00:00:00Z'
        self.item['not_before']='2026-11-26T06:15:00Z'
        self.check()

    def test_duplicate_keys(self):
        self.registry['keys'].append(self.item.copy())
        self.check()
        self.check(data=b'{"schema":1,"schema":1,"keys":[]}')

    def test_bad_signature(self):
        e=self.envelope();e['signature']=base64.b64encode(b'x'*64).decode()
        self.check(envelope=e)

    def test_wrong_digest(self):
        self.expected['config_sha256']='e'*64
        self.check()

    def test_invalid_registry(self):
        for raw in (b'null',b'{}',b'\xff',b'x'*65537):
            self.check(data=raw)
