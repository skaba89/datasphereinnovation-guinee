import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
import server
import operations
import prod_snapshot_review as p


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        src=root/'source'
        src.mkdir(mode=0o700)
        dst=root/'backup'
        dst.mkdir(mode=0o700)
        self.db=src/'source.sqlite3'
        self.archive=dst/'dsig-prod-20261126T011500Z.dsigbak'
        self.key=Fernet.generate_key()
        with patch.object(server,'DB',self.db):
            with closing(server.connect()) as db:
                db.commit()

    def create(self,check=lambda:{'status':'PASS'}):
        return p.create_review_snapshot(self.db,self.archive,backup_key=self.key,source_check=check)

    def test_review(self):
        result=self.create()
        self.assertTrue(result['restore_verified'])
        self.assertTrue(result['qualification_only'])
        self.assertFalse(result['production_authorized'])
        self.assertFalse(result['business_provenance_verified'])
        self.assertEqual(self.archive.stat().st_mode&0o777,0o600)

    def test_wal_committed_rows(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE snapshot_probe (value TEXT)')
            db.execute("INSERT INTO snapshot_probe VALUES ('wal committed')")
            db.commit()
            self.create()
        restored=self.archive.parent/'restored.sqlite3'
        operations.write_new(restored,Fernet(self.key).decrypt(self.archive.read_bytes()))
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute('SELECT value FROM snapshot_probe').fetchone()[0],'wal committed')

    def test_failed_precheck(self):
        with self.assertRaises(ValueError):self.create(lambda:{'status':'FAIL'})
        self.assertFalse(self.archive.exists())

    def test_failed_postcheck(self):
        results=iter(['PASS','FAIL'])
        with self.assertRaises(ValueError):self.create(lambda:{'status':next(results)})
        self.assertFalse(self.archive.exists())

    def test_existing_preserved(self):
        self.archive.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):self.create()
        self.assertEqual(self.archive.read_bytes(),b'existing')

    def test_invalid_key(self):
        self.key=b'wrong'
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.archive.exists())

    def test_symlink_source(self):
        original=self.db.with_name('original.sqlite3')
        self.db.rename(original)
        self.db.symlink_to(original)
        with self.assertRaises(ValueError):self.create()
        self.assertFalse(self.archive.exists())
