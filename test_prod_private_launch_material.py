import base64
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import prod_private_launch_material as material


class LaunchMaterialTests(unittest.TestCase):
    def setUp(self):
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)
        expected = {name: ('a'*40 if name == 'commit' else
            'sha256:'+'b'*64 if name in ('image_id','image_digest') else 'c'*64)
            for name in material.contract.PATTERNS}
        now = datetime.now(timezone.utc).replace(microsecond=0)
        payload = dict(expected, schema=2, purpose=material.contract.PURPOSE,
            scope=material.contract.SCOPE, nonce='d'*64,
            issued_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'),
            expires_at=(now+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        envelope = dict(payload=payload,
            signature=base64.b64encode(key.sign(material.auth.canonical(payload))).decode('ascii'))
        self.kw = dict(envelope=envelope, public=public,
            approved_pin=hashlib.sha256(public).hexdigest(), approved_measurements=expected)

    def test_roundtrip(self):
        raw = material.encode(**self.kw)
        result = material.decode(raw)
        self.assertEqual(result['expected'], self.kw['approved_measurements'])
        self.assertEqual(result['public'], self.kw['public'])
        self.assertEqual(set(json.loads(raw)), {'envelope','public','authority_pin','expected'})

    def test_wrong_independent_pin(self):
        with self.assertRaises(ValueError):
            material.encode(**dict(self.kw, approved_pin='0'*64))

    def test_changed_expected_refused(self):
        value = json.loads(material.encode(**self.kw))
        value['expected']['container_id'] = 'e'*64
        with self.assertRaises(ValueError):
            material.decode(material.auth.canonical(value))

    def test_extra_secret_field_refused(self):
        value = json.loads(material.encode(**self.kw))
        value['private_key'] = 'synthetic'
        with self.assertRaises(ValueError):
            material.decode(material.auth.canonical(value))

    def test_exclusive_publication(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            with patch.object(material.channel, '_directory', return_value=path), \
                 patch.object(material.os, 'fchown'):
                material.publish(**self.kw)
                file = path / material.NAME
                self.assertEqual(file.stat().st_mode & 0o777, 0o440)
                before = file.read_bytes()
                with self.assertRaises(FileExistsError):
                    material.publish(**self.kw)
                self.assertEqual(file.read_bytes(), before)

    def test_oversized_refused(self):
        with self.assertRaises(ValueError):
            material.decode(b'x'*(material.LIMIT+1))


if __name__ == '__main__':
    unittest.main()
