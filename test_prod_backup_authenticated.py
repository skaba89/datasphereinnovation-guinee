import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import server
import prod_authorization
import prod_backup_authenticated as p
from test_prod_b2_export import Remote


class AuthenticatedBackupTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source=Path(tmp.name)/'source.sqlite3'
        with patch.object(server,'DB',source):
            with closing(server.connect()) as db:
                db.commit()
        self.key=Fernet.generate_key()
        self.data=Fernet(self.key).encrypt(source.read_bytes())
        self.signer=Ed25519PrivateKey.generate()
        self.public=self.signer.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.now=datetime(2026,11,27,3,0,tzinfo=timezone.utc)
        self.remote=Remote()
        self.proof=dict(schema=1,kind='business-daily',archive='dsig-prod-20261127T011500Z.dsigbak',
            object='prod/2026/11/dsig-prod-20261127T011500Z.dsigbak',sha256=hashlib.sha256(self.data).hexdigest(),
            bucket_id='prod-bucket-id',verified_at='2026-11-27T02:25:00+00:00',
            qualification_only=False,synthetic_data=False,ephemeral_key=False,
            remote_restore_verified=True,daily_backup_qualified=True,production_authorized=False)
        self.remote.create_only('dsig-prod-backups',self.proof['object'],self.data)

    def envelope(self):
        payload=dict(purpose=p.PURPOSE,key_id=self.pin,proof=dict(self.proof))
        return dict(payload,signature=base64.b64encode(self.signer.sign(prod_authorization.canonical(payload))).decode())

    def check(self,envelope=None,status='FAIL'):
        result=p.verify(self.envelope() if envelope is None else envelope,self.public,
            pinned_key_id=self.pin,expected_bucket_id='prod-bucket-id',remote=self.remote,
            backup_key=self.key,now=self.now)
        self.assertEqual(result['status'],status)
        self.assertFalse(result['production_authorized'])
        self.assertEqual(self.remote.writes,1)
        return result

    def test_valid(self):
        result=self.check(status='PASS')
        self.assertTrue(result['evidence_authenticated'])
        self.assertTrue(result['remote_verified'])

    def test_tamper(self):
        env=self.envelope()
        env['proof']['sha256']='b'*64
        self.assertFalse(self.check(env)['evidence_authenticated'])

    def test_wrong_pin(self):
        self.pin='0'*64
        self.check()

    def test_wrong_purpose(self):
        env=self.envelope()
        env['purpose']='DSIG-PROD-ISOLATED-REVIEW'
        self.check(env)

    def test_signed_synthetic(self):
        self.proof['synthetic_data']=True
        self.assertFalse(self.check()['remote_verified'])

    def test_missing_remote(self):
        self.remote.objects.clear()
        self.assertFalse(self.check()['remote_verified'])

    def test_remote_mismatch(self):
        self.remote.objects.clear()
        self.proof['sha256']='a'*64
        self.check()

    def test_wrong_decryption_key(self):
        self.key=Fernet.generate_key()
        self.assertFalse(self.check()['remote_verified'])

    def test_stale(self):
        self.now=datetime(2026,11,28,3,0,tzinfo=timezone.utc)
        self.check()
