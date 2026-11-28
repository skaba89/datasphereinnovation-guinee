import base64
import hashlib
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import prod_backup_business_permit as p
import prod_authorization as auth

class PermitTests(unittest.TestCase):
    def setUp(self):
        self.key=Ed25519PrivateKey.generate()
        self.public=self.key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
        self.pin=hashlib.sha256(self.public).hexdigest()
        self.now=datetime(2026,11,26,13,20,tzinfo=timezone.utc)
        self.payload=dict(purpose=p.PURPOSE,schema=1,container_id='a'*64,image_id='sha256:'+'b'*64,bucket_id='prod-bucket-id',signer_pin='c'*64,backup_key_id='d'*64,slot='2026-11-26T13:15Z',issued_at='2026-11-26T13:15:00Z',expires_at='2026-11-26T16:00:00Z')
    def envelope(self):
        return dict(payload=dict(self.payload),signature=base64.b64encode(self.key.sign(auth.canonical(self.payload))).decode())
    def verify(self):
        return p.verify(self.envelope(),self.public,authority_pin=self.pin,now=self.now)
    def test_valid(self):self.assertEqual(self.verify()['slot'],self.payload['slot'])
    def test_wrong_slot(self):
        self.payload['slot']='2026-11-26T01:15Z'
        with self.assertRaises(ValueError):self.verify()
    def test_wrong_domain(self):
        self.payload['purpose']=auth.PURPOSE
        with self.assertRaises(ValueError):self.verify()
    def test_expired(self):
        self.payload['expires_at']='2026-11-26T13:19:00Z'
        with self.assertRaises(ValueError):self.verify()
    def test_long_validity(self):
        self.payload['expires_at']='2026-11-26T17:00:00Z'
        with self.assertRaises(ValueError):self.verify()
    def test_same_signer(self):
        self.payload['signer_pin']=self.pin
        with self.assertRaises(ValueError):self.verify()
    def test_tamper(self):
        e=self.envelope();e['payload']['container_id']='e'*64
        with self.assertRaises(ValueError):p.verify(e,self.public,authority_pin=self.pin,now=self.now)
    def test_wrong_pin(self):
        with self.assertRaises(ValueError):p.verify(self.envelope(),self.public,authority_pin='0'*64,now=self.now)
    def test_preflight_binds_generation_across_remote_check(self):
        key = bytes(range(32))
        self.payload['backup_key_id'] = hashlib.sha256(key).hexdigest()
        first = dict(status='PASS', local_daemon_used=True, source_started_at='2026-11-26T13:00:00Z')
        args = dict(authority_pin=self.pin, backup_path='backup', signer_path='signer',
                    forbidden_backup_ids=set(), expected_bucket_id=self.payload['bucket_id'])
        for final_status in ('PASS', 'FAIL'):
            with self.subTest(final_status=final_status), patch.object(p, 'datetime') as clock, \
                    patch.object(p.acquisition, 'acquire', side_effect=[first, dict(first, status=final_status)]) as inspect, \
                    patch.object(p.keys, 'load_keys', return_value=(base64.urlsafe_b64encode(key), None)), \
                    patch.object(p, 'B2ReviewAdapter'):
                clock.now.return_value = self.now
                if final_status == 'PASS':
                    report = p.preflight(self.envelope(), self.public, **args)
                    self.assertEqual(report['source_started_at'], first['source_started_at'])
                    self.assertFalse(report['execution_authorized'])
                else:
                    with self.assertRaisesRegex(ValueError, 'source changed'):
                        p.preflight(self.envelope(), self.public, **args)
                self.assertEqual(inspect.call_args.kwargs['expected_started_at'], first['source_started_at'])

    def test_no_source(self):
        with patch.object(p,'verify',return_value=self.payload),patch.object(p.acquisition,'acquire',return_value=dict(status='FAIL',local_daemon_used=True)),patch.object(p.keys,'load_keys') as load:
            with self.assertRaises(ValueError):p.preflight(self.envelope(),self.public,authority_pin=self.pin,backup_path='x',signer_path='y',forbidden_backup_ids=set(),expected_bucket_id='prod-bucket-id')
            load.assert_not_called()
