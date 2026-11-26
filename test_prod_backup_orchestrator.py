import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from cryptography.fernet import Fernet
import server
import prod_backup_orchestrator as p
from test_prod_b2_export import Remote


class OrchestratorTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.backups=root/'archives'
        self.state=root/'state'
        self.backups.mkdir(mode=0o700)
        self.state.mkdir(mode=0o700)
        self.name='dsig-prod-20261126T021500Z.dsigbak'
        self.archive=self.backups/self.name
        self.key=Fernet.generate_key()
        source=root/'source.sqlite3'
        with patch.object(server,'DB',source):
            with closing(server.connect()) as db:
                db.commit()
        self.archive.write_bytes(Fernet(self.key).encrypt(source.read_bytes()))
        self.archive.chmod(0o600)
        self.remote=Remote()
        self.marker=self.state/(self.name+'.review.json')

    def export(self):
        return p.review_export(self.name,backups=self.backups,state=self.state,
             expected_bucket_id='prod-bucket-id',remote=self.remote,backup_key=self.key)

    def test_persistent_idempotent_proof(self):
        first=self.export()
        self.assertTrue(first['proof_created'])
        proof=self.marker.read_bytes()
        self.assertFalse(self.export()['proof_created'])
        self.assertEqual(self.marker.read_bytes(),proof)
        self.assertEqual(self.remote.writes,1)

    def test_exclusive_lock(self):
        with p.locked(self.state):
            with self.assertRaises(ValueError):self.export()
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.remote.writes,0)

    def test_missing_remote_after_proof(self):
        self.export()
        self.remote.objects.clear()
        with self.assertRaises(ValueError):self.export()
        self.assertEqual(self.remote.writes,1)

    def test_wrong_key_no_proof(self):
        self.key=Fernet.generate_key()
        with self.assertRaises(ValueError):self.export()
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.remote.writes,0)

    def test_changed_archive(self):
        self.export()
        self.archive.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.export()
        self.assertEqual(self.remote.writes,1)

    def test_unsafe_state(self):
        self.state.chmod(0o755)
        with self.assertRaises(ValueError):self.export()
        self.assertEqual(self.remote.writes,0)
