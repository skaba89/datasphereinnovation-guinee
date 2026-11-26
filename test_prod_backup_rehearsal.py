import tempfile
import unittest
import hashlib
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import server
import operations
import prod_backup_rehearsal as p
import prod_backup_orchestrator as guard


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.root=root/'cycle'
        src=root/'source'
        keys=root/'keys'
        for d in (self.root,src,keys,self.root/'archives',self.root/'replica',self.root/'state'):
            d.mkdir(mode=0o700)
        self.db=src/'source.sqlite3'
        with patch.object(server,'DB',self.db):
            with closing(server.connect()) as db:db.commit()
        self.backup=keys/'backup.key'
        self.signer=keys/'signer.key'
        operations.write_new(self.backup,Fernet.generate_key())
        key=Ed25519PrivateKey.generate()
        operations.write_new(self.signer,key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption()))
        self.pin=hashlib.sha256(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).hexdigest()
        self.name='dsig-prod-20261126T011500Z.dsigbak'
        self.archive=self.root/'archives'/self.name
        self.copy=self.root/'replica'/self.name
        self.marker=self.root/'state'/(self.name+'.qualification.json')

    def cycle(self,check=lambda:{'status':'PASS'}):
        return p.run_rehearsal(active=self.db,root=self.root,name=self.name,backup_path=self.backup,
            signer_path=self.signer,pinned_signer_id=self.pin,forbidden_backup_ids={'a'*64, 'b'*64},source_check=check)

    def test_full_cycle_and_repeat(self):
        first=self.cycle()
        proof=self.marker.read_bytes()
        second=self.cycle()
        self.assertTrue(first['created'])
        self.assertFalse(second['created'])
        self.assertEqual(first['sha256'],second['sha256'])
        self.assertEqual(proof,self.marker.read_bytes())
        self.assertTrue(second['qualification_only'])
        self.assertFalse(second['remote_verified'])
        self.assertFalse(second['production_authorized'])

    def test_source_failure(self):
        with self.assertRaises(ValueError):self.cycle(lambda:{'status':'FAIL'})
        self.assertFalse(self.marker.exists())
        self.assertFalse(self.archive.exists())

    def test_partial_cycle(self):
        operations.write_new(self.archive,b'partial')
        with self.assertRaises(ValueError):self.cycle()
        self.assertFalse(self.marker.exists())

    def test_replica_missing(self):
        self.cycle()
        self.copy.unlink()
        with self.assertRaises(OSError):self.cycle()
        self.assertFalse(self.copy.exists())

    def test_replica_tampered(self):
        self.cycle()
        self.copy.write_bytes(b'bad')
        with self.assertRaises(ValueError):self.cycle()

    def test_lock(self):
        with guard.locked(self.root/'state'):
            with self.assertRaises(ValueError):self.cycle()
        self.assertFalse(self.archive.exists())

    def test_no_overwrite(self):
        operations.write_new(self.copy,b'existing')
        with self.assertRaises(ValueError):self.cycle()
        self.assertEqual(self.copy.read_bytes(),b'existing')
