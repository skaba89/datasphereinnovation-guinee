import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import server
import prod_authorization
import prod_backup_review_signing as p


class ReviewSigningTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.backup=self.root/'backup.key'
        self.signing=self.root/'signing.key'
        self.key=Fernet.generate_key()
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.forbidden={'a'*64,'b'*64}
        self.backup.write_bytes(self.key)
        self.signing.write_bytes(self.signer.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
        for path in (self.backup,self.signing):path.chmod(0o600)
        source=self.root/'source.sqlite3'
        with patch.object(server,'DB',source):
            with closing(server.connect()) as db:db.commit()
        self.data=Fernet(self.key).encrypt(source.read_bytes())
        self.name='dsig-prod-20261126T011500Z.dsigbak'
        self.result=dict(archive=self.name,sha256=hashlib.sha256(self.data).hexdigest(),
            qualification_only=True,business_provenance_verified=False,production_authorized=False,restore_verified=True)

    def load(self):
        return p.load_keys(self.backup,self.signing,pinned_signer_id=self.pin,forbidden_backup_ids=self.forbidden)

    def sign(self):
        key,signer=self.load()
        return p.sign_qualification(self.result,signer,archive=self.name,archive_bytes=self.data,backup_key=key)

    def test_valid_signature(self):
        env=self.sign()
        sig=base64.b64decode(env.pop('signature'))
        self.signer.public_key().verify(sig,prod_authorization.canonical(env))
        self.assertEqual(env['purpose'],p.PURPOSE)
        self.assertTrue(env['proof']['qualification_only'])

    def test_permissions(self):
        self.backup.chmod(0o644)
        with self.assertRaises(ValueError):self.load()

    def test_symlink(self):
        self.backup.rename(self.root/'original')
        self.backup.symlink_to(self.root/'original')
        with self.assertRaises(OSError):self.load()

    def test_reused_key(self):
        self.forbidden.add(hashlib.sha256(base64.urlsafe_b64decode(self.key)).hexdigest())
        with self.assertRaises(ValueError):self.load()

    def test_wrong_pin(self):
        self.pin='0'*64
        with self.assertRaises(ValueError):self.load()

    def test_missing_reference(self):
        self.forbidden=set()
        with self.assertRaises(ValueError):self.load()

    def test_business_claim_rejected(self):
        self.result['qualification_only']=False
        with self.assertRaises(ValueError):self.sign()

    def test_changed_bytes(self):
        self.data=b'changed'
        with self.assertRaises(ValueError):self.sign()

    def test_bad_ciphertext(self):
        self.data=b'not encrypted'
        self.result['sha256']=hashlib.sha256(self.data).hexdigest()
        with self.assertRaises(ValueError):self.sign()
